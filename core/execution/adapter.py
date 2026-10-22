# core/execution/adapter.py
"""
Non-destructive normalization adapter for Jarvis V2 execution outcomes.
Converts diverse outcome representations (ActionOutcome, StepExecutionResult,
AgentExecutionSummary, dict, etc.) into canonical ExecutionResult instances.

Invariants:
1. Preserve existing ActionOutcome, ExecutionResult, and VerificationResult classes without mutation.
2. executed_action must preserve the actual requested/executed semantic action, never outcome.status.
3. needs_clarification / PARTIAL status must be preserved for AMBIGUOUS precedence.
"""

import logging
from typing import Any, Optional

from core.execution.models import ExecutionResult, ExecutionState, VerificationResult

logger = logging.getLogger("jarvis.execution.adapter")


class OutcomeAdapter:
    """
    Non-destructive normalization adapter that standardizes diverse subsystem
    outcomes into a canonical ExecutionResult.
    """

    @classmethod
    def from_action_outcome(
        cls,
        outcome: Any,
        requested_action: str = "",
        target: str = "",
        action_type: str = "general"
    ) -> ExecutionResult:
        """
        Normalizes a core.target_engine.ActionOutcome into a canonical ExecutionResult.
        Preserves requested/executed semantic action and disambiguation state.
        """
        if isinstance(outcome, ExecutionResult):
            return outcome

        if outcome is None or not hasattr(outcome, "success"):
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=requested_action,
                executed_action=requested_action,
                error="Invalid outcome object provided",
                target=target,
                action_type=action_type
            )

        is_success = bool(outcome.success)
        is_verified = bool(getattr(outcome, "verified", False))
        needs_clarification = bool(getattr(outcome, "needs_clarification", False))

        # Determine ExecutionState
        if needs_clarification:
            status = ExecutionState.PARTIAL
        elif is_verified:
            status = ExecutionState.SUCCESS
        elif is_success:
            status = ExecutionState.UNVERIFIED
        else:
            status = ExecutionState.FAILED

        # Extract details/candidates if present
        details = {}
        raw_candidates = getattr(outcome, "candidates", None)
        if raw_candidates:
            details["candidates"] = [
                getattr(c, "identity", str(c)) for c in raw_candidates
            ]
        if needs_clarification:
            details["needs_clarification"] = True

        outcome_msg = getattr(outcome, "message", "") or ""
        v_check = getattr(outcome, "verification", "target_engine_check") or "target_engine_check"

        v_result = VerificationResult(
            verified=is_verified,
            state=status,
            check_type=str(v_check),
            expected=target or getattr(outcome, "url", "") or requested_action,
            actual=target if is_verified else None,
            details=details,
            message=outcome_msg,
            error=None if is_success else (outcome_msg or "Action failed")
        )

        # Invariant 2: executed_action MUST preserve the actual semantic action, NEVER outcome.status
        actual_executed_action = requested_action or "target_action"

        data_dict = {}
        if getattr(outcome, "url", None):
            data_dict["url"] = outcome.url
        if getattr(outcome, "candidates", None):
            data_dict["candidates"] = outcome.candidates
        if needs_clarification:
            data_dict["needs_clarification"] = True

        return ExecutionResult(
            success=is_success,
            status=status,
            requested_action=requested_action,
            executed_action=actual_executed_action,
            verification_result=v_result,
            error=None if is_success else (outcome_msg or "Action failed"),
            reason="needs_clarification" if needs_clarification else (None if is_success else outcome_msg),
            data=data_dict,
            target=target or getattr(outcome, "url", ""),
            action_type=action_type
        )

    @classmethod
    def from_plugin_result(
        cls,
        result: Any,
        requested_action: str = "",
        target: str = "",
        action_type: str = "plugin"
    ) -> ExecutionResult:
        """
        Normalizes a plugin execution result (e.g. PluginResult or dict) into an ExecutionResult.

        Invariant (B3-A): A plugin returning success=True WITHOUT a real VerificationResult
        must produce ExecutionState.UNVERIFIED, not SUCCESS/VERIFIED.
        Physical verification is NOT claimed from a simple API return value.
        Only a caller-supplied VerificationResult with verified=True may elevate status to VERIFIED.
        """
        if isinstance(result, ExecutionResult):
            return result

        if isinstance(result, dict):
            is_success = bool(result.get("success", True))
            msg = result.get("message", "") or result.get("error", "")
            err = result.get("error") if not is_success else None
            data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
        else:
            is_success = bool(getattr(result, "success", True))
            msg = getattr(result, "message", "") or (
                getattr(result, "data", {}).get("message", "") if isinstance(getattr(result, "data", None), dict) else ""
            )
            err = getattr(result, "error", None)
            data = getattr(result, "data", {}) if isinstance(getattr(result, "data", None), dict) else {}

        # B3-A Invariant: passthrough only a genuine VerificationResult supplied by the plugin.
        # Auto-synthesize an UNVERIFIED sentinel when none is provided — success=True from a
        # plugin's own return value does NOT constitute physical verification.
        v_result = getattr(result, "verification_result", None)
        has_real_verification = isinstance(v_result, VerificationResult)
        if not has_real_verification:
            # Synthesise UNVERIFIED sentinel — verified=False regardless of is_success.
            v_result = VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED if is_success else ExecutionState.FAILED,
                check_type="plugin_return_check",
                expected=target or requested_action,
                actual=None,
                message=msg,
                error=err
            )

        # Derive canonical ExecutionState.
        # Real VerificationResult with verified=True → SUCCESS.
        # Synthesised sentinel (no real verification) for a successful plugin → UNVERIFIED.
        # Failed plugin → FAILED.
        if has_real_verification and getattr(v_result, "verified", False):
            canonical_status = ExecutionState.SUCCESS
        elif is_success:
            canonical_status = ExecutionState.UNVERIFIED
        else:
            canonical_status = ExecutionState.FAILED

        return ExecutionResult(
            success=is_success,
            status=canonical_status,
            requested_action=requested_action,
            executed_action=requested_action,
            verification_result=v_result,
            error=err,
            reason=err or (msg if not is_success else None),
            data=data,
            target=target,
            action_type=action_type
        )

    @classmethod
    def from_agent_summary(
        cls,
        summary: Any,
        goal: str = "",
        action_type: str = "agent_goal"
    ) -> ExecutionResult:
        """
        Normalizes an AgentExecutionSummary from AutonomousAgent into an ExecutionResult.
        """
        if isinstance(summary, ExecutionResult):
            return summary

        is_success = bool(getattr(summary, "success", False))
        final_answer = getattr(summary, "final_answer", "") or ""
        error_msg = getattr(summary, "error", None)

        v_result = VerificationResult(
            verified=is_success,
            state=ExecutionState.SUCCESS if is_success else ExecutionState.FAILED,
            check_type="agent_goal_verification",
            expected=goal,
            actual=final_answer if is_success else None,
            message=final_answer,
            error=error_msg
        )

        return ExecutionResult(
            success=is_success,
            status=ExecutionState.SUCCESS if is_success else ExecutionState.FAILED,
            requested_action=goal,
            executed_action="execute_goal",
            verification_result=v_result,
            error=error_msg,
            reason=error_msg or ("Goal accomplished" if is_success else "Goal execution failed"),
            data={"summary": summary} if summary else {},
            target=goal,
            action_type=action_type
        )
