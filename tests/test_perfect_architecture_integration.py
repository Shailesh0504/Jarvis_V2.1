# tests/test_perfect_architecture_integration.py
"""
Architectural Integration Test Suite for Jarvis V2.1.
Verifies the 6 key architectural enhancements:
1. FastPathEngine Dynamic Learning Bridge (Vocabulary, Preferences, Custom Aliases)
2. InteractionGate Multimodal Attention & Presence Gating
3. JarvisCore Tri-Bridge Dispatchers (_dispatch_fast_route, _dispatch_chat_route, _dispatch_agent_route)
4. LayaCore Authoritative Verification & Telemetry
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from core.execution.fast_path import FastPathEngine
from core.interaction_gate import InteractionGate, GateDecision, InteractionState
from core.laya import get_laya_core, LayaRoute, LayaDecision
from voice.wake_word import WakeWordMatchResult


def test_fast_path_dynamic_vocabulary_learning():
    """Verify FastPathEngine resolves dynamically learned vocabulary before matching."""
    mock_core = MagicMock()
    mock_core.dialog_manager = None
    mock_core._finalize_fast_turn.side_effect = lambda t, r, *args, **kwargs: r
    mock_learning = MagicMock()
    # Learned mapping: replaces "chotu browser" -> "chrome"
    mock_learning.resolve_vocabulary.side_effect = lambda t: t.replace("chotu browser", "chrome")
    mock_core.learning_manager = mock_learning
    mock_core.execution_strategies.launch_application_verified.return_value = MagicMock(
        success=True, data={"message": "Google Chrome open kar diya."}
    )

    engine = FastPathEngine(core=mock_core)
    mock_turn = MagicMock()
    mock_turn.raw_input = "open chotu browser"
    mock_turn.normalized_input = "open chotu browser"

    resp = engine.try_handle(
        raw_text=mock_turn.raw_input,
        normalized_input=mock_turn.normalized_input,
        turn=mock_turn,
        start_time=time.perf_counter(),
        tracker=None,
        source="cli"
    )

    assert resp is not None
    assert "Google Chrome" in resp or "Chrome" in resp
    mock_learning.resolve_vocabulary.assert_called()


def test_fast_path_user_preferences_resolution():
    """Verify FastPathEngine resolves user application preferences (e.g. browser -> brave)."""
    mock_core = MagicMock()
    mock_core.dialog_manager = None
    mock_core._finalize_fast_turn.side_effect = lambda t, r, *args, **kwargs: r
    mock_learning = MagicMock()
    mock_learning.resolve_vocabulary.side_effect = lambda t: t
    mock_learning.preferences.get.side_effect = lambda k: "brave" if k == "preferred_browser" else None
    mock_core.learning_manager = mock_learning
    mock_core.execution_strategies.launch_application_verified.return_value = MagicMock(
        success=True, data={"message": "Brave open kar diya."}
    )

    engine = FastPathEngine(core=mock_core)
    mock_turn = MagicMock()
    mock_turn.raw_input = "browser open karo"
    mock_turn.normalized_input = "browser open karo"

    resp = engine.try_handle(
        raw_text=mock_turn.raw_input,
        normalized_input=mock_turn.normalized_input,
        turn=mock_turn,
        start_time=time.perf_counter(),
        tracker=None,
        source="cli"
    )

    assert resp is not None
    assert "Brave" in resp


def test_fast_path_custom_alias_resolution():
    """Verify FastPathEngine resolves user-taught custom aliases."""
    mock_core = MagicMock()
    mock_core.dialog_manager = None
    mock_core.learning_manager = None
    mock_core._finalize_fast_turn.side_effect = lambda t, r, *args, **kwargs: r
    mock_core.execution_strategies.launch_application_verified.return_value = MagicMock(
        success=True, data={"message": "Spotify open kar diya."}
    )

    mock_alias_mgr = MagicMock()
    mock_alias_mgr.get_alias.return_value = {
        "alias": "my tunes",
        "target": "spotify",
        "action_type": "OPEN_APPLICATION"
    }

    with patch("core.alias_manager.get_alias_manager", return_value=mock_alias_mgr):
        engine = FastPathEngine(core=mock_core)
        mock_turn = MagicMock()
        mock_turn.raw_input = "launch my tunes"
        mock_turn.normalized_input = "launch my tunes"

        resp = engine.try_handle(
            raw_text=mock_turn.raw_input,
            normalized_input=mock_turn.normalized_input,
            turn=mock_turn,
            start_time=time.perf_counter(),
            tracker=None,
            source="cli"
        )

        assert resp is not None
        assert "Spotify" in resp


def test_interaction_gate_multimodal_attention_scoring():
    """Verify InteractionGate factors visual attention / presence into gating decision."""
    mock_wake = MagicMock()
    mock_wake.detect.return_value = WakeWordMatchResult(
        detected=True,
        cleaned_command="volume badao",
        matched_variant="jarvis",
        position="prefix",
        confidence=0.9
    )

    gate = InteractionGate(wake_detector=mock_wake)

    # 1. Attentive user (face present, high attention score)
    attentive_context = {"face_detected": True, "attention_score": 0.95}
    decision1 = gate.evaluate("jarvis volume badao", attention_context=attentive_context)
    assert decision1.accepted is True
    assert decision1.attention_score >= 0.9

    # 2. Distracted / looking away user (face not detected)
    unattentive_context = {"face_detected": False, "attention_score": 0.8}
    decision2 = gate.evaluate("jarvis volume badao", attention_context=unattentive_context)
    assert decision2.attention_score <= 0.5


def test_core_dispatch_fast_route_verified():
    """Verify JarvisCore._dispatch_fast_route executes and records verification."""
    from core.app import JarvisCore

    # Instantiate or mock core methods
    core = JarvisCore.__new__(JarvisCore)
    core.laya_core = get_laya_core()
    core.state_machine = MagicMock()
    core.conversation_manager = MagicMock()
    core.action_logger = MagicMock()
    core.memory_manager = MagicMock()
    core.event_bus = MagicMock()

    # FastPath returns immediate response
    core._try_fast_command_path = MagicMock(return_value="Current time is 10:30 AM.")

    mock_turn = MagicMock()
    mock_turn.turn_id = "test_turn_1"
    mock_turn.raw_input = "what time is it"
    mock_turn.normalized_input = "what time is it"
    mock_turn.metadata = {}

    laya_dec = LayaDecision(
        raw_text="what time is it",
        normalized_text="what time is it",
        laya_route=LayaRoute.FAST_ROUTER,
        intent="time"
    )

    resp = core._dispatch_fast_route(
        turn=mock_turn,
        laya_decision=laya_dec,
        start_time=time.perf_counter(),
        source="cli"
    )

    assert resp == "Current time is 10:30 AM."
    assert "laya_verification" in mock_turn.metadata
    assert mock_turn.metadata["laya_verification"]["verified"] is True
    core.conversation_manager.complete_turn.assert_called_once_with(mock_turn, resp)


def test_core_dispatch_chat_route_scoped():
    """Verify JarvisCore._dispatch_chat_route binds scoped context and memory."""
    from core.app import JarvisCore

    core = JarvisCore.__new__(JarvisCore)
    core.laya_core = get_laya_core()
    core.state_machine = MagicMock()
    core.conversation_manager = MagicMock()
    core.action_logger = MagicMock()
    core.memory_manager = MagicMock()
    core.event_bus = MagicMock()
    core.brain = MagicMock()
    core.brain.chat.return_value = "Main bilkul badhiya hoon, aap bataiye!"
    core._ensure_response = lambda r: r

    mock_turn = MagicMock()
    mock_turn.turn_id = "test_turn_2"
    mock_turn.raw_input = "kaise ho"
    mock_turn.normalized_input = "kaise ho"
    mock_turn.metadata = {}

    laya_dec = LayaDecision(
        raw_text="kaise ho",
        normalized_text="kaise ho",
        laya_route=LayaRoute.CHAT,
        intent="chat",
        context_scope="MINIMAL"
    )

    resp = core._dispatch_chat_route(
        turn=mock_turn,
        laya_decision=laya_dec,
        start_time=time.perf_counter(),
        source="cli"
    )

    assert "bilkul badhiya" in resp
    core.brain.chat.assert_called_once()
    core.conversation_manager.complete_turn.assert_called_once_with(mock_turn, resp)


def test_core_dispatch_agent_route():
    """Verify JarvisCore._dispatch_agent_route plans and traces goal execution."""
    from core.app import JarvisCore

    core = JarvisCore.__new__(JarvisCore)
    core.laya_core = get_laya_core()
    core.state_machine = MagicMock()
    core.conversation_manager = MagicMock()
    core.action_logger = MagicMock()
    core.memory_manager = MagicMock()
    core.event_bus = MagicMock()
    core._ensure_response = lambda r: r

    # Mock agent execution
    mock_agent = MagicMock()
    mock_step = MagicMock()
    mock_step.success = True
    mock_step.observation = "Report created"
    mock_step.error = None
    mock_summary = MagicMock(
        final_answer="Maine aapke liye daily briefing bana di hai.",
        trace=[mock_step]
    )
    mock_agent.execute_goal.return_value = mock_summary
    core.agent = mock_agent

    mock_turn = MagicMock()
    mock_turn.turn_id = "test_turn_3"
    mock_turn.raw_input = "create daily briefing report and save to desktop"
    mock_turn.normalized_input = "create daily briefing report and save to desktop"
    mock_turn.metadata = {}

    laya_dec = LayaDecision(
        raw_text=mock_turn.raw_input,
        normalized_text=mock_turn.normalized_input,
        laya_route=LayaRoute.AGENT_PLANNER,
        intent="complex_workflow"
    )

    resp = core._dispatch_agent_route(
        turn=mock_turn,
        laya_decision=laya_dec,
        start_time=time.perf_counter(),
        source="cli"
    )

    assert "daily briefing" in resp
    mock_agent.execute_goal.assert_called_once_with(mock_turn.normalized_input)
    core.memory_manager.record_interaction.assert_called_once()
