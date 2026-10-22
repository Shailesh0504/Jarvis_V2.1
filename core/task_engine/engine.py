# core/task_engine/engine.py
"""
Task Continuity Engine for Jarvis V2.
Orchestrates long-horizon multi-step requests adhering to the strict invariant:
PLAN → EXECUTE STEP → VERIFY → CHECKPOINT → NEXT STEP → VERIFY → ... → FINAL VALIDATION → COMPLETE.
Features an Active Workflow Lock, interruption suspension/auto-resume,
watchdog protection, crash recovery, and experience learning.
"""

import logging
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .diagnostics import FailureDiagnosis, FailureDiagnoser
from .experience import ExperienceLearner
from .models import StepExecutionReport, TaskState, TaskStatus, TaskStep
from .persistence import TaskPersistenceManager
from .verifier import TaskVerifier
from .watchdog import TaskWatchdog

logger = logging.getLogger("jarvis.task_engine")


class TaskContinuityEngine:
    """Central orchestrator for verified, recoverable, long-horizon task execution."""

    CANCELLATION_PATTERNS = [
        re.compile(r"\b(?:stop\s+this\s+task|cancel\s+this\s+task|abort\s+this\s+task|stop\s+task|cancel\s+task|abort\s+task|forget\s+this\s+task|forget\s+task|terminate\s+task|ruk\s+jao|ruko|chhod\s+do|rehne\s+do|band\s+karo)\b", re.IGNORECASE),
        re.compile(r"^(?:stop|cancel|abort)$", re.IGNORECASE),
    ]

    TASK_QUERY_PATTERNS = [
        re.compile(r"\b(?:what\s+step|current\s+step|which\s+step|task\s+status|status\s+kya\s+hai|kya\s+kar\s+rahe\s+ho|kitna\s+(?:hua|bacha|time)|progress|kahan\s+tak\s+pahuncha)\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        persistence_manager: Optional[TaskPersistenceManager] = None,
        plugin_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        permission_guard: Optional[Any] = None,
        watchdog: Optional[TaskWatchdog] = None,
        db_path: str = "data/jarvis.db"
    ):
        self.persistence = persistence_manager or TaskPersistenceManager(db_path)
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.permission_guard = permission_guard

        self.verifier = TaskVerifier(plugin_manager=self.plugin_manager)
        self.watchdog = watchdog or TaskWatchdog()
        self.diagnoser = FailureDiagnoser()
        self.experience = ExperienceLearner(persistence_manager=self.persistence, plugin_manager=self.plugin_manager)

        self.active_task: Optional[TaskState] = None
        self._is_handling_interruption: bool = False
        self._lock = threading.RLock()
        self._interrupt_lock = threading.RLock()

    def has_active_task(self) -> bool:
        """Returns True if there is an in-flight, non-terminal workflow."""
        with self._lock:
            if getattr(self, "_is_handling_interruption", False):
                return False
            return self.active_task is not None and self.active_task.final_status in (
                TaskStatus.RUNNING, TaskStatus.SUSPENDED, TaskStatus.RETRYING, TaskStatus.PLANNING
            )

    def is_cancellation(self, text: str) -> bool:
        """Checks if utterance is an intentional cancellation directive."""
        cleaned = text.strip()
        return any(p.search(cleaned) for p in self.CANCELLATION_PATTERNS)

    def is_task_query(self, text: str) -> bool:
        """Checks if utterance is a question regarding the active workflow status."""
        cleaned = text.strip()
        return any(p.search(cleaned) for p in self.TASK_QUERY_PATTERNS)

    def handle_conversational_input(
        self,
        text: str,
        interruption_executor: Optional[Callable[[str], str]] = None
    ) -> Tuple[bool, str]:
        """
        Active Workflow Lock input filter:
        1. Cancellation -> Terminate active task intentionally.
        2. Task question -> Answer with current progress without resetting task.
        3. Unrelated urgent command -> Suspend workflow, execute interruption, and auto-resume.
        """
        with self._lock:
            if not self.has_active_task():
                return False, ""

            raw = text.strip()
            task = self.active_task

            # 1. Intentional Cancellation
            if self.is_cancellation(raw):
                task.final_status = TaskStatus.CANCELLED
                self.persistence.save_task_state(task)
                self.active_task = None
                logger.info("TaskContinuityEngine: Task '%s' intentionally cancelled by user.", task.task_id)
                self._emit("task_cancelled", {"task_id": task.task_id, "goal": task.goal})
                return True, f"Understood Boss, '{task.goal}' task cancel kar diya gaya hai."

            # 2. Task-Related Status Question
            if self.is_task_query(raw):
                curr = task.current_step + 1
                tot = task.total_steps
                curr_desc = (task.current_step_obj.name or task.current_step_obj.description) if task.current_step_obj else "finalizing"
                resp = (
                    f"Task '{task.goal}' progress mein hai (Step {curr}/{tot}: {curr_desc}). "
                    f"Abhi tak {len(task.completed_steps)} steps successfully complete aur verify ho chuke hain, Boss."
                )
                return True, resp

            # 3. Unrelated Urgent Command Interruption -> Suspend -> Execute -> Auto-Resume
            logger.info("TaskContinuityEngine: Suspending active task '%s' for urgent interruption: '%s'",
                        task.task_id, raw)
            self._suspend_active_task(interruption_text=raw)

            interruption_response = ""
            if interruption_executor:
                self._is_handling_interruption = True
                try:
                    interruption_response = interruption_executor(raw)
                except Exception as e:
                    interruption_response = f"Interruption command failed: {e}"
                finally:
                    self._is_handling_interruption = False

            # Auto-resume previous task from exact saved state
            resume_msg = self._resume_suspended_task()
            combined = f"{interruption_response}\n\n[Resuming Task: '{task.goal}']\n{resume_msg}" if interruption_response else resume_msg
            return True, combined.strip()

    def _suspend_active_task(self, interruption_text: str = "") -> None:
        """Suspends the active workflow and stores exact runtime state in SQLite."""
        if not self.active_task:
            return
        task = self.active_task
        task.final_status = TaskStatus.SUSPENDED
        task.suspension_stack.append({
            "interruption": interruption_text,
            "step_at_suspension": task.current_step,
            "suspended_at": time.time(),
        })
        self.persistence.save_task_state(task)
        self._emit("task_suspended", {"task_id": task.task_id, "step": task.current_step})

    def _resume_suspended_task(self) -> str:
        """Resumes a suspended task from its exact saved checkpoint."""
        if not self.active_task:
            return ""
        task = self.active_task
        task.final_status = TaskStatus.RUNNING
        self.persistence.save_task_state(task)
        self._emit("task_resumed", {"task_id": task.task_id, "step": task.current_step})

        # Run next steps to completion
        outcome_success, message = self._execute_workflow_loop(task)
        return message

    def start_workflow(
        self,
        goal: str,
        steps: List[TaskStep],
        execution_context: Optional[Dict[str, Any]] = None,
        required_entities: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Dict[str, List[str]]] = None
    ) -> Tuple[bool, str, TaskState]:
        """
        Initializes and executes an explicit multi-step workflow following the invariant:
        PLAN → EXECUTE STEP → VERIFY → CHECKPOINT → NEXT STEP → VERIFY → ... → FINAL VALIDATION → COMPLETE.
        """
        with self._lock:
            # Check experience learner for past insights
            past_exp = self.experience.retrieve_applicable_experience(goal)
            if past_exp and not steps:
                logger.info("TaskContinuityEngine: Formulating plan using verified previous experience for '%s'", goal)
                steps = [TaskStep.from_dict(s) for s in past_exp.get("procedure", [])]

            task = TaskState(
                goal=goal,
                plan=steps,
                current_step=0,
                completed_steps=[],
                remaining_steps=list(steps),
                failed_steps=[],
                retry_count=0,
                execution_context=dict(execution_context or {}),
                required_entities=dict(required_entities or {}),
                dependencies=dict(dependencies or {}),
                final_status=TaskStatus.PLANNING
            )

            self.persistence.save_task_state(task)
            self.active_task = task
            self._emit("task_started", {"task_id": task.task_id, "goal": goal, "total_steps": len(steps)})

            task.final_status = TaskStatus.RUNNING
            self.persistence.save_task_state(task)

            success, message = self._execute_workflow_loop(task)
            return success, message, task

    def _execute_workflow_loop(self, task: TaskState) -> Tuple[bool, str]:
        """
        The core step-by-step invariant execution loop.
        Executes ONLY the current step, verifies it, checkpoints it, then continues.
        """
        while task.current_step < len(task.plan):
            if task.final_status == TaskStatus.CANCELLED:
                return False, f"Task '{task.goal}' was cancelled."
            if task.final_status == TaskStatus.SUSPENDED:
                return True, f"Task '{task.goal}' is currently suspended."

            step = task.plan[task.current_step]
            step_success = self._execute_and_verify_single_step(task, step)

            if not step_success:
                # Watchdog & failure recovery was exhausted
                task.final_status = TaskStatus.FAILED
                self.persistence.save_task_state(task)
                self.experience.record_failed_workflow(task)
                last_fail = task.failed_steps[-1] if task.failed_steps else {}
                err_msg = (
                    f"Task '{task.goal}' stopped at Step {task.current_step + 1}/{task.total_steps} "
                    f"('{step.name or step.description}').\n"
                    f"Reason: {last_fail.get('error', 'Execution failure')}\n"
                    f"Attempted Strategy: {last_fail.get('strategy_attempted', 'default')}\n"
                    f"Preserved exact task state '{task.task_id}'. Required to continue: resolve failure condition and resume."
                )
                self.active_task = None
                return False, err_msg

        # All steps executed -> Final Completion Validation
        completion_verified, final_err, final_details = self.verifier.verify_completion(task)
        if not completion_verified:
            task.final_status = TaskStatus.FAILED
            self.persistence.save_task_state(task)
            self.active_task = None
            return False, f"Task completed steps but final validation failed: {final_err}"

        task.final_status = TaskStatus.COMPLETED
        task.final_verification = final_details
        self.persistence.save_task_state(task)
        self.experience.record_completed_workflow(task)
        self.active_task = None

        logger.info("TaskContinuityEngine: Task '%s' successfully completed and verified.", task.task_id)
        self._emit("task_completed", {"task_id": task.task_id, "goal": task.goal})
        return True, f"Task '{task.goal}' successfully completed and verified all {len(task.completed_steps)} steps, Boss."

    def _execute_and_verify_single_step(self, task: TaskState, step: TaskStep) -> bool:
        """
        Executes a single step with watchdog checks, verification, failure diagnosis,
        adaptive strategy retry, and verified checkpointing.
        """
        self.watchdog.start_step_timer(step.step_id)
        active_strategy = "primary"
        current_parameters = dict(step.parameters)

        while True:
            # 1. Watchdog limit check
            can_retry, watchdog_reason = self.watchdog.can_retry_step(task, step)
            if not can_retry:
                logger.error("TaskContinuityEngine: Cannot attempt step '%s': %s", step.step_id, watchdog_reason)
                task.record_step_failure(step, error=watchdog_reason, strategy=active_strategy, diagnosis="LIMIT_EXCEEDED")
                self.watchdog.clear_step(step.step_id)
                return False

            # 2. Dependency resolution
            for dep_id in step.depends_on:
                dep_done = any(c.step_id == dep_id and c.verified for c in task.completed_steps)
                if not dep_done:
                    diag_msg = f"Dependency '{dep_id}' is not yet verified"
                    task.record_step_failure(step, error=diag_msg, strategy=active_strategy, diagnosis="DEPENDENCY_UNMET")
                    self.watchdog.clear_step(step.step_id)
                    return False

            # 3. Dynamic parameter substitution from execution_context
            resolved_params = self._resolve_params(current_parameters, task.execution_context)

            # 4. Action Execution
            start_t = time.perf_counter()
            self._emit("step_start", {"task_id": task.task_id, "step_id": step.step_id, "step_name": step.name})
            raw_result = self._dispatch_action(step.plugin_name, step.action_name, resolved_params)
            duration = (time.perf_counter() - start_t) * 1000

            # 5. Verification (Never assume success based merely on invocation)
            is_verified, verify_err, verify_details = self.verifier.verify_step(step, raw_result, task.execution_context)

            if is_verified:
                # Step Succeeded and Verified!
                step_report = StepExecutionReport(
                    step_id=step.step_id,
                    step_name=step.name or step.description,
                    success=True,
                    verified=True,
                    data=getattr(raw_result, "data", raw_result),
                    error=None,
                    attempt=task.step_retry_counts.get(step.step_id, 0) + 1,
                    strategy_used=active_strategy,
                    verification_details=verify_details,
                    duration_ms=duration
                )

                # Store output variables in execution_context
                if isinstance(step_report.data, dict):
                    task.execution_context.update(step_report.data)
                task.execution_context[f"{step.step_id}.result"] = step_report.data
                task.execution_context[f"{step.step_id}.output"] = step_report.data

                # Advance and Checkpoint immediately to SQLite
                task.advance_step(step_report)
                self.persistence.checkpoint_step(task, step_report)
                self.watchdog.clear_step(step.step_id)
                self._emit("step_completed", {"task_id": task.task_id, "step_id": step.step_id, "verified": True})
                return True

            # Step Failed -> Run Failure Diagnosis & Adaptive Strategy
            fail_error = verify_err or getattr(raw_result, "error", "Execution failed")
            diag: FailureDiagnosis = self.diagnoser.diagnose(
                step=step,
                error_msg=str(fail_error),
                context=task.execution_context,
                attempt_number=task.step_retry_counts.get(step.step_id, 0) + 1
            )
            logger.warning("Step '%s' failed attempt %d: %s. Diagnosis: %s (Strategy: %s)",
                           step.step_id, task.step_retry_counts.get(step.step_id, 0) + 1,
                           fail_error, diag.category, diag.recommended_strategy)

            task.record_step_failure(step, error=str(fail_error), strategy=active_strategy, diagnosis=diag.category)

            if not diag.can_recover:
                logger.error("Step '%s' failure diagnosed as unrecoverable: %s", step.step_id, diag.root_cause)
                self._emit("step_failed", {"task_id": task.task_id, "step_id": step.step_id, "error": str(diag.root_cause)})
                self.watchdog.clear_step(step.step_id)
                return False

            # Adapt strategy and parameters for next attempt
            active_strategy = diag.recommended_strategy
            if diag.adjusted_parameters:
                current_parameters = dict(diag.adjusted_parameters)

            self._emit("task_retry", {"task_id": task.task_id, "step_id": step.step_id, "strategy": active_strategy})
            # Brief backoff before retry
            time.sleep(0.1)

    def _resolve_params(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Substitutes $var references with evaluated context values."""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("$"):
                var_key = v[1:]
                resolved[k] = context.get(var_key, v)
            else:
                resolved[k] = v
        return resolved

    def _dispatch_action(self, plugin_name: str, action_name: str, parameters: Dict[str, Any]) -> Any:
        """Dispatches action through PluginManager or handles core builtins."""
        if not plugin_name:
            return {"success": True, "data": parameters}

        if self.plugin_manager:
            return self.plugin_manager.execute_action(plugin_name, action_name, parameters)

        return {"success": False, "error": f"Plugin manager not available to execute '{plugin_name}.{action_name}'"}

    def recover_incomplete_tasks(self) -> List[Tuple[TaskState, bool, str]]:
        """
        Discovers uncompleted workflows from previous sessions on startup.
        Validates the current environment and resumes them from the latest verified checkpoint.
        """
        incomplete = self.persistence.get_incomplete_tasks()
        results = []

        for task in incomplete:
            logger.info("TaskContinuityEngine: Found incomplete task '%s' ('%s', step %d/%d). Validating environment...",
                        task.task_id, task.goal, task.current_step, task.total_steps)

            # Validate environment (e.g. check required plugins are available)
            env_valid = True
            for step in task.plan:
                if step.plugin_name and self.plugin_manager:
                    if not self.plugin_manager.get_plugin(step.plugin_name):
                        logger.warning("Recovery: Plugin '%s' missing for task '%s'. Cannot auto-resume.",
                                       step.plugin_name, task.task_id)
                        env_valid = False
                        break

            if not env_valid:
                results.append((task, False, "Environment validation failed: required plugins missing"))
                continue

            # Resume task from latest verified checkpoint
            self.active_task = task
            task.final_status = TaskStatus.RUNNING
            self.persistence.save_task_state(task)
            succ, msg = self._execute_workflow_loop(task)
            results.append((task, succ, msg))

        return results

    def _emit(self, event_name: str, data: Dict[str, Any]) -> None:
        try:
            from core.logger import JarvisEvent, log_event
            event_map = {
                "task_started": JarvisEvent.TASK_STARTED,
                "step_start": JarvisEvent.TASK_STEP_STARTED,
                "step_completed": JarvisEvent.TASK_STEP_COMPLETED,
                "step_failed": JarvisEvent.TASK_STEP_FAILED,
                "task_retry": JarvisEvent.TASK_RETRY,
                "task_resumed": JarvisEvent.TASK_RESUMED,
                "task_cancelled": JarvisEvent.TASK_CANCELLED,
                "task_completed": JarvisEvent.TASK_COMPLETED,
            }
            if event_name in event_map:
                log_event(event_map[event_name], details=data)
        except Exception:
            pass

        if self.event_bus:
            self.event_bus.emit(f"task_engine.{event_name}", data=data)

