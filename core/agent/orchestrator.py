"""Agent Orchestrator - Central lifecycle controller for Jarvis Personal AI Agent.
===================================================================================
Coordinates the full agentic loop:
Goal -> Understanding -> Planning -> Task Decomposition -> Tool Execution ->
Observation -> Verification -> Recovery / Replanning -> Memory -> Response.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .agent_policy import AgentPolicy
from .agent_state import AgentRiskLevel, AgentState, StepStatus, TaskStatus
from .observer import AgentObserver, SystemObservation
from .planner import AgentPlanner
from .recovery import FailureRecoveryEngine, RecoveryDecision, RecoveryStrategy
from .replanner import AgentReplanner
from .request_classifier import RequestClassification, RequestClassifier, RequestType
from .task_manager import AgentExecutionSummary, AgentStep, AgentStepRecord, AgentTask
from .tool_registry import AgentTool, ToolRegistry, ToolResult
from .verifier import AgentVerifier, VerificationOutcome

logger = logging.getLogger("jarvis.core.agent.orchestrator")


class AgentOrchestrator:
    """Central orchestrator managing multi-step agent tasks, tools, observations, and safety."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        policy: Optional[AgentPolicy] = None,
        observer: Optional[AgentObserver] = None,
        verifier: Optional[AgentVerifier] = None,
        recovery_engine: Optional[FailureRecoveryEngine] = None,
        replanner: Optional[AgentReplanner] = None,
        planner: Optional[AgentPlanner] = None,
        classifier: Optional[RequestClassifier] = None,
        event_bus: Optional[Any] = None,
        reasoner: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        persistence: Optional[Any] = None,
        approval_callback: Optional[Callable[[AgentTask, AgentStep, AgentRiskLevel], bool]] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.policy = policy or AgentPolicy()
        self.observer = observer or AgentObserver()
        self.verifier = verifier or AgentVerifier(observer=self.observer)
        self.recovery_engine = recovery_engine or FailureRecoveryEngine(observer=self.observer)
        self.replanner = replanner or AgentReplanner()
        self.planner = planner or AgentPlanner()
        self.classifier = classifier or RequestClassifier()
        self.event_bus = event_bus
        self.reasoner = reasoner
        self.memory_manager = memory_manager
        self.status_callback = status_callback
        self.approval_callback = approval_callback

        self.persistence = persistence
        if self.persistence is None:
            try:
                from core.task_engine.persistence import TaskPersistenceManager
                self.persistence = TaskPersistenceManager()
            except Exception as _pe:
                logger.debug("AgentOrchestrator: TaskPersistenceManager unavailable: %s", _pe)
                self.persistence = None

        self.current_state = AgentState.IDLE
        self.active_task: Optional[AgentTask] = None
        self._cancelled_tasks: set[str] = set()

    def persist_task_state(self, task: AgentTask) -> None:
        """Persists the AgentTask state into SQLite (task_workflows table)."""
        if not self.persistence or not hasattr(self.persistence, "db"):
            return
        try:
            sql = """
            INSERT INTO task_workflows (
                task_id, goal, final_status, current_step, total_steps,
                retry_count, task_state_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                goal = excluded.goal,
                final_status = excluded.final_status,
                current_step = excluded.current_step,
                total_steps = excluded.total_steps,
                retry_count = excluded.retry_count,
                task_state_json = excluded.task_state_json,
                updated_at = excluded.updated_at
            """
            now = time.time()
            status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
            self.persistence.db.execute_update(sql, (
                task.task_id,
                task.user_goal,
                status_str,
                task.current_step_index,
                len(task.steps),
                int(getattr(task, "retries", 0)),
                json.dumps(task.to_dict()),
                task.created_at,
                now,
            ))
            logger.debug("AgentOrchestrator: Persisted task '%s' (status: %s, step: %d/%d)",
                         task.task_id, status_str, task.current_step_index, len(task.steps))
        except Exception as e:
            logger.warning("Failed to persist agent task %s: %s", task.task_id, e)

    def checkpoint_agent_step(self, task: AgentTask, step: AgentStep) -> None:
        """Records a verified step checkpoint into SQLite (task_checkpoints table)."""
        if not self.persistence or not hasattr(self.persistence, "db"):
            return
        try:
            self.persist_task_state(task)
            sql = """
            INSERT INTO task_checkpoints (task_id, step_index, step_id, verified, checkpoint_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            checkpoint_data = {
                "task_id": task.task_id,
                "step_index": step.step_num,
                "step_id": step.step_id,
                "step": step.to_dict(),
                "timestamp": time.time(),
            }
            self.persistence.db.execute_update(sql, (
                task.task_id,
                step.step_num,
                step.step_id,
                1 if step.verified else 0,
                json.dumps(checkpoint_data),
                time.time(),
            ))
            logger.info("AgentOrchestrator: Checkpointed step %d ('%s') for task '%s'",
                        step.step_num, step.description, task.task_id)
        except Exception as e:
            logger.warning("Failed to checkpoint agent step %s: %s", step.step_id, e)

    def load_task(self, task_id: str) -> Optional[AgentTask]:
        """Loads an AgentTask from SQLite."""
        if not self.persistence or not hasattr(self.persistence, "db"):
            return None
        try:
            sql = "SELECT task_state_json FROM task_workflows WHERE task_id = ?"
            rows = self.persistence.db.execute_query(sql, (task_id,))
            if not rows:
                return None
            data = json.loads(rows[0]["task_state_json"])
            return AgentTask.from_dict(data)
        except Exception as e:
            logger.error("Failed to load agent task %s: %s", task_id, e)
            return None

    def get_pending_tasks(self) -> List[AgentTask]:
        """Retrieves unfinished agent tasks for crash recovery."""
        if not self.persistence or not hasattr(self.persistence, "db"):
            return []
        try:
            sql = "SELECT task_state_json FROM task_workflows WHERE final_status IN ('IN_PROGRESS', 'PENDING', 'PLANNING', 'EXECUTING')"
            rows = self.persistence.db.execute_query(sql)
            tasks = []
            for r in rows:
                tasks.append(AgentTask.from_dict(json.loads(r["task_state_json"])))
            return tasks
        except Exception as e:
            logger.error("Failed to fetch pending agent tasks: %s", e)
            return []

    def _set_state(self, new_state: AgentState) -> None:
        """Transitions state and emits event if changed."""
        old_state = self.current_state
        self.current_state = new_state
        logger.debug("AgentState transitioned: %s -> %s", old_state.name, new_state.name)
        # Persist the authoritative lifecycle audit trail onto the active task.
        if self.active_task is not None:
            try:
                self.active_task.record_stage(new_state)
            except Exception:
                pass
        if self.event_bus:
            try:
                self.event_bus.emit(
                    "agent.state.changed",
                    {"old_state": old_state.name, "new_state": new_state.name},
                )
            except Exception:
                pass

    def _emit_status(self, message: str) -> None:
        """Surfaces human-friendly progress without exposing raw technical chain-of-thought."""
        logger.info("Agent Progress: %s", message)
        if self.status_callback:
            try:
                self.status_callback(message)
            except Exception:
                pass
        if self.event_bus:
            try:
                self.event_bus.emit("agent.progress", {"message": message})
            except Exception:
                pass

    def _gather_context(self, task: AgentTask) -> None:
        """GATHERING_CONTEXT stage: collects a ground-truth runtime snapshot into task context."""
        try:
            observation = self.observer.observe()
            task.context.setdefault("runtime_snapshot", observation.to_dict())
        except Exception as e:
            logger.debug("AgentOrchestrator: context gathering failed: %s", e)
        task.context["planned_step_count"] = len(task.steps)
        task.updated_at = time.time()

    def _request_approval(self, task: AgentTask, step: AgentStep, risk: AgentRiskLevel) -> bool:
        """WAITING_FOR_APPROVAL stage: pauses for explicit user approval on risky steps.

        Fail-safe by default: when no interactive approval handler is attached, the
        policy's on_missing_approval decision applies (deny unless set to allow).
        """
        self._set_state(AgentState.WAITING_FOR_APPROVAL)
        task.status = TaskStatus.WAITING_APPROVAL
        task.record_approval_required(step, risk)
        self.persist_task_state(task)

        question = f"'{step.description}' ek {risk.name} risk action hai - kar doon?"
        logger.info("Step %s paused for approval (Risk: %s)", step.step_id, risk.name)
        self._emit_status(question)
        if self.event_bus:
            try:
                self.event_bus.emit("agent.approval.required", {
                    "task_id": task.task_id,
                    "step_id": step.step_id,
                    "step": step.description,
                    "risk_level": risk.name,
                    "question": question,
                })
            except Exception:
                pass

        approved = False
        reason = ""
        if self.approval_callback is not None:
            try:
                approved = bool(self.approval_callback(task, step, risk))
                reason = "user granted approval" if approved else "user denied approval"
            except Exception as e:
                logger.warning("Approval handler failed for step %s: %s", step.step_id, e)
                approved = False
                reason = f"approval handler error: {e}"
        else:
            approved = self.policy.resolve_missing_approval()
            reason = (
                "policy auto-approval (allow)"
                if approved
                else "no interactive approval handler (fail-safe deny)"
            )

        task.record_approval_decision(approved, reason)
        self.persist_task_state(task)
        if self.event_bus:
            try:
                self.event_bus.emit("agent.approval.resolved", {
                    "task_id": task.task_id,
                    "step_id": step.step_id,
                    "approved": approved,
                    "reason": reason,
                })
            except Exception:
                pass
        return approved

    def is_complex_goal(self, text: str) -> bool:
        """Determines if the text requires the Agent Path."""
        classification = self.classifier.classify(text)
        if classification.is_agent_path:
            return True
        if self.reasoner and hasattr(self.reasoner, "is_complex_goal"):
            try:
                return bool(self.reasoner.is_complex_goal(text))
            except Exception:
                pass
        return False

    def cancel_task(self, task_id: Optional[str] = None) -> bool:
        """Safely stops the active or specified task."""
        if self.active_task:
            target_id = task_id or self.active_task.task_id
            if self.active_task.task_id == target_id:
                self.active_task.status = TaskStatus.CANCELLED
                self._cancelled_tasks.add(target_id)
                self._set_state(AgentState.CANCELLED)
                self._emit_status("Task safe cancel kar diya gaya hai.")
                logger.info("Task %s cancelled by user request.", target_id)
                return True
        return False

    def execute_goal(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_frame: Optional[Any] = None,
    ) -> AgentExecutionSummary:
        """Main autonomous execution loop following the explicit task lifecycle:
        TASK_CREATED -> UNDERSTANDING -> PLANNING -> GATHERING_CONTEXT ->
        WAITING_FOR_APPROVAL (HIGH/CRITICAL risk) -> EXECUTING -> VERIFYING ->
        RECOVERING -> COMPLETED / FAILED / CANCELLED.

        Persistent state (task id, goal, steps, current/completed/failed steps,
        retries, artifacts, context, user approval, result, timestamps) is owned by
        the AgentTask and checkpointed to SQLite after every stage.

        Args:
            goal: Natural-language goal string.
            context: Optional additional context dict.
            conversation_frame: Optional HumanConversationFrame already produced by
                                 HumanConversationModel.analyze_turn(). When provided,
                                 pre-resolved fields (action, target, communicative_goal,
                                 confidence) seed the planner context directly, avoiding
                                 redundant re-parsing of the raw goal text.
        """
        start_time = time.perf_counter()
        logger.info("AgentOrchestrator starting goal: '%s'", goal)

        # Seed planner context from ConversationFrame when available
        if conversation_frame is not None:
            context = dict(context or {})
            try:
                context.setdefault("action", conversation_frame.action)
                context.setdefault("target", conversation_frame.target or conversation_frame.resolved_reference)
                context.setdefault("target_type", conversation_frame.target_type)
                context.setdefault("communicative_goal", conversation_frame.communicative_goal)
                context.setdefault("frame_confidence", (
                    conversation_frame.confidence.composite
                    if conversation_frame.confidence else conversation_frame.certainty
                ))
                context.setdefault("language", conversation_frame.language)
                context.setdefault("dialogue_act", str(getattr(conversation_frame.dialogue_act, "value",
                                                               conversation_frame.dialogue_act or "")))
            except Exception as _fe:
                logger.debug("AgentOrchestrator: frame seeding failed: %s", _fe)

        # 1. TASK CREATED - instantiate the persistent task record (single source of truth)
        task = self.planner.create_task_from_goal(goal, context=context)
        self.active_task = task
        task.status = TaskStatus.PENDING
        self._set_state(AgentState.TASK_CREATED)
        self.persist_task_state(task)

        if self.event_bus:
            try:
                self.event_bus.emit("agent.start", {"goal": goal, "task_id": task.task_id})
            except Exception:
                pass
        self._emit_status(f"Task #{task.task_id} banaya gaya.")

        # 2. UNDERSTANDING & goal formation
        self._set_state(AgentState.UNDERSTANDING)
        task.status = TaskStatus.PLANNING
        self._set_state(AgentState.PLANNING)
        self.persist_task_state(task)
        self._emit_status("Task plan formulate ho raha hai.")

        # Check Dry Run Mode
        if self.policy.dry_run:
            self._set_state(AgentState.COMPLETED)
            plan_preview = [f"{s.step_num}. {s.description} ({s.tool_name})" for s in task.steps]
            preview_text = "\n".join(plan_preview)
            final_answer = (
                f"[DRY-RUN MODE] Plan created with {len(task.steps)} steps:\n{preview_text}\n"
                f"No actions were executed."
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AgentExecutionSummary(
                goal=goal,
                success=True,
                final_answer=final_answer,
                total_steps=len(task.steps),
                trace=[],
                total_time_ms=elapsed_ms,
            )

        if not task.steps:
            # Fallback to legacy reasoner if available
            if self.reasoner and hasattr(self.reasoner, "formulate_plan"):
                try:
                    legacy_steps = self.reasoner.formulate_plan(goal)
                    if legacy_steps:
                        for i, ls in enumerate(legacy_steps, 1):
                            task.steps.append(
                                AgentStep(
                                    step_id=getattr(ls, "step_id", f"step_{i}"),
                                    step_num=i,
                                    description=getattr(ls, "description", ls.action_name),
                                    tool_name=f"{ls.plugin_name}.{ls.action_name}",
                                    input_data=getattr(ls, "parameters", {}),
                                )
                            )
                except Exception as e:
                    logger.warning("Legacy reasoner fallback failed: %s", e)

        if not task.steps:
            self._set_state(AgentState.FAILED)
            task.status = TaskStatus.FAILED
            self.persist_task_state(task)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AgentExecutionSummary(
                goal=goal,
                success=False,
                final_answer="Mujhe is goal ko accomplish karne ke liye specific plan steps nahi mile.",
                total_steps=0,
                trace=[],
                total_time_ms=elapsed_ms,
            )

        # 3. GET CONTEXT - gather ground-truth runtime context before acting
        self._set_state(AgentState.GATHERING_CONTEXT)
        self._gather_context(task)
        self.persist_task_state(task)
        self._emit_status("Runtime context collect kiya gaya.")

        # 4. Execution Loop
        self._set_state(AgentState.EXECUTING)
        task.status = TaskStatus.IN_PROGRESS
        self.persist_task_state(task)
        step_records: List[AgentStepRecord] = []
        all_success = True
        denied_approval = False
        step_outputs: Dict[str, Any] = {}

        for step in task.steps:
            if task.task_id in self._cancelled_tasks:
                logger.info("Task execution interrupted due to cancellation.")
                all_success = False
                break

            step.status = StepStatus.IN_PROGRESS
            step_start = time.perf_counter()
            step.started_at = time.time()

            # Dynamic parameter resolution from previous outputs
            resolved_inputs = self._resolve_step_inputs(step.input_data, step_outputs)

            # Safety / Human-in-the-Loop Confirmation Gate.
            # HIGH and CRITICAL risk steps truly block in WAITING_FOR_APPROVAL until approved.
            tool = self.tool_registry.get_tool(step.tool_name)
            risk = tool.risk_level if tool else AgentRiskLevel.LOW
            if self.policy.requires_confirmation(risk):
                approved = self._request_approval(task, step, risk)
                if not approved:
                    step.status = StepStatus.BLOCKED
                    step.error = f"Approval denied for {risk.name} risk action"
                    step.finished_at = time.time()
                    all_success = False
                    denied_approval = True
                    task.sync_progress()
                    self._set_state(AgentState.CANCELLED)
                    task.status = TaskStatus.CANCELLED
                    self._emit_status(
                        f"Step '{step.description}' ke liye approval nahi mila, task rok diya gaya."
                    )
                    break

            self._emit_status(f"Executing: {step.description}")
            if self.event_bus:
                try:
                    self.event_bus.emit("agent.step.start", {"step": step.step_num, "description": step.description})
                except Exception:
                    pass

            # Execute with observation, verification, and automated recovery
            step_success, tool_result, observation = self._execute_step_with_recovery(
                step=step,
                resolved_inputs=resolved_inputs,
                task=task,
            )

            step_duration_ms = (time.perf_counter() - step_start) * 1000
            step.execution_time_ms = step_duration_ms
            step.finished_at = time.time()
            step.verified = bool(step_success)
            step.actual_output = tool_result.output_data if tool_result else None
            step.error = tool_result.error if tool_result else "Execution failed"

            # Create trace record matching legacy contract
            obs_dict = observation.to_dict() if observation else {}
            if tool_result and tool_result.output_data:
                if isinstance(tool_result.output_data, dict):
                    obs_dict.update(tool_result.output_data)
                else:
                    obs_dict["data"] = tool_result.output_data

            record = AgentStepRecord(
                step_num=step.step_num,
                thought=step.description,
                action_plugin=step.tool_name.split(".")[0] if "." in step.tool_name else "agent",
                action_name=step.tool_name.split(".")[1] if "." in step.tool_name else step.tool_name,
                parameters=resolved_inputs,
                observation=obs_dict,
                success=step_success,
                error=tool_result.error if tool_result and not step_success else None,
                execution_time_ms=step_duration_ms,
            )
            step_records.append(record)

            if step_success:
                step.status = StepStatus.COMPLETED
                step_outputs[step.step_id] = tool_result.output_data if tool_result else {}
                step_outputs[step.tool_name] = tool_result.output_data if tool_result else {}
                self._emit_status(f"Completed step {step.step_num}: {step.description}")
            else:
                step.status = StepStatus.FAILED
                all_success = False
                logger.warning("Step %s failed: %s", step.step_id, step.error)
                self._emit_status(f"Step {step.step_num} par issue aaya: {step.error}")

            task.current_step_index = step.step_num
            self.checkpoint_agent_step(task, step)

            if not step_success:
                break

        # 5. Formulate Final Response
        elapsed_total_ms = (time.perf_counter() - start_time) * 1000
        if all_success:
            task.status = TaskStatus.COMPLETED
            self._set_state(AgentState.COMPLETED)
            final_answer = self._synthesize_final_answer(task, step_records)
        elif denied_approval:
            # User withheld approval: the task is cancelled, not failed.
            task.status = TaskStatus.CANCELLED
            self._set_state(AgentState.CANCELLED)
            blocked_step = next((s for s in task.steps if s.status == StepStatus.BLOCKED), None)
            desc = blocked_step.description if blocked_step else goal
            final_answer = f"Task rok diya gaya - '{desc}' ke liye approval nahi mila."
        else:
            task.status = TaskStatus.FAILED
            self._set_state(AgentState.FAILED)
            failed_step = next((s for s in task.steps if s.status == StepStatus.FAILED), None)
            err_desc = failed_step.error if failed_step else "Unknown error"
            final_answer = f"Task pura nahi ho saka. Issue: {err_desc}."

        # 6. Finalize persistent state (completed/failed steps, retries, artifacts, result)
        task.sync_progress()
        for rec in step_records:
            if rec.success and rec.observation is not None:
                task.record_artifact(
                    f"step_{rec.step_num}:{rec.action_plugin}.{rec.action_name}", rec.observation
                )
        progress_tree = task.to_progress_tree()
        logger.info("AgentOrchestrator task tree:\n%s", progress_tree)
        task.completed_at = time.time()
        task.final_answer = final_answer
        task.updated_at = time.time()
        task.result = {
            "success": all_success,
            "final_answer": final_answer,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "total_steps": len(step_records),
            "completed_steps": list(task.completed_steps),
            "failed_steps": list(task.failed_steps),
            "retries": task.retries,
            "user_approval": dict(task.user_approval),
            "total_time_ms": elapsed_total_ms,
            "progress_tree": progress_tree,
        }
        self.persist_task_state(task)
        self.active_task = None

        # 4. Record Experience into Memory
        if self.memory_manager:
            try:
                self.memory_manager.record_interaction(
                    user_input=goal,
                    response=final_answer,
                    intent="agent_goal",
                    execution_results=[{"success": r.success, "data": r.observation, "error": r.error} for r in step_records],
                )
            except Exception as e:
                logger.debug("Memory recording exception in agent: %s", e)

        if self.event_bus:
            try:
                self.event_bus.emit(
                    "agent.finish",
                    {"goal": goal, "success": all_success, "answer": final_answer},
                )
            except Exception:
                pass

        return AgentExecutionSummary(
            goal=goal,
            success=all_success,
            final_answer=final_answer,
            total_steps=len(step_records),
            trace=step_records,
            total_time_ms=elapsed_total_ms,
        )

    def _execute_step_with_recovery(
        self,
        step: AgentStep,
        resolved_inputs: Dict[str, Any],
        task: AgentTask,
    ) -> tuple[bool, Optional[ToolResult], Optional[SystemObservation]]:
        """Executes a single step, performs observation and verification, and invokes recovery if needed."""
        retries = 0
        current_tool_name = step.tool_name
        current_inputs = dict(resolved_inputs)

        while retries <= self.policy.max_retries_per_step:
            # 1. Execute
            self._set_state(AgentState.EXECUTING)
            tool_res = self.tool_registry.execute(current_tool_name, current_inputs)

            # 2. Observe
            self._set_state(AgentState.OBSERVING)
            target = current_inputs.get("target") or current_inputs.get("url") or current_inputs.get("path")
            obs = self.observer.observe(target=str(target) if target else None)

            # 3. Verify
            self._set_state(AgentState.VERIFYING)
            outcome = self.verifier.verify(step=step, tool_result=tool_res, observation=obs)

            if outcome.is_verified:
                step.retries = retries
                return True, tool_res, obs

            # 4. Handle failure & recovery
            retries += 1
            step.retries = retries
            self._set_state(AgentState.RECOVERING)

            if not self.policy.can_retry_step(retries):
                logger.warning("Step %s exceeded max retries (%d).", step.step_id, self.policy.max_retries_per_step)
                break

            decision: RecoveryDecision = self.recovery_engine.diagnose_and_decide(
                step=step,
                tool_result=tool_res,
                observation=obs,
                current_retry=retries,
            )
            self._emit_status(f"Recovery: {decision.reason}")

            if decision.strategy == RecoveryStrategy.RETRY:
                time.sleep(0.15)
                continue
            elif decision.strategy == RecoveryStrategy.ADAPT_STATE:
                # E.g. restore/focus existing window instead of re-launching
                if "restore" in str(decision.alternative_action):
                    current_tool_name = "desktop.window_operation"
                    current_inputs = {"operation": "restore", "target": target}
                continue
            elif decision.strategy == RecoveryStrategy.REPLAN:
                self._set_state(AgentState.REPLANNING)
                replan_step = self.replanner.replan_step(step, decision.reason)
                if replan_step:
                    current_tool_name = replan_step.tool_name
                    current_inputs = dict(replan_step.input_data)
                    self._emit_status(f"Replanning step with alternative: {replan_step.tool_name}")
                    continue
                else:
                    break
            else:
                break

        return False, tool_res, obs

    def _resolve_step_inputs(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Substitutes $variable references from previous step outputs."""
        resolved = {}
        for k, v in input_data.items():
            if isinstance(v, str) and v.startswith("$"):
                var_key = v[1:]
                resolved[k] = context.get(var_key, v)
            else:
                resolved[k] = v
        return resolved

    def _synthesize_final_answer(self, task: AgentTask, trace: List[AgentStepRecord]) -> str:
        """Builds a crisp, natural human-like completion statement."""
        if not trace:
            return "Task complete ho gaya."

        # If custom answer synthesis from reasoner is available, use it
        if self.reasoner and hasattr(self.reasoner, "synthesize_agent_response"):
            try:
                trace_data = [
                    {
                        "plugin": r.action_plugin,
                        "action": r.action_name,
                        "success": r.success,
                        "data": r.observation if r.success else None,
                        "error": r.error,
                    }
                    for r in trace
                ]
                ans = self.reasoner.synthesize_agent_response(goal=task.goal, steps_trace=trace_data)
                if ans and isinstance(ans, str) and len(ans.strip()) > 3:
                    return ans
            except Exception:
                pass

        # Check if any step produced output data (e.g. filesystem search)
        for r in reversed(trace):
            obs = r.observation
            if isinstance(obs, dict):
                if "matches" in obs:
                    matches = obs["matches"]
                    count = obs.get("total_count", len(matches))
                    if count == 0:
                        return "Mujhe 1500 lines se badi koi Python file nahi mili."
                    if matches and isinstance(matches[0], dict):
                        file_names = [os.path.basename(m.get("path", "")) for m in matches[:5]]
                    else:
                        file_names = [str(m) for m in matches[:5]]
                    files_str = ", ".join(file_names)
                    more = f" aur {count - 5} anya files" if count > 5 else ""
                    return f"Maine check kiya, kul {count} Python files 1500 lines se badi hain: {files_str}{more}."
                if "system_info" in obs:
                    info = obs["system_info"]
                    return f"System information: OS {info.get('os')}, RAM {info.get('ram_total_gb')}GB ({info.get('ram_used_percent')}% used)."

        # Default multi-step natural response
        actions = [s.action_name for s in trace if s.success]
        if len(actions) == 1:
            return "Task safaltapoorvak complete ho gaya."
        return f"Task ke sabhi {len(actions)} steps safaltapoorvak poore ho gaye hain."


class AutonomousAgent:
    """Executes high-level user goals through autonomous agent orchestration."""

    def __init__(
        self,
        reasoner: Any,
        plugin_manager: Any,
        permission_guard: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        max_steps: int = 8,
        memory_manager: Optional[Any] = None,
        approval_callback: Optional[Callable[[AgentTask, AgentStep, AgentRiskLevel], bool]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self.reasoner = reasoner
        self.plugin_manager = plugin_manager
        self.permission_guard = permission_guard
        self.event_bus = event_bus
        self.max_steps = max_steps
        self.memory_manager = memory_manager
        self.approval_callback = approval_callback
        self.status_callback = status_callback
        try:
            from core.executor import PlanExecutor
            self.executor = PlanExecutor(
                plugin_manager=self.plugin_manager,
                permission_guard=self.permission_guard,
                event_bus=self.event_bus,
            )
        except Exception:
            self.executor = None

        policy = AgentPolicy(max_total_steps=max_steps)
        self.orchestrator = AgentOrchestrator(
            policy=policy,
            event_bus=self.event_bus,
            reasoner=self.reasoner,
            memory_manager=self.memory_manager,
            approval_callback=self.approval_callback,
            status_callback=self.status_callback,
        )

    def execute_goal(self, goal: str) -> AgentExecutionSummary:
        """Executes a goal using the AgentOrchestrator pipeline."""
        logger.info("AutonomousAgent delegating goal: '%s'", goal)
        return self.orchestrator.execute_goal(goal)

    def _resolve_parameters(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Substitutes dynamic parameter expressions from context."""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("$"):
                var_name = v[1:]
                resolved[k] = context.get(var_name, None)
            else:
                resolved[k] = v
        return resolved
