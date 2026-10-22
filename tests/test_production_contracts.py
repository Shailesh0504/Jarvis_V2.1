# tests/test_production_contracts.py
import pytest
from core.contracts import (
    RequestSource,
    UserRequest,
    ConversationFrame,
    IntentResult,
    Target,
    ExecutionContext,
    ExecutionStep,
    ExecutionPlan,
    RecoveryAction,
    RecoveryDecision,
    ResponsePayload,
    AgentTask,
    AgentTaskStep,
    MemoryRecord,
    LearningCandidate,
    Event,
)
from core.context import TurnOutcomeStatus
from core.execution.models import ExecutionState, VerificationResult, ExecutionResult


def test_user_request_contract():
    req = UserRequest(raw_input="open chrome", source=RequestSource.VOICE, user_id="admin")
    assert req.raw_input == "open chrome"
    assert req.source == RequestSource.VOICE
    assert req.request_id is not None
    d = req.to_dict()
    assert d["raw_input"] == "open chrome"
    assert d["source"] == "voice"


def test_intent_result_contract():
    res = IntentResult(
        intent_name="app.open",
        confidence=0.98,
        domain="system",
        speech_act="ACTION_COMMAND",
        slots={"app_name": "chrome"}
    )
    assert res.intent_name == "app.open"
    assert res.speech_act == "ACTION_COMMAND"
    d = res.to_dict()
    assert d["slots"]["app_name"] == "chrome"


def test_target_contract():
    tgt = Target(name="chrome", target_type="application", identifier="chrome.exe", hwnd=12345, pid=6789)
    assert tgt.name == "chrome"
    assert tgt.hwnd == 12345
    d = tgt.to_dict()
    assert d["pid"] == 6789


def test_execution_plan_and_step():
    step = ExecutionStep(action="open", parameters={"target": "notepad"})
    plan = ExecutionPlan(goal="launch notepad", steps=[step])
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "open"
    d = plan.to_dict()
    assert d["goal"] == "launch notepad"


def test_recovery_decision_contract():
    decision = RecoveryDecision(
        action=RecoveryAction.RETRY_ALTERNATE,
        reason="Win32 spawn timed out",
        target_strategy="process_spawner",
        retry_count=1,
        max_retries=2
    )
    assert decision.action == RecoveryAction.RETRY_ALTERNATE
    d = decision.to_dict()
    assert d["action"] == "RETRY_ALTERNATE"
    assert d["retry_count"] == 1


def test_response_payload_contract():
    payload = ResponsePayload(
        text="Chrome open kar diya.",
        spoken_text="Chrome open ho gaya.",
        status=TurnOutcomeStatus.VERIFIED
    )
    assert payload.text == "Chrome open kar diya."
    assert payload.status == TurnOutcomeStatus.VERIFIED
    d = payload.to_dict()
    assert d["spoken_text"] == "Chrome open ho gaya."
    assert d["status"] == "VERIFIED"
