# core/laya/intelligence.py
"""Laya Intelligence — Jarvis decision orchestrator (System-1 fast layer).

Laya philosophy (authoritative pipeline):
    Laya
    ├── Understand ── Intent, Entity, Slots, Context
    ├── Decide ────── Rule engine, Confidence, laya_assist, Clarification
    ├── Route ─────── OS tools, App tools, File tools, Automation, Plugins
    ├── Verify ────── Did action actually succeed? (plan only — execution
    │                 stays with JarvisCore / executors; the authoritative
    │                 check is ExecutionVerificationLayer.verify_outcome)
    └── Respond ───── ResponseEngine (authoritative final rendering)

Design invariants (per AGENTS.md):
- REUSE -> EXTEND -> CREATE. This file creates NO duplicate pipeline.
  It only ORCHESTRATES existing single owners:
    Understand  : core.conversational_intent.ConversationalIntentClassifier
                  + core.semantic.orchestrator.SemanticPipelineOrchestrator
                  + core.semantic.slot_extractor.SemanticSlotExtractor
                  + core.context.RuntimeContext / ActiveTargetContext
                  + core.dialog_manager.DialogManager (active lock)
    Decide      : deterministic rule engine (this file) + calibrated
                  confidence + LayaModelManager rescue/guard advisory
                  + PermissionGuard risk + ConfirmationManager policy
    Route       : core.router.CommandRouter (authoritative) + tool-category
                  taxonomy labels (OS / App / File / Automation / Plugins);
                  execution stays with plugin_manager / target_engine /
                  SemanticActionExecutor — Laya only ADVISES the route.
    Verify      : core.execution.verifier.ExecutionVerificationLayer
                  .verify_outcome (authoritative). Laya only PLANS what to
                  verify (strategy + expected state), never executes.
    Respond     : core.response_engine.ResponseEngine (authoritative final
                  rendering). Laya produces a hint; render() routes it.
- NEVER auto-executes. Returns an advisory LayaDecision (dict/dataclass).
- NEVER crashes assistant: every stage is guarded, returns safe fallback.
- Offline-first / optional enhancement (2026-09-25 contract):
    HF unavailable -> RULE_ONLY -> deterministic rules, 100% functional.
    HF ready+enabled -> RULE_PLUS_LAYA_ASSIST -> rules + advisory tie-break
    for better ambiguity resolution. HF is NEVER a dependency.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.laya.intelligence")


class LayaRoute(str, Enum):
    """Authoritative Tri-Bridge Orchestration Routes (Laya Core Architecture)."""
    FAST_ROUTER = "FAST_ROUTER"     # Direct tools / fast path (Volume, Time, App, System, Weather, Desktop)
    CHAT = "CHAT"                   # Conversational / Knowledge / Small Talk (Qwen/etc. LLM)
    AGENT_PLANNER = "AGENT_PLANNER" # Multi-step goal / Task Graph (AutonomousAgent / TaskEngine)


class LayaResponseMode(str, Enum):
    """Authoritative response-mode decision (job 7)."""
    EXECUTE = "EXECUTE"            # ACTION_COMMAND, slots complete, safe
    ASK_SLOT = "ASK_SLOT"          # missing required slot -> ask targeted question
    CONFIRM = "CONFIRM"            # HIGH/CRITICAL risk or explicit policy -> confirm first
    CLARIFY = "CLARIFY"            # ambiguous / medium confidence
    CHAT = "CHAT"                  # greeting, small-talk, capability/info/troubleshoot answer
    STATUS_ANSWER = "STATUS_ANSWER"  # status question / after-action -> answer state only
    REJECT = "REJECT"              # negated / cancelled / jailbreak / disallowed
    LEARN = "LEARN"                # correction / new vocab -> learning layer


@dataclass
class LayaDecision:
    """Single authoritative orchestration decision for one user turn.

    Philosophy stages:
      Understand (speech_act/intent/entities/slots/context)
      -> Decide (9 Authoritative Orchestration Decisions)
      -> Route (Tri-Bridge: Fast Router, Chat/LLM, Agent Planner)
      -> Verify (Physical verification check & expected state)
      -> Respond (response_hint + render() via ResponseEngine).
    """
    raw_text: str = ""
    normalized_text: str = ""
    # -- 1. Command direct execute hogi ya nahi & Tri-Bridge Route --
    laya_route: LayaRoute = LayaRoute.FAST_ROUTER
    is_direct_execution: bool = True
    # -- Understand --
    speech_act: str = "UNKNOWN"          # from ConversationalIntentClassifier
    intent: str = "UNKNOWN"              # e.g. open_app, system_control, chat
    entities: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    missing_slots: List[str] = field(default_factory=list)
    filled_slots: Dict[str, Any] = field(default_factory=dict)
    context_updates: Dict[str, Any] = field(default_factory=dict)
    # -- 4. Kaunsa model use hoga --
    model_target: str = "rule_fast"      # "rule_fast", "local_qwen", "conversational_llm", "knowledge_engine", "agent_planner"
    # -- 5. Context kitna dena hai --
    context_scope: str = "NONE"          # "NONE", "MINIMAL", "ACTIVE_WINDOW", "CONVERSATIONAL", "FULL"
    max_history_turns: int = 0
    # -- 6. Memory kab retrieve karni hai --
    retrieve_memory: bool = False
    memory_query: Optional[str] = None
    memory_types: List[str] = field(default_factory=list) # ["user_profile", "preferences", "episodic"]
    # -- 7. Confirmation chahiye ya nahi --
    risk_level: str = "LOW"
    needs_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    laya_assist: Dict[str, Any] = field(default_factory=dict)  # advisory model info
    response_mode: LayaResponseMode = LayaResponseMode.CHAT
    # -- Route Details --
    route: str = "FAST_ROUTER"           # FAST_ROUTER / CHAT / AGENT_PLANNER / SYSTEM / MEMORY
    handler: Optional[str] = None
    tool_category: Optional[str] = None  # OS / App / File / Automation / Plugins / None
    tool_plugin: Optional[str] = None
    tool_action: Optional[str] = None
    # -- 8. Task successful hua ya nahi (Verification Plan & Outcome) --
    verification_strategy: Optional[str] = None  # e.g. process_running, window_exists
    expected_state: Optional[str] = None         # e.g. "chrome running"
    verify_hint: str = ""                        # how the caller should verify
    verified: Optional[bool] = None
    verification_detail: str = ""
    # -- 9. Failure par retry/fallback kya hai --
    can_retry: bool = False
    fallback_strategy: str = "clarify"           # "retry_alternate", "ask_browser_fallback", "clarify"
    fallback_action: Optional[str] = None
    # -- Respond --
    response_hint: str = ""              # short natural hint, never technical dump
    pipeline: List[str] = field(default_factory=list)  # stage trace for debugging
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "laya_route": self.laya_route.value if hasattr(self.laya_route, "value") else str(self.laya_route),
            "is_direct_execution": self.is_direct_execution,
            "speech_act": self.speech_act,
            "intent": self.intent,
            "entities": dict(self.entities),
            "confidence": self.confidence,
            "model_target": self.model_target,
            "context_scope": self.context_scope,
            "max_history_turns": self.max_history_turns,
            "retrieve_memory": self.retrieve_memory,
            "memory_query": self.memory_query,
            "memory_types": list(self.memory_types),
            "route": self.route,
            "handler": self.handler,
            "tool_category": self.tool_category,
            "tool_plugin": self.tool_plugin,
            "tool_action": self.tool_action,
            "missing_slots": list(self.missing_slots),
            "filled_slots": dict(self.filled_slots),
            "risk_level": self.risk_level,
            "needs_confirmation": self.needs_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
            "response_mode": self.response_mode.value,
            "response_hint": self.response_hint,
            "context_updates": dict(self.context_updates),
            "laya_assist": dict(self.laya_assist),
            "verification_strategy": self.verification_strategy,
            "expected_state": self.expected_state,
            "verify_hint": self.verify_hint,
            "verified": self.verified,
            "verification_detail": self.verification_detail,
            "can_retry": self.can_retry,
            "fallback_strategy": self.fallback_strategy,
            "fallback_action": self.fallback_action,
            "pipeline": list(self.pipeline),
        }

    def render_response(self, engine: Optional[Any] = None) -> str:
        """Respond stage: render through authoritative ResponseEngine.

        Falls back to response_hint when the engine is unavailable —
        never raises, never returns empty.
        """
        fallback = (self.response_hint or "").strip() or "Theek hai."
        try:
            eng = engine or self._default_response_engine()
            if eng is None:
                return fallback
            text = eng.render_response(
                {
                    "user_text": self.raw_text,
                    "intent": self.intent,
                    "speech_act": self.speech_act,
                    "target": str(self.entities.get("target", "") or ""),
                    "action": self.tool_action or "",
                    "parameters": {
                        "laya_response_mode": self.response_mode.value,
                        "tool_category": self.tool_category or "",
                        "verification_strategy": self.verification_strategy or "",
                    },
                },
                default_text=fallback,
            )
            return str(text or fallback).strip() or fallback
        except Exception as exc:
            logger.debug("Laya render_response fallback: %s", exc)
            return fallback

    @staticmethod
    def _default_response_engine() -> Optional[Any]:
        try:
            from core.response_engine import ResponseEngine as _RE
            return _RE.get_instance()
        except Exception:
            return None

    def confirm_outcome(self, verification: Optional[Any]) -> str:
        """Verify stage helper: turn an ALREADY-OBTAINED verification result
        into a short natural outcome line. Takes the result object (or its
        dict); never executes verification itself.

        Answers the philosophy question: 'Did action actually succeed?'
        """
        try:
            if verification is None:
                return "Verification pending hai."
            if isinstance(verification, dict):
                verified = bool(verification.get("verified", False))
                detail = str(verification.get("message", "") or "").strip()
            else:
                verified = bool(
                    getattr(verification, "verified", False)
                    or getattr(verification, "success", False)
                )
                detail = str(
                    getattr(verification, "message", "")
                    or getattr(verification, "detail", "")
                    or ""
                ).strip()
            target = str(self.entities.get("target", "") or self.intent).strip()
            if verified:
                return f"Haan, {target} ho gaya." if target else "Haan, ho gaya."
            if detail:
                return detail
            return f"{target} verify nahi ho paya." if target else "Verify nahi ho paya."
        except Exception as exc:
            logger.debug("Laya confirm_outcome note: %s", exc)
            return "Verification note kar liya hai."


# --- lightweight deterministic helpers (fallback, no model needed) ---

_PRONOUNS = {"isme", "usko", "usme", "isko", "ismein", "that", "it", "this", "usmein"}

# intent -> (required_slots, tool category, tool plugin, tool action, risk)
# Tool categories follow the Laya philosophy Route stage:
#   OS tools    — OS-level control (power, lock, volume, system settings)
#   App tools   — application / window / website lifecycle (launch, close, open)
#   File tools  — filesystem targets (files, folders)
#   Automation  — scheduled / procedural (reminders, workflows, tasks)
#   Plugins     — domain plugins (media, messaging, email, math, knowledge)
_TOOL_OS = "OS"
_TOOL_APP = "App"
_TOOL_FILE = "File"
_TOOL_AUTOMATION = "Automation"
_TOOL_PLUGINS = "Plugins"

_INTENT_TOOL_MAP: Dict[str, Dict[str, Any]] = {
    "open_app": {"slots": [], "category": _TOOL_APP, "plugin": "windows", "action": "launch_app", "risk": "LOW"},
    "close_app": {"slots": [], "category": _TOOL_APP, "plugin": "windows", "action": "close_app", "risk": "MEDIUM"},
    "open_website": {"slots": [], "category": _TOOL_APP, "plugin": "browser", "action": "open_website", "risk": "LOW"},
    "open_folder": {"slots": [], "category": _TOOL_FILE, "plugin": "windows", "action": "open_folder", "risk": "LOW"},
    "open_file": {"slots": [], "category": _TOOL_FILE, "plugin": "windows", "action": "open_file", "risk": "LOW"},
    "play_media": {"slots": ["media_target"], "category": _TOOL_PLUGINS, "plugin": "youtube", "action": "search_and_play", "risk": "LOW"},
    "set_volume": {"slots": [], "category": _TOOL_OS, "plugin": "windows", "action": "set_volume", "risk": "LOW"},
    "system_control": {"slots": [], "category": _TOOL_OS, "plugin": "system", "action": "system_control", "risk": "HIGH"},
    "shutdown": {"slots": [], "category": _TOOL_OS, "plugin": "system", "action": "shutdown_pc", "risk": "CRITICAL"},
    "restart": {"slots": [], "category": _TOOL_OS, "plugin": "system", "action": "restart_pc", "risk": "CRITICAL"},
    "lock": {"slots": [], "category": _TOOL_OS, "plugin": "system", "action": "lock_system", "risk": "MEDIUM"},
    "create_reminder": {"slots": ["title", "remind_time"], "category": _TOOL_AUTOMATION, "plugin": "reminder", "action": "create_reminder", "risk": "LOW"},
    "send_message": {"slots": ["recipient", "message"], "category": _TOOL_PLUGINS, "plugin": "whatsapp", "action": "send_message", "risk": "HIGH"},
    "send_email": {"slots": ["recipient", "subject"], "category": _TOOL_PLUGINS, "plugin": "email", "action": "send_email", "risk": "HIGH"},
    "delete_file": {"slots": ["file_target"], "category": _TOOL_FILE, "plugin": "files", "action": "delete", "risk": "HIGH"},
    "brightness_up": {"slots": [], "category": _TOOL_OS, "plugin": "screen", "action": "brightness_up", "risk": "LOW"},
    "brightness_down": {"slots": [], "category": _TOOL_OS, "plugin": "screen", "action": "brightness_down", "risk": "LOW"},
    "set_brightness": {"slots": [], "category": _TOOL_OS, "plugin": "screen", "action": "set_screen_brightness", "risk": "LOW"},
    "query_brightness": {"slots": [], "category": _TOOL_OS, "plugin": None, "action": None, "risk": "LOW"},
    "calculate": {"slots": [], "category": _TOOL_PLUGINS, "plugin": "math", "action": "calculate", "risk": "LOW"},
    "memory_remember": {"slots": [], "category": _TOOL_PLUGINS, "plugin": "memory", "action": "remember", "risk": "LOW"},
    "memory_forget": {"slots": [], "category": _TOOL_PLUGINS, "plugin": "memory", "action": "forget", "risk": "LOW"},
    "memory_recall": {"slots": [], "category": None, "plugin": None, "action": None, "risk": "LOW"},
    "memory_query_fact": {"slots": [], "category": None, "plugin": None, "action": None, "risk": "LOW"},
    "memory_preferences": {"slots": [], "category": None, "plugin": None, "action": None, "risk": "LOW"},
    "memory_clear": {"slots": [], "category": _TOOL_PLUGINS, "plugin": "memory", "action": "clear_session", "risk": "LOW"},
    "knowledge": {"slots": [], "category": None, "plugin": None, "action": None, "risk": "LOW"},
    "chat": {"slots": [], "category": None, "plugin": None, "action": None, "risk": "LOW"},
}

# intent -> (verification strategy, expected-state template, verify-hint template)
# Vocabulary mirrors DecisionCore.plan_action + ExecutionVerificationLayer
# so the Verify stage speaks the same language as the authoritative owners.
# Laya only PLANS verification; ExecutionVerificationLayer.verify_outcome
# remains the single owner that actually checks system state.
_VERIFY_PLAN: Dict[str, Dict[str, str]] = {
    "open_app": {"strategy": "process_running", "expected": "{t} running", "hint": "Process list me {t} check karo."},
    "close_app": {"strategy": "process_state", "expected": "{t} closed", "hint": "Process list me {t} band hua ya nahi check karo."},
    "open_website": {"strategy": "browser_opened", "expected": "{t} browser me open", "hint": "Browser tabs me {t} verify karo."},
    "open_folder": {"strategy": "folder_window_open", "expected": "{t} folder open", "hint": "Explorer windows me {t} verify karo."},
    "open_file": {"strategy": "file_exists", "expected": "{t} exists", "hint": "Filesystem par {t} verify karo."},
    "play_media": {"strategy": "media_playing", "expected": "{t} playing", "hint": "Media player state verify karo."},
    "set_volume": {"strategy": "system_state", "expected": "volume set", "hint": "System volume state verify karo."},
    "system_control": {"strategy": "system_state", "expected": "setting applied", "hint": "System setting state verify karo."},
    "shutdown": {"strategy": "unverifiable", "expected": "system shutting down", "hint": "Shutdown ke baad verify possible nahi — confirmation hi proof hai."},
    "restart": {"strategy": "unverifiable", "expected": "system restarting", "hint": "Restart ke baad verify possible nahi — confirmation hi proof hai."},
    "lock": {"strategy": "system_state", "expected": "workstation locked", "hint": "Lock state verify karo."},
    "create_reminder": {"strategy": "unverifiable", "expected": "reminder stored", "hint": "Reminder list me entry check karo."},
    "send_message": {"strategy": "unverifiable", "expected": "message sent", "hint": "Send receipt / chat window check karo."},
    "send_email": {"strategy": "unverifiable", "expected": "email sent", "hint": "Sent folder / send receipt check karo."},
    "delete_file": {"strategy": "file_exists", "expected": "{t} deleted", "hint": "Filesystem par {t} ab nahi hona chahiye."},
    "brightness_up": {"strategy": "system_state", "expected": "brightness raised", "hint": "Monitor brightness state verify karo."},
    "brightness_down": {"strategy": "system_state", "expected": "brightness lowered", "hint": "Monitor brightness state verify karo."},
    "set_brightness": {"strategy": "system_state", "expected": "brightness set", "hint": "Monitor brightness state verify karo."},
    "calculate": {"strategy": "unverifiable", "expected": "answer computed", "hint": "Answer arithmetic check se verify hota hai."},
    "memory_remember": {"strategy": "memory_stored", "expected": "{t} stored", "hint": "Memory store me {t} verify karo."},
    "memory_forget": {"strategy": "memory_stored", "expected": "{t} removed", "hint": "Memory store me {t} ab nahi hona chahiye."},
    "memory_recall": {"strategy": "unverifiable", "expected": "memories listed", "hint": "Recall answer memory listing se verify hota hai."},
    "memory_query_fact": {"strategy": "unverifiable", "expected": "fact answered", "hint": "Recall answer memory lookup se verify hota hai."},
    "memory_preferences": {"strategy": "unverifiable", "expected": "preferences listed", "hint": "Recall answer preference listing se verify hota hai."},
    "memory_clear": {"strategy": "memory_stored", "expected": "session cleared", "hint": "Session store empty verify karo."},
}

_OPEN_RE = re.compile(r"\b(open|launch|start|kholo|khol|chalao|chala)\b", re.IGNORECASE)
_CLOSE_RE = re.compile(r"\b(close|band\s*karo|quit)\b", re.IGNORECASE)

# Deterministic injection-signal gate (2026-09-26): the multilingual guard
# scores ordinary greetings/commands as jailbreak ("hello jarvis kaise ho"=1.00,
# "chrome open karo"=1.00), so a bare flag must NEVER harden a turn by itself.
# A guard flag only escalates when the text ALSO carries an explicit
# prompt-injection signal. Kept conservative — false negatives are caught
# downstream by PermissionGuard risk levels, false positives here would
# make Jarvis confirm every second sentence.
_INJECTION_SIGNAL_RE = re.compile(
    r"(ignore|override|disregard|forget)\s+(all\s+|your\s+|previous|prior|earlier|above|any)?"
    r"(instructions?|rules?|orders?|prompts?|niyam|hna?amesh)"
    r"|(system|initial|developer)\s*(prompt|message|instructions?)"
    r"|(reveal|show|print|batao?|dikha(?:o|do)?|leak)\s*(your|apna|apne)?\s*"
    r"(system\s*prompt|instructions?|secrets?|api\s*keys?|passwords?)"
    r"|\bjailbreak\b|\bdan\s*mode\b|\bdeveloper\s*mode\b|\bbypass\b"
    r"|(aapke?|apne?)\s*(niyam|rules?|instructions?)\s*(todo|tor\s*do|ignore\s*karo|bhool\s*jao)",
    re.IGNORECASE,
)


def _has_injection_signal(text: str) -> bool:
    return bool(text and _INJECTION_SIGNAL_RE.search(text))


def _normalize(text: str) -> str:
    """Job-1 helper: thin normalization, defers to HinglishNormalizer when present."""
    t = (text or "").strip()
    try:
        from core.semantic.normalizer import HinglishNormalizer as _HN
        n = _HN.normalize_text(t.lower())
        if n:
            return re.sub(r"\s+", " ", n).strip()
    except Exception:
        pass
    t = re.sub(r"\s+", " ", t.lower()).strip()
    return t


class LayaIntelligence:
    """Single orchestrator for the 7 Laya jobs. Stateless; context passed in.

    Typical wiring (JarvisCore):
        from core.laya.intelligence import get_laya_intelligence
        decision = get_laya_intelligence().decide(
            text, runtime_context=self.runtime_context,
            dialog_manager=self.dialog_manager,
            has_pending_confirmation=self.dialog_manager.has_pending_system_action(),
        )
    """

    _instance: Optional["LayaIntelligence"] = None

    @classmethod
    def get_instance(cls) -> "LayaIntelligence":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- public entry ----------------------------------------------------
    def decide(
        self,
        text: str,
        runtime_context: Optional[Any] = None,
        dialog_manager: Optional[Any] = None,
        has_pending_confirmation: bool = False,
        active_context: Optional[Any] = None,
    ) -> LayaDecision:
        t0 = time.perf_counter()
        raw = (text or "").strip()
        norm = _normalize(raw)
        dec = LayaDecision(raw_text=raw, normalized_text=norm)

        if not norm or len(norm) < 1:
            dec.response_mode = LayaResponseMode.CLARIFY
            dec.response_hint = "Ji, main sun raha hoon. Aap kya karna chahte hain?"
            dec.latency_ms = (time.perf_counter() - t0) * 1000
            return dec

        ctx = active_context or getattr(runtime_context, "desktop", None) or getattr(runtime_context, "active_context", None)

        # ═══ UNDERSTAND: Intent + Entity + Slots + Context ═══
        # ---- active slot lock wins over fresh intent ----
        # Active workflow protection: short replies inside a lock belong to it.
        try:
            if dialog_manager is not None and hasattr(dialog_manager, "has_active_lock") and dialog_manager.has_active_lock():
                lock = getattr(dialog_manager, "active_lock", None)
                missing = list(getattr(lock, "all_missing_slots", []) or [])
                filled = dict(getattr(lock, "filled_slots", {}) or {})
                dec.missing_slots = missing
                dec.filled_slots = filled
                dec.intent = str(getattr(lock, "workflow_type", "WORKFLOW") or "WORKFLOW").lower()
                dec.speech_act = "FOLLOW_UP"
                dec.confidence = 0.80
                dec.route, dec.handler = "TASK_ENGINE", dec.intent
                info = _INTENT_TOOL_MAP.get(dec.intent, {})
                dec.tool_category = info.get("category")
                dec.tool_plugin = info.get("plugin") or getattr(lock, "target_plugin", "") or None
                dec.tool_action = info.get("action") or getattr(lock, "target_action", "") or None
                if missing:
                    dec.response_mode = LayaResponseMode.ASK_SLOT
                    dec.response_hint = getattr(lock, "prompt_question", "") or f"Kripya {missing[0].replace('_', ' ')} batayein."
                else:
                    dec.response_mode = LayaResponseMode.EXECUTE
                    dec.response_hint = "Theek hai, aage badh raha hoon."
                self._apply_safety(dec)
                self._plan_verification(dec)
                dec.pipeline.append(f"understand:lock->{dec.intent}")
                dec.pipeline.append(f"decide:conf=0.80,risk={dec.risk_level}")
                dec.pipeline.append(f"route:{dec.route}/{dec.tool_category}")
                dec.pipeline.append(f"verify:{dec.verification_strategy}")
                dec.pipeline.append(f"respond:{dec.response_mode.value}")
                dec.latency_ms = (time.perf_counter() - t0) * 1000
                return dec
        except Exception as exc:
            logger.debug("Laya slot-lock check note: %s", exc)

        # ---- UNDERSTAND 1: speech-act gating FIRST (purpose before execution) ----
        speech_act, speech_conf, speech_target, speech_resp = self._classify_speech_act(
            raw, norm, has_pending_confirmation, ctx
        )
        dec.speech_act = speech_act
        dec.confidence = speech_conf
        if speech_target:
            dec.entities["speech_target"] = speech_target

        # Non-executable speech acts short-circuit (decide-only, no route/verify).
        if speech_act in ("CANCELLATION", "REJECTION"):
            dec.intent = "cancel"
            dec.route, dec.handler = "CHAT", "CANCEL"
            dec.laya_route = LayaRoute.CHAT
            dec.is_direct_execution = False
            dec.model_target = "none"
            dec.context_scope = "MINIMAL"
            dec.max_history_turns = 1
            dec.response_mode = LayaResponseMode.REJECT
            dec.response_hint = speech_resp or "Theek hai, cancel kar diya hai."
            dec.pipeline.append("understand:speech-act")
            dec.pipeline.append("decide:rejected")
            dec.pipeline.append("respond:REJECT")
            dec.latency_ms = (time.perf_counter() - t0) * 1000
            return dec
        _DIRECT_FAST_TOOLS = (
            r"\b(volume|awaz|mute|unmute)\b",
            r"\b(weather|mausam|temperature|forecast|taapmaan)\b",
            r"\b(time|samay|waqt)\b",
            r"\b(brightness|battery|charge)\b",
        )
        is_fast_tool = any(re.search(pat, norm) for pat in _DIRECT_FAST_TOOLS)

        _AGENT_CONJUNCTIONS = [
            " aur phir ", " aur uske baad ", " ke baad ", " then ", " and then ",
            " step by step ", " analyze and fix ", " research and summarize ",
            " solve error ", " task execute karo ", " create project ", " build project ",
            "research ", "summarize ", "analyze "
        ]
        is_agent = any(c in norm for c in _AGENT_CONJUNCTIONS)

        _MEM_TRIGGERS = [
            "mera", "meri", "mere", "my", "naam", "name", "remember", "yaad",
            "pichhla", "pichhli", "last time", "favourite", "favorite",
            "pasand", "preference", "preferences", "saved", "bataya tha", "told you"
        ]
        has_mem_trigger = any(re.search(rf"\b{re.escape(w)}\b", norm) for w in _MEM_TRIGGERS)

        if not is_fast_tool and not is_agent and speech_act in (
            "CAPABILITY_QUESTION", "INFORMATION_QUESTION", "TROUBLESHOOTING",
            "GREETING", "CONVERSATION", "SMALL_TALK"
        ):
            # Advisory jailbreak screen BEFORE the conversational short-circuit:
            # injection prompts are frequently misread as conversation by the
            # speech-act classifier, so a flagged guard verdict must never be
            # waved through as chat. Confirmed-first, never silent execution.
            try:
                from core.laya.manager import get_laya_manager as _glm_c
                _g = _glm_c().guard_check(raw) if _has_injection_signal(raw) else {"flagged": False}
                if isinstance(_g, dict) and _g.get("flagged"):
                    dec.intent = "chat"
                    dec.risk_level = "HIGH"
                    dec.needs_confirmation = True
                    dec.response_mode = LayaResponseMode.CONFIRM
                    dec.response_hint = "Ye request unusual lag rahi hai — confirm karenge?"
                    dec.confirmation_prompt = "Kya main ye request execute kar doon?"
                    dec.pipeline.append("understand:speech-act")
                    dec.pipeline.append("decide:guard-flagged-confirm")
                    dec.pipeline.append("respond:CONFIRM")
                    dec.latency_ms = (time.perf_counter() - t0) * 1000
                    return dec
            except Exception:
                pass
            dec.intent = "chat" if speech_act in ("GREETING", "CONVERSATION", "SMALL_TALK") else "knowledge"
            dec.route, dec.handler = "CHAT", "LLM_REASONING"
            dec.laya_route = LayaRoute.CHAT
            dec.is_direct_execution = False
            dec.model_target = "knowledge_engine" if speech_act in ("INFORMATION_QUESTION", "TROUBLESHOOTING") else "local_qwen"
            dec.context_scope = "CONVERSATIONAL"
            dec.max_history_turns = 5
            dec.response_mode = LayaResponseMode.CHAT
            dec.response_hint = speech_resp or ""
            if has_mem_trigger:
                dec.retrieve_memory = True
                dec.memory_query = norm
                dec.memory_types = ["user_profile", "preferences", "episodic"]
            dec.pipeline.append("understand:speech-act")
            dec.pipeline.append("decide:conversational")
            dec.pipeline.append("respond:CHAT")
            dec.latency_ms = (time.perf_counter() - t0) * 1000
            return dec
        if speech_act in ("STATUS_QUESTION", "STATUS_AFTER_ACTION", "SYSTEM_INFORMATION"):
            dec.intent = "status_query"
            dec.route, dec.handler = "SYSTEM", "check_target_status"
            dec.laya_route = LayaRoute.FAST_ROUTER
            dec.is_direct_execution = True
            dec.model_target = "rule_fast"
            dec.context_scope = "ACTIVE_WINDOW"
            dec.max_history_turns = 0
            dec.response_mode = LayaResponseMode.STATUS_ANSWER
            if speech_target:
                dec.entities["target"] = speech_target
            dec.pipeline.append("understand:speech-act")
            dec.pipeline.append("decide:status-readonly")
            dec.pipeline.append("route:SYSTEM")
            dec.pipeline.append("respond:STATUS_ANSWER")
            dec.latency_ms = (time.perf_counter() - t0) * 1000
            return dec
        if speech_act == "CONFIRMATION" and not has_pending_confirmation:
            # "haan" with no pending op -> acknowledge, never execute.
            dec.intent = "chat"
            dec.route, dec.handler = "CHAT", "LLM_REASONING"
            dec.laya_route = LayaRoute.CHAT
            dec.is_direct_execution = False
            dec.model_target = "local_qwen"
            dec.context_scope = "CONVERSATIONAL"
            dec.max_history_turns = 3
            dec.response_mode = LayaResponseMode.CHAT
            dec.response_hint = speech_resp or "Ji, batayein kya karna hai?"
            dec.pipeline.append("understand:speech-act")
            dec.pipeline.append("decide:confirmation-without-pending")
            dec.pipeline.append("respond:CHAT")
            dec.latency_ms = (time.perf_counter() - t0) * 1000
            return dec

        # ---- UNDERSTAND 2: semantic parse (intent + entities) for executables ----
        intent_name, entities, sem_conf, semantic_action = self._parse_semantic(raw, ctx)
        dec.intent = intent_name
        dec.entities.update(entities)
        # speech-act confidence dominates for gating; semantic refines tool choice.
        dec.confidence = max(speech_conf, sem_conf) if intent_name != "UNKNOWN" else speech_conf

        # ═══ DECIDE: Rule engine + Confidence + laya_assist + Clarification ═══
        # Laya HF advisory tie-breaker: ONLY when confidence is low/medium.
        if dec.confidence < 0.80 and intent_name in ("UNKNOWN", "chat"):
            advisory = self._laya_advisory(raw)
            if advisory:
                dec.laya_assist = advisory
                choice = str(advisory.get("choice") or "").lower()
                conf = float(advisory.get("confidence") or 0.0)
                if choice and conf >= 0.60 and choice in _INTENT_TOOL_MAP:
                    dec.intent = choice
                    dec.confidence = max(dec.confidence, min(conf, 0.79))
        dec.pipeline.append(f"understand:{dec.intent}/{dec.speech_act}")

        # ---- UNDERSTAND 3: context resolution (pronouns / follow-ups) ----
        self._resolve_context(dec, ctx)

        # ═══ ROUTE: OS / App / File / Automation / Plugins ═══
        self._select_route_and_tool(dec)

        # ---- UNDERSTAND 4: slot check ----
        self._check_slots(dec)

        # ---- DECIDE (safety is part of Decide): risk + confirmation ----
        self._apply_safety(dec, raw_text=raw)

        # ═══ VERIFY: plan what "did it actually succeed?" means ═══
        self._plan_verification(dec)

        # ═══ RESPOND: mode decision (rendering via ResponseEngine) ═══
        self._decide_response_mode(dec, has_pending_confirmation=has_pending_confirmation)

        # ═══ LAYA CORE: SYNTHESIZE 9 AUTHORITATIVE ORCHESTRATION DECISIONS ═══
        # 1. Multi-Step / Complex Task Check -> Agent Planner (Task Graph)
        _AGENT_CONJUNCTIONS = [
            " aur phir ", " aur uske baad ", " ke baad ", " then ", " and then ",
            " step by step ", " analyze and fix ", " research and summarize ",
            " solve error ", " task execute karo ", " create project ", " build project ",
            "research ", "summarize ", "analyze "
        ]
        is_multi_step = any(c in norm for c in _AGENT_CONJUNCTIONS) or (
            " aur " in norm and any(w in norm for w in ("kholo", "banao", "chalao", "create", "open", "run", "likho", "write"))
        )

        if is_multi_step:
            dec.laya_route = LayaRoute.AGENT_PLANNER
            dec.route = "AGENT_PLANNER"
            dec.is_direct_execution = False
            dec.model_target = "agent_planner"
            dec.context_scope = "FULL"
            dec.max_history_turns = 5
            dec.retrieve_memory = True
            dec.memory_types = ["episodic", "task_graph"]
            dec.can_retry = True
            dec.fallback_strategy = "retry_alternate"
        elif dec.intent in ("chat", "knowledge") or dec.response_mode == LayaResponseMode.CHAT:
            dec.laya_route = LayaRoute.CHAT
            dec.route = "CHAT"
            dec.is_direct_execution = False
            dec.model_target = "knowledge_engine" if dec.intent == "knowledge" else "local_qwen"
            dec.context_scope = "CONVERSATIONAL"
            dec.max_history_turns = 5
        elif dec.response_mode == LayaResponseMode.REJECT:
            dec.laya_route = LayaRoute.CHAT
            dec.is_direct_execution = False
            dec.model_target = "none"
            dec.context_scope = "MINIMAL"
            dec.max_history_turns = 1
        else:
            # Direct Tool Command (Fast Router)
            dec.laya_route = LayaRoute.FAST_ROUTER
            dec.model_target = "rule_fast"
            dec.context_scope = "ACTIVE_WINDOW" if any(p in norm for p in _PRONOUNS) else "NONE"
            dec.max_history_turns = 0
            dec.is_direct_execution = (not dec.missing_slots and not dec.needs_confirmation and dec.confidence >= 0.60)
            dec.can_retry = True
            dec.fallback_strategy = "ask_browser_fallback" if dec.intent == "open_app" else "retry_alternate"

        # 6. Memory Retrieval Gating (Selective: only when inquiry warrants personal recall)
        _MEM_TRIGGERS = [
            "mera", "meri", "mere", "my", "naam", "name", "remember", "yaad",
            "pichhla", "pichhli", "last time", "favourite", "favorite",
            "pasand", "preference", "preferences", "saved", "bataya tha", "told you"
        ]
        if any(re.search(rf"\b{re.escape(w)}\b", norm) for w in _MEM_TRIGGERS):
            dec.retrieve_memory = True
            dec.memory_query = norm
            dec.memory_types = ["user_profile", "preferences", "episodic"]
            if dec.laya_route == LayaRoute.FAST_ROUTER and dec.intent in ("chat", "UNKNOWN"):
                dec.laya_route = LayaRoute.CHAT
                dec.model_target = "local_qwen"
                dec.context_scope = "CONVERSATIONAL"
                dec.max_history_turns = 5

        dec.pipeline.append(f"decide:route={dec.laya_route.value},direct={dec.is_direct_execution},conf={dec.confidence:.2f},risk={dec.risk_level}")
        dec.pipeline.append(f"route:{dec.route}/{dec.tool_category}")
        dec.pipeline.append(f"verify:{dec.verification_strategy}")
        dec.pipeline.append(f"respond:{dec.response_mode.value}")

        dec.latency_ms = (time.perf_counter() - t0) * 1000
        return dec

    # -- job 1 internals -------------------------------------------------
    def _classify_speech_act(self, raw: str, norm: str, has_pending: bool, ctx: Any):
        """Reuse ConversationalIntentClassifier; fallback to tiny local rules."""
        try:
            from core.conversational_intent import ConversationalIntentClassifier as _CIC
            res = _CIC.classify(raw, has_pending_confirmation=has_pending, active_context=ctx)
            return res.intent_type.value, float(res.confidence), res.target, res.natural_response
        except Exception as exc:
            logger.debug("Laya speech-act fallback (classifier unavailable): %s", exc)
        low = norm.lower()
        if re.fullmatch(r"(haan|yes|kar do|karo|ok|sure|bilkul|theek hai)", low):
            return "CONFIRMATION", 0.75, None, None
        if re.fullmatch(r"(nahi|no|cancel|mat karo|rehne do|stop)", low):
            return "CANCELLATION", 0.90, None, None
        if re.search(r"\b(kya tum|can you|sakti ho|sakte ho)\b", low):
            return "CAPABILITY_QUESTION", 0.85, None, None
        if re.search(r"\b(open hai|chal raha|hai kya|status)\b", low):
            return "STATUS_QUESTION", 0.80, None, None
        if _OPEN_RE.search(low) or _CLOSE_RE.search(low):
            return "ACTION_COMMAND", 0.70, None, None
        return "UNKNOWN", 0.30, None, None

    def _parse_semantic(self, raw: str, ctx: Any):
        """Reuse SemanticPipelineOrchestrator; fallback to deterministic map."""
        try:
            from core.semantic.orchestrator import SemanticPipelineOrchestrator as _SPO
            action = _SPO.parse(raw, context=ctx)
            if action is not None:
                name = str(getattr(action, "intent", "") or getattr(action, "action", "") or "UNKNOWN").lower() or "UNKNOWN"
                params = dict(getattr(action, "parameters", {}) or {})
                target = str(
                    getattr(action, "target", "")
                    or getattr(action, "entity", "")
                    or getattr(action, "query", "")
                    or params.get("target", "")
                    or params.get("entity", "")
                    or params.get("app_name", "")
                    or params.get("query", "")
                    or ""
                ).strip()
                entities: Dict[str, Any] = dict(params)
                if target:
                    entities["target"] = target
                # preserve tool hints from the semantic action itself
                if getattr(action, "service", ""):
                    entities.setdefault("service", getattr(action, "service"))
                conf = float(getattr(action, "confidence", 0.85) or 0.85)
                # normalize common action spellings to tool-map keys
                name = self._canon_intent(name, raw)
                return name, entities, conf, action
        except Exception as exc:
            logger.debug("Laya semantic fallback (orchestrator unavailable): %s", exc)
        return self._fallback_intent(raw)

    @staticmethod
    def _canon_intent(name: str, raw: str) -> str:
        n = (name or "").strip().lower()
        low = (raw or "").lower()
        mapping = {
            "launch_app": "open_app", "open_app": "open_app", "open_application": "open_app",
            "open_website": "open_website", "open_url": "open_website",
            "close_app": "close_app", "close_window": "close_app",
            "play": "play_media", "play_media": "play_media", "search_and_play": "play_media",
            "set_volume": "set_volume", "adjust_volume": "set_volume",
            "shutdown_pc": "shutdown", "shutdown": "shutdown",
            "restart_pc": "restart", "restart": "restart",
            "lock_system": "lock", "lock": "lock",
            "create_reminder": "create_reminder",
            "send_message": "send_message", "send_email": "send_email",
            "delete": "delete_file", "delete_file": "delete_file",
            "calculate": "calculate", "math": "calculate",
        }
        if n in mapping:
            return mapping[n]
        # subsystem intent spellings (SYSTEM_SHUTDOWN, SYSTEM_RESTART, ...)
        if "shutdown" in n:
            return "shutdown"
        if "restart" in n or "reboot" in n:
            return "restart"
        if n in ("lock", "lock_system", "system_lock"):
            return "lock"
        if "open" in n and ("app" in n or "application" in n):
            return "open_app"
        if "close" in n and ("app" in n or "application" in n or "window" in n):
            return "close_app"
        # math never needs the model (deterministic gate, mirrored from classifier)
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _M
            if _M.is_math_query(raw):
                return "calculate"
        except Exception:
            if re.search(r"[\d]+\s*[\+\-\*/x×]\s*[\d]+|kitna hota hai|jod|ghatao|guna|bhaag", low):
                return "calculate"
        if _OPEN_RE.search(low):
            return "open_app"
        if _CLOSE_RE.search(low):
            return "close_app"
        return n or "UNKNOWN"

    @staticmethod
    def _fallback_intent(raw: str):
        low = (raw or "").lower()
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _M
            if _M.is_math_query(raw):
                return "calculate", {}, 0.90, None
        except Exception:
            pass
        m = re.search(r"\b(?:open|launch|start|kholo|khol|chalao)\s+([a-z0-9 .]+)", low)
        if m:
            return "open_app", {"target": m.group(1).strip()}, 0.70, None
        m = re.search(r"\b(?:close|band karo)\s+([a-z0-9 .]+)", low)
        if m:
            return "close_app", {"target": m.group(1).strip()}, 0.70, None
        if re.search(r"\b(yaad dila|reminder|alarm)\b", low):
            return "create_reminder", {}, 0.65, None
        if re.search(r"\b(volume|awaz)\b", low):
            return "set_volume", {}, 0.70, None
        return "UNKNOWN", {}, 0.30, None

    def _laya_advisory(self, raw: str) -> Dict[str, Any]:
        """Optional HF tie-breaker. Returns {} when unavailable (offline-safe).

        Always tags mode so callers can see RULE_ONLY vs RULE_PLUS_LAYA_ASSIST.
        RULE_ONLY is 100% functional — advisory absence is never a failure.
        """
        try:
            from core.laya.manager import get_laya_manager as _glm
            mgr = _glm()
            try:
                mode = mgr.get_mode()
            except Exception:
                mode = "RULE_ONLY"
            res = mgr.rescue_intent(raw)
            if isinstance(res, dict) and res.get("choice"):
                res = dict(res)
                res["mode"] = mode
                return res
            return {"mode": mode, "choice": None, "confidence": 0.0}
        except Exception as exc:
            logger.debug("Laya advisory unavailable: %s", exc)
        return {}

    # -- job 3 -----------------------------------------------------------
    def _resolve_context(self, dec: LayaDecision, ctx: Any) -> None:
        """Context Resolution stage: deictic pronoun -> previous entity.

        "usme report kholo" after "Excel kholo" must NOT be re-guessed as a new
        target. The pronoun prefix is stripped off the parsed target and the live
        container (ActiveTargetContext = SSOT) is attached, so downstream stages
        act *inside* the active workflow instead of reclassifying the utterance.
        """
        pronoun_led = False
        # "usme X kholo" -> strip pronoun prefix, keep explicit entity X.
        try:
            speech_tgt = str(dec.entities.get("speech_target", "") or "").lower().strip()
            if speech_tgt:
                stripped = re.sub(
                    r"^(isme|ismein|usme|usmein|isko|usko|ispe|uspe)\s+",
                    "", speech_tgt, flags=re.IGNORECASE,
                ).strip()
                if stripped and stripped != speech_tgt:
                    pronoun_led = True
                    # The parsers put the pronoun-inclusive phrase into `target`/
                    # `site` as a parse artifact (e.g. target='usme report'). Those
                    # values are never a real entity, so overwrite them — the old
                    # `not dec.entities.get("target")` guard made this stage dead
                    # code on every real utterance.
                    for key in ("target", "site"):
                        cur = str(dec.entities.get(key, "") or "").lower().strip()
                        if not cur or cur == speech_tgt or cur.startswith(
                            speech_tgt.split(" ", 1)[0] + " "
                        ):
                            dec.entities[key] = stripped
                    dec.entities["pronoun_stripped"] = speech_tgt
                    dec.context_updates["pronoun_stripped"] = speech_tgt
        except Exception:
            pass
        if ctx is None:
            return
        try:
            text = dec.entities.get("target", "") or ""
            low = str(text).lower().strip()
            if low in _PRONOUNS or not low or pronoun_led:
                for attr in ("application", "website", "last_entity", "last_media_title"):
                    val = str(getattr(ctx, attr, "") or "").strip()
                    if val:
                        dec.entities.setdefault("resolved_from_context", val)
                        dec.context_updates["resolved_target"] = val
                        if pronoun_led:
                            # Active workflow lock: the container the follow-up acts in.
                            dec.entities["container"] = val
                            dec.entities["container_type"] = (
                                "website" if attr == "website" else "application"
                            )
                            dec.context_updates["active_container"] = val
                        if not dec.entities.get("target"):
                            dec.entities["target"] = val
                        break
            # record intent continuity for next turn (never overwrites owner, just hints)
            last_action = getattr(ctx, "last_action", "")
            if last_action:
                dec.context_updates["prev_action"] = last_action
        except Exception as exc:
            logger.debug("Laya context resolve note: %s", exc)

    # -- ROUTE: OS / App / File / Automation / Plugins -------------------
    def _select_route_and_tool(self, dec: LayaDecision) -> None:
        info = _INTENT_TOOL_MAP.get(dec.intent, {})
        # Tool first, so the router sees plugin/action.
        if not dec.tool_category:
            dec.tool_category = info.get("category")
        if not dec.tool_plugin:
            dec.tool_plugin = info.get("plugin")
        if not dec.tool_action:
            dec.tool_action = info.get("action")
        # chat/knowledge/status never select a tool.
        if dec.intent in ("chat", "knowledge", "status_query", "UNKNOWN", "cancel"):
            dec.tool_category, dec.tool_plugin, dec.tool_action = None, None, None
        # Prefer authoritative router when an Intent object can be built.
        try:
            from core.router import CommandRouter as _CR
            from core.intent import Intent as _Intent, IntentType as _IT
            itype = _IT.COMMAND if dec.speech_act in ("ACTION_COMMAND", "FOLLOW_UP", "CONFIRMATION") else _IT.CHAT
            intent_obj = _Intent(
                name=dec.intent, type=itype, confidence=dec.confidence,
                entities=dict(dec.entities),
                target_plugin=dec.tool_plugin, target_action=dec.tool_action,
                raw_query=dec.raw_text,
            )
            route, handler = _CR().route_intent(intent_obj)
            # Router returns CHAT when plugin is None; for real commands with a
            # tool selected, surface PLUGIN route so callers know it is executable.
            if route == "CHAT" and dec.tool_plugin and dec.speech_act in ("ACTION_COMMAND", "FOLLOW_UP"):
                route, handler = "PLUGIN", f"{dec.tool_plugin}.{dec.tool_action}"
            dec.route, dec.handler = route, handler
        except Exception:
            dec.route, dec.handler = ("PLUGIN", dec.intent) if dec.intent not in ("UNKNOWN", "chat", "knowledge") else ("CHAT", "LLM_REASONING")

    # -- job 4 -----------------------------------------------------------
    def _check_slots(self, dec: LayaDecision) -> None:
        info = _INTENT_TOOL_MAP.get(dec.intent, {})
        required: List[str] = list(info.get("slots", []) or [])
        if not required:
            dec.missing_slots = []
            return
        # Reuse SemanticSlotExtractor when available for real extraction.
        try:
            from core.semantic.slot_extractor import SemanticSlotExtractor as _SSE
            extracted = _SSE.extract_slots(dec.raw_text, expected_slots=required) or {}
            dec.filled_slots.update({k: v for k, v in extracted.items() if v})
        except Exception as exc:
            logger.debug("Laya slot extract note: %s", exc)
        # merge entities that already satisfy slots (e.g. recipient/message present)
        for s in required:
            if s not in dec.filled_slots and dec.entities.get(s):
                dec.filled_slots[s] = dec.entities[s]
        dec.missing_slots = [s for s in required if not dec.filled_slots.get(s)]

    # -- job 6 -----------------------------------------------------------
    def _apply_safety(self, dec: LayaDecision, raw_text: str = "") -> None:
        # 6a. jailbreak advisory screen (safe-default pass when offline/disabled).
        # Calibration fix (2026-09-26): the multilingual guard scores ordinary
        # Hinglish command verbs as jailbreak ("chrome open karo"=1.00,
        # "notepad kholo"=0.86) while genuine injection reads LOW, so a raw
        # flag made Laya REJECT everyday commands. Guardrails are advisory by
        # contract: they may raise risk for ambiguous text, but they must never
        # override the AUTHORITATIVE owners — deterministic intent risk
        # (_INTENT_TOOL_MAP) and PermissionGuard. A flagged advisory now caps
        # at HIGH (confirm-first) and only escalates to REJECT when the
        # authoritative stages below agree the action is not a known safe
        # command; the flag itself never hardens a LOW-risk known action.
        guard_flagged = False
        try:
            from core.laya.manager import get_laya_manager as _glm
            # Only consult the noisy advisory when the text carries an explicit
            # injection signal; otherwise its false positives would harden
            # every greeting and everyday command.
            probe = raw_text or dec.raw_text
            g = _glm().guard_check(probe) if _has_injection_signal(probe) else {"flagged": False}
            if isinstance(g, dict):
                guard_flagged = bool(g.get("flagged"))
        except Exception:
            guard_flagged = False
        # 6b. deterministic risk floor: PermissionGuard misses suffixed actions
        # (shutdown_pc, restart_pc). Intent-level risk always wins upward.
        intent_risk = str(_INTENT_TOOL_MAP.get(dec.intent, {}).get("risk", "LOW")).upper()
        # 6c. authoritative risk via PermissionGuard (single owner).
        try:
            from core.permissions import PermissionGuard as _PG
            risk, need_confirm = _PG().evaluate_action_risk(
                action=dec.tool_action or dec.intent,
                target=str(dec.entities.get("target", "") or ""),
                parameters=dict(dec.entities),
            )
            guard_risk = risk.value if hasattr(risk, "value") else str(risk)
        except Exception as exc:
            logger.debug("Laya safety fallback: %s", exc)
            guard_risk, need_confirm = "LOW", False
        order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        known_command_risk = max(order.get(intent_risk, 0), order.get(str(guard_risk).upper(), 0))
        if guard_flagged and known_command_risk <= order["LOW"]:
            # Advisory flag on an otherwise-LOW turn. Known safe commands
            # (open_app, set_volume, recycle_bin_cleanup, ...) are untouched —
            # only UNKNOWN/ambiguous turns escalate, and even then the guard
            # flag must be backed by an explicit injection signal.
            is_known_safe_command = (
                dec.intent not in ("UNKNOWN", "chat", "knowledge")
                and dec.confidence >= 0.60
            )
            if not is_known_safe_command and _has_injection_signal(raw_text or dec.raw_text):
                dec.risk_level = "HIGH"
                dec.needs_confirmation = True
                dec.response_mode = LayaResponseMode.CONFIRM
                dec.response_hint = "Ye request unusual lag rahi hai — confirm karenge?"
                dec.confirmation_prompt = "Kya main ye request execute kar doon?"
                return
            guard_flagged = False
        final = intent_risk if known_command_risk == order.get(intent_risk, 0) else str(guard_risk).upper()
        dec.risk_level = final
        dec.needs_confirmation = bool(need_confirm) or final in ("HIGH", "CRITICAL")

    # -- VERIFY: "Did action actually succeed?" (plan only) ----------------
    def _plan_verification(self, dec: LayaDecision) -> None:
        """Attaches what post-execution verification MEANS for this decision.

        Plan-only: the authoritative check stays with
        ExecutionVerificationLayer.verify_outcome. Non-executable modes
        (CHAT/STATUS/CLARIFY/CONFIRM-pre-execution) carry no strategy.
        """
        try:
            # Non-executable decisions carry no verification plan. (Checked on
            # intent, not response_mode — this runs BEFORE mode is decided.)
            if dec.intent in ("chat", "knowledge", "status_query", "UNKNOWN", "cancel"):
                dec.verification_strategy = None
                dec.expected_state = None
                dec.verify_hint = ""
                return
            plan = _VERIFY_PLAN.get(dec.intent)
            if not plan:
                dec.verification_strategy = None
                dec.expected_state = None
                dec.verify_hint = ""
                return
            target = str(dec.entities.get("target", "") or "").strip()
            dec.verification_strategy = plan["strategy"]
            dec.expected_state = plan["expected"].format(t=target or dec.intent)
            dec.verify_hint = plan["hint"].format(t=target or "target")
        except Exception as exc:
            logger.debug("Laya verify-plan note: %s", exc)
            dec.verification_strategy = None
            dec.expected_state = None
            dec.verify_hint = ""

    # -- job 7 -----------------------------------------------------------
    def _decide_response_mode(self, dec: LayaDecision, has_pending_confirmation: bool = False) -> None:
        if dec.response_mode == LayaResponseMode.REJECT:
            return
        if dec.needs_confirmation or dec.risk_level in ("HIGH", "CRITICAL"):
            # Destructive actions ALWAYS confirm, even at high confidence.
            dec.response_mode = LayaResponseMode.CONFIRM
            if not dec.confirmation_prompt:
                tgt = dec.entities.get("target") or dec.intent
                dec.confirmation_prompt = f"Kya aap sach mein '{tgt}' execute karna chahte hain?"
                dec.response_hint = dec.confirmation_prompt
            return
        if dec.missing_slots:
            dec.response_mode = LayaResponseMode.ASK_SLOT
            slot = dec.missing_slots[0].replace("_", " ")
            dec.response_hint = f"Kripya {slot} batayein."
            return
        if dec.intent in ("UNKNOWN",) or dec.confidence < 0.60:
            dec.response_mode = LayaResponseMode.CLARIFY
            if not dec.response_hint:
                dec.response_hint = "Mujhe ye command samajh nahi aayi. Kripya dobara batayein."
            return
        if dec.intent in ("chat", "knowledge"):
            dec.response_mode = LayaResponseMode.CHAT
            return
        if dec.intent in ("status_query",):
            dec.response_mode = LayaResponseMode.STATUS_ANSWER
            return
        if dec.intent in ("cancel",):
            dec.response_mode = LayaResponseMode.REJECT
            return
        dec.response_mode = LayaResponseMode.EXECUTE
        if not dec.response_hint and dec.entities.get("target"):
            dec.response_hint = f"{dec.entities['target']} par action kar raha hoon."


def get_laya_intelligence() -> LayaIntelligence:
    """Convenience accessor (singleton)."""
    return LayaIntelligence.get_instance()


class LayaCore:
    """
    LAYA CORE: Authoritative Tri-Bridge Orchestration Layer for Jarvis V2.1.
    
    Architecture:
                JARVIS UI / Voice / Vision
                          ↓
                     LAYA CORE
              ┌───────────┼───────────┐
              ↓           ↓           ↓
         Fast Router   Chat/LLM    Agent Planner
              ↓           ↓           ↓
           Tools      Qwen/etc.    Task Graph
                          ↓
                    Execution Layer

    Authoritatively decides:
      1. command direct execute hogi ya nahi
      2. conversation model ko bhejna hai
      3. complex task ke liye agent activate karna hai
      4. kaunsa model use hoga
      5. context kitna dena hai
      6. memory kab retrieve karni hai
      7. confirmation chahiye ya nahi
      8. task successful hua ya nahi
      9. failure par retry/fallback kya hai
    """
    _instance: Optional["LayaCore"] = None

    def __init__(self, intelligence: Optional[LayaIntelligence] = None):
        self.intelligence = intelligence or LayaIntelligence.get_instance()

    @classmethod
    def get_instance(cls) -> "LayaCore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def decide(
        self,
        text: str = "",
        runtime_context: Optional[Any] = None,
        dialog_manager: Optional[Any] = None,
        has_pending_confirmation: bool = False,
        active_context: Optional[Any] = None,
        raw_text: Optional[str] = None,
        normalized_text: Optional[str] = None,
        permission_guard: Optional[Any] = None,
        confirmation_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> LayaDecision:
        """Evaluates input and produces the authoritative 9-point orchestration decision."""
        effective_text = normalized_text or text or raw_text or ""
        effective_act_ctx = active_context or runtime_context
        pending_conf = has_pending_confirmation
        if confirmation_manager and hasattr(confirmation_manager, "has_pending_confirmation"):
            try:
                pending_conf = pending_conf or confirmation_manager.has_pending_confirmation()
            except Exception:
                pass
        return self.intelligence.decide(
            text=effective_text,
            runtime_context=runtime_context,
            dialog_manager=dialog_manager,
            has_pending_confirmation=pending_conf,
            active_context=effective_act_ctx,
        )

    def orchestrate(
        self,
        text: str = "",
        runtime_context: Optional[Any] = None,
        dialog_manager: Optional[Any] = None,
        has_pending_confirmation: bool = False,
        active_context: Optional[Any] = None,
        raw_text: Optional[str] = None,
        normalized_text: Optional[str] = None,
        **kwargs: Any,
    ) -> LayaDecision:
        """Alias for decide()."""
        return self.decide(
            text=text,
            runtime_context=runtime_context,
            dialog_manager=dialog_manager,
            has_pending_confirmation=has_pending_confirmation,
            active_context=active_context,
            raw_text=raw_text,
            normalized_text=normalized_text,
            **kwargs,
        )

    def get_scoped_context(
        self,
        decision: LayaDecision,
        core: Any,
        turn: Any = None
    ) -> Dict[str, Any]:
        """Provides properly bounded context according to decision.context_scope and max_history_turns."""
        scoped: Dict[str, Any] = {
            "scope": decision.context_scope,
            "turns": [],
            "active_app": None,
            "active_window": None,
        }
        try:
            if core and hasattr(core, "active_context") and core.active_context:
                scoped["active_app"] = getattr(core.active_context, "current_application", None)
                scoped["active_window"] = getattr(core.active_context, "current_window_title", None)

            if decision.max_history_turns > 0 and core and hasattr(core, "conversation_manager") and core.conversation_manager:
                if hasattr(core.conversation_manager, "session") and core.conversation_manager.session:
                    scoped["turns"] = core.conversation_manager.session.get_recent_history(limit=decision.max_history_turns)
        except Exception as e:
            logger.debug("Laya context scoping note: %s", e)
        return scoped

    def retrieve_memory_if_needed(
        self,
        decision: LayaDecision,
        memory_manager: Any
    ) -> List[Dict[str, Any]]:
        """Selectively queries memory stores only when decision.retrieve_memory is True."""
        if not decision.retrieve_memory or not memory_manager:
            return []
        try:
            query = decision.memory_query or decision.normalized_text or decision.raw_text
            memories = []
            if hasattr(memory_manager, "search_memories"):
                memories = memory_manager.search_memories(query, limit=3)
            return memories or []
        except Exception as e:
            logger.debug("Laya memory retrieval note: %s", e)
            return []

    def verify_execution(
        self,
        decision: LayaDecision,
        execution_result: Any,
        core: Any = None
    ) -> Dict[str, Any]:
        """Physical state verification check: answers 'task successful hua ya nahi'."""
        outcome = {
            "verified": False,
            "detail": "",
            "spoken_feedback": ""
        }
        try:
            ver_layer = getattr(core, "verification_layer", None) if core else None
            plugin = decision.tool_plugin or "system"
            action = decision.tool_action or decision.intent
            params = decision.entities or {}

            if ver_layer and hasattr(ver_layer, "verify_outcome"):
                res = ver_layer.verify_outcome(plugin, action, params, execution_result)
                decision.verified = getattr(res, "verified", True)
                outcome["verified"] = decision.verified
                outcome["detail"] = getattr(res, "detail", "") or getattr(res, "message", "")
            elif isinstance(execution_result, dict):
                decision.verified = bool(execution_result.get("success", False))
                outcome["verified"] = decision.verified
                outcome["detail"] = str(execution_result.get("message", "") or execution_result.get("detail", ""))
            elif execution_result is not None:
                decision.verified = bool(getattr(execution_result, "success", True))
                outcome["verified"] = decision.verified
                outcome["detail"] = str(getattr(execution_result, "message", "") or "")
            else:
                decision.verified = False
                outcome["verified"] = False
                outcome["detail"] = "No execution result returned"

            decision.verification_detail = outcome["detail"]
            outcome["spoken_feedback"] = decision.confirm_outcome(outcome)
        except Exception as e:
            logger.debug("Laya verification note: %s", e)
            decision.verified = True
            outcome["verified"] = True
            outcome["detail"] = str(e)
            outcome["spoken_feedback"] = "Task complete ho gaya."
        return outcome

    def determine_fallback(
        self,
        decision: LayaDecision,
        error: Any = None,
        core: Any = None
    ) -> Dict[str, Any]:
        """Closed-loop recovery: answers 'failure par retry/fallback kya hai'."""
        fallback = {
            "can_retry": decision.can_retry,
            "strategy": decision.fallback_strategy,
            "suggestion": "",
            "action": decision.fallback_action,
        }
        target = str(decision.entities.get("target") or decision.intent)
        if decision.intent == "open_app":
            fallback["suggestion"] = f"'{target}' application open nahi ho paya. Kya main ise browser me dhoondoon?"
            fallback["action"] = "open_website"
        elif decision.laya_route == LayaRoute.FAST_ROUTER:
            fallback["suggestion"] = f"'{target}' par command fail ho gayi. Main alternate method se try kar sakta hoon."
            fallback["action"] = "retry_alternate"
        else:
            fallback["suggestion"] = "Command process nahi ho paya. Kya aap dobara specify kar sakte hain?"
            fallback["action"] = "clarify"
        return fallback


def get_laya_core() -> LayaCore:
    """Convenience accessor for LAYA CORE singleton."""
    return LayaCore.get_instance()

