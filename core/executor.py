# core/executor.py
"""Plan executor for safely executing planned tasks via plugins."""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

from .event_bus import EventBus
from .permissions import PermissionGuard, PermissionLevel
from .planner import ExecutionPlan, PlanStatus, PlanStep

logger = logging.getLogger("jarvis.executor")


@dataclass
class StepExecutionResult:
    step_id: str
    plugin_name: str
    action_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


class PlanExecutor:
    """Safely executes an ExecutionPlan step-by-step using the PluginManager."""

    def __init__(
        self,
        plugin_manager: Any,
        permission_guard: Optional[PermissionGuard] = None,
        event_bus: Optional[EventBus] = None
    ):
        self.plugin_manager = plugin_manager
        self.permission_guard = permission_guard or PermissionGuard()
        self.event_bus = event_bus

    def execute_step(self, step: PlanStep, step_context: Optional[Dict[str, Any]] = None) -> StepExecutionResult:
        start_time = time.perf_counter()

        # 1. Check permissions
        if not self.permission_guard.is_action_allowed(
            plugin_name=step.plugin_name,
            action_name=step.action_name,
            required_level=step.required_permission
        ):
            elapsed = (time.perf_counter() - start_time) * 1000
            err_msg = f"Permission denied for {step.plugin_name}.{step.action_name}"
            logger.warning(err_msg)
            return StepExecutionResult(
                step_id=step.step_id,
                plugin_name=step.plugin_name,
                action_name=step.action_name,
                success=False,
                error=err_msg,
                execution_time_ms=elapsed
            )

        # 2. Emit step starting event
        if self.event_bus:
            self.event_bus.emit(
                "executor.step_start",
                data={"step_id": step.step_id, "plugin": step.plugin_name, "action": step.action_name}
            )

        # 3. Resolve parameters (inject step_context if dynamic)
        params = dict(step.parameters)
        if step_context:
            for k, v in params.items():
                if isinstance(v, str) and v.startswith("$"):
                    var_key = v[1:]
                    if var_key in step_context:
                        params[k] = step_context[var_key]

        # 4. Invoke Plugin Manager
        try:
            plugin_result = self.plugin_manager.execute_action(
                plugin_name=step.plugin_name,
                action_name=step.action_name,
                parameters=params
            )
            elapsed = (time.perf_counter() - start_time) * 1000

            result = StepExecutionResult(
                step_id=step.step_id,
                plugin_name=step.plugin_name,
                action_name=step.action_name,
                success=plugin_result.success,
                data=plugin_result.data,
                error=plugin_result.error,
                execution_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.error(f"Execution error on step {step.step_id} ({step.plugin_name}.{step.action_name}): {e}", exc_info=True)
            result = StepExecutionResult(
                step_id=step.step_id,
                plugin_name=step.plugin_name,
                action_name=step.action_name,
                success=False,
                error=str(e),
                execution_time_ms=elapsed
            )

        # 5. Emit step finished event
        if self.event_bus:
            self.event_bus.emit(
                "executor.step_end",
                data={"step_id": step.step_id, "success": result.success, "error": result.error}
            )

        return result

    def execute_plan(self, plan: ExecutionPlan) -> List[StepExecutionResult]:
        """Executes all steps in a plan sequentially, respecting dependencies and critical flags."""
        plan.status = PlanStatus.IN_PROGRESS
        results: List[StepExecutionResult] = []
        step_outputs: Dict[str, Any] = {}

        if self.event_bus:
            self.event_bus.emit("executor.plan_start", data={"plan_id": plan.plan_id, "total_steps": len(plan.steps)})

        for step in plan.steps:
            # Check dependencies
            missing_deps = [dep for dep in step.depends_on if dep not in step_outputs]
            if missing_deps:
                err_msg = f"Step {step.step_id} dependencies not met: {missing_deps}"
                res = StepExecutionResult(
                    step_id=step.step_id,
                    plugin_name=step.plugin_name,
                    action_name=step.action_name,
                    success=False,
                    error=err_msg
                )
                results.append(res)
                if step.critical:
                    plan.status = PlanStatus.FAILED
                    break
                continue

            res = self.execute_step(step, step_context=step_outputs)
            results.append(res)

            if res.success:
                step_outputs[step.step_id] = res.data
                step_outputs[f"{step.plugin_name}.{step.action_name}.result"] = res.data
            else:
                if step.critical:
                    logger.error(f"Critical step {step.step_id} failed: {res.error}. Aborting remaining steps.")
                    plan.status = PlanStatus.FAILED
                    break

        if plan.status != PlanStatus.FAILED:
            plan.status = PlanStatus.COMPLETED

        if self.event_bus:
            self.event_bus.emit(
                "executor.plan_end",
                data={"plan_id": plan.plan_id, "status": plan.status.value, "results_count": len(results)}
            )

        return results
