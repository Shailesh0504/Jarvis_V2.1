# tests/test_proactive_suggestion_manager.py
"""
Unit tests for Phase 6: Suggestion Manager & Cooldowns Engine.
Validates global frequency capping, per-pattern cooldowns, rejection backoff,
acceptance reinforcement, and pending suggestion timeout lifecycle.
"""

import time
from unittest.mock import MagicMock

import pytest

from core.intelligence import (
    PatternLearningEngine,
    PatternRecord,
    PatternType,
    ProactiveSuggestion,
    SuggestionManager,
    SuggestionState,
    SuggestionUrgency,
)


class TestGlobalCooldown:
    """Tests for global frequency capping across all proactive suggestions."""

    def test_global_cooldown_blocks_frequent_suggestions(self):
        manager = SuggestionManager(min_global_cooldown_sec=900.0)  # 15 min
        t0 = 1000.0

        sug1 = ProactiveSuggestion(
            suggestion_id="s1",
            intent="LAUNCH_APP",
            action="open_app",
            target="youtube"
        )
        allowed, reason = manager.can_present_suggestion(sug1, current_time=t0)
        assert allowed is True

        manager.register_presented(sug1, current_time=t0)

        # Immediate next suggestion 60 seconds later (different target)
        sug2 = ProactiveSuggestion(
            suggestion_id="s2",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Coldplay"
        )
        allowed2, reason2 = manager.can_present_suggestion(sug2, current_time=t0 + 60.0)
        assert allowed2 is False
        assert "Global proactive cooldown active" in reason2

        # After 901 seconds (> 900s), next suggestion is allowed
        allowed3, reason3 = manager.can_present_suggestion(sug2, current_time=t0 + 901.0)
        assert allowed3 is True

    def test_high_urgency_bypasses_global_cooldown(self):
        manager = SuggestionManager(min_global_cooldown_sec=900.0)
        t0 = 1000.0

        sug1 = ProactiveSuggestion(suggestion_id="s1", target="app1")
        manager.register_presented(sug1, current_time=t0)

        # High urgency alert 30 seconds later
        sug_urgent = ProactiveSuggestion(
            suggestion_id="s_urg",
            intent="SYSTEM_ALERT",
            target="battery_low",
            urgency=SuggestionUrgency.HIGH
        )
        allowed, _ = manager.can_present_suggestion(sug_urgent, current_time=t0 + 30.0)
        assert allowed is True


class TestPerPatternCooldown:
    """Tests for per-pattern cooldowns preventing repetitive suggestions."""

    def test_per_pattern_cooldown_enforced(self):
        # Global: 300s (5 min), Pattern: 3600s (1 hour)
        manager = SuggestionManager(
            min_global_cooldown_sec=300.0,
            min_pattern_cooldown_sec=3600.0
        )
        t0 = 1000.0

        sug_arijit = ProactiveSuggestion(
            suggestion_id="s1",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Arijit Singh",
            metadata={"pattern_key": "media_artist:arijit_singh"}
        )
        manager.register_presented(sug_arijit, current_time=t0)

        # At t0 + 600s (global cooldown 300s is over, but pattern cooldown 3600s is not)
        sug_arijit_repeat = ProactiveSuggestion(
            suggestion_id="s2",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Arijit Singh",
            metadata={"pattern_key": "media_artist:arijit_singh"}
        )
        allowed, reason = manager.can_present_suggestion(sug_arijit_repeat, current_time=t0 + 600.0)
        assert allowed is False
        assert "Per-pattern cooldown active" in reason

        # However, a DIFFERENT pattern at t0 + 600s is allowed
        sug_diff = ProactiveSuggestion(
            suggestion_id="s3",
            intent="LAUNCH_APP",
            action="open_app",
            target="notepad",
            metadata={"pattern_key": "trans:chrome->notepad"}
        )
        allowed_diff, _ = manager.can_present_suggestion(sug_diff, current_time=t0 + 600.0)
        assert allowed_diff is True


class TestRejectionBackoff:
    """Tests for extended 24-hour suppression when user rejects a suggestion."""

    def test_rejection_activates_extended_suppression(self):
        pattern_engine = PatternLearningEngine()
        pattern_engine._record_pattern_evidence("media_artist:arijit_singh", PatternType.MEDIA_PREFERENCE)
        pat = pattern_engine.get_pattern("media_artist:arijit_singh")
        initial_conf = pat.confidence

        manager = SuggestionManager(
            pattern_engine=pattern_engine,
            min_global_cooldown_sec=300.0,
            min_pattern_cooldown_sec=600.0,
            rejection_backoff_sec=86400.0  # 24 hours
        )
        t0 = 1000.0

        sug = ProactiveSuggestion(
            suggestion_id="s_rej",
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target="Arijit Singh",
            metadata={"pattern_key": "media_artist:arijit_singh"}
        )
        manager.register_presented(sug, current_time=t0)

        # User says "nahi" -> record rejection feedback
        feedback_sug = manager.record_feedback("s_rej", accepted=False, current_time=t0 + 5.0)
        assert feedback_sug is not None
        assert feedback_sug.state == SuggestionState.REJECTED

        # Confidence should be penalized
        assert pat.confidence < initial_conf

        # Check permission at t0 + 1000s (both global 300s and pattern 600s have passed)
        allowed, reason = manager.can_present_suggestion(sug, current_time=t0 + 1000.0)
        assert allowed is False
        assert "User previously rejected this suggestion" in reason

        # After 24 hours (86401 seconds later), suppression lifts
        allowed_after, _ = manager.can_present_suggestion(sug, current_time=t0 + 86410.0)
        assert allowed_after is True


class TestPendingSuggestionLifecycle:
    """Tests for active pending suggestion retrieval and timeout expiration."""

    def test_pending_suggestion_timeout(self):
        manager = SuggestionManager(confirmation_timeout_sec=30.0)
        t0 = 1000.0

        sug = ProactiveSuggestion(suggestion_id="pending1", target="excel")
        manager.register_presented(sug, current_time=t0)

        # Within 15 seconds -> still pending
        p1 = manager.get_pending_suggestion(current_time=t0 + 15.0)
        assert p1 is not None
        assert p1.suggestion_id == "pending1"

        # After 31 seconds -> timed out & expired
        p2 = manager.get_pending_suggestion(current_time=t0 + 31.0)
        assert p2 is None
        assert sug.state == SuggestionState.EXPIRED

    def test_acceptance_feedback_marks_accepted(self):
        manager = SuggestionManager()
        t0 = 1000.0

        sug = ProactiveSuggestion(suggestion_id="accept1", target="spotify")
        manager.register_presented(sug, current_time=t0)

        # User says "ha chala do" -> record acceptance
        res = manager.record_feedback("accept1", accepted=True, current_time=t0 + 5.0)
        assert res is not None
        assert res.state == SuggestionState.ACCEPTED
        # Pending suggestion cleared
        assert manager.get_pending_suggestion(current_time=t0 + 6.0) is None
