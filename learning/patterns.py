# learning/patterns.py
"""Learns user behavioral habits and recurring command patterns."""

import logging
import time
from typing import Any, Dict, List

from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.patterns")


class PatternLearner:
    """Tracks frequency of commands and detects usage patterns."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def observe(self, command_signature: str) -> None:
        if not command_signature:
            return

        sql = """
        INSERT INTO usage_patterns (pattern_signature, action_sequence, count, last_seen)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(pattern_signature) DO UPDATE SET
            count = count + 1,
            last_seen = excluded.last_seen
        """
        now = time.time()
        self.db.execute_update(sql, (command_signature.lower(), command_signature, now))

    def get_frequent_patterns(self, min_count: int = 3, limit: int = 5) -> List[Dict[str, Any]]:
        sql = """
        SELECT pattern_signature, count, last_seen
        FROM usage_patterns
        WHERE count >= ?
        ORDER BY count DESC, last_seen DESC
        LIMIT ?
        """
        return self.db.execute_query(sql, (min_count, limit))
