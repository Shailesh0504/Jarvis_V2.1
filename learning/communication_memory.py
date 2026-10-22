# learning/communication_memory.py
"""Dedicated SQLite Repository for the Learning Communication Engine (LCE)."""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.communication_memory")


class CommunicationMemory:
    """Thread-safe persistence layer for communication patterns, vocabulary, and feedback."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save_pattern(
        self,
        user_phrase: str,
        normalized_phrase: str,
        intent: str,
        entities: Optional[Dict[str, Any]] = None,
        context_key: str = "global",
        confidence: float = 0.50,
        source: str = "interaction",
        status: str = "candidate"
    ) -> int:
        """Saves or updates a communication pattern with usage frequency tracking."""
        now = time.time()
        entities_json = json.dumps(entities or {})
        sql = """
        INSERT INTO communication_patterns (
            user_phrase, normalized_phrase, language, context_key, intent,
            entities_json, confidence, usage_count, success_count, failure_count,
            created_at, updated_at, last_used_at, source, status
        ) VALUES (?, ?, 'hinglish', ?, ?, ?, ?, 1, 0, 0, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_phrase, context_key) DO UPDATE SET
            user_phrase = excluded.user_phrase,
            intent = excluded.intent,
            entities_json = excluded.entities_json,
            confidence = min(1.0, max(0.0, communication_patterns.confidence + (excluded.confidence - communication_patterns.confidence) * 0.5)),
            usage_count = communication_patterns.usage_count + 1,
            updated_at = excluded.updated_at,
            last_used_at = excluded.last_used_at,
            status = CASE
                WHEN communication_patterns.status = 'user_confirmed' THEN 'user_confirmed'
                WHEN communication_patterns.confidence >= 0.85 AND communication_patterns.usage_count >= 3 THEN 'trusted'
                ELSE 'candidate'
            END
        """
        self.db.execute_update(
            sql,
            (user_phrase, normalized_phrase, context_key, intent, entities_json, confidence, now, now, now, source, status)
        )
        rows = self.db.execute_query(
            "SELECT id FROM communication_patterns WHERE normalized_phrase = ? AND context_key = ?",
            (normalized_phrase, context_key)
        )
        return rows[0]["id"] if rows else 0

    def get_pattern(self, normalized_phrase: str, context_key: str = "global") -> Optional[Dict[str, Any]]:
        """Retrieves an exact pattern match for the given context key or global fallback."""
        rows = self.db.execute_query(
            """
            SELECT * FROM communication_patterns 
            WHERE normalized_phrase = ? AND (context_key = ? OR context_key = 'global')
            ORDER BY CASE WHEN context_key = ? THEN 1 ELSE 2 END, confidence DESC
            LIMIT 1
            """,
            (normalized_phrase, context_key, context_key)
        )
        if rows:
            row = dict(rows[0])
            row["entities"] = json.loads(row.get("entities_json") or "{}")
            return row
        return None

    def get_all_patterns(self, status: Optional[str] = None, min_confidence: float = 0.0) -> List[Dict[str, Any]]:
        """Returns all communication patterns meeting filter criteria."""
        if status:
            rows = self.db.execute_query(
                "SELECT * FROM communication_patterns WHERE status = ? AND confidence >= ? ORDER BY usage_count DESC, confidence DESC",
                (status, min_confidence)
            )
        else:
            rows = self.db.execute_query(
                "SELECT * FROM communication_patterns WHERE confidence >= ? ORDER BY usage_count DESC, confidence DESC",
                (min_confidence,)
            )
        result = []
        for r in rows:
            d = dict(r)
            d["entities"] = json.loads(d.get("entities_json") or "{}")
            result.append(d)
        return result

    def update_pattern_confidence(self, pattern_id: int, delta: float, success: bool = True) -> float:
        """Updates pattern confidence score with anti-drift bounds [0.0, 1.0]."""
        rows = self.db.execute_query("SELECT confidence, status FROM communication_patterns WHERE id = ?", (pattern_id,))
        if not rows:
            return 0.0
        curr_conf = float(rows[0]["confidence"])
        curr_status = rows[0]["status"]
        new_conf = max(0.0, min(1.0, curr_conf + delta))

        new_status = curr_status
        if curr_status != "user_confirmed":
            if new_conf >= 0.85:
                new_status = "trusted"
            elif new_conf < 0.70:
                new_status = "candidate"

        now = time.time()
        success_inc = 1 if success else 0
        failure_inc = 0 if success else 1

        self.db.execute_update(
            """
            UPDATE communication_patterns SET
                confidence = ?,
                status = ?,
                success_count = success_count + ?,
                failure_count = failure_count + ?,
                updated_at = ?,
                last_used_at = ?
            WHERE id = ?
            """,
            (new_conf, new_status, success_inc, failure_inc, now, now, pattern_id)
        )
        return new_conf

    def delete_pattern_by_phrase(self, phrase: str, context_key: Optional[str] = None) -> int:
        """Granular deletion of learned communication pattern."""
        phrase_clean = phrase.strip().lower()
        if context_key:
            return self.db.execute_update(
                "DELETE FROM communication_patterns WHERE (LOWER(user_phrase) = ? OR LOWER(normalized_phrase) = ?) AND context_key = ?",
                (phrase_clean, phrase_clean, context_key)
            )
        return self.db.execute_update(
            "DELETE FROM communication_patterns WHERE LOWER(user_phrase) = ? OR LOWER(normalized_phrase) = ?",
            (phrase_clean, phrase_clean)
        )

    def reset_all_patterns(self) -> int:
        """Wipes all non-confirmed communication patterns."""
        return self.db.execute_update("DELETE FROM communication_patterns WHERE status != 'user_confirmed'")

    def record_correction(
        self,
        original_text: str,
        wrong_interpretation: str,
        correct_interpretation: str,
        context_key: str = "global",
        reason: str = "user_correction"
    ) -> int:
        """Persists a negative correction event for auditing and rollback."""
        return self.db.execute_update(
            """
            INSERT INTO communication_corrections (
                original_text, wrong_interpretation, correct_interpretation, context_key, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (original_text, wrong_interpretation, correct_interpretation, context_key, reason, time.time())
        )

    def record_feedback(
        self,
        utterance: str,
        interpretation: str,
        feedback_type: str,
        context_key: str,
        conf_before: float,
        conf_after: float
    ) -> int:
        """Logs positive/negative feedback transitions."""
        return self.db.execute_update(
            """
            INSERT INTO communication_feedback (
                utterance, interpretation, feedback_type, context_key, confidence_before, confidence_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (utterance, interpretation, feedback_type, context_key, conf_before, conf_after, time.time())
        )

    def save_vocabulary_term(
        self,
        spoken_form: str,
        canonical_form: str,
        language: str = "hinglish",
        confidence: float = 0.50
    ) -> int:
        """Saves or updates a phonetic/spelling vocabulary mapping."""
        now = time.time()
        sql = """
        INSERT INTO learned_vocabulary (spoken_form, canonical_form, language, confidence, usage_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(spoken_form) DO UPDATE SET
            canonical_form = excluded.canonical_form,
            confidence = min(1.0, learned_vocabulary.confidence + 0.10),
            usage_count = learned_vocabulary.usage_count + 1,
            updated_at = excluded.updated_at
        """
        self.db.execute_update(sql, (spoken_form.strip(), canonical_form.strip(), language, confidence, now, now))
        rows = self.db.execute_query("SELECT id FROM learned_vocabulary WHERE LOWER(spoken_form) = LOWER(?)", (spoken_form.strip(),))
        return rows[0]["id"] if rows else 0

    def get_all_vocabulary(self) -> Dict[str, str]:
        """Returns dictionary of spoken_form -> canonical_form for vocabulary translation."""
        rows = self.db.execute_query("SELECT spoken_form, canonical_form FROM learned_vocabulary WHERE confidence >= 0.60")
        return {r["spoken_form"].lower(): r["canonical_form"] for r in rows}

    def save_alias(
        self,
        alias: str,
        canonical_command: str,
        context_key: str = "global",
        confidence: float = 0.50,
        source: str = "learned"
    ) -> int:
        """Persists a command alias."""
        now = time.time()
        sql = """
        INSERT INTO communication_aliases (alias, canonical_command, context_key, confidence, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(alias, context_key) DO UPDATE SET
            canonical_command = excluded.canonical_command,
            confidence = min(1.0, communication_aliases.confidence + 0.10),
            updated_at = excluded.updated_at
        """
        return self.db.execute_update(sql, (alias.strip(), canonical_command.strip(), context_key, confidence, source, now, now))

    def get_alias(self, alias: str, context_key: str = "global") -> Optional[str]:
        """Looks up command alias for active context."""
        rows = self.db.execute_query(
            """
            SELECT canonical_command FROM communication_aliases 
            WHERE LOWER(alias) = LOWER(?) AND (context_key = ? OR context_key = 'global')
            ORDER BY CASE WHEN context_key = ? THEN 1 ELSE 2 END, confidence DESC
            LIMIT 1
            """,
            (alias.strip(), context_key, context_key)
        )
        return rows[0]["canonical_command"] if rows else None

    def decay_stale_patterns(self, decay_days: int = 14, decay_amount: float = 0.02, min_confidence: float = 0.20) -> int:
        """Applies gradual confidence decay to non-user-confirmed patterns unused for decay_days."""
        cutoff = time.time() - (decay_days * 86400)
        return self.db.execute_update(
            """
            UPDATE communication_patterns
            SET confidence = max(?, confidence - ?),
                status = CASE WHEN (confidence - ?) < 0.70 THEN 'candidate' ELSE status END
            WHERE last_used_at < ? AND status != 'user_confirmed' AND confidence > ?
            """,
            (min_confidence, decay_amount, decay_amount, cutoff, min_confidence)
        )
