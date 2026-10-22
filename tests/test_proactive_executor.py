# tests/test_proactive_executor.py
"""
Unit tests for Phase 7: Confirmation & Verified Action Execution Engine.
Validates natural conversational affirmation and negation recognition,
safe action dispatch through existing controllers, and closed-loop feedback.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.intelligence import (
    ProactiveActionExecutor,
    ProactiveSuggestion,
    SuggestionManager,
    SuggestionState,
    SuggestionUrgency,
)


class TestAffirmationAndNegationParsing:
    """Tests for NLP parsing of affirmations and negations in English, Hindi, and Hinglish."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "ha", "haan", "haa", "yes", "yeah", "yep", "sure", "ok", "okay",
            "karo", "kar do", "kardo", "chala do", "chalado", "khol do",
            "play karo", "bilkul", "thik hai", "sahi hai", "do it"
        ]
    )
    def test_affirmation_phrases(self, phrase):
        assert ProactiveActionExecutor.is_affirmation(phrase) is True
        assert ProactiveActionExecutor.is_negation(phrase) is False

    @pytest.mark.parametrize(
        "phrase",
        [
            "nahi", "na", "no", "nope", "nah", "cancel", "mat karo",
            "rehne do", "rehnedo", "abhi nahi", "baad mein", "cancel karo",
            "nevermind", "not now"
        ]
    )
    def test_negation_phrases(self, phrase):
        assert ProactiveActionExecutor.is_negation(phrase) is True
        assert ProactiveActionExecutor.is_affirmation(phrase) is False


class TestProactiveUtteranceHandling:
    """Tests for utterance dispatch, feedback recording, and execution."""

    def test_no_pending_suggestion_returns_none(self):
        manager = SuggestionManager()
        executor = ProactiveActionExecutor(suggestion_manager=manager)
        assert executor.handle_user_utterance("ha") is None
        assert executor.handle_user_utterance("kuch bhi") is None

    def test_confirmed_media_suggestion_executes_and_accepts(self):
        manager = SuggestionManager()
        mock_core = MagicMock()
        mock_speaker = MagicMock()
        executor = ProactiveActionExecutor(
            suggestion_manager=manager,
            app_core=mock_core,
            speaker=mock_speaker
        )

        sug = ProactiveSuggestion(
            suggestion_id="s_media",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Arijit Singh"
        )
        manager.register_presented(sug)

        res = executor.handle_user_utterance("haan chala do")
        assert res is not None
        assert res["handled"] is True
        assert res["accepted"] is True
        assert "Arijit Singh play kar raha hoon, Boss." in res["message"]
        assert sug.state == SuggestionState.ACCEPTED
        assert mock_core.process_input.called
        assert "Arijit Singh" in mock_core.process_input.call_args[0][0]
        assert mock_speaker.speak.called

    def test_rejected_suggestion_records_backoff(self):
        manager = SuggestionManager()
        mock_speaker = MagicMock()
        executor = ProactiveActionExecutor(
            suggestion_manager=manager,
            speaker=mock_speaker
        )

        sug = ProactiveSuggestion(
            suggestion_id="s_app",
            intent="LAUNCH_APP",
            action="open_app",
            target="youtube"
        )
        manager.register_presented(sug)

        res = executor.handle_user_utterance("nahi rehne do")
        assert res is not None
        assert res["handled"] is True
        assert res["accepted"] is False
        assert "Theek hai, Boss." in res["message"]
        assert sug.state == SuggestionState.REJECTED

        # Per-pattern or rejection backoff must be active in manager
        allowed, reason = manager.can_present_suggestion(sug)
        assert allowed is False

    def test_unrelated_command_marks_ignored_and_yields(self):
        manager = SuggestionManager()
        executor = ProactiveActionExecutor(suggestion_manager=manager)

        sug = ProactiveSuggestion(
            suggestion_id="s_vol",
            intent="ADJUST_VOLUME",
            action="set_volume",
            target="30"
        )
        manager.register_presented(sug)

        # User ignores volume suggestion and asks to open calculator
        res = executor.handle_user_utterance("calculator kholo")
        assert res is None
        assert sug.state == SuggestionState.IGNORED
        # Pending suggestion cleared
        assert manager.get_pending_suggestion() is None

    def test_volume_action_dispatch(self):
        manager = SuggestionManager()
        executor = ProactiveActionExecutor(suggestion_manager=manager)

        sug = ProactiveSuggestion(
            suggestion_id="s_vol_action",
            intent="ADJUST_VOLUME",
            action="set_volume",
            target="25"
        )
        manager.register_presented(sug)

        with patch("plugins.audio.volume_controller.set_system_volume") as mock_set_vol:
            mock_set_vol.return_value = {"success": True}
            res = executor.handle_user_utterance("ha kar do")
            assert res is not None
            assert res["handled"] is True
            assert res["accepted"] is True
            assert mock_set_vol.called
            assert mock_set_vol.call_args[0][0] == 25
            assert "Volume 25% set kar diya hai, Boss." in res["message"]
