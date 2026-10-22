# tests/test_phase_3_b1_contract.py
"""
Unit and Contract Verification Suite for Phase 3.0-B1.
Validates:
1. TurnOutcomeStatus precedence: AMBIGUOUS (clarification/PARTIAL) > FAILED > VERIFIED > UNVERIFIED.
2. OutcomeAdapter normalization preserves requested/executed semantic action (never outcome.status).
3. TurnContext.execution_outcome is optional and defaults to None.
4. Gated Anti-Noise Filter for Learning: Routine verified actions do not pollute Experience system.
5. Telemetry emission and structure.
6. Zero side-effects on existing classes and methods.
"""

from unittest.mock import MagicMock
import pytest

from core.context import TurnContext, TurnOutcome, TurnOutcomeStatus
from core.execution.adapter import OutcomeAdapter
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.outcome_hook import ExecutionOutcomeHook
from core.target_engine import ActionOutcome, TargetCandidate, TargetKind


class TestPhase3B1Contracts:
    """Test suite ensuring strict compliance with Phase 3.0-B1 specifications."""

    def test_turn_context_execution_outcome_defaults_to_none(self):
        """Invariant 3: TurnContext.execution_outcome must remain strictly optional and default to None."""
        turn = TurnContext(raw_input="hello world", source="cli")
        assert hasattr(turn, "execution_outcome")
        assert turn.execution_outcome is None
        assert turn.status == "COMPLETED"
        assert isinstance(turn.execution_results, list)

    def test_ambiguous_precedence_over_failed(self):
        """Invariant 1: needs_clarification / PARTIAL must resolve to AMBIGUOUS before FAILED."""
        # Case A: needs_clarification=True even when success=False
        res_clarify = ExecutionResult(
            success=False,
            status=ExecutionState.PARTIAL,
            requested_action="close_window",
            executed_action="close_window",
            error="Multiple matching windows",
            reason="needs_clarification",
            data={"needs_clarification": True}
        )
        status_a = ExecutionOutcomeHook.resolve_status(res_clarify)
        assert status_a == TurnOutcomeStatus.AMBIGUOUS

        # Case B: ActionOutcome with needs_clarification=True and success=False
        action_outcome = ActionOutcome(
            success=False,
            message="2 matches found. Kaunsa close karun?",
            needs_clarification=True,
            candidates=[
                TargetCandidate(kind=TargetKind.WINDOW, identity="Chrome 1"),
                TargetCandidate(kind=TargetKind.WINDOW, identity="Chrome 2"),
            ],
            status="failed"
        )
        adapted = OutcomeAdapter.from_action_outcome(
            action_outcome,
            requested_action="close_window",
            target="chrome"
        )
        status_b = ExecutionOutcomeHook.resolve_status(adapted)
        assert status_b == TurnOutcomeStatus.AMBIGUOUS

    def test_outcome_adapter_preserves_executed_action(self):
        """Invariant 2: executed_action must preserve the actual action, never outcome.status."""
        action_outcome = ActionOutcome(
            success=True,
            message="Chrome window minimize kar diya",
            verified=True,
            status="completed"  # Lifecycle string, NOT the action
        )
        adapted = OutcomeAdapter.from_action_outcome(
            action_outcome,
            requested_action="minimize_window",
            target="chrome"
        )
        assert adapted.requested_action == "minimize_window"
        assert adapted.executed_action == "minimize_window"  # Not "completed"
        assert adapted.status == ExecutionState.SUCCESS
        assert adapted.verification_result is not None
        assert adapted.verification_result.verified is True

    def test_failed_status_resolution(self):
        """Failed action without clarification must resolve to FAILED."""
        res_failed = ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="launch_app",
            executed_action="launch_app",
            error="Binary not found"
        )
        assert ExecutionOutcomeHook.resolve_status(res_failed) == TurnOutcomeStatus.FAILED

    def test_verified_status_resolution(self):
        """Action with verified=True verification_result must resolve to VERIFIED."""
        v_res = VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="process_running",
            expected="excel.exe",
            actual="excel.exe"
        )
        res_verified = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            verification_result=v_res
        )
        assert ExecutionOutcomeHook.resolve_status(res_verified) == TurnOutcomeStatus.VERIFIED

    def test_unverified_status_resolution(self):
        """Action successful at API level but lacking physical state verification resolves to UNVERIFIED."""
        res_unverified = ExecutionResult(
            success=True,
            status=ExecutionState.UNVERIFIED,
            requested_action="send_keys",
            executed_action="send_keys",
            verification_result=None
        )
        assert ExecutionOutcomeHook.resolve_status(res_unverified) == TurnOutcomeStatus.UNVERIFIED

    def test_learning_anti_noise_filter(self):
        """Invariant 4: Routine VERIFIED actions must NOT automatically write experience records."""
        # 1. Routine single app launch (verified) -> NOT eligible
        routine_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            strategy_used="primary",
            retry_count=0,
            action_type="application",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="process")
        )
        assert ExecutionOutcomeHook.is_learning_eligible(routine_res, TurnOutcomeStatus.VERIFIED) is False

        # 2. Multi-step desktop workflow (verified) -> ELIGIBLE
        workflow_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="desktop_workflow",
            executed_action="desktop_workflow",
            strategy_used="primary",
            action_type="desktop_workflow",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="flow")
        )
        assert ExecutionOutcomeHook.is_learning_eligible(workflow_res, TurnOutcomeStatus.VERIFIED) is True

        # 3. Action that required self-healing retries -> ELIGIBLE
        recovered_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="open_folder",
            executed_action="open_folder",
            strategy_used="win32_shell_fallback",
            retry_count=2,
            action_type="folder",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="hwnd")
        )
        assert ExecutionOutcomeHook.is_learning_eligible(recovered_res, TurnOutcomeStatus.VERIFIED) is True

        # 4. Action that failed with diagnostics -> ELIGIBLE for failure learning
        failed_res = ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="open_file",
            executed_action="open_file",
            error="AccessDeniedException",
            action_type="file"
        )
        assert ExecutionOutcomeHook.is_learning_eligible(failed_res, TurnOutcomeStatus.FAILED) is True

    def test_process_outcome_wiring_and_telemetry(self):
        """Tests ExecutionOutcomeHook.process_outcome sets turn.execution_outcome and emits telemetry."""
        mock_core = MagicMock()
        mock_core.event_bus = MagicMock()
        mock_core.learning_manager = MagicMock()
        mock_core.last_execution_result = None

        turn = TurnContext(raw_input="excel kholo", source="cli")
        v_res = VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="process_running")
        exec_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            target="excel",
            action_type="application",
            verification_result=v_res
        )

        outcome = ExecutionOutcomeHook.process_outcome(mock_core, turn, exec_res)

        assert outcome.status == TurnOutcomeStatus.VERIFIED
        assert turn.execution_outcome is outcome
        assert mock_core.last_execution_result is exec_res
        assert mock_core.event_bus.emit.called
        event_name, event_data = mock_core.event_bus.emit.call_args[0]
        assert event_name == "execution.outcome"
        assert event_data["status"] == "VERIFIED"

        # Because routine action, experience_system was not spammed
        assert not mock_core.learning_manager.experience_system.record_task_success.called
