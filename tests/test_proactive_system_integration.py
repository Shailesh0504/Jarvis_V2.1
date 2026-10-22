# tests/test_proactive_system_integration.py
"""
End-to-End System Integration tests for the complete Proactive Intelligence System.
Validates the coordinated pipeline: observation -> memory -> pattern mining ->
opportunistic decisions -> cooldowns -> conversational confirmation -> execution -> adaptation.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.intelligence import (
    AdaptivePreferenceLearner,
    PatternLearningEngine,
    PatternRecord,
    PatternType,
    ProactiveActionExecutor,
    ProactiveIntelligenceCoordinator,
    ProactiveSuggestion,
    SuggestionManager,
    SuggestionState,
    SuggestionUrgency,
)
from core.observer.models import ActivityEvent, ActivityImportance, ActivityType
from main import create_jarvis


class TestCoordinatorLifecycle:
    """Tests for starting and stopping the coordinator and its underlying threads."""

    def test_lifecycle_start_and_stop(self):
        coord = ProactiveIntelligenceCoordinator(
            config={"poll_interval_sec": 0.1, "min_suggestion_interval_sec": 1.0}
        )
        assert coord.is_running is False
        assert coord.observer.is_running is False

        coord.start()
        assert coord.is_running is True
        assert coord.observer.is_running is True

        coord.stop()
        assert coord.is_running is False
        assert coord.observer.is_running is False

    def test_maintenance_loop_execution(self):
        """Verifies periodic maintenance loop executes decay and prune_history with retention_days."""
        coord = ProactiveIntelligenceCoordinator(
            config={"memory_retention_days": 5}
        )
        coord.memory = MagicMock()
        coord.preference_learner = MagicMock()

        # Simulate one wait timeout cycle then stop
        coord._stop_event.wait = MagicMock(side_effect=[False, True])
        coord._stop_event.is_set = MagicMock(side_effect=[False, False, True])

        coord._maintenance_loop()

        coord.preference_learner.apply_temporal_decay.assert_called_once()
        coord.memory.prune_history.assert_called_once_with(retention_days=5)


class TestEndToEndPipeline:
    """Tests for the complete pipeline from activity observation to user confirmation and execution."""

    def test_end_to_end_media_suggestion_and_affirmation(self):
        mock_core = MagicMock()
        mock_speaker = MagicMock()

        coord = ProactiveIntelligenceCoordinator(
            app_core=mock_core,
            speaker=mock_speaker,
            config={
                "min_suggestion_interval_sec": 1.0,
                "min_confidence_threshold": 0.70
            }
        )

        # 1. Establish a strong habit: User plays Arijit Singh 3 times
        t0 = 1000.0
        for i in range(3):
            ev_play = ActivityEvent(
                event_type=ActivityType.VIDEO_PLAYED,
                application="brave",
                website="youtube",
                content_title="Arijit Singh - Kesariya Audio",
                timestamp=t0 + (i * 100.0)
            )
            coord.pattern_engine.observe_event(ev_play)

        pat = coord.pattern_engine.get_pattern("media_artist:arijit_singh")
        assert pat is not None
        assert pat.confidence >= 0.70

        # 2. User opens YouTube home surface -> triggers proactive evaluation
        ev_open = ActivityEvent(
            event_type=ActivityType.WEBSITE_OPENED,
            application="brave",
            website="youtube",
            window_title="YouTube - Home",
            timestamp=t0 + 500.0
        )
        coord._on_activity_observed(ev_open)

        # Proactive suggestion should now be proposed and pending confirmation
        pending = coord.suggestion_manager.get_pending_suggestion()
        assert pending is not None
        assert pending.intent == "MEDIA_PLAY_ARTIST"
        assert "Arijit Singh" in pending.target
        assert mock_speaker.speak.called

        # 3. User affirms verbally: "haan chala do"
        resp = coord.executor.handle_user_utterance("haan chala do")
        assert resp is not None
        assert resp["handled"] is True
        assert resp["accepted"] is True
        assert "Arijit Singh play kar raha hoon, Boss." in resp["message"]

        # 4. Action executed through core
        assert mock_core.process_input.called
        assert "Arijit Singh" in mock_core.process_input.call_args[0][0]

        # 5. Suggestion state accepted and pending cleared
        assert pending.state == SuggestionState.ACCEPTED
        assert coord.suggestion_manager.get_pending_suggestion() is None

    def test_end_to_end_rejection_activates_backoff(self):
        coord = ProactiveIntelligenceCoordinator(
            config={"min_suggestion_interval_sec": 1.0}
        )

        sug = ProactiveSuggestion(
            suggestion_id="s_app_test",
            intent="LAUNCH_APP",
            action="open_app",
            target="discord",
            metadata={"pattern_key": "trans:chrome->discord"}
        )
        coord.suggestion_manager.register_presented(sug)

        # User rejects verbally: "nahi rehne do"
        resp = coord.executor.handle_user_utterance("nahi rehne do")
        assert resp is not None
        assert resp["handled"] is True
        assert resp["accepted"] is False
        assert "Theek hai, Boss." in resp["message"]
        assert sug.state == SuggestionState.REJECTED

        # Subsequent presentation of the same pattern is blocked by rejection backoff
        allowed, reason = coord.suggestion_manager.can_present_suggestion(sug)
        assert allowed is False
        assert "rejected" in reason.lower()


class TestJarvisCoreIntegration:
    """Tests for JarvisCore wiring and input interception."""

    def test_jarvis_core_intercepts_proactive_confirmation(self):
        core = create_jarvis()
        mock_executor = MagicMock()
        mock_coord = MagicMock()
        mock_coord.executor = mock_executor
        core.proactive_coordinator = mock_coord

        # When an affirmative confirmation is given
        mock_executor.handle_user_utterance.return_value = {
            "handled": True,
            "accepted": True,
            "message": "Arijit Singh play kar raha hoon, Boss."
        }

        resp = core.process_input("haan chala do", source="cli")
        assert "Arijit Singh play kar raha hoon" in resp
        assert mock_executor.handle_user_utterance.called

    def test_jarvis_core_passes_through_unrelated_command(self):
        core = create_jarvis()
        mock_executor = MagicMock()
        mock_coord = MagicMock()
        mock_coord.executor = mock_executor
        core.proactive_coordinator = mock_coord

        # User gives an unprompted fresh command -> executor returns None
        mock_executor.handle_user_utterance.return_value = None

        with patch("threading.Timer") as mock_timer:
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance
            resp = core.process_input("jarvis restart karo", source="cli")
            assert mock_executor.handle_user_utterance.called
            assert "restart" in resp.lower()
