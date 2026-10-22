# learning/corrections.py
"""Learning user corrections and custom alias re-mappings."""

import logging
import time
from typing import Dict, List, Optional

from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.corrections")


class CorrectionsLearner:
    """Manages learned user phrase corrections and synonym aliases."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._cache: Dict[str, str] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        try:
            sql = "SELECT original_phrase, corrected_phrase FROM learned_corrections"
            rows = self.db.execute_query(sql)
            for r in rows:
                self._cache[r["original_phrase"].lower()] = r["corrected_phrase"]
        except Exception as e:
            logger.error(f"Error loading corrections cache: {e}")

    def register_correction(self, original: str, correction: str) -> None:
        sql = """
        INSERT INTO learned_corrections (original_phrase, corrected_phrase, occurrence_count, last_used)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(original_phrase) DO UPDATE SET
            corrected_phrase = excluded.corrected_phrase,
            occurrence_count = occurrence_count + 1,
            last_used = excluded.last_used
        """
        orig_clean = original.strip().lower()
        corr_clean = correction.strip()
        self.db.execute_update(sql, (orig_clean, corr_clean, time.time()))
        self._cache[orig_clean] = corr_clean
        logger.info(f"Registered user correction: '{orig_clean}' -> '{corr_clean}'")

    def get_correction(self, phrase: str) -> Optional[str]:
        return self._cache.get(phrase.strip().lower())
