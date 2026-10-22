# core/observability/health.py
"""
Health & Status Monitoring Subsystem for Jarvis V2.1.
Tracks component state across 9 subsystems:
STT, TTS, GUI, EventBus, Memory, Database, Plugins, Agent, ModelGateway.
Ensures non-critical degradation never crashes core operations.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.observability.health")


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus = HealthStatus.HEALTHY
    details: str = "Operating normally"
    last_check: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "details": self.details,
            "last_check": self.last_check,
            "consecutive_failures": self.consecutive_failures,
            "error": self.error,
        }


class HealthMonitor:
    """
    Central monitor observing runtime component health.
    Emits structured events upon status changes and reports unified diagnostics.
    """

    DEFAULT_COMPONENTS = [
        "stt", "tts", "gui", "event_bus", "memory", "database", "plugins", "agent", "model_gateway"
    ]

    def __init__(self, event_bus: Optional[Any] = None):
        self.event_bus = event_bus
        self._components: Dict[str, ComponentHealth] = {
            name: ComponentHealth(name=name) for name in self.DEFAULT_COMPONENTS
        }
        self._checkers: Dict[str, Callable[[], Tuple[HealthStatus, str]]] = {}

    def register_checker(self, name: str, checker: Callable[[], Tuple[HealthStatus, str]]) -> None:
        self._checkers[name] = checker
        if name not in self._components:
            self._components[name] = ComponentHealth(name=name)

    def record_status(
        self,
        name: str,
        status: HealthStatus,
        details: str = "",
        error: Optional[str] = None
    ) -> None:
        """Manually records status from runtime events (e.g. plugin failure or DB lock)."""
        comp = self._components.setdefault(name, ComponentHealth(name=name))
        old_status = comp.status
        comp.status = status
        comp.details = details or ("Operating normally" if status == HealthStatus.HEALTHY else "Degraded")
        comp.error = error
        comp.last_check = time.time()

        if status != HealthStatus.HEALTHY:
            comp.consecutive_failures += 1
            logger.warning(f"[HealthMonitor] Component '{name}' status: {status.value} - {details}")
        else:
            comp.consecutive_failures = 0

        if old_status != status and self.event_bus and hasattr(self.event_bus, "emit"):
            self.event_bus.emit(
                "system.health.changed",
                {"component": name, "old_status": old_status.value, "new_status": status.value, "details": details}
            )

    def run_health_checks(self) -> Dict[str, ComponentHealth]:
        """Executes all registered health checkers safely."""
        for name, checker in self._checkers.items():
            try:
                status, details = checker()
                self.record_status(name, status, details=details)
            except Exception as e:
                self.record_status(name, HealthStatus.UNHEALTHY, details="Checker threw exception", error=str(e))
        return dict(self._components)

    def get_system_summary(self) -> Dict[str, Any]:
        """Returns unified system health status (HEALTHY, DEGRADED, or UNHEALTHY)."""
        statuses = [c.status for c in self._components.values()]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return {
            "overall_status": overall.value,
            "components": {name: comp.to_dict() for name, comp in self._components.items()},
            "timestamp": time.time(),
        }

    run_diagnostics = get_system_summary

