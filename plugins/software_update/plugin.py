# plugins/software_update/plugin.py
"""Software Update Plugin wrapping SoftwareUpdateManager."""

import logging
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.software_update.manager import SoftwareUpdateManager, get_software_update_manager
from core.software_update.models import UpdateScope
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.software_update")


class SoftwareUpdatePlugin(BasePlugin):
    """Production Software Update Plugin for Jarvis V2.1."""

    def __init__(
        self,
        manifest: Optional[PluginManifest] = None,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(manifest=manifest, config=config, event_bus=event_bus, **kwargs)
        self.manager = get_software_update_manager()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="software_update",
            version="1.0.0",
            description="Orchestrates WinGet, Windows Update, and Microsoft Store software updates.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS,
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        lang = parameters.get("language", "hi")

        try:
            if action_name == "check_updates":
                scope_str = parameters.get("scope", "ALL_SUPPORTED")
                scope = getattr(UpdateScope, scope_str.upper(), UpdateScope.ALL_SUPPORTED)
                inc_unknown = bool(parameters.get("include_unknown", False))
                inc_pinned = bool(parameters.get("include_pinned", False))

                plan, msg = self.manager.check_updates(
                    scope=scope,
                    include_unknown=inc_unknown,
                    include_pinned=inc_pinned,
                    language=lang,
                )
                return PluginResult(
                    success=True,
                    data={"message": msg, "plan": plan.to_dict()},
                )

            elif action_name == "install_updates":
                allow_reboot = bool(parameters.get("allow_reboot", False))
                success, msg = self.manager.execute_updates(
                    allow_reboot=allow_reboot,
                    language=lang,
                )
                return PluginResult(
                    success=success,
                    data={"message": msg},
                    error=None if success else msg,
                )

            elif action_name == "windows_update":
                mode = parameters.get("action_mode", "check").lower()
                if mode == "install":
                    success, msg = self.manager.execute_updates(
                        plan=None,
                        language=lang,
                    )
                    return PluginResult(success=success, data={"message": msg})
                else:
                    plan, msg = self.manager.check_updates(
                        scope=UpdateScope.OS,
                        language=lang,
                    )
                    return PluginResult(success=True, data={"message": msg, "plan": plan.to_dict()})

            elif action_name == "get_status":
                status = self.manager.get_status()
                return PluginResult(success=True, data=status)

            elif action_name == "cancel_update":
                cancelled = self.manager.cancel()
                msg = (
                    "Update process cancel request bhej di gayi hai, Boss."
                    if lang == "hi"
                    else "Update cancellation requested."
                )
                return PluginResult(success=cancelled, data={"message": msg})

            else:
                return PluginResult(success=False, error=f"Unknown action '{action_name}'")

        except Exception as e:
            logger.error("SoftwareUpdatePlugin error on %s: %s", action_name, e, exc_info=True)
            return PluginResult(success=False, error=str(e))
