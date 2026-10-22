# tests/test_proactive_pattern_engine.py
"""
Unit tests for Phase 4: Proactive Intelligence Pattern Learning Engine.
Validates dynamic confidence scaling, app transition mining, time habits,
media preference extraction, adaptive volume learning, and SQLite persistence.
"""

from datetime import datetime
import json
import time
from unittest.mock import MagicMock

import pytest

from core.intelligence import (
    PatternLearningEngine,
    PatternRecord,
    PatternType,
    TimePeriod,
)
from core.observer.models import ActivityEvent, ActivityImportance, ActivityType


class TestPatternModels:
    """Tests for PatternType, TimePeriod, and PatternRecord."""

    def test_time_period_from_timestamp(self):
        # 08:00 -> MORNING
        dt_morning = datetime(2026, 9, 6, 8, 30, 0)
        assert TimePeriod.from_timestamp(dt_morning.timestamp()) == TimePeriod.MORNING

        # 14:00 -> AFTERNOON
        dt_afternoon = datetime(2026, 9, 6, 14, 0, 0)
        assert TimePeriod.from_timestamp(dt_afternoon.timestamp()) == TimePeriod.AFTERNOON

        # 19:00 -> EVENING
        dt_evening = datetime(2026, 9, 6, 19, 15, 0)
        assert TimePeriod.from_timestamp(dt_evening.timestamp()) == TimePeriod.EVENING

        # 23:30 -> NIGHT
        dt_night = datetime(2026, 9, 6, 23, 30, 0)
        assert TimePeriod.from_timestamp(dt_night.timestamp()) == TimePeriod.NIGHT

        # 03:00 -> NIGHT
        dt_early = datetime(2026, 9, 6, 3, 0, 0)
        assert TimePeriod.from_timestamp(dt_early.timestamp()) == TimePeriod.NIGHT

    def test_pattern_record_serialization(self):
        rec = PatternRecord(
            pattern_id="test1",
            pattern_type=PatternType.APP_TRANSITION,
            pattern_key="trans:chrome->youtube",
            frequency=3,
            confidence=0.70,
            data={"from_app": "chrome", "to_app": "youtube"}
        )
        d = rec.to_dict()
        assert d["pattern_id"] == "test1"
        assert d["pattern_type"] == "APP_TRANSITION"
        assert d["pattern_key"] == "trans:chrome->youtube"
        assert d["frequency"] == 3
        assert d["confidence"] == 0.70
        assert d["data"]["to_app"] == "youtube"


class TestPatternConfidenceScaling:
    """Tests for dynamic confidence calculation."""

    def test_dynamic_confidence_progression(self):
        calc = PatternLearningEngine.calculate_confidence
        assert calc(0) == 0.35
        assert calc(1) == 0.35
        assert calc(2) == 0.55
        assert calc(3) == 0.70
        assert calc(4) == 0.82
        assert calc(5) == 0.88
        assert calc(6) >= 0.89
        assert calc(10) <= 0.95


class TestAppTransitionMining:
    """Tests for app-to-app transition chain mining."""

    def test_app_transition_mined_successfully(self):
        engine = PatternLearningEngine()
        t0 = 1000.0

        ev1 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="chrome",
            window_title="Google Chrome",
            timestamp=t0
        )
        ev2 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="youtube",
            window_title="YouTube - Brave",
            timestamp=t0 + 10.0
        )

        engine.observe_event(ev1)
        res = engine.observe_event(ev2)

        trans = [p for p in res if p.pattern_type == PatternType.APP_TRANSITION]
        assert len(trans) == 1
        assert trans[0].pattern_key == "trans:chrome->youtube"
        assert trans[0].frequency == 1
        assert trans[0].confidence == 0.35

        # Second transition
        ev3 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="chrome",
            timestamp=t0 + 50.0
        )
        ev4 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="youtube",
            timestamp=t0 + 60.0
        )
        engine.observe_event(ev3)
        res2 = engine.observe_event(ev4)
        trans2 = [p for p in res2 if p.pattern_type == PatternType.APP_TRANSITION]
        assert len(trans2) == 1
        assert trans2[0].frequency == 2
        assert trans2[0].confidence == 0.55

    def test_transition_not_linked_if_time_gap_too_large(self):
        engine = PatternLearningEngine()
        t0 = 1000.0

        ev1 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="excel",
            timestamp=t0
        )
        ev2 = ActivityEvent(
            event_type=ActivityType.WINDOW_CHANGED,
            application="spotify",
            timestamp=t0 + 600.0  # 10 minutes later (>300s window)
        )

        engine.observe_event(ev1)
        res = engine.observe_event(ev2)
        trans = [p for p in res if p.pattern_type == PatternType.APP_TRANSITION]
        assert len(trans) == 0


class TestMediaPreferenceMining:
    """Tests for extracting media artist and track habits."""

    def test_extract_media_artist_habit(self):
        engine = PatternLearningEngine()

        for i in range(3):
            ev = ActivityEvent(
                event_type=ActivityType.VIDEO_PLAYED,
                application="brave",
                website="youtube",
                content_title="Arijit Singh - Kesariya Audio",
                timestamp=1000.0 + (i * 200.0)
            )
            res = engine.observe_event(ev)

        pattern = engine.get_pattern("media_artist:arijit_singh")
        assert pattern is not None
        assert pattern.frequency == 3
        assert pattern.confidence == 0.70
        assert pattern.pattern_type == PatternType.MEDIA_PREFERENCE


class TestAdaptiveVolumeHabit:
    """Tests for contextual volume habits and adaptive moving averages."""

    def test_volume_habit_adaptive_update(self):
        engine = PatternLearningEngine()
        night = TimePeriod.NIGHT

        # User listens at 30% first
        p1 = engine.learn_volume_habit(night, "general", 30)
        assert p1.data["preferred_volume"] == 30
        assert p1.frequency == 1
        assert p1.confidence == 0.35

        # Not yet confident enough to predict
        assert engine.get_predicted_volume(night, "general") is None

        # User listens at 30% second time
        p2 = engine.learn_volume_habit(night, "general", 30)
        assert p2.frequency == 2

        # User listens at 40% third time (preference shift)
        p3 = engine.learn_volume_habit(night, "general", 40)
        assert p3.frequency == 3
        assert p3.confidence == 0.70
        # Expected rolling avg: round((0.65 * 30) + (0.35 * 40)) = round(19.5 + 14) = 34
        assert p3.data["preferred_volume"] == 34

        # Now confident enough (confidence >= 0.70)
        pred = engine.get_predicted_volume(night, "general")
        assert pred == 34


class TestSQLitePersistence:
    """Tests for loading and saving patterns to SQLite."""

    def test_save_and_load_patterns(self):
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {
                "pattern_key": "time_app:morning:excel",
                "pattern_type": "TIME_APP_HABIT",
                "frequency": 4,
                "confidence": 0.82,
                "context_data": json.dumps({"app": "excel", "time_period": "MORNING"}),
                "last_seen": 123456789.0
            }
        ]

        engine = PatternLearningEngine(db=mock_db)
        pat = engine.get_pattern("time_app:morning:excel")
        assert pat is not None
        assert pat.frequency == 4
        assert pat.confidence == 0.82
        assert pat.data["app"] == "excel"

        # Update pattern and check db save
        engine._record_pattern_evidence(
            pattern_key="time_app:morning:excel",
            pattern_type=PatternType.TIME_APP_HABIT,
            extra_data={"note": "updated"}
        )
        assert mock_db.execute_update.called

        # Test get_all_patterns
        all_pats = engine.get_all_patterns()
        assert len(all_pats) == 1
        assert all_pats[0].pattern_key == "time_app:morning:excel"

        # Test filtering by min_confidence
        assert len(engine.get_all_patterns(min_confidence=0.90)) == 0
        assert len(engine.get_all_patterns(min_confidence=0.50)) == 1
