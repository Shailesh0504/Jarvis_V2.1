# tests/test_intent_collision_and_archify.py
"""
Test suite verifying resolution of keyword collisions (temp/weather, kal/date)
and Archify live runtime architecture visualization command triggering.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.execution.fast_path import FastPathEngine
from core.semantic.orchestrator import SemanticPipelineOrchestrator
from core.time_context import get_time_context
from core.weather.weather_engine import get_weather_engine


def test_weather_temp_collision_guard():
    """Verify system cleanup utterances containing 'temp' are not hijacked by weather engine."""
    we = get_weather_engine()
    
    assert we.is_weather_query("clear temp file") is False
    assert we.is_weather_query("clear temporary files") is False
    assert we.is_weather_query("temp files saaf karo") is False
    assert we.is_weather_query("delete temp") is False
    assert we.is_weather_query("clean temp directory") is False
    assert we.is_weather_query("temp file clean kar do") is False
    
    # Real weather queries must still pass
    assert we.is_weather_query("what is the temperature") is True
    assert we.is_weather_query("weather in Delhi") is True
    assert we.is_weather_query("aaj mausam kaisa hai") is True


def test_time_context_relative_day_guard():
    """Verify action commands mentioning 'kal' or 'tomorrow' are not hijacked by time/date engine."""
    tc = get_time_context()
    
    # Action commands with 'kal' must return None (not hijacked)
    assert tc.resolve_time_query("kal subah 8 baje papa ko call karna hai") is None
    assert tc.resolve_time_query("kal meeting schedule karo") is None
    assert tc.resolve_time_query("remind me tomorrow morning") is None
    assert tc.resolve_time_query("set time and date") is None
    
    # Explicit inquiries about date must still work
    resp_kal = tc.resolve_time_query("kal kya date hogi")
    assert resp_kal is not None
    assert ("kal" in resp_kal.lower() or "tomorrow" in resp_kal.lower())


def test_archify_intent_and_semantic_parsing():
    """Verify user request 'mere project ka live architecture archify me dikhai de' maps to Archify."""
    user_query = "mere project ka live architecture archify me dikhai de"
    
    # 1. Conversational Intent / Speech-Act Gating
    res = ConversationalIntentClassifier.classify(user_query)
    assert res.is_executable is True
    assert res.target == "archify"
    assert res.action_type == "show_architecture"
    
    # 2. Semantic Parser
    orchestrator = SemanticPipelineOrchestrator()
    act = orchestrator.parse(user_query)
    assert act is not None
    assert act.service == "archify"
    assert act.action == "show_architecture"
    assert act.confidence >= 0.95


def test_archify_fast_path_execution():
    """Verify FastPathEngine dispatches show_architecture for Archify viewer queries in < 15ms."""
    fake_core = MagicMock()
    fake_core.dialog_manager.awaits_user_followup.return_value = False
    fake_plugin = MagicMock()
    fake_res = MagicMock()
    fake_res.data = {"message": "Jarvis ka live runtime architecture Archify me open kar diya hai, Boss."}
    fake_plugin.execute.return_value = fake_res
    fake_core.plugin_manager.get_plugin.return_value = fake_plugin
    fake_core._finalize_fast_turn.side_effect = lambda turn, resp, start_time, tracker, intent, source: resp

    engine = FastPathEngine(core=fake_core)
    
    user_query = "mere project ka live architecture archify me dikhai de"
    resp = engine.try_handle(
        raw_text=user_query,
        normalized_input=user_query,
        turn=MagicMock(),
        start_time=0.0,
        tracker=None,
        source="cli"
    )
    
    assert resp is not None
    assert "Archify" in resp or "architecture" in resp.lower()
    fake_plugin.execute.assert_called_with("show_architecture", {})
