# core/intelligence/preference_learner.py
"""
Adaptive Preference Learning and Habit Evolution Engine for Jarvis V2.
Implements temporal confidence decay for unobserved habits, preference shifting
across competing habits, consecutive rejection unlearning, and SQLite persistence.
"""

import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import PatternRecord, PatternType, TimePeriod
from .pattern_engine import PatternLearningEngine

logger = logging.getLogger("jarvis.core.intelligence.preference")


class AdaptivePreferenceLearner:
    """
    Manages the temporal evolution, decay, competition, and unlearning of
    user behavioral patterns so Jarvis stays in sync with changing human habits.
    """

    def __init__(
        self,
        pattern_engine: PatternLearningEngine,
        half_life_days: float = 14.0,
        min_confidence_floor: float = 0.20
    ):
        self.pattern_engine = pattern_engine
        self.half_life_days = max(1.0, half_life_days)
        self.min_confidence_floor = max(0.05, min_confidence_floor)
        self._rejection_streaks: Dict[str, int] = {}
        self._lock = threading.RLock()

    def apply_temporal_decay(
        self,
        current_time: Optional[float] = None,
        stale_threshold_days: float = 7.0
    ) -> int:
        """
        Applies exponential temporal decay to habits that have not been observed recently.
        Habits unobserved for > stale_threshold_days experience gradual confidence decay.
        Persists updated records to SQLite.
        Returns count of decayed patterns.
        """
        now = current_time if current_time is not None else time.time()
        stale_threshold_sec = stale_threshold_days * 86400.0
        half_life_sec = self.half_life_days * 86400.0
        decayed_count = 0

        with self._lock, self.pattern_engine._lock:
            for p_key, record in self.pattern_engine._patterns.items():
                elapsed = now - record.last_observed
                if elapsed > stale_threshold_sec and record.confidence > self.min_confidence_floor:
                    # Exponential decay: C(t) = C0 * 0.5 ^ (elapsed / half_life)
                    decay_exponent = (elapsed - stale_threshold_sec) / half_life_sec
                    decay_factor = math.pow(0.5, decay_exponent)
                    new_conf = max(self.min_confidence_floor, round(record.confidence * decay_factor, 2))

                    if new_conf < record.confidence:
                        record.confidence = new_conf
                        record.data["last_decayed_at"] = now
                        self.pattern_engine._save_pattern_to_db(record)
                        decayed_count += 1
                        logger.debug("Decayed pattern '%s' confidence to %.2f", p_key, new_conf)

        if decayed_count > 0:
            logger.info("Temporal decay applied to %d stale patterns", decayed_count)
        return decayed_count

    def record_consecutive_rejection(
        self,
        pattern_key: str,
        current_time: Optional[float] = None
    ) -> Optional[PatternRecord]:
        """
        Tracks consecutive rejections for a pattern.
        If rejected 2 consecutive times: confidence is penalized by -0.15.
        If rejected 3+ consecutive times: pattern is deactivated/suppressed to floor confidence.
        """
        now = current_time if current_time is not None else time.time()

        with self._lock:
            streak = self._rejection_streaks.get(pattern_key, 0) + 1
            self._rejection_streaks[pattern_key] = streak

            record = self.pattern_engine.get_pattern(pattern_key)
            if not record:
                return None

            if streak == 2:
                record.confidence = max(self.min_confidence_floor, round(record.confidence - 0.15, 2))
                record.data["rejection_streak"] = streak
                logger.info("Pattern '%s' rejected twice consecutively. Confidence reduced to %.2f", pattern_key, record.confidence)
            elif streak >= 3:
                record.confidence = self.min_confidence_floor
                record.data["deactivated"] = True
                record.data["rejection_streak"] = streak
                logger.info("Pattern '%s' rejected %d times. Pattern deactivated.", pattern_key, streak)

            self.pattern_engine._save_pattern_to_db(record)
            return record

    def reset_rejection_streak(self, pattern_key: str) -> None:
        """Resets the consecutive rejection streak when a user accepts or observes a pattern."""
        with self._lock:
            self._rejection_streaks.pop(pattern_key, None)
            record = self.pattern_engine.get_pattern(pattern_key)
            if record and "deactivated" in record.data:
                record.data.pop("deactivated", None)
                record.data.pop("rejection_streak", None)
                self.pattern_engine._save_pattern_to_db(record)

    def get_top_competing_pattern(
        self,
        category_prefix: str,
        min_confidence: float = 0.50,
        current_time: Optional[float] = None
    ) -> Optional[PatternRecord]:
        """
        Evaluates competing habits within a specific category prefix (e.g. 'media_artist:' or 'trans:chrome->').
        Dynamically re-ranks habits combining confidence and recency to select the currently dominant habit.
        """
        now = current_time if current_time is not None else time.time()

        with self.pattern_engine._lock:
            candidates: List[Tuple[float, PatternRecord]] = []

            for p_key, record in self.pattern_engine._patterns.items():
                if p_key.startswith(category_prefix) and record.confidence >= min_confidence:
                    if record.data.get("deactivated"):
                        continue

                    # Recency discount: habits observed today score higher than habits from weeks ago
                    elapsed_days = max(0.0, (now - record.last_observed) / 86400.0)
                    recency_weight = 1.0 / (1.0 + (0.10 * elapsed_days))
                    score = record.confidence * recency_weight
                    candidates.append((score, record))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
