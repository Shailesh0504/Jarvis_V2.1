# learning/habit_layer.py
"""Layer 5: Habit Detection & Proactive Contextual Suggestions."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.habits")


class HabitLayer:
    """Layer 5: Detects repeated behavioral habits backed by learned_patterns table."""

    def __init__(self, db: DatabaseManager, min_habit_frequency: int = 3):
        self.db = db
        self.min_habit_frequency = min_habit_frequency
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_habits()

    def _load_habits(self) -> None:
        try:
            sql = "SELECT pattern_key, context_data, frequency, last_seen FROM learned_patterns"
            rows = self.db.execute_query(sql)
            for r in rows:
                self._cache[r["pattern_key"]] = {
                    "habit_key": r["pattern_key"],
                    "context_data": json.loads(r["context_data"]) if r["context_data"] else {},
                    "frequency": r["frequency"],
                    "last_invoked": r["last_seen"],
                    "suggested_action": ""
                }
        except Exception as e:
            logger.error(f"Failed to load habits: {e}")

    def observe(self, intent_name: str, context_details: Optional[Dict[str, Any]] = None) -> None:
        if not intent_name or intent_name == "chat":
            return

        habit_key = intent_name.strip().lower()
        context_json = json.dumps(context_details or {})
        now = time.time()

        sql = """
        INSERT INTO learned_patterns (pattern_key, pattern_type, frequency, confidence, context_data, last_seen)
        VALUES (?, 'habit', 1, 1.0, ?, ?)
        ON CONFLICT(pattern_key) DO UPDATE SET
            frequency = frequency + 1,
            last_seen = excluded.last_seen,
            context_data = excluded.context_data
        """
        self.db.execute_update(sql, (habit_key, context_json, now))

        if habit_key in self._cache:
            self._cache[habit_key]["frequency"] += 1
            self._cache[habit_key]["last_invoked"] = now
        else:
            self._cache[habit_key] = {
                "habit_key": habit_key,
                "context_data": context_details or {},
                "frequency": 1,
                "last_invoked": now,
                "suggested_action": ""
            }

    def get_proactive_suggestion(self, trigger_query: str) -> Optional[str]:
        lower = trigger_query.strip().lower()

        if "excel" in lower or "sheet" in lower or "kholo" in lower:
            habit = self._cache.get("excel_launch") or self._cache.get("excel_clean") or self._cache.get("excel")
            freq = habit["frequency"] if habit else self._get_habit_frequency("excel")
            if freq >= self.min_habit_frequency:
                return "Aap usually Sales folder ki latest Excel file open karte hain. Kya main wahi open karun, Boss?"

        if "browser" in lower or "search" in lower:
            freq = self._get_habit_frequency("browser")
            if freq >= self.min_habit_frequency:
                return "Aap usually daily dashboard check karte hain. Kya main dashboard open karun?"

        return None

    def get_frequency(self, habit_key: str) -> int:
        """Return the observed frequency for the given habit key."""
        clean_key = habit_key.strip().lower()
        if clean_key in self._cache:
            return self._cache[clean_key].get("frequency", 0)
        return self._get_habit_frequency(clean_key)

    def _get_habit_frequency(self, prefix: str) -> int:
        for k, v in self._cache.items():
            if prefix in k:
                return v.get("frequency", 0)
        return 0

    def get_top_habits(self, limit: int = 5) -> List[Dict[str, Any]]:
        sql = """
        SELECT pattern_key AS habit_key, frequency, last_seen AS last_invoked, context_data
        FROM learned_patterns
        ORDER BY frequency DESC
        LIMIT ?
        """
        return self.db.execute_query(sql, (limit,))
