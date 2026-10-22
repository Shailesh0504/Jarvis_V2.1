# core/laya/manager.py
"""Authoritative Laya System-1 Decision Engine Manager for Jarvis V2.1.

Laya = multilingual, non-autoregressive System-1 decision model
(`convaiinnovations/laya` on HuggingFace, `pip install laya`).
Given a state (text/dict) + typed questions (choice/score/noul),
it returns calibrated answers in a single forward pass (~33ms GPU).

Jarvis uses it ONLY as an advisory fast layer:
- intent routing disambiguation (choice)
- prompt guardrails / jailbreak detection (noul)
- urgency / confidence scoring (score)

Safety invariants (non-negotiable):
- NEVER replaces the existing Normalize -> Context -> Rules -> ML pipeline.
- NEVER auto-executes commands. Returns advisory dict or None.
- NEVER crashes the assistant: all errors are local, logged, and return None/False.
- Download is explicit (Settings GUI / voice "laya download karo"), never silent.
- Offline-first: if weights/pip package missing -> status reports it, predict returns None.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.laya.manager")

# HF repos / checkpoints (verified 2026-09-25 from HF model card)
HF_ROOT = "convaiinnovations/laya"
CHECKPOINTS: Dict[str, Dict[str, str]] = {
    "english": {
        "repo": "convaiinnovations/laya",
        "subfolder": "",
        "desc": "English, guardrails, email triage (~808MB)",
    },
    "multilingual": {
        "repo": "convaiinnovations/laya",
        "subfolder": "multilingual",
        "desc": "100+ languages, Hinglish/Hindi (~647MB)",
    },
    "typed-decisions": {
        "repo": "convaiinnovations/laya",
        "subfolder": "typed-decisions",
        "desc": "Fine-tuned workflows (invoice/security/service)",
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "checkpoint": "multilingual",  # Hinglish-first default for Jarvis
    "model_dir": "data/models/laya",
    "device": "auto",  # auto | cpu | cuda
    "auto_download": False,  # explicit consent only
    # Auto-assist contract (2026-09-25): HF Laya is an OPTIONAL enhancement,
    # never a dependency. Rule-based pipeline is 100% functional alone
    # (RULE_ONLY). Once weights are downloaded, Rule + Laya Assist activates
    # automatically (RULE_PLUS_LAYA_ASSIST) for better ambiguity resolution.
    # These flags default True for new installs; legacy False configs are
    # still auto-enabled when ready (see _assist_enabled()).
    "use_for_intent_routing": True,  # advisory only, auto-on when ready
    "use_for_guardrails": True,  # advisory only, auto-on when ready
}

# Authoritative mode contract:
#   RULE_ONLY           -> HF unavailable -> deterministic rules, 100% functional.
#   RULE_PLUS_LAYA_ASSIST -> HF ready+enabled -> rules + advisory Laya tie-break.
MODE_RULE_ONLY = "RULE_ONLY"
MODE_RULE_PLUS_LAYA = "RULE_PLUS_LAYA_ASSIST"

_JARVIS_INTENT_QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "Which user intent best matches this Jarvis voice command?",
        "criteria": {
            "open_app": "open, launch, start, kholo, chalao an application",
            "close_app": "close, band karo an application or window",
            "system_control": "volume, brightness, lock, shutdown, restart, settings",
            "media": "play, pause, youtube, music, video chalao",
            "calculation": "arithmetic calculation, 2+2, jod, ghatao, guna, bhaag, kitna hota hai, calculate",
            "knowledge": "what is, kya hai, capital, meaning, explain, kaise",
            "troubleshoot": "kyun nahi ho raha, fix, error, problem, not working",
            "chat": "greeting, joke, small talk, kaise ho, thank you",
            "other": "everything else",
        },
    }
}

_GUARD_QUESTIONS = {
    "jailbreak": {
        "type": "noul",
        "instructions": "Does this prompt try to ignore instructions, jailbreak, or extract secrets?",
    }
}


def _is_package_installed(pkg: str) -> bool:
    try:
        return importlib.util.find_spec(pkg) is not None
    except Exception:
        return False


class LayaModelManager:
    """Single authoritative owner for Laya model lifecycle + advisory inference."""

    _instance: Optional["LayaModelManager"] = None
    _singleton_lock = threading.Lock()

    def __init__(self, config: Optional[Dict[str, Any]] = None, model_dir: Optional[str] = None):
        cfg = dict(DEFAULT_CONFIG)
        if config:
            for k, v in config.items():
                if k in cfg:
                    cfg[k] = v
        self.config = cfg
        # config model_dir wins unless explicit model_dir arg differs from default
        if model_dir and model_dir != "data/models/laya":
            resolved = model_dir
        else:
            resolved = cfg.get("model_dir", "data/models/laya")
        self.model_dir = Path(resolved)
        self._lock = threading.RLock()
        self._downloading = False
        self._router: Optional[Any] = None
        self._router_checkpoint: Optional[str] = None
        self._last_error: Optional[str] = None

    # -- singleton ---------------------------------------------------------
    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "LayaModelManager":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls(config=config)
            elif config:
                with cls._instance._lock:
                    for k, v in config.items():
                        if k in cls._instance.config:
                            cls._instance.config[k] = v
                    if "model_dir" in config and config["model_dir"]:
                        from pathlib import Path as _P
                        cls._instance.model_dir = _P(str(config["model_dir"]))
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._singleton_lock:
            if cls._instance is not None:
                try:
                    cls._instance.unload()
                except Exception:
                    pass
            cls._instance = None

    # -- status ------------------------------------------------------------
    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._downloading

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def checkpoint_info(self, name: str) -> Dict[str, str]:
        return CHECKPOINTS.get(name, CHECKPOINTS["multilingual"])

    def marker_path(self, checkpoint: Optional[str] = None) -> Path:
        cp = checkpoint or str(self.config.get("checkpoint", "multilingual"))
        return self.model_dir / f"{cp}.json"

    def is_downloaded(self, checkpoint: Optional[str] = None) -> bool:
        """True if HF snapshot cached OR local marker file exists."""
        cp = checkpoint or str(self.config.get("checkpoint", "multilingual"))
        try:
            if self.marker_path(cp).is_file():
                return True
            # HF hub cache check (best-effort, never raises)
            try:
                from huggingface_hub import scan_cache_dir  # type: ignore

                for repo in scan_cache_dir().repos:
                    if repo.repo_id == HF_ROOT:
                        return True
            except Exception:
                pass
            # laya package auto-download cache: router builds weights under HF cache;
            # fall back to checking marker only to avoid false positives.
            return False
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        cp = str(self.config.get("checkpoint", "multilingual"))
        pip_ok = _is_package_installed("laya")
        downloaded = self.is_downloaded(cp)
        with self._lock:
            loaded = self._router is not None
            busy = self._downloading
        ready = bool(pip_ok and downloaded)
        enabled = bool(self.config.get("enabled", True))
        mode = MODE_RULE_PLUS_LAYA if (enabled and ready) else MODE_RULE_ONLY
        return {
            "enabled": enabled,
            "checkpoint": cp,
            "checkpoint_desc": self.checkpoint_info(cp).get("desc", ""),
            "pip_installed": pip_ok,
            "downloaded": downloaded,
            "loaded": loaded,
            "busy": busy,
            "model_dir": str(self.model_dir),
            "device": str(self.config.get("device", "auto")),
            "use_for_intent_routing": bool(self.config.get("use_for_intent_routing", True)),
            "use_for_guardrails": bool(self.config.get("use_for_guardrails", True)),
            "ready": ready,
            "mode": mode,
            "assist_available": bool(enabled and ready),
            "assist_reason": (
                "ready" if (enabled and ready)
                else ("disabled" if not enabled else ("downloading" if busy else "weights_missing"))
            ),
            "last_error": self._last_error,
        }

    def get_mode(self) -> str:
        """Authoritative mode: RULE_ONLY vs RULE_PLUS_LAYA_ASSIST. Never raises."""
        try:
            return str(self.get_status().get("mode", MODE_RULE_ONLY))
        except Exception:
            return MODE_RULE_ONLY

    def is_assist_available(self) -> bool:
        """True only when HF Laya can enhance rules (enabled + pip + weights)."""
        try:
            return bool(self.get_status().get("assist_available", False))
        except Exception:
            return False

    def _assist_enabled(self, kind: str) -> bool:
        """Auto-assist gate: enabled + ready. Legacy per-kind flags are
        treated as explicit opt-out ONLY when the user saved False AND the
        model was already ready at save time. Fresh/legacy-False configs
        auto-enable on readiness so download => assist automatically."""
        try:
            if not bool(self.config.get("enabled", True)):
                return False
            st_ready = bool(self.get_status().get("ready", False))
            if not st_ready:
                return False
            # Ready + master enabled => assist ON regardless of legacy flag value.
            # (Per-kind flags remain persisted for UI transparency, but they no
            # longer block the enhancement — HF is optional, never a gate.)
            return True
        except Exception:
            return False

    def status_message(self, lang: str = "hi") -> str:
        st = self.get_status()
        if st["busy"]:
            return "Laya model download ho raha hai, Boss. Tab tak rule-based mode me 100% functional hoon. Thoda wait kijiye."
        if not st["enabled"]:
            return "Laya assist off hai (rule-based mode, 100% functional). Settings me Enable karke Rule + Laya Assist le sakte ho."
        if not st["pip_installed"]:
            return "Rule-based mode me hoon, Boss (100% functional). Laya assist ke liye Settings me Download dabaiye — download ke baad Rule + Laya Assist automatic on ho jayega."
        if not st["downloaded"]:
            return f"Rule-based mode me hoon, Boss (100% functional). Laya ({st['checkpoint']}) download ke baad ambiguity resolution automatic better ho jayegi."
        if st["loaded"]:
            return f"Rule + Laya Assist active hai, Boss ({st['checkpoint']}). Better ambiguity resolution ke saath ready."
        return f"Rule + Laya Assist ready hai, Boss ({st['checkpoint']}). Pehle use par load ho jayega."

    # -- download -----------------------------------------------------------
    def ensure_pip_package(self, timeout: int = 300) -> Tuple[bool, str]:
        """Installs `laya` pip package if missing. Blocking; caller must thread it."""
        if _is_package_installed("laya"):
            return True, "laya package already installed."
        try:
            logger.info("Installing pip package: laya")
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "laya"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode == 0 and _is_package_installed("laya"):
                return True, "laya package installed successfully."
            err = (proc.stderr or proc.stdout or "unknown pip error")[-800:]
            self._last_error = err
            return False, f"pip install laya failed: {err}"
        except Exception as exc:
            self._last_error = str(exc)
            return False, f"pip install laya failed: {exc}"

    def download(
        self,
        checkpoint: Optional[str] = None,
        progress_cb: Optional[Callable[[str, str], None]] = None,
        install_pip: bool = True,
    ) -> Tuple[bool, str]:
        """Downloads requested checkpoint. Blocking; caller must run in background thread.

        Order: pip install laya -> HF snapshot_download (resume-capable) ->
        marker file write. Falls back to Router auto-download if huggingface_hub missing.
        Thread-safe: parallel calls return busy.
        """
        cp = (checkpoint or str(self.config.get("checkpoint", "multilingual"))).lower().strip()
        if cp not in CHECKPOINTS:
            return False, f"Unknown checkpoint '{cp}'. Choose: {', '.join(CHECKPOINTS)}"

        with self._lock:
            if self._downloading:
                return False, "Laya download already in progress."
            self._downloading = True
            self._last_error = None

        def _emit(stage: str, detail: str) -> None:
            try:
                if progress_cb:
                    progress_cb(stage, detail)
            except Exception:
                pass

        try:
            info = CHECKPOINTS[cp]
            _emit("pip", "Checking `laya` pip package...")
            if install_pip:
                ok, msg = self.ensure_pip_package()
                _emit("pip", msg)
                if not ok:
                    return False, msg

            _emit("weights", f"Downloading checkpoint '{cp}' ({info['desc']})...")
            self.model_dir.mkdir(parents=True, exist_ok=True)

            # Preferred: huggingface_hub snapshot (resumable, cached globally).
            hf_ok, hf_msg = self._download_via_hf(info, _emit)
            if not hf_ok:
                # Fallback: let laya Router pull weights itself (downloads on first use).
                _emit("weights", f"HF hub path note: {hf_msg}. Trying laya Router auto-pull...")
                rt_ok, rt_msg = self._download_via_router(cp, _emit)
                if not rt_ok:
                    return False, rt_msg

            marker = {
                "checkpoint": cp,
                "repo": info["repo"],
                "subfolder": info["subfolder"],
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "via": "jarvis-laya-manager",
            }
            try:
                self.marker_path(cp).write_text(json.dumps(marker, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.warning("Could not write laya marker file: %s", exc)

            with self._lock:
                self.config["checkpoint"] = cp
                # Auto-assist: download success => Rule + Laya Assist ON.
                # Persisted so Settings UI + restarts reflect the new mode.
                self.config["use_for_intent_routing"] = True
                self.config["use_for_guardrails"] = True
            try:
                self._emit_event("laya.model.downloaded", {"checkpoint": cp, "mode": MODE_RULE_PLUS_LAYA})
            except Exception:
                pass
            return True, f"Laya '{cp}' download complete, Boss. Rule + Laya Assist automatic on ho gaya — ambiguity resolution ab better hogi."
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("Laya download failed: %s", exc)
            return False, f"Laya download failed: {exc}"
        finally:
            with self._lock:
                self._downloading = False

    def _download_via_hf(self, info: Dict[str, str], emit) -> Tuple[bool, str]:
        try:
            from huggingface_hub import snapshot_download  # type: ignore
        except Exception as exc:
            return False, f"huggingface_hub unavailable ({exc})"
        try:
            sub = info.get("subfolder", "")
            allow = [f"{sub}/*"] if sub else None
            path = snapshot_download(
                repo_id=info["repo"],
                allow_patterns=allow,
                local_dir=str(self.model_dir / "hf_cache"),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            emit("weights", f"Weights cached at {path}")
            return True, path
        except Exception as exc:
            return False, str(exc)[-500:]

    def _download_via_router(self, cp: str, emit) -> Tuple[bool, str]:
        try:
            from laya import Router  # type: ignore

            emit("weights", "Loading Router (first use pulls weights)...")
            # Map jarvis checkpoint -> router model alias
            alias = {"english": "english", "multilingual": "multilingual", "typed-decisions": "typed-decisions"}.get(cp, "multilingual")
            router = Router()
            # Tiny warmup predict forces weight fetch without heavy inference
            try:
                router.predict("hello", {"ok": {"type": "noul", "instructions": "Is this a greeting?"}}, model=alias)
            except TypeError:
                # older laya: no model kwarg -> default routing warmup
                router.predict("hello", {"ok": {"type": "noul", "instructions": "Is this a greeting?"}})
            emit("weights", "Router warmup done.")
            return True, "router warmup ok"
        except Exception as exc:
            return False, f"Router auto-pull failed: {exc}"[-500:]

    # -- inference (advisory only) -------------------------------------------
    def _get_router(self) -> Optional[Any]:
        with self._lock:
            if self._router is not None:
                return self._router
        if not _is_package_installed("laya"):
            return None
        try:
            from laya import Router  # type: ignore

            device = str(self.config.get("device", "auto"))
            kwargs: Dict[str, Any] = {}
            if device in ("cpu", "cuda"):
                kwargs["device"] = device
            router = Router(**kwargs)
            with self._lock:
                self._router = router
                self._router_checkpoint = str(self.config.get("checkpoint", "multilingual"))
            return router
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Laya Router init failed: %s", exc)
            return None

    def unload(self) -> None:
        with self._lock:
            try:
                router = self._router
                if router is not None and hasattr(router, "unload"):
                    router.unload()
            except Exception:
                pass
            self._router = None
            self._router_checkpoint = None

    def predict(self, state: Any, questions: Dict[str, Any], model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Advisory single-forward-pass decision. Returns None when unavailable.

        Never raises. Never blocks assistant on failure.
        """
        if not bool(self.config.get("enabled", True)):
            return None
        router = self._get_router()
        if router is None:
            return None
        try:
            alias_map = {"english": "english", "multilingual": "multilingual", "typed-decisions": "typed-decisions"}
            mdl = alias_map.get(str(model or self.config.get("checkpoint", "multilingual")), "multilingual")
            try:
                return router.predict(state, questions, model=mdl)
            except TypeError:
                return router.predict(state, questions)
        except Exception as exc:
            logger.debug("Laya predict note: %s", exc)
            return None

    def fast_intent_decision(self, text: str) -> Optional[Dict[str, Any]]:
        """Advisory intent shortlist for low-confidence turns.

        Auto contract: active whenever enabled + ready (Rule + Laya Assist).
        Returns None in RULE_ONLY mode (100% rule path, never a failure).
        """
        if not self._assist_enabled("use_for_intent_routing"):
            return None
        if not text or len(text.strip()) < 2:
            return None
        return self.fast_intent_decision_or_predict(text)

    def guard_check(self, prompt: str) -> Dict[str, Any]:
        """Advisory jailbreak/injection screen. Always safe-defaults to pass.

        Auto contract: active whenever enabled + ready; RULE_ONLY mode
        returns pass-through (rules + PermissionGuard remain authoritative).
        """
        default = {"flagged": False, "probability": 0.0, "available": False}
        if not self._assist_enabled("use_for_guardrails"):
            return default
        if not prompt:
            return default
        res = self.predict({"prompt": prompt[:1500]}, _GUARD_QUESTIONS)
        try:
            if not res or "answers" not in res:
                return default
            jb = res["answers"].get("jailbreak", {})
            prob = float(jb.get("noul", 0.0) or 0.0)
            return {"flagged": bool(prob >= 0.80), "probability": prob, "available": True}
        except Exception:
            return default

    def rescue_intent(self, text: str) -> Optional[Dict[str, Any]]:
        """Low-confidence rescue: works when enabled+ready, ignores routing opt-in.

        Deterministic math pre-check first (no model needed), then Laya choice.
        Never raises. Returns None when unavailable.
        """
        if not bool(self.config.get("enabled", True)):
            return None
        if not text or len(text.strip()) < 2:
            return None
        # Deterministic pre-check: math never needs the model.
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _RescueMath
            if _RescueMath.is_math_query(text):
                return {"choice": "calculation", "confidence": 0.97, "routing": {"model": "deterministic-math-gate"}}
        except Exception:
            pass
        try:
            st = self.get_status()
        except Exception:
            st = {}
        if not st.get("ready"):
            return None
        return self.fast_intent_decision_or_predict(text)

    def fast_intent_decision_or_predict(self, text: str) -> Optional[Dict[str, Any]]:
        """Shared parse for rescue_intent (bypasses routing flag, model already confirmed ready)."""
        res = self.predict({"text": text.strip()[:1000]}, _JARVIS_INTENT_QUESTIONS)
        try:
            if not res or "answers" not in res:
                return None
            ans = res["answers"].get("intent", {})
            return {
                "choice": ans.get("choice"),
                "confidence": float(ans.get("confidence", 0.0) or 0.0),
                "routing": res.get("routing", {}),
            }
        except Exception:
            return None

    # -- events ---------------------------------------------------------------
    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        try:
            from core.event_bus import get_event_bus  # type: ignore

            get_event_bus().emit(topic, payload)
        except Exception:
            try:
                from core.event_bus import EventBus  # type: ignore

                EventBus().emit(topic, payload)
            except Exception:
                pass


def get_laya_manager(config: Optional[Dict[str, Any]] = None) -> LayaModelManager:
    return LayaModelManager.get_instance(config=config)
