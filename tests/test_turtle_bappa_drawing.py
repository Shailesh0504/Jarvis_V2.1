# tests/test_turtle_bappa_drawing.py
"""
Unit and integration tests for Bappa Turtle Drawing capability (Feature #65).
Verifies script existence, conversational intent classification, knowledge engine disambiguation,
automation plugin action execution, and fast-path handling.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from plugins.automation.commands import ACTIONS
from plugins.automation.plugin import AutomationPlugin


def test_drawing_script_exists_and_importable():
    """Verifies that bappa_drawing.py exists and exports draw_bappa callable."""
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "plugins", "automation", "drawings", "bappa_drawing.py")
    )
    assert os.path.isfile(script_path), f"Drawing script missing at {script_path}"

    from plugins.automation.drawings.bappa_drawing import draw_bappa
    assert callable(draw_bappa)


def test_conversational_intent_action_command_variations():
    """Verifies that all variations of 'drawing bappa' resolve to ACTION_COMMAND."""
    test_phrases = [
        "drawing bappa",
        "draw bappa",
        "bappa drawing",
        "bappa ki drawing",
        "bappa draw karo",
        "bappa drawing banao",
        "drawing bappa banao",
        "draw ganpati",
        "draw ganpati bappa",
        "ganpati bappa drawing",
        "draw ganesha",
        "ganesha drawing",
        "bappa ki drawing banao",
        "bappa ki drawing dikhao",
    ]
    for phrase in test_phrases:
        res = ConversationalIntentClassifier.classify(phrase)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND, f"Failed on '{phrase}': {res.intent_type}"
        assert res.is_executable is True, f"Expected executable for '{phrase}'"
        assert res.action_type == "draw", f"Expected action_type 'draw' for '{phrase}'"
        assert res.target == "bappa", f"Expected target 'bappa' for '{phrase}'"


def test_conversational_intent_capability_question():
    """Verifies that capability questions about drawing Bappa are NOT executed."""
    cap_phrases = [
        "kya tum bappa ki drawing bana sakte ho?",
        "kya tum bappa draw kar sakte ho?",
        "can you draw bappa?",
        "tum bappa ki drawing bana sakte ho kya?",
    ]
    for phrase in cap_phrases:
        res = ConversationalIntentClassifier.classify(phrase)
        assert res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION, f"Failed on '{phrase}': {res.intent_type}"
        assert res.is_executable is False, f"Expected non-executable for '{phrase}'"
        assert res.natural_response is not None
        assert "bappa" in res.natural_response.lower() or "drawing" in res.natural_response.lower()


def test_knowledge_router_disambiguation():
    """Verifies that KnowledgeRouter does NOT hijack 'drawing bappa' as a festival query."""
    from core.knowledge import get_knowledge_engine
    ke = get_knowledge_engine()

    # Drawing commands must NOT be treated as knowledge candidates
    assert ke.is_knowledge_candidate("drawing bappa") is False
    assert ke.is_knowledge_candidate("draw bappa") is False
    assert ke.is_knowledge_candidate("bappa drawing") is False

    # Actual festival questions must still be recognized as knowledge candidates
    assert ke.is_knowledge_candidate("Ganesh Chaturthi kab hai?") is True
    assert ke.is_knowledge_candidate("Diwali kab hai?") is True


def test_automation_plugin_manifest_and_action():
    """Verifies that AutomationPlugin manifests and executes draw_bappa action."""
    action_names = [a.name for a in ACTIONS]
    assert "draw_bappa" in action_names

    plugin = AutomationPlugin()
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        result = plugin.execute("draw_bappa", {})
        assert result.success is True
        assert result.data["action"] == "draw_bappa"
        assert result.data["pid"] == 9999
        assert "Bappa ki drawing" in result.data["message"]
        mock_popen.assert_called_once()


def test_fast_path_bappa_drawing():
    """Verifies that JarvisCore fast-path handles 'drawing bappa' without latency."""
    from core.app import JarvisCore
    core = JarvisCore.__new__(JarvisCore)
    core.plugin_manager = MagicMock()

    turn = MagicMock()
    tracker = MagicMock()

    with patch("subprocess.Popen") as mock_popen, patch.object(core, "_finalize_fast_turn", return_value="Bappa ki drawing bana raha hoon, Boss."):
        resp = core._try_fast_command_path(
            raw_text="drawing bappa",
            normalized_input="drawing bappa",
            turn=turn,
            start_time=0.0,
            tracker=tracker,
            source="cli"
        )
        assert resp == "Bappa ki drawing bana raha hoon, Boss."
        mock_popen.assert_called_once()
