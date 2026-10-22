# tests/test_proactive_decision_engine.py
"""
Unit tests for Phase 5: Proactive Decision and Intent Engine.
Validates opportunistic proactive triggers (app transitions, media artist suggestions,
contextual volume habits, task resumption) and anti-nuisance distraction guardrails.
"""

from unittest.mock import MagicMock

import pytest

from core.intelligence import (
    PatternLearningEngine,
    PatternRecord,
    PatternType,
    ProactiveDecisionEngine,
    ProactiveSuggestion,
    SuggestionUrgency,
    TimePeriod,
)
from core.observer.models import ActivityEvent, ActivityImportance, ActivityType


class TestProactiveModels:
    """Tests for ProactiveSuggestion dataclass and serialization."""

    def test_suggestion_serialization(self):
        sug = ProactiveSuggestion(
            suggestion_id="sug123",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Arijit Singh",
            confidence=0.85,
            rationale="Aap shaam ko aksar Arijit Singh sunte hain.",
            urgency=SuggestionUrgency.NORMAL,
            metadata={"source": "test"}
        )
        d = sug.to_dict()
        assert d["suggestion_id"] == "sug123"
        assert d["intent"] == "MEDIA_PLAY_ARTIST"
        assert d["action"] == "play_music"
        assert d["target"] == "Arijit Singh"
        assert d["confidence"] == 0.85
        assert d["urgency"] == "NORMAL"
        assert d["metadata"]["source"] == "test"


class TestDistractionGuardrails:
    """Tests for suppressing unsolicited interruptions when user is in deep focus."""

    def test_distraction_guard_active_document_suppression(self):
        engine = ProactiveDecisionEngine()

        ev = ActivityEvent(
            event_type=ActivityType.DOCUMENT_EDITED,
            application="excel",
            window_title="Budget 2026.xlsx - Excel"
        )
        assert engine.is_user_in_focus_state(ev) is True
        # Opportunity evaluation must return None during focus
        assert engine.evaluate_opportunity(ev) is None

    def test_distraction_guard_ide_and_code_suppression(self):
        engine = ProactiveDecisionEngine()

        ev = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="vscode",
            window_title="decision_engine.py - Visual Studio Code"
        )
        assert engine.is_user_in_focus_state(ev) is True
        assert engine.evaluate_opportunity(ev) is None

    def test_distraction_guard_disabled(self):
        engine = ProactiveDecisionEngine(enable_distraction_guard=False)

        ev = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="vscode"
        )
        assert engine.is_user_in_focus_state(ev) is False


class TestTransitionOpportunities:
    """Tests for evaluating app transition triggers."""

    def test_confident_transition_triggers_suggestion(self):
        pattern_engine = PatternLearningEngine()
        # Seed an established transition habit: chrome -> youtube (frequency 3 => confidence 0.70)
        for _ in range(3):
            pattern_engine._record_pattern_evidence(
                pattern_key="trans:chrome->youtube",
                pattern_type=PatternType.APP_TRANSITION,
                extra_data={"from_app": "chrome", "to_app": "youtube"}
            )

        decision_engine = ProactiveDecisionEngine(pattern_engine=pattern_engine)

        ev = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="chrome",
            window_title="New Tab - Google Chrome"
        )
        sug = decision_engine.evaluate_opportunity(ev)
        assert sug is not None
        assert sug.intent == "LAUNCH_APP"
        assert sug.action == "open_app"
        assert sug.target == "youtube"
        assert sug.confidence >= 0.70

    def test_unconfident_transition_suppressed(self):
        pattern_engine = PatternLearningEngine()
        # Only 1 occurrence => confidence 0.35 (< 0.70)
        pattern_engine._record_pattern_evidence(
            pattern_key="trans:chrome->github",
            pattern_type=PatternType.APP_TRANSITION
        )

        decision_engine = ProactiveDecisionEngine(pattern_engine=pattern_engine)

        ev = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="chrome"
        )
        sug = decision_engine.evaluate_opportunity(ev)
        assert sug is None


class TestMediaOpportunities:
    """Tests for media and artist proactive triggers."""

    def test_media_artist_suggestion_on_youtube_open(self):
        pattern_engine = PatternLearningEngine()
        # Seed an established artist preference: Arijit Singh
        for _ in range(4):
            pattern_engine._record_pattern_evidence(
                pattern_key="media_artist:arijit_singh",
                pattern_type=PatternType.MEDIA_PREFERENCE,
                extra_data={"content_title": "Arijit Singh - Kesariya"}
            )

        decision_engine = ProactiveDecisionEngine(pattern_engine=pattern_engine)

        ev = ActivityEvent(
            event_type=ActivityType.WEBSITE_OPENED,
            application="brave",
            website="youtube",
            window_title="YouTube"
        )
        sug = decision_engine.evaluate_opportunity(ev)
        assert sug is not None
        assert sug.intent == "MEDIA_PLAY_ARTIST"
        assert sug.action == "play_music"
        assert "Arijit Singh" in sug.target
        assert sug.confidence >= 0.70

    def test_media_suggestion_suppressed_when_video_already_playing(self):
        pattern_engine = PatternLearningEngine()
        for _ in range(4):
            pattern_engine._record_pattern_evidence(
                pattern_key="media_artist:arijit_singh",
                pattern_type=PatternType.MEDIA_PREFERENCE
            )

        decision_engine = ProactiveDecisionEngine(pattern_engine=pattern_engine)

        ev = ActivityEvent(
            event_type=ActivityType.VIDEO_PLAYED,
            application="brave",
            website="youtube",
            content_title="Coldplay - Yellow"
        )
        # Should NOT interrupt active video playback with a new artist suggestion
        sug = decision_engine.evaluate_opportunity(ev)
        # However, volume opportunity could evaluate if volume mismatch occurs
        if sug:
            assert sug.intent != "MEDIA_PLAY_ARTIST"


class TestVolumeOpportunities:
    """Tests for contextual volume habit proactive suggestions."""

    def test_volume_adjustment_suggested_on_significant_mismatch(self):
        pattern_engine = PatternLearningEngine()
        night = TimePeriod.NIGHT
        # Establish a night volume habit of 30% (3 occurrences => confidence 0.70)
        for _ in range(3):
            pattern_engine.learn_volume_habit(time_period=night, app="spotify", volume=30)

        decision_engine = ProactiveDecisionEngine(pattern_engine=pattern_engine)

        # Spotify starts playing at night, but volume is currently 70% (diff >= 10%)
        # Timestamp around 23:00 (NIGHT)
        ev = ActivityEvent(
            event_type=ActivityType.VIDEO_PLAYED,
            application="spotify",
            content_title="Lo-Fi Chill Beats",
            timestamp=1725577200.0,  # Any fixed night timestamp
            metadata={"new_volume": 70}
        )
        # Force timestamp to night
        from unittest.mock import patch
        with patch.object(TimePeriod, "from_timestamp", return_value=TimePeriod.NIGHT):
            sug = decision_engine.evaluate_opportunity(ev)

        assert sug is not None
        assert sug.intent == "ADJUST_VOLUME"
        assert sug.action == "set_volume"
        assert sug.target == "30"


class TestTaskResumptionOpportunities:
    """Tests for suggesting task resumption after returning from idle."""

    def test_resume_task_suggested_on_user_active(self):
        mock_memory = MagicMock()
        prev_ev = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="blender",
            content_title="ProjectRender.blend",
            window_title="Blender - ProjectRender.blend"
        )
        mock_memory.get_recent_history.return_value = [prev_ev]

        decision_engine = ProactiveDecisionEngine(memory=mock_memory)

        active_ev = ActivityEvent(
            event_type=ActivityType.USER_ACTIVE,
            application="desktop"
        )
        sug = decision_engine.evaluate_opportunity(active_ev)
        assert sug is not None
        assert sug.intent == "RESUME_TASK"
        assert sug.action == "resume_context"
        assert "ProjectRender.blend" in sug.target
