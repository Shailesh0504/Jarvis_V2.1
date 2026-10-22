# tests/test_multi_turn_conversation_state.py
"""
Comprehensive tests for multi-turn conversation state understanding:
TURN N + ACTIVE QUESTION + PENDING GOAL + MISSING SLOT + TURN N+1 ANSWER.

Verifies that Jarvis interprets user utterances within the conversation state context
before generic intent routing begins.
"""

import os
import shutil
import pytest
from unittest.mock import MagicMock

from core.context import RuntimeContext, TurnContext, TaskContext
from core.dialog_manager import DialogManager, WorkflowLock
from core.speech_understanding import SpeechUnderstandingEngine, InputQualityEvaluator, InputQuality
from core.app import JarvisCore
from main import create_jarvis


@pytest.fixture
def jarvis_instance(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "state_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_STATE_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


class TestContextStateFields:
    """Verifies TurnContext and TaskContext fields for Turn N state tracking."""

    def test_turn_context_fields(self):
        tc = TurnContext(
            raw_input="movie chalao",
            normalized_input="movie chalao",
            active_question="Kaunsi movie play karun, Boss?",
            pending_goal="MEDIA_PLAY",
            missing_slots=["media_target"],
        )
        assert tc.active_question == "Kaunsi movie play karun, Boss?"
        assert tc.pending_goal == "MEDIA_PLAY"
        assert tc.missing_slots == ["media_target"]

    def test_task_context_lifecycle(self):
        task = TaskContext(
            workflow="MEDIA_PLAY",
            active_question="Kaunsi movie play karun?",
            pending_goal="MEDIA_PLAY",
            missing_slots=["media_target"],
        )
        assert task.active_question == "Kaunsi movie play karun?"
        assert task.pending_goal == "MEDIA_PLAY"
        assert task.missing_slots == ["media_target"]

        task.clear()
        assert task.active_question is None
        assert task.pending_goal is None
        assert task.missing_slots == []


class TestSpeechUnderstandingWithActiveDialog:
    """Verifies that short tokens are preserved when active dialog is pending."""

    def test_short_token_marked_clean_when_active_dialog_pending(self):
        evaluator = InputQualityEvaluator()

        # Without active dialog, short non-dictionary tokens are dropped as INCOMPLETE_FRAGMENT
        q_normal, _, _ = evaluator.evaluate_quality("Thor", "Thor", active_dialog_pending=False)
        assert q_normal == InputQuality.INCOMPLETE_FRAGMENT

        # With active dialog pending (Turn N+1 answer), they are accepted as CLEAN
        q_pending, _, _ = evaluator.evaluate_quality("Thor", "Thor", active_dialog_pending=True)
        assert q_pending == InputQuality.CLEAN

        q_num, _, _ = evaluator.evaluate_quality("12", "12", active_dialog_pending=True)
        assert q_num == InputQuality.CLEAN

    def test_speech_understanding_engine_preserves_short_answer(self):
        engine = SpeechUnderstandingEngine()
        result = engine.process_speech_input("16", active_dialog_pending=True)
        assert result.cleaned_input == "16"
        assert result.input_quality == InputQuality.CLEAN


class TestDialogManagerMultiTurnState:
    """Unit tests for DialogManager Turn N+1 interpretation."""

    def test_set_pending_goal_and_awaits_followup(self):
        dm = DialogManager()
        assert dm.awaits_user_followup() is False

        dm.set_pending_goal(
            pending_goal="MEDIA_PLAY",
            active_question="Kaunsi movie play karun, Boss?",
            missing_slots=["media_target"],
            turn_n=TurnContext(raw_input="movie chalao"),
            language="hi",
        )
        assert dm.awaits_user_followup() is True
        assert dm.has_active_lock() is True

        lock = dm.active_lock
        assert lock.pending_goal == "MEDIA_PLAY"
        assert lock.active_question == "Kaunsi movie play karun, Boss?"
        assert lock.missing_slots == ["media_target"]
        assert lock.turn_n["raw_input"] == "movie chalao"

    def test_interpret_turn_n_plus_1_slot_filling(self):
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="PASSWORD_GENERATE",
            active_question="Kitne characters ka?",
            missing_slots=["length"],
            turn_n=TurnContext(raw_input="password banao"),
            language="hi",
        )

        mock_core = MagicMock()
        handled, response = dm.interpret_turn_n_plus_1("16", mock_core)
        assert handled is True
        assert "16" in response
        assert dm.has_active_lock() is False

    def test_interpret_turn_n_plus_1_cancellation(self):
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="PASSWORD_GENERATE",
            active_question="Kitne characters ka?",
            missing_slots=["length"],
            turn_n=TurnContext(raw_input="password banao"),
            language="hi",
        )

        mock_core = MagicMock()
        handled, response = dm.interpret_turn_n_plus_1("nahi rehne do", mock_core)
        assert handled is True
        assert any(w in response.lower() for w in ["cancel", "radd", "chhod", "rehne"])
        assert dm.has_active_lock() is False

    def test_topic_switch_breaks_workflow_lock(self):
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="PASSWORD_GENERATE",
            active_question="Kitne characters ka?",
            missing_slots=["length"],
            turn_n=TurnContext(raw_input="password banao"),
            language="hi",
        )

        mock_core = MagicMock()
        handled, _ = dm.interpret_turn_n_plus_1("laptop lock kar do", mock_core)
        # Should NOT consume the turn as slot filling, but release lock to allow router to lock laptop
        assert handled is False
        assert dm.has_active_lock() is False


class TestEndToEndMultiTurnIntegration:
    """End-to-end integration tests using full Jarvis pipeline."""

    def test_e2e_media_slot_filling_flow(self, jarvis_instance):
        """
        Turn N: 'Movie chalao' -> Active question + Missing slot 'media_target'
        Turn N+1: 'Inception' -> Interpreted as media_target -> Launches VLC Inception
        """
        # Turn N
        resp1 = jarvis_instance.process_input("Movie chalao")
        assert "Kaunsi movie" in resp1
        assert jarvis_instance.dialog_manager.awaits_user_followup() is True

        # Turn N+1
        resp2 = jarvis_instance.process_input("Inception")
        assert jarvis_instance.dialog_manager.has_active_lock() is False
        assert "inception" in resp2.lower() or "vlc" in resp2.lower()

    def test_e2e_password_slot_filling_flow(self, jarvis_instance):
        """
        Turn N: 'Ek password banao' -> Active question + Missing slot 'length'
        Turn N+1: '16' -> Interpreted as length -> Generates 16-character password
        """
        # Turn N
        resp1 = jarvis_instance.process_input("Ek password banao")
        assert "Kitne characters ka?" in resp1
        assert jarvis_instance.dialog_manager.awaits_user_followup() is True

        # Turn N+1
        resp2 = jarvis_instance.process_input("16")
        assert jarvis_instance.dialog_manager.has_active_lock() is False
        assert "16" in resp2
        assert any(w in resp2.lower() for w in ["clipboard", "copy"])

    def test_e2e_excel_multi_turn_cancellation(self, jarvis_instance):
        """
        Turn N: 'Excel file kholo' -> Active question asking for filename/selection
        Turn N+1: 'Rehne do, mat kholo' -> Cancels pending goal cleanly
        """
        # Turn N
        resp1 = jarvis_instance.process_input("Excel file kholo")
        assert jarvis_instance.dialog_manager.awaits_user_followup() is True

        # Turn N+1
        resp2 = jarvis_instance.process_input("Rehne do, mat kholo")
        assert jarvis_instance.dialog_manager.awaits_user_followup() is False
        assert any(w in resp2.lower() for w in ["theek", "cancel", "rehne do", "radd"])

    def test_e2e_topic_switch_during_pending_dialog(self, jarvis_instance):
        """
        Turn N: 'Movie chalao' -> Active Question: 'Kaunsi movie play karun, Boss?'
        Turn N+1: User switches context entirely: 'System time batao'
        Jarvis should abort the pending movie goal and answer the time request.
        """
        # Turn N
        resp1 = jarvis_instance.process_input("Movie chalao")
        assert "Kaunsi movie" in resp1
        assert jarvis_instance.dialog_manager.awaits_user_followup() is True

        # Turn N+1: Complete topic switch
        resp2 = jarvis_instance.process_input("time batao")
        assert jarvis_instance.dialog_manager.has_active_lock() is False
        assert any(w in resp2.lower() for w in ["samay", "time", ":", "baje"])
