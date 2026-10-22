# core/intelligence/pattern_engine.py
"""
Evidence-based Pattern Learning Engine for Jarvis V2.
Mines user behavioral patterns (app transitions, time-of-day habits, media preferences,
and adaptive volume levels) without single-event over-learning.
"""

import json
import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from core.observer.models import ActivityEvent, ActivityImportance, ActivityType
from .models import PatternRecord, PatternType, TimePeriod

logger = logging.getLogger("jarvis.core.intelligence.pattern")


class PatternLearningEngine:
    """
    Learns recurring user habits across desktop activities.
    Requires repeated evidence before establishing a high-confidence preference.
    Adapts dynamically when user preferences shift.
    """

    def __init__(self, db: Optional[Any] = None, min_evidence_for_pattern: int = 3):
        self.db = db
        self.min_evidence_for_pattern = max(2, min_evidence_for_pattern)
        self._patterns: Dict[str, PatternRecord] = {}
        self._last_app: Optional[str] = None
        self._last_event_time: float = 0.0
        self._lock = threading.RLock()
        self._load_patterns_from_db()

    @staticmethod
    def calculate_confidence(frequency: int) -> float:
        """
        Calculates dynamic confidence based on observation frequency:
        - 1 occurrence  -> ~0.35 (simple observation)
        - 2 occurrences -> ~0.55 (emerging observation)
        - 3 occurrences -> ~0.70 (weak pattern)
        - 4 occurrences -> ~0.82 (established pattern)
        - 5 occurrences -> ~0.88 (established pattern)
        - 6+ occurrences -> 0.90 to 0.95 (strong preference)
        """
        if frequency <= 1:
            return 0.35
        elif frequency == 2:
            return 0.55
        elif frequency == 3:
            return 0.70
        elif frequency == 4:
            return 0.82
        elif frequency == 5:
            return 0.88
        else:
            return min(0.95, round(0.88 + ((frequency - 5) * 0.015), 2))

    def _load_patterns_from_db(self) -> None:
        """Loads existing learned patterns from SQLite database if available."""
        if not self.db or not hasattr(self.db, "execute_query"):
            return

        try:
            sql = "SELECT pattern_key, pattern_type, frequency, confidence, context_data, last_seen FROM learned_patterns"
            rows = self.db.execute_query(sql)
            with self._lock:
                for r in rows:
                    p_key = r["pattern_key"]
                    p_type_raw = r.get("pattern_type") or "APP_TRANSITION"
                    p_type = PatternType(p_type_raw) if p_type_raw in PatternType._value2member_map_ else PatternType.APP_TRANSITION
                    data_obj = {}
                    if r.get("context_data"):
                        try:
                            data_obj = json.loads(r["context_data"])
                        except Exception:
                            pass

                    self._patterns[p_key] = PatternRecord(
                        pattern_type=p_type,
                        pattern_key=p_key,
                        frequency=r["frequency"],
                        confidence=r["confidence"],
                        data=data_obj,
                        last_observed=r["last_seen"]
                    )
            logger.info("Loaded %d learned patterns from SQLite", len(self._patterns))
        except Exception as e:
            logger.debug("Failed to load learned patterns from SQLite: %s", e)

    def _save_pattern_to_db(self, record: PatternRecord) -> None:
        """Persists or updates a learned pattern in SQLite."""
        if not self.db or not hasattr(self.db, "execute_update"):
            return

        try:
            sql = """
            INSERT INTO learned_patterns (pattern_key, pattern_type, frequency, confidence, context_data, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pattern_key) DO UPDATE SET
                frequency=excluded.frequency,
                confidence=excluded.confidence,
                context_data=excluded.context_data,
                last_seen=excluded.last_seen
            """
            p_type_str = record.pattern_type.value if hasattr(record.pattern_type, "value") else str(record.pattern_type)
            data_str = json.dumps(record.data)
            self.db.execute_update(sql, (
                record.pattern_key,
                p_type_str,
                record.frequency,
                record.confidence,
                data_str,
                record.last_observed
            ))
        except Exception as e:
            logger.debug("Failed to persist pattern to SQLite: %s", e)

    def _record_pattern_evidence(
        self,
        pattern_key: str,
        pattern_type: PatternType,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> PatternRecord:
        """Records an occurrence of a pattern and recalculates confidence."""
        now = time.time()
        with self._lock:
            if pattern_key in self._patterns:
                rec = self._patterns[pattern_key]
                rec.frequency += 1
                rec.last_observed = now
                rec.confidence = self.calculate_confidence(rec.frequency)
                if extra_data:
                    rec.data.update(extra_data)
            else:
                rec = PatternRecord(
                    pattern_type=pattern_type,
                    pattern_key=pattern_key,
                    frequency=1,
                    confidence=self.calculate_confidence(1),
                    data=extra_data or {},
                    first_observed=now,
                    last_observed=now
                )
                self._patterns[pattern_key] = rec

            self._save_pattern_to_db(rec)
            return rec

    def observe_event(self, event: ActivityEvent) -> List[PatternRecord]:
        """
        Processes an incoming ActivityEvent, mines relevant patterns across
        transitions, time periods, media choices, and volume settings.
        Returns a list of updated PatternRecords.
        """
        updated_patterns: List[PatternRecord] = []
        now = event.timestamp or time.time()
        time_period = TimePeriod.from_timestamp(now)

        with self._lock:
            curr_app = (event.application or "").lower().strip()

            # 1. Mine App-to-App Transition Chains
            if curr_app and self._last_app and curr_app != self._last_app:
                # Only link transitions that occurred within a reasonable window (5 minutes)
                if (now - self._last_event_time) <= 300.0:
                    trans_key = f"trans:{self._last_app}->{curr_app}"
                    rec_trans = self._record_pattern_evidence(
                        pattern_key=trans_key,
                        pattern_type=PatternType.APP_TRANSITION,
                        extra_data={"from_app": self._last_app, "to_app": curr_app}
                    )
                    updated_patterns.append(rec_trans)

            if curr_app:
                self._last_app = curr_app
                self._last_event_time = now

            # 2. Mine Time-of-Day App Usage Habits
            if curr_app:
                time_key = f"time_app:{time_period.value.lower()}:{curr_app}"
                rec_time = self._record_pattern_evidence(
                    pattern_key=time_key,
                    pattern_type=PatternType.TIME_APP_HABIT,
                    extra_data={"time_period": time_period.value, "app": curr_app}
                )
                updated_patterns.append(rec_time)

            # 3. Mine Media & Artist Preferences
            if event.event_type == ActivityType.VIDEO_PLAYED and event.content_title:
                media_key = self._extract_media_preference_key(event)
                if media_key:
                    rec_media = self._record_pattern_evidence(
                        pattern_key=media_key,
                        pattern_type=PatternType.MEDIA_PREFERENCE,
                        extra_data={
                            "content_title": event.content_title,
                            "website": event.website or "media",
                            "time_period": time_period.value
                        }
                    )
                    updated_patterns.append(rec_media)

            # 4. Mine Master Volume Contextual Habits
            if event.event_type == ActivityType.VOLUME_CHANGED:
                new_vol = (event.metadata or {}).get("new_volume")
                if isinstance(new_vol, (int, float)):
                    vol_val = int(round(new_vol))
                    rec_vol = self.learn_volume_habit(
                        time_period=time_period,
                        app=curr_app or "general",
                        volume=vol_val
                    )
                    updated_patterns.append(rec_vol)

        return updated_patterns

    @staticmethod
    def _extract_media_preference_key(event: ActivityEvent) -> Optional[str]:
        """Normalizes media titles and artists into clean preference keys."""
        title = (event.content_title or "").strip()
        if not title:
            return None

        # Clean artist names e.g. "Arijit Singh - Kesariya" -> "arijit_singh"
        if " - " in title:
            artist = title.split(" - ")[0].strip().lower()
            if len(artist) > 2:
                clean_artist = artist.replace(" ", "_")
                return f"media_artist:{clean_artist}"

        clean_title = title[:30].strip().lower().replace(" ", "_")
        site = event.website or "media"
        return f"media:{site}:{clean_title}"

    def learn_volume_habit(
        self,
        time_period: TimePeriod,
        app: str,
        volume: int
    ) -> PatternRecord:
        """
        Learns and updates the preferred volume for a specific time period and app.
        Maintains an adaptive moving average that dynamically reflects user adjustments.
        """
        key = f"volume_habit:{time_period.value.lower()}:{app.lower()}"
        with self._lock:
            if key in self._patterns:
                rec = self._patterns[key]
                rec.frequency += 1
                rec.last_observed = time.time()
                rec.confidence = self.calculate_confidence(rec.frequency)

                # Adaptive rolling average: weighted towards recent observations
                prev_avg = rec.data.get("preferred_volume", volume)
                # Exponential moving average with alpha=0.35 to adapt rapidly to preference changes
                new_avg = int(round((0.65 * prev_avg) + (0.35 * volume)))
                rec.data["preferred_volume"] = new_avg
                rec.data["last_actual_volume"] = volume
            else:
                rec = PatternRecord(
                    pattern_type=PatternType.VOLUME_HABIT,
                    pattern_key=key,
                    frequency=1,
                    confidence=self.calculate_confidence(1),
                    data={"preferred_volume": volume, "last_actual_volume": volume, "time_period": time_period.value, "app": app},
                    first_observed=time.time(),
                    last_observed=time.time()
                )
                self._patterns[key] = rec

            self._save_pattern_to_db(rec)
            return rec

    def get_pattern(self, pattern_key: str) -> Optional[PatternRecord]:
        """Retrieves a pattern by its unique key."""
        with self._lock:
            return self._patterns.get(pattern_key)

    def get_all_patterns(self, min_confidence: float = 0.0) -> List[PatternRecord]:
        """Returns all learned patterns, optionally filtered by minimum confidence."""
        with self._lock:
            if min_confidence > 0.0:
                return [p for p in self._patterns.values() if p.confidence >= min_confidence]
            return list(self._patterns.values())

    def get_strong_patterns(self, min_confidence: float = 0.70) -> List[PatternRecord]:
        """Returns all learned patterns whose confidence exceeds the threshold."""
        return self.get_all_patterns(min_confidence=min_confidence)

    def get_predicted_volume(
        self,
        time_period: Optional[TimePeriod] = None,
        app: str = "general"
    ) -> Optional[int]:
        """
        Predicts preferred volume level based on established patterns (confidence >= 0.70).
        Returns None if no confident habit has been established yet.
        """
        tp = time_period or TimePeriod.from_timestamp()
        key = f"volume_habit:{tp.value.lower()}:{app.lower()}"
        with self._lock:
            # 1. Check app-specific habit
            p = self._patterns.get(key)
            if p and p.confidence >= 0.70:
                return p.data.get("preferred_volume")

            # 2. Check general time period habit
            gen_key = f"volume_habit:{tp.value.lower()}:general"
            p_gen = self._patterns.get(gen_key)
            if p_gen and p_gen.confidence >= 0.70:
                return p_gen.data.get("preferred_volume")

            return None
