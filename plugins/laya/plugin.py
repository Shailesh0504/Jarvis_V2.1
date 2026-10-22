# plugins/laya/plugin.py
"""Laya System-1 Decision Engine plugin (voice entry-point, thin over core manager)."""

import logging
import threading
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS

logger = logging.getLogger("jarvis.plugins.laya")

try:
    from plugins.laya.permissions import PERMISSIONS_REQUIRED  # type: ignore
except Exception:
    PERMISSIONS_REQUIRED = ["network", "storage"]


class LayaPlugin(BasePlugin):
    """Voice + programmatic control for Laya model lifecycle."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="laya",
            version="1.0.0",
            description="Laya System-1 Decision Engine: fast multilingual decisions, download & status.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS,
        )

    def _manager(self):
        from core.laya import get_laya_manager

        try:
            cfg = {}
            if isinstance(self.config, dict):
                cfg = self.config.get("laya", self.config)
        except Exception:
            cfg = {}
        return get_laya_manager(config=cfg if isinstance(cfg, dict) else None)

    def check_dependencies(self) -> bool:
        # Plugin stays ENABLED even without weights (status guides download).
        return True

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        try:
            mgr = self._manager()
        except Exception as exc:
            return PluginResult(success=False, data={"message": f"Laya manager unavailable: {exc}"})

        if action_name == "laya_status":
            try:
                st = mgr.get_status()
                msg = mgr.status_message()
                return PluginResult(success=True, data={**st, "message": msg, "formatted_answer": msg})
            except Exception as exc:
                return PluginResult(success=False, data={"message": f"Laya status failed: {exc}"})

        if action_name == "laya_download":
            cp = str(parameters.get("checkpoint", "multilingual") or "multilingual").lower().strip()
            # Never block voice turn on multi-hundred-MB download: background thread.
            st = mgr.get_status()
            if st.get("busy"):
                msg = "Laya download already chal raha hai, Boss. Complete hone par bata dunga."
                return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, **st})
            if mgr.is_downloaded(cp):
                msg = f"Laya '{cp}' pehle se downloaded hai, Boss. Dobara download ki zaroorat nahi."
                return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, **mgr.get_status()})

            def _bg():
                try:
                    mgr.download(checkpoint=cp)
                except Exception as exc:
                    logger.warning("Background laya download note: %s", exc)

            threading.Thread(target=_bg, daemon=True, name="laya-download").start()
            msg = f"Laya '{cp}' download background me start kar diya, Boss. Settings me progress dekh sakte ho."
            return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, "checkpoint": cp})

        if action_name == "laya_test":
            text = str(parameters.get("text", "chrome kholo") or "chrome kholo")[:500]
            st = mgr.get_status()
            mode = st.get("mode", "RULE_ONLY")
            if not st.get("ready"):
                msg = mgr.status_message() + " Pehle download complete kijiye."
                return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, **st})
            intent = mgr.fast_intent_decision(text)
            if intent is None:
                # Model present but inference unavailable right now: rules still 100%.
                msg = f"Mode: {mode}, Boss. Laya inference is baar unavailable raha — rule-based path se 100% functional hoon."
                return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, **st})
            msg = f"Laya test done, Boss. Decision: {intent}."
            return PluginResult(success=True, data={"message": msg, "formatted_answer": msg, "decision": intent, **st})

        return PluginResult(success=False, data={"message": f"Unknown laya action: {action_name}"})
