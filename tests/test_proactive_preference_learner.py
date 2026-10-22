# tests/test_proactive_preference_learner.py
"""
Unit tests for Phase 8: Adaptive Preference Learning & Habit Evolution Engine.
Validates exponential temporal decay of unobserved habits, competitive preference
re-ranking, consecutive rejection unlearning, and SQLite persistence.
"""

from unittest.mock import MagicMock

import pytest

from core.intelligence import (
    AdaptivePreferenceLearner,
    PatternLearningEngine,
    PatternRecord,
    PatternType,
)


class TestTemporalDecay:
    """Tests for exponential temporal decay applied to stale habits."""

    def test_stale_pattern_decays(self):
        engine = PatternLearningEngine()
        t_now = 10000000.0
        # Observed 21 days ago (21 * 86400 = 1,814,400s)
        t_past = t_now - (21 * 86400.0)

        engine._patterns["media_artist:old_artist"] = PatternRecord(
            pattern_type=PatternType.MEDIA_PREFERENCE,
            pattern_key="media_artist:old_artist",
            frequency=5,
            confidence=0.88,
            last_observed=t_past
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine, half_life_days=14.0)
        decayed = learner.apply_temporal_decay(current_time=t_now, stale_threshold_days=7.0)
        assert decayed == 1

        rec = engine.get_pattern("media_artist:old_artist")
        assert rec.confidence < 0.88
        assert rec.confidence >= 0.20
        assert "last_decayed_at" in rec.data

    def test_recent_pattern_does_not_decay(self):
        engine = PatternLearningEngine()
        t_now = 10000000.0
        # Observed 2 days ago (< 7 days threshold)
        t_recent = t_now - (2 * 86400.0)

        engine._patterns["media_artist:new_artist"] = PatternRecord(
            pattern_type=PatternType.MEDIA_PREFERENCE,
            pattern_key="media_artist:new_artist",
            frequency=5,
            confidence=0.88,
            last_observed=t_recent
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine, half_life_days=14.0)
        decayed = learner.apply_temporal_decay(current_time=t_now, stale_threshold_days=7.0)
        assert decayed == 0

        rec = engine.get_pattern("media_artist:new_artist")
        assert rec.confidence == 0.88


class TestConsecutiveRejectionUnlearning:
    """Tests for unlearning stale habits when user repeatedly rejects them."""

    def test_consecutive_rejection_penalizes_and_deactivates(self):
        engine = PatternLearningEngine()
        engine._patterns["trans:chrome->unwanted"] = PatternRecord(
            pattern_type=PatternType.APP_TRANSITION,
            pattern_key="trans:chrome->unwanted",
            frequency=4,
            confidence=0.82
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine)

        # 1st rejection
        learner.record_consecutive_rejection("trans:chrome->unwanted")
        rec = engine.get_pattern("trans:chrome->unwanted")
        assert rec.confidence == 0.82

        # 2nd rejection -> penalize confidence
        learner.record_consecutive_rejection("trans:chrome->unwanted")
        assert rec.confidence == 0.67

        # 3rd rejection -> deactivate pattern
        learner.record_consecutive_rejection("trans:chrome->unwanted")
        assert rec.confidence == 0.20
        assert rec.data.get("deactivated") is True

        # Deactivated patterns should be skipped in competitive ranking
        top = learner.get_top_competing_pattern("trans:chrome->")
        assert top is None

    def test_reset_rejection_streak(self):
        engine = PatternLearningEngine()
        engine._patterns["test_key"] = PatternRecord(
            pattern_key="test_key",
            data={"deactivated": True, "rejection_streak": 3}
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine)
        learner.reset_rejection_streak("test_key")

        rec = engine.get_pattern("test_key")
        assert "deactivated" not in rec.data
        assert "rejection_streak" not in rec.data


class TestCompetitivePreferenceRanking:
    """Tests for shifting preferences when user habit transitions to a new favorite."""

    def test_competing_preferences_favor_recent_favorite(self):
        engine = PatternLearningEngine()
        t_now = 10000000.0

        # Habit A: Former favorite (Arijit Singh), high initial confidence 0.88, but observed 15 days ago
        engine._patterns["media_artist:arijit_singh"] = PatternRecord(
            pattern_type=PatternType.MEDIA_PREFERENCE,
            pattern_key="media_artist:arijit_singh",
            confidence=0.88,
            last_observed=t_now - (15 * 86400.0)
        )

        # Habit B: Emerging favorite (Taylor Swift), confidence 0.80, observed today (0 days ago)
        engine._patterns["media_artist:taylor_swift"] = PatternRecord(
            pattern_type=PatternType.MEDIA_PREFERENCE,
            pattern_key="media_artist:taylor_swift",
            confidence=0.80,
            last_observed=t_now
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine)
        top = learner.get_top_competing_pattern("media_artist:", current_time=t_now)
        assert top is not None
        # Emerging recent favorite should take precedence
        assert top.pattern_key == "media_artist:taylor_swift"


class TestSQLitePersistence:
    """Tests for saving decayed and penalized patterns to SQLite."""

    def test_decay_and_unlearning_persist_to_db(self):
        mock_db = MagicMock()
        engine = PatternLearningEngine(db=mock_db)

        t_now = 10000000.0
        engine._patterns["media_artist:decay_target"] = PatternRecord(
            pattern_type=PatternType.MEDIA_PREFERENCE,
            pattern_key="media_artist:decay_target",
            confidence=0.90,
            last_observed=t_now - (30 * 86400.0)
        )

        learner = AdaptivePreferenceLearner(pattern_engine=engine)
        learner.apply_temporal_decay(current_time=t_now)

        assert mock_db.execute_update.called
