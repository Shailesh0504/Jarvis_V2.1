# plugins/base.py
"""Abstract Base Plugin class with capability-based security isolation and error handling."""

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Dict, List, Optional

from core.permissions import PermissionGuard, PermissionDeniedError
from .manifest import PluginManifest, PluginResult, PluginStatus

logger = logging.getLogger("jarvis.plugins.base")


class BasePlugin(ABC):
    """Abstract base class that all Jarvis plugins inherit from with security sandboxing."""

    def __init__(
        self,
        manifest: Optional[PluginManifest] = None,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        **kwargs: Any,
    ):
        self.manifest = manifest or self.get_manifest()
        self.config = config or {}
        self.event_bus = event_bus
        self.status = PluginStatus.ENABLED if self.manifest.enabled else PluginStatus.DISABLED
        self.last_error: Optional[str] = None
        self._initialized = False
        self.permission_guard = PermissionGuard()

    @property
    def is_enabled(self) -> bool:
        return self.status in (PluginStatus.ENABLED, PluginStatus.DEGRADED)

    @abstractmethod
    def get_manifest(self) -> PluginManifest:
        """Returns the metadata manifest describing the plugin, capabilities, and actions."""
        pass

    def check_dependencies(self) -> bool:
        """Lifecycle hook to verify external libraries or binaries. Returns True if operational."""
        return True

    def get_health_status(self) -> Dict[str, Any]:
        """Returns detailed health, availability, and diagnostic metrics."""
        deps_ok = self.check_dependencies()
        effective_status = self.status
        if not deps_ok and self.status == PluginStatus.ENABLED:
            effective_status = PluginStatus.DEGRADED

        return {
            "plugin": self.manifest.name,
            "status": effective_status.value,
            "version": self.manifest.version,
            "enabled": self.manifest.enabled,
            "initialized": self._initialized,
            "dependencies_met": deps_ok,
            "actions_count": len(self.manifest.actions),
            "last_error": self.last_error,
        }

    def initialize(self) -> bool:
        """Lifecycle hook called when the plugin is loaded."""
        self._initialized = True
        if not self.check_dependencies():
            self.status = PluginStatus.DEGRADED
        else:
            self.status = PluginStatus.ENABLED
        return True

    def shutdown(self) -> None:
        """Lifecycle hook called when plugin or Jarvis shuts down."""
        self._initialized = False
        self.status = PluginStatus.DISABLED

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        """Optional post-execution verification hook. Subclasses can override for observable system checks."""
        return None

    @abstractmethod
    def execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        """Executes a specific named action with the provided parameters."""
        pass

    def safe_execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        """Guarded execution wrapper that checks capability permissions and isolates unexpected crashes."""
        if not self.is_enabled:
            return PluginResult(
                success=False,
                error=f"Plugin '{self.manifest.name}' is currently {self.status.value}."
            )

        # 1. Capability Permission Validation
        action = self.manifest.get_action(action_name)
        if action and action.required_capability:
            try:
                declared_perms = getattr(self.manifest, "normalized_permissions", self.manifest.permissions)
                self.permission_guard.validate_plugin_action(
                    plugin_name=self.manifest.name,
                    action_name=action_name,
                    required_capability=action.required_capability,
                    declared_permissions=declared_perms
                )
            except PermissionDeniedError as pe:
                return PluginResult(success=False, error=str(pe))

        # 2. Crash-Isolated Execution with Timing and Optional Verification
        start_time = time.perf_counter()
        try:
            res = self.execute(action_name=action_name, parameters=parameters)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if getattr(res, "execution_time_ms", 0.0) == 0.0:
                res.execution_time_ms = round(elapsed_ms, 2)

            # 3. Post-Execution State Verification
            if res.success and getattr(res, "verification_result", None) is None:
                verification = self.verify_state(action_name, parameters, res.data)
                if verification is not None:
                    res.verification_result = verification
                    if hasattr(verification, "verified") and not verification.verified:
                        res.success = False
                        res.error = getattr(verification, "error", None) or "Verification check failed."

            return res
        except Exception as e:
            self.last_error = str(e)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"Crash in plugin '{self.manifest.name}' action '{action_name}': {e}", exc_info=True)
            return PluginResult(
                success=False,
                error=f"Crash in plugin '{self.manifest.name}' action '{action_name}': {e}",
                execution_time_ms=round(elapsed_ms, 2)
            )
