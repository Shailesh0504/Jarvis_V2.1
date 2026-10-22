# tests/test_request_state_machine.py
import pytest
from core.state import RequestLifecycleState, RequestStateMachine


def test_request_state_machine_valid_happy_path():
    sm = RequestStateMachine(request_id="req-1")
    assert sm.current_state == RequestLifecycleState.IDLE

    assert sm.transition_to(RequestLifecycleState.LISTENING, "speech started")
    assert sm.transition_to(RequestLifecycleState.UNDERSTANDING, "transcription complete")
    assert sm.transition_to(RequestLifecycleState.PLANNING, "intent parsed")
    assert sm.transition_to(RequestLifecycleState.EXECUTING, "plan generated")
    assert sm.transition_to(RequestLifecycleState.VERIFYING, "action spawned")
    assert sm.transition_to(RequestLifecycleState.COMPLETED, "physical state verified")
    assert sm.transition_to(RequestLifecycleState.RESPONDING, "response formatting")
    assert sm.transition_to(RequestLifecycleState.IDLE, "turn finished")

    history = sm.get_history()
    assert len(history) == 9
    assert history[-1]["to"] == "IDLE"


def test_request_state_machine_fast_path_bypass():
    sm = RequestStateMachine(request_id="req-fast")
    assert sm.transition_to(RequestLifecycleState.UNDERSTANDING)
    # Direct bypass from understanding to executing for <10ms fast path
    assert sm.transition_to(RequestLifecycleState.EXECUTING, "fast path direct execute")
    assert sm.transition_to(RequestLifecycleState.VERIFYING)
    assert sm.transition_to(RequestLifecycleState.COMPLETED)
    assert sm.transition_to(RequestLifecycleState.RESPONDING)
    assert sm.transition_to(RequestLifecycleState.IDLE)


def test_request_state_machine_recovery_path():
    sm = RequestStateMachine(request_id="req-rec")
    sm.transition_to(RequestLifecycleState.UNDERSTANDING)
    sm.transition_to(RequestLifecycleState.PLANNING)
    sm.transition_to(RequestLifecycleState.EXECUTING)
    sm.transition_to(RequestLifecycleState.VERIFYING)
    # Verification failure -> recovery
    assert sm.transition_to(RequestLifecycleState.RECOVERING, "verification failed, retrying")
    assert sm.transition_to(RequestLifecycleState.EXECUTING, "retry with alternate strategy")
    assert sm.transition_to(RequestLifecycleState.VERIFYING)
    assert sm.transition_to(RequestLifecycleState.COMPLETED)
    assert sm.transition_to(RequestLifecycleState.RESPONDING)
    assert sm.transition_to(RequestLifecycleState.IDLE)


def test_request_state_machine_illegal_transition_blocked():
    sm = RequestStateMachine(request_id="req-bad")
    # Illegal jump from IDLE to COMPLETED
    assert not sm.transition_to(RequestLifecycleState.COMPLETED)
    assert sm.current_state == RequestLifecycleState.IDLE
