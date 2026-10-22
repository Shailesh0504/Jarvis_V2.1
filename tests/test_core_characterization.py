# tests/test_core_characterization.py
"""
Baseline Characterization & Behavioral Regression Test Suite for JarvisCore.
Captures exact runtime behavior across all input modes before and during modular extraction.
"""

import os
import time
import pytest
from unittest.mock import MagicMock, patch

os.environ["JARVIS_TEST_MODE"] = "1"
from core.app import JarvisCore
from core.state import SystemState
from core.interaction_gate import GateDecision, InteractionState
from core.laya import LayaDecision, LayaRoute


@pytest.fixture
def core():
    """Provides a fully initialized JarvisCore instance in test mode."""
    c = JarvisCore()
    c._process_lock = MagicMock()
    return c


def test_characterization_shutdown_command(core):
    """Verify shutdown command transitions state and returns farewell."""
    resp = core.process_input("exit", source="cli")
    assert any(w in resp.lower() for w in ("alvida", "goodbye", "shutting down", "milte hain"))
    assert core.state_machine.current_state == SystemState.SHUTDOWN


def test_characterization_fast_path_time(core):
    """Verify fast path time command returns deterministic answer without heavy NLP."""
    resp = core.process_input("what time is it", source="cli")
    assert resp is not None
    assert any(w in resp.lower() for w in ("time", ":", "am", "pm", "baje"))


def test_characterization_standalone_wake_word(core):
    """Verify standalone wake word prompts listening state."""
    mock_gate = MagicMock()
    mock_gate.evaluate.return_value = GateDecision(
        accepted=True,
        command="",
        reason="wake_word_standalone",
        state=InteractionState.LISTENING,
        is_standalone_wake=True,
        matched_variant="jarvis"
    )
    core.interaction_gate = mock_gate

    resp = core.process_input("jarvis", source="voice")
    assert resp == "Yes, I'm listening."


def test_characterization_stop_interruption(core):
    """Verify stop / interruption phrase stops session gracefully."""
    mock_gate = MagicMock()
    mock_gate.evaluate.return_value = GateDecision(
        accepted=True,
        command="stop listening",
        reason="stop_command",
        state=InteractionState.IDLE
    )
    core.interaction_gate = mock_gate

    resp = core.process_input("stop listening", source="voice")
    assert "ruk gaya" in resp


def test_characterization_laya_chat_route(core):
    """Verify conversational queries get answered politely."""
    resp = core.process_input("kaise ho", source="cli")
    assert resp is not None
    assert len(resp) > 3


def test_characterization_agent_goal_route(core):
    """Verify complex autonomous goals delegate to Agent Planner."""
    from core.laya import LayaDecision, LayaRoute
    core.laya_core.decide = MagicMock(return_value=LayaDecision(
        raw_text="run autonomous multi-step workflow",
        normalized_text="run autonomous multi-step workflow",
        laya_route=LayaRoute.AGENT_PLANNER,
        intent="agent_goal"
    ))

    mock_agent = MagicMock()
    mock_agent.execute_goal.return_value = MagicMock(
        final_answer="Autonomous multi-step workflow completed.",
        trace=[]
    )
    core.agent = mock_agent

    resp = core.process_input("run autonomous multi-step workflow", source="cli")
    assert "Autonomous multi-step workflow completed." in resp
    mock_agent.execute_goal.assert_called()
