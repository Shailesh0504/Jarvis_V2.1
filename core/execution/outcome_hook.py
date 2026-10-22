# core/execution/outcome_hook.py
"""
Central Execution Outcome and Feedback Hook for Jarvis V2.
Authoritative boundary for:
1. TurnOutcome creation and status resolution with strict precedence.
2. TurnContext attachment (TurnContext.execution_outcome).
3. Telemetry emission via EventBus.
4. Gated Experience Learning ingestion (anti-noise filtering for routine actions).

Invariants:
- AMBIGUOUS precedence: needs_clarification / PARTIAL -> AMBIGUOUS before FAILED evaluation.
- Preserves executed_action without modification.
- Routine VERIFIED actions must NOT automatically create learning experience records
  unless explicitly marked eligible (e.g. multi-step workflow, self-healed retry).
- Operates standalone without breaking existing callers or changing return signatures.
"""

import logging
import time
from typing import Any, List, Optional
import uuid

from core.context import TurnContext, TurnOutcome, TurnOutcomeStatus
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult

logger = logging.getLogger("jarvis.execution.outcome_hook")


class ExecutionOutcomeHook:
    """
    Authoritative post-execution hook orchestrating outcome evaluation,
    TurnContext persistence, telemetry, and gated experience learning.
    """

    @classmethod
    def resolve_status(cls, execution_result: ExecutionResult) -> TurnOutcomeStatus:
        """
        Resolves TurnOutcomeStatus with strict precedence rules:
        1. AMBIGUOUS: needs_clarification is True OR status == ExecutionState.PARTIAL.
        2. FAILED: status == ExecutionState.FAILED OR success is False.
        3. VERIFIED: verification_result is present and verified is True.
        4. UNVERIFIED: Default for successful API completion without confirmed physical state change.
        """
        # 1. AMBIGUOUS precedence check
        v_res = execution_result.verification_result
        details = getattr(v_res, "details", {}) if v_res and isinstance(v_res.details, dict) else {}
        data = getattr(execution_result, "data", {}) if isinstance(execution_result.data, dict) else {}

        needs_clarification = (
            bool(getattr(execution_result, "needs_clarification", False))
            or bool(details.get("needs_clarification", False))
            or bool(data.get("needs_clarification", False))
            or execution_result.status == ExecutionState.PARTIAL
            or execution_result.reason == "needs_clarification"
        )

        if needs_clarification:
            return TurnOutcomeStatus.AMBIGUOUS

        # 2. FAILED precedence check
        if execution_result.status == ExecutionState.FAILED or not execution_result.success:
            return TurnOutcomeStatus.FAILED

        # 3. VERIFIED precedence check
        if v_res and getattr(v_res, "verified", False):
            return TurnOutcomeStatus.VERIFIED

        # 4. UNVERIFIED fallback
        return TurnOutcomeStatus.UNVERIFIED

    @classmethod
    def is_learning_eligible(
        cls,
        execution_result: ExecutionResult,
        status: TurnOutcomeStatus,
        explicit_eligible: Optional[bool] = None
    ) -> bool:
        """
        Gated Anti-Noise Filter for Learning Layer:
        Routine successful commands (single app launch, volume set, time check)
        must NOT write experience noise to the database.

        Learning is eligible only if:
        - explicit_eligible is True, OR
        - Action failed (diagnostics and failure recovery recording), OR
        - Action was recovered via retry (retry_count > 0 or strategy != 'primary'), OR
        - Multi-step workflow or agent goal (action_type in ('desktop_workflow', 'agent_goal', 'multi_action')).
        """
        if explicit_eligible is not None:
            return explicit_eligible

        # Failures with error diagnostics are eligible for mistake analysis
        if status == TurnOutcomeStatus.FAILED:
            return bool(execution_result.error or execution_result.reason)

        # Ambiguous clarifications are handled by dialog/confirmation, not experience logging
        if status == TurnOutcomeStatus.AMBIGUOUS:
            return False

        # If verified, only complex, recovered, or multi-step tasks are eligible
        if status == TurnOutcomeStatus.VERIFIED:
            if execution_result.retry_count > 0:
                return True
            if execution_result.strategy_used not in ("primary", "", None):
                return True
            if execution_result.action_type in ("desktop_workflow", "agent_goal", "multi_action"):
                return True
            if execution_result.diagnostics:
                return True
            # Routine deterministic success is filtered out
            return False

        return False

    @classmethod
    def process_outcome(
        cls,
        core: Any,
        turn: Optional[TurnContext],
        execution_result: ExecutionResult,
        source: str = "user",
        is_eligible_for_learning: Optional[bool] = None
    ) -> TurnOutcome:
        """
        Processes an ExecutionResult through the authoritative closed loop:
        1. Resolves canonical TurnOutcomeStatus.
        2. Constructs TurnOutcome.
        3. Attaches to TurnContext.execution_outcome (strictly optional).
        4. Updates core.last_execution_result.
        5. Emits telemetry event via EventBus.
        6. Selectively informs LearningManager / ExperienceLearningSystem.
        """
        # 1. Resolve status
        status = cls.resolve_status(execution_result)
        v_res = execution_result.verification_result

        turn_id = turn.turn_id if turn else str(uuid.uuid4())
        error_msg = execution_result.error or (v_res.error if v_res else None)

        turn_outcome = TurnOutcome(
            turn_id=turn_id,
            status=status,
            execution_result=execution_result,
            verification_result=v_res,
            error=error_msg,
            diagnostics=list(execution_result.diagnostics),
            timestamp=time.time()
        )

        # 2. Attach to TurnContext (Optional field)
        if turn is not None:
            turn.execution_outcome = turn_outcome
            if execution_result not in turn.execution_results:
                turn.execution_results.append(execution_result)

        # 3. Update core tracking
        if core is not None and hasattr(core, "last_execution_result"):
            core.last_execution_result = execution_result

        # 4. Telemetry Emission
        if core is not None and hasattr(core, "event_bus") and core.event_bus:
            try:
                core.event_bus.emit("execution.outcome", turn_outcome.to_dict())
            except Exception as tel_err:
                logger.debug("Failed to emit outcome telemetry: %s", tel_err)

        # 5. Gated Experience Learning
        if core is not None and hasattr(core, "learning_manager") and core.learning_manager:
            lm = core.learning_manager
            exp_sys = getattr(lm, "experience_system", None)
            if exp_sys and cls.is_learning_eligible(execution_result, status, explicit_eligible=is_eligible_for_learning):
                target_ident = execution_result.target or execution_result.requested_action
                try:
                    if status == TurnOutcomeStatus.VERIFIED:
                        exp_sys.record_task_success(
                            goal=execution_result.requested_action,
                            steps=[{"action": execution_result.executed_action, "target": target_ident}],
                            category=execution_result.action_type or "general"
                        )
                    elif status == TurnOutcomeStatus.FAILED:
                        exp_sys.record_task_failure(
                            goal=execution_result.requested_action,
                            failed_step={"action": execution_result.executed_action, "target": target_ident},
                            error_msg=error_msg or "Execution verification failed",
                            diagnosis=f"Outcome status: {status.value}",
                            category=execution_result.action_type or "general"
                        )
                except Exception as exp_err:
                    logger.debug("Failed to record experience in hook: %s", exp_err)

        return turn_outcome
