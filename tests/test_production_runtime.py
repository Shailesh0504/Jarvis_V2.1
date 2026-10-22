# tests/test_production_runtime.py
import pytest
from core.app import JarvisCore
from core.contracts import RequestSource, UserRequest
from core.context import TurnOutcomeStatus
from core.runtime import JarvisRuntime
from core.state import RequestLifecycleState


def test_runtime_initialized_in_core():
    core = JarvisCore()
    assert hasattr(core, "runtime")
    assert isinstance(core.runtime, JarvisRuntime)
    assert hasattr(core, "capability_policy")
    assert hasattr(core, "recovery_manager")
    assert hasattr(core, "cancellation_manager")
    assert hasattr(core, "health_monitor")


def test_runtime_standalone_execution():
    runtime = JarvisRuntime()
    payload = runtime.execute_turn("hello world", source=RequestSource.CLI)
    assert payload.text is not None
    assert payload.status == TurnOutcomeStatus.VERIFIED
    assert runtime.current_state == RequestLifecycleState.IDLE


def test_runtime_cancellation_execution():
    runtime = JarvisRuntime()
    payload = runtime.execute_turn("stop", source=RequestSource.VOICE)
    assert "cancel" in payload.text.lower()
    assert payload.status == TurnOutcomeStatus.VERIFIED
    assert runtime.current_state == RequestLifecycleState.IDLE
