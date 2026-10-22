# tests/test_recovery_and_cancellation.py
import pytest
from core.cancellation import CancellationManager, CancellationToken
from core.contracts import RecoveryAction
from core.execution.models import ActionPlan, ExecutionResult, ExecutionState, VerificationResult
from core.recovery import RecoveryManager


def test_recovery_manager_transient_retry():
    rm = RecoveryManager(max_retries=2)
    plan = ActionPlan(action="open", target="chrome", plan_id="p-1")
    exec_res = ExecutionResult(
        success=False,
        status=ExecutionState.FAILED,
        requested_action="open",
        executed_action="open",
        error="Process spawn timeout, busy"
    )
    decision = rm.evaluate_failure(plan, exec_res, retry_count=0)
    assert decision.action == RecoveryAction.RETRY
    assert decision.retry_count == 1


def test_recovery_manager_alternate_strategy_failover():
    rm = RecoveryManager(max_retries=2)
    plan = ActionPlan(action="open", target="chrome", plan_id="p-2")
    exec_res = ExecutionResult(
        success=False,
        status=ExecutionState.FAILED,
        requested_action="open",
        executed_action="open",
        strategy_used="win32_api",
        error="Win32 API execution failed"
    )
    decision = rm.evaluate_failure(plan, exec_res, retry_count=0)
    assert decision.action == RecoveryAction.RETRY_ALTERNATE
    assert decision.target_strategy == "process_spawner"


def test_recovery_manager_max_retry_abort():
    rm = RecoveryManager(max_retries=2)
    plan = ActionPlan(action="open", target="chrome", plan_id="p-3")
    exec_res = ExecutionResult(
        success=False,
        status=ExecutionState.FAILED,
        requested_action="open",
        executed_action="open",
        error="Fatal error"
    )
    decision = rm.evaluate_failure(plan, exec_res, retry_count=2)
    assert decision.action == RecoveryAction.ABORT


def test_cancellation_manager_token_lifecycle():
    cm = CancellationManager()
    token = cm.create_token("req-123")
    assert not token.is_cancelled

    called = []
    token.register_callback(lambda reason: called.append(reason))

    cancelled = cm.cancel("req-123", reason="User clicked stop")
    assert cancelled
    assert token.is_cancelled
    assert token.reason == "User clicked stop"
    assert len(called) == 1
    assert called[0] == "User clicked stop"


def test_cancellation_manager_intent_detection():
    cm = CancellationManager()
    assert cm.is_cancellation_intent("stop")
    assert cm.is_cancellation_intent("cancel")
    assert cm.is_cancellation_intent("ruk jao")
    assert cm.is_cancellation_intent("jarvis stop")
    assert not cm.is_cancellation_intent("open chrome")
    assert not cm.is_cancellation_intent("excel mein report prepare karo")
