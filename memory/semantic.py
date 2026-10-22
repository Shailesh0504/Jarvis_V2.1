# memory/semantic.py
"""Semantic memory system storing facts, key-value knowledge, and tags."""

import logging
import time
from typing import Any, Dict, List, Optional

from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.semantic")


class SemanticMemory:
    """Stores and retrieves long-term factual statements, user details, and knowledge."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def store_fact(self, key: str, value: str, category: str = "general", tags: str = "", confidence: float = 1.0) -> None:
        sql = """
        INSERT INTO semantic_memory (key, value, category, tags, confidence, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            tags = excluded.tags,
            confidence = excluded.confidence,
            updated_at = excluded.updated_at
        """
        now = time.time()
        self.db.execute_update(sql, (key.strip().lower(), value.strip(), category, tags, confidence, now, now))
        logger.info(f"Stored semantic fact: [{category}] {key} = {value}")

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT key, value, category, tags, confidence, updated_at FROM semantic_memory WHERE key = ?"
        rows = self.db.execute_query(sql, (key.strip().lower(),))
        return rows[0] if rows else None

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        cleaned = query.strip().lower()
        # Search by key or value substring or category
        sql = """
        SELECT key, value, category, tags, confidence
        FROM semantic_memory
        WHERE key LIKE ? OR value LIKE ? OR category LIKE ? OR tags LIKE ?
        ORDER BY updated_at DESC
        LIMIT ?
        """
        wildcard = f"%{cleaned}%"
        return self.db.execute_query(sql, (wildcard, wildcard, wildcard, wildcard, limit))

    def delete_fact(self, key: str) -> bool:
        sql = "DELETE FROM semantic_memory WHERE key = ?"
        count = self.db.execute_update(sql, (key.strip().lower(),))
        return count > 0

    def get_all_facts(self) -> List[Dict[str, Any]]:
        sql = "SELECT key, value, category, tags, confidence FROM semantic_memory ORDER BY category, key"
        return self.db.execute_query(sql)
