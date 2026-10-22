# core/permissions.py
"""Granular Capability-Based Plugin Permission & Security Guard for Jarvis V2."""

from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.core.permissions")


class PluginCapability(str, Enum):
    """The 7 standardized granular plugin capabilities."""
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PROCESS = "process"
    MICROPHONE = "microphone"
    CAMERA = "camera"
    SYSTEM_CONTROL = "system_control"
    OFFICE = "office"


class PermissionLevel(str, Enum):
    """Permission levels for backward compatibility."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class ActionRiskLevel(str, Enum):
    """Normalized policy risk tiers for action execution safety."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionDeniedError(Exception):
    """Raised when a plugin attempts an action without holding required capabilities."""
    pass


class PermissionGuard:
    def __init__(
        self,
        default_level: PermissionLevel = PermissionLevel.EXECUTE,
        enforce: bool = True,
        admin_mode: bool = False
    ):
        self.default_level = default_level
        self.enforce = enforce
        self.admin_mode = admin_mode
        self._all_capabilities = [c.value for c in PluginCapability]

    @staticmethod
    def _coerce_level(level: Any, fallback: PermissionLevel) -> PermissionLevel:
        if isinstance(level, PermissionLevel):
            return level
        try:
            return PermissionLevel(str(level).strip().lower())
        except (TypeError, ValueError):
            return fallback

    def validate_plugin_action(
        self,
        plugin_name: str,
        action_name: str,
        required_capability: Optional[str],
        declared_permissions: List[str]
    ) -> bool:
        """
        Validates if the plugin declared the required capability in its manifest.
        Raises PermissionDeniedError if unauthorized.
        """
        if not self.enforce or not required_capability:
            return True

        normalized_req = required_capability.strip().lower()
        normalized_declared = {str(p).strip().lower() for p in declared_permissions}

        if normalized_req not in normalized_declared and not self.admin_mode:
            err_msg = (
                f"Security Violation: Plugin '{plugin_name}' requested capability '{normalized_req}' "
                f"for action '{action_name}', but only declared permissions: {sorted(list(normalized_declared))}."
            )
            logger.error(err_msg)
            raise PermissionDeniedError(err_msg)

        return True

    def get_security_audit(self, declared_permissions: List[str]) -> Dict[str, bool]:
        """Generates a checklist of granted (True) vs blocked (False) capabilities for display."""
        normalized_declared = {str(p).strip().lower() for p in declared_permissions}
        return {cap: (cap in normalized_declared) for cap in self._all_capabilities}

    def is_action_allowed(
        self,
        plugin_name: str,
        action_name: str,
        required_level: Any = None,
        context: Optional[Any] = None
    ) -> bool:
        """Return whether the configured permission level can run an action."""
        if not self.enforce or self.admin_mode:
            return True

        rank = {
            PermissionLevel.NONE: 0,
            PermissionLevel.READ: 1,
            PermissionLevel.WRITE: 2,
            PermissionLevel.EXECUTE: 3,
            PermissionLevel.ADMIN: 4,
        }
        required = self._coerce_level(required_level, PermissionLevel.READ)
        current = self.default_level
        if isinstance(context, dict) and context.get("permission_level") is not None:
            current = self._coerce_level(context["permission_level"], self.default_level)
        allowed = rank[current] >= rank[required]
        if not allowed:
            logger.warning(
                "Permission denied for %s.%s: current=%s required=%s",
                plugin_name,
                action_name,
                current.value,
                required.value,
            )
        return allowed

    def can_execute(self, required_permission: Any, current_level: Any = None) -> bool:
        """Legacy helper for backward compatibility."""
        context = None if current_level is None else {"permission_level": current_level}
        return self.is_action_allowed("legacy", "execute", required_permission, context)

    def evaluate_action_risk(
        self,
        action: str,
        target: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[ActionRiskLevel, bool]:
        """
        Evaluates action risk level and whether explicit user confirmation is required.
        Returns: (ActionRiskLevel, confirmation_required)
        """
        act = (action or "").strip().lower()
        tgt = (target or "").strip().lower()

        # Critical / High-risk destructive actions
        critical_keywords = {"shutdown", "restart", "reboot", "format", "wipe", "delete_all", "make_payment"}
        if act in critical_keywords or any(k in act for k in ["delete_all", "wipe", "format"]):
            return ActionRiskLevel.CRITICAL, True

        high_keywords = {"delete", "remove", "unlink", "terminate", "kill_process", "send_message", "send_email", "clear_memory"}
        if act in high_keywords or any(k in act for k in ["delete", "remove", "kill", "drop"]):
            return ActionRiskLevel.HIGH, True

        # Medium risk actions (file modifications, system toggles)
        medium_keywords = {"write_file", "append_file", "edit_file", "modify", "disable_auth", "uninstall"}
        if act in medium_keywords:
            return ActionRiskLevel.MEDIUM, False

        # Low risk actions (reading, launching apps, opening web, volume, playback, screen)
        return ActionRiskLevel.LOW, False

    def validate_action_plan(self, action_plan: Any) -> bool:
        """
        Validates an ActionPlan against configured policy and security boundaries.
        Returns True if authorized, False otherwise.
        """
        if not self.enforce or self.admin_mode:
            return True

        req_perm = getattr(action_plan, "required_permission", PermissionLevel.EXECUTE)
        action_name = getattr(action_plan, "action", "execute")
        plugin_name = getattr(action_plan, "resolver", "core")

        return self.is_action_allowed(
            plugin_name=plugin_name,
            action_name=action_name,
            required_level=req_perm
        )
