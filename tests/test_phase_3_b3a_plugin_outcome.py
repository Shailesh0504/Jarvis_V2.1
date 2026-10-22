# tests/test_phase_3_b3a_plugin_outcome.py
"""
Phase 3.0-B3-A: Plugin/Fallback Outcome Infrastructure Tests.

Covers:
1. Normalization correctness (PluginResult / dict -> ExecutionResult)
2. UNVERIFIED invariant: success=True without real VerificationResult -> UNVERIFIED, not VERIFIED
3. Real VerificationResult passthrough -> VERIFIED when verified=True
4. Failed plugin normalization -> FAILED
5. Telemetry emission via EventBus (exactly once per outcome)
6. TurnContext attachment (execution_outcome set)
7. Learning eligibility gate: routine plugin success must NOT create learning noise
8. Hook is non-fatal when core components are absent
9. resolve_status AMBIGUOUS precedence check (B1 invariant preserved)
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.execution.adapter import OutcomeAdapter
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.outcome_hook import ExecutionOutcomeHook
from core.context import TurnContext, TurnOutcome, TurnOutcomeStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_plugin_result(success=True, message="", error=None, data=None,
                        verification_result=None):
    """Minimal object mimicking a PluginResult."""
    r = SimpleNamespace(
        success=success,
        message=message,
        error=error,
        data=data or {},
        verification_result=verification_result,
    )
    return r


def _make_turn():
    turn = TurnContext(
        turn_id=str(uuid.uuid4()),
        raw_input="test command",
        normalized_input="test command",
    )
    return turn


def _make_core(emit_raises=False):
    """Minimal core stub with event_bus and learning_manager."""
    core = MagicMock()
    core.last_execution_result = None
    if emit_raises:
        core.event_bus.emit.side_effect = RuntimeError("bus error")
    else:
        core.event_bus.emit.return_value = None
    # No experience system by default keeps learning gate closed
    core.learning_manager.experience_system = None
    return core


# ---------------------------------------------------------------------------
# Section 1: OutcomeAdapter.from_plugin_result normalization
# ---------------------------------------------------------------------------

class TestFromPluginResultNormalization:

    def test_success_without_verification_yields_unverified(self):
        """B3-A Core Invariant: success=True without VerificationResult -> UNVERIFIED."""
        res = _make_plugin_result(success=True, message="Done")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="play_music", target="youtube")
        assert adapted.success is True
        assert adapted.status == ExecutionState.UNVERIFIED, (
            f"Expected UNVERIFIED, got {adapted.status}"
        )
        assert adapted.verification_result is not None
        assert adapted.verification_result.verified is False
        assert adapted.verification_result.state == ExecutionState.UNVERIFIED

    def test_failed_plugin_yields_failed(self):
        """Failed plugin (success=False) -> FAILED status."""
        res = _make_plugin_result(success=False, error="Network error")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="browse", target="google.com")
        assert adapted.success is False
        assert adapted.status == ExecutionState.FAILED
        assert adapted.verification_result.verified is False
        assert adapted.verification_result.state == ExecutionState.FAILED
        assert adapted.error == "Network error"

    def test_real_verification_passthrough_verified(self):
        """A plugin supplying VerificationResult(verified=True) must yield SUCCESS."""
        real_vr = VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="physical_ui_check",
            expected="youtube",
            actual="youtube",
        )
        res = _make_plugin_result(success=True, message="OK", verification_result=real_vr)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="open_youtube")
        assert adapted.status == ExecutionState.SUCCESS
        assert adapted.verification_result is real_vr
        assert adapted.verification_result.verified is True

    def test_real_verification_passthrough_unverified_flag(self):
        """A plugin supplying VerificationResult(verified=False) must yield UNVERIFIED."""
        real_vr = VerificationResult(
            verified=False,
            state=ExecutionState.UNVERIFIED,
            check_type="physical_ui_check",
            expected="spotify",
            actual=None,
        )
        res = _make_plugin_result(success=True, verification_result=real_vr)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="open_spotify")
        assert adapted.status == ExecutionState.UNVERIFIED
        assert adapted.verification_result is real_vr

    def test_dict_success_normalization(self):
        """Dict plugin result (success=True) -> UNVERIFIED."""
        d = {"success": True, "message": "Volume set", "data": {"level": 50}}
        adapted = OutcomeAdapter.from_plugin_result(d, requested_action="set_volume", target="50")
        assert adapted.success is True
        assert adapted.status == ExecutionState.UNVERIFIED
        assert adapted.verification_result.verified is False

    def test_dict_failure_normalization(self):
        """Dict plugin result (success=False) -> FAILED with error preserved."""
        d = {"success": False, "error": "VLC not running"}
        adapted = OutcomeAdapter.from_plugin_result(d, requested_action="vlc.pause")
        assert adapted.success is False
        assert adapted.status == ExecutionState.FAILED
        assert adapted.error == "VLC not running"

    def test_execution_result_passthrough(self):
        """Already-adapted ExecutionResult must be returned unchanged (idempotent)."""
        er = ExecutionResult(
            success=True,
            status=ExecutionState.UNVERIFIED,
            requested_action="play",
            executed_action="play",
        )
        result = OutcomeAdapter.from_plugin_result(er)
        assert result is er

    def test_requested_action_preserved_not_status(self):
        """executed_action must never be populated from outcome.status (B1 invariant)."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="launch_spotify")
        assert adapted.executed_action == "launch_spotify"
        assert "SUCCESS" not in adapted.executed_action
        assert "UNVERIFIED" not in adapted.executed_action

    def test_action_type_preserved(self):
        """action_type='plugin' must flow through to ExecutionResult."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="test", action_type="plugin")
        assert adapted.action_type == "plugin"


# ---------------------------------------------------------------------------
# Section 2: resolve_status AMBIGUOUS precedence (B1 invariant must hold in B3-A)
# ---------------------------------------------------------------------------

class TestResolveStatusPrecedence:

    def test_ambiguous_precedence_over_failed(self):
        """AMBIGUOUS must be resolved before FAILED: PARTIAL status -> AMBIGUOUS."""
        er = ExecutionResult(
            success=False,
            status=ExecutionState.PARTIAL,
            requested_action="play",
            executed_action="play",
            reason="needs_clarification",
        )
        status = ExecutionOutcomeHook.resolve_status(er)
        assert status == TurnOutcomeStatus.AMBIGUOUS, (
            f"Expected AMBIGUOUS (needs_clarification+PARTIAL), got {status}"
        )

    def test_verified_from_real_vr(self):
        """VERIFIED only when verified=True in the VerificationResult."""
        vr = VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="test")
        er = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="open_chrome",
            executed_action="open_chrome",
            verification_result=vr,
        )
        status = ExecutionOutcomeHook.resolve_status(er)
        assert status == TurnOutcomeStatus.VERIFIED

    def test_unverified_without_real_vr(self):
        """UNVERIFIED when plugin success=True but no verified VerificationResult."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="open_app")
        status = ExecutionOutcomeHook.resolve_status(adapted)
        assert status == TurnOutcomeStatus.UNVERIFIED

    def test_failed_for_failed_plugin(self):
        """FAILED for success=False plugin result."""
        res = _make_plugin_result(success=False, error="Plugin crash")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="do_thing")
        status = ExecutionOutcomeHook.resolve_status(adapted)
        assert status == TurnOutcomeStatus.FAILED


# ---------------------------------------------------------------------------
# Section 3: ExecutionOutcomeHook.process_outcome integration
# ---------------------------------------------------------------------------

class TestProcessOutcome:

    def test_turn_outcome_returned_for_success(self):
        """process_outcome must return a TurnOutcome."""
        res = _make_plugin_result(success=True, message="Done")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="youtube.search_and_play")
        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert isinstance(outcome, TurnOutcome)
        assert outcome.status == TurnOutcomeStatus.UNVERIFIED

    def test_turn_context_execution_outcome_attached(self):
        """TurnContext.execution_outcome must be set after process_outcome."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="browser.open")
        core = _make_core()
        turn = _make_turn()
        assert turn.execution_outcome is None
        ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert turn.execution_outcome is not None
        assert isinstance(turn.execution_outcome, TurnOutcome)

    def test_telemetry_emitted_exactly_once(self):
        """EventBus.emit('execution.outcome') must fire exactly once per call."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="vlc.play")
        core = _make_core()
        turn = _make_turn()
        ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        emit_calls = [c for c in core.event_bus.emit.call_args_list
                      if c.args and c.args[0] == "execution.outcome"]
        assert len(emit_calls) == 1, f"Expected 1 telemetry emission, got {len(emit_calls)}"

    def test_telemetry_emitted_exactly_once_on_failure(self):
        """Telemetry must also fire exactly once for failed plugin results."""
        res = _make_plugin_result(success=False, error="Timeout")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="system.shutdown")
        core = _make_core()
        turn = _make_turn()
        ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        emit_calls = [c for c in core.event_bus.emit.call_args_list
                      if c.args and c.args[0] == "execution.outcome"]
        assert len(emit_calls) == 1

    def test_failed_outcome_status_is_failed(self):
        """process_outcome with failed plugin must produce FAILED TurnOutcome."""
        res = _make_plugin_result(success=False, error="Crash")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="excel.open")
        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.FAILED

    def test_core_last_execution_result_updated(self):
        """core.last_execution_result must be updated to the adapted ExecutionResult."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="media.play")
        core = _make_core()
        turn = _make_turn()
        ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert core.last_execution_result is adapted

    def test_hook_non_fatal_when_event_bus_raises(self):
        """A failing event_bus.emit must not propagate or crash the hook."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="test.action")
        core = _make_core(emit_raises=True)
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert isinstance(outcome, TurnOutcome)

    def test_hook_non_fatal_with_none_core(self):
        """process_outcome must function even if core=None."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="fallback.action")
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(None, turn, adapted, source="user")
        assert isinstance(outcome, TurnOutcome)
        assert turn.execution_outcome is outcome

    def test_hook_non_fatal_with_none_turn(self):
        """process_outcome with turn=None must still return a TurnOutcome."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="no_turn_action")
        core = _make_core()
        outcome = ExecutionOutcomeHook.process_outcome(core, None, adapted, source="user")
        assert isinstance(outcome, TurnOutcome)


# ---------------------------------------------------------------------------
# Section 4: Learning eligibility gate
# ---------------------------------------------------------------------------

class TestLearningEligibilityGate:

    def test_routine_plugin_success_not_eligible(self):
        """Routine UNVERIFIED plugin success must NOT be learning eligible."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(
            res, requested_action="youtube.search_and_play", action_type="plugin"
        )
        eligible = ExecutionOutcomeHook.is_learning_eligible(adapted, TurnOutcomeStatus.UNVERIFIED)
        assert eligible is False

    def test_plugin_failure_eligible_when_has_error(self):
        """Plugin failure with error IS eligible (diagnostic value)."""
        res = _make_plugin_result(success=False, error="VLC not responding")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="vlc.pause")
        eligible = ExecutionOutcomeHook.is_learning_eligible(adapted, TurnOutcomeStatus.FAILED)
        assert eligible is True

    def test_explicit_eligible_true_overrides_filter(self):
        """explicit_eligible=True must bypass the anti-noise filter."""
        res = _make_plugin_result(success=True)
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="routine.action")
        eligible = ExecutionOutcomeHook.is_learning_eligible(
            adapted, TurnOutcomeStatus.UNVERIFIED, explicit_eligible=True
        )
        assert eligible is True

    def test_explicit_eligible_false_overrides_filter(self):
        """explicit_eligible=False blocks even failure-eligible outcomes."""
        res = _make_plugin_result(success=False, error="Error")
        adapted = OutcomeAdapter.from_plugin_result(res, requested_action="action")
        eligible = ExecutionOutcomeHook.is_learning_eligible(
            adapted, TurnOutcomeStatus.FAILED, explicit_eligible=False
        )
        assert eligible is False

    def test_ambiguous_outcome_never_eligible(self):
        """AMBIGUOUS outcomes must never go to learning."""
        er = ExecutionResult(
            success=False,
            status=ExecutionState.PARTIAL,
            requested_action="play",
            executed_action="play",
            reason="needs_clarification",
        )
        eligible = ExecutionOutcomeHook.is_learning_eligible(er, TurnOutcomeStatus.AMBIGUOUS)
        assert eligible is False

    def test_plugin_workflow_action_type_eligible(self):
        """action_type='desktop_workflow' is eligible when VERIFIED."""
        vr = VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="test")
        er = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="workflow.step",
            executed_action="workflow.step",
            action_type="desktop_workflow",
            verification_result=vr,
        )
        eligible = ExecutionOutcomeHook.is_learning_eligible(er, TurnOutcomeStatus.VERIFIED)
        assert eligible is True


# ---------------------------------------------------------------------------
# Section 5: End-to-end normalization + hook integration
# ---------------------------------------------------------------------------

class TestEndToEndPluginPath:

    def test_success_pipeline_full(self):
        """Full: PluginResult -> OutcomeAdapter -> ExecutionOutcomeHook -> TurnOutcome."""
        plugin_res = _make_plugin_result(success=True, message="YouTube opened")
        adapted = OutcomeAdapter.from_plugin_result(
            plugin_res,
            requested_action="youtube.search_and_play",
            target="{'query': 'arijit singh'}",
            action_type="plugin",
        )
        assert adapted.status == ExecutionState.UNVERIFIED
        assert adapted.success is True

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")

        assert outcome.status == TurnOutcomeStatus.UNVERIFIED
        assert turn.execution_outcome is outcome
        assert core.last_execution_result is adapted
        assert core.event_bus.emit.called

    def test_failure_pipeline_full(self):
        """Full failure pipeline: PluginResult(success=False) -> FAILED TurnOutcome."""
        plugin_res = _make_plugin_result(success=False, error="Browser not found")
        adapted = OutcomeAdapter.from_plugin_result(
            plugin_res,
            requested_action="browser.open",
            target="chrome",
            action_type="plugin",
        )
        assert adapted.status == ExecutionState.FAILED

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")

        assert outcome.status == TurnOutcomeStatus.FAILED
        assert turn.execution_outcome is outcome

    def test_dict_plugin_result_full_pipeline(self):
        """Dict-form plugin result flows through the full pipeline correctly."""
        plugin_dict = {"success": True, "message": "Volume set to 80%", "data": {"level": 80}}
        adapted = OutcomeAdapter.from_plugin_result(
            plugin_dict,
            requested_action="audio.set_volume",
            target="80",
            action_type="plugin",
        )
        assert adapted.status == ExecutionState.UNVERIFIED

        core = _make_core()
        turn = _make_turn()
        outcome = ExecutionOutcomeHook.process_outcome(core, turn, adapted, source="user")
        assert outcome.status == TurnOutcomeStatus.UNVERIFIED
