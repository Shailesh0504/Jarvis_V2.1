# memory/long_term.py
"""Long-Term Memory Tier: Durable knowledge, facts, and personalized preferences."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.long_term")


class LongTermMemory:
    """Manages enduring user facts, knowledge graphs, and personalized preferences."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # 1. Facts & Semantic Knowledge (memories table)
    def store_fact(self, key: str, value: str, category: str = "facts", tags: str = "", confidence: float = 1.0, user_id: str = "default_user",
                   memory_type: str = "FACT", importance: float = 0.5, expires_at: Optional[float] = None,
                   metadata: Optional[Dict[str, Any]] = None, source: str = "user") -> None:
        sql = """
        INSERT INTO memories (user_id, category, key, value, tags, confidence, source, created_at, updated_at,
                              memory_type, importance, last_used_at, expires_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            tags = excluded.tags,
            confidence = excluded.confidence,
            source = excluded.source,
            updated_at = excluded.updated_at,
            memory_type = excluded.memory_type,
            importance = excluded.importance,
            expires_at = excluded.expires_at,
            metadata_json = excluded.metadata_json
        """
        now = time.time()
        try:
            meta_str = json.dumps(metadata or {})
        except Exception:
            meta_str = "{}"
        self.db.execute_update(sql, (user_id, category, key.strip().lower(), value.strip(), tags, confidence, source,
                                     now, now, memory_type, importance, now, expires_at, meta_str))
        logger.info(f"Long-Term Memory stored fact: [{category}] {key} = {value}")

    @staticmethod
    def _is_expired(row: Dict[str, Any], now: Optional[float] = None) -> bool:
        try:
            exp = row.get("expires_at")
            if exp is None:
                return False
            return float(exp) <= (now if now is not None else time.time())
        except Exception:
            return False

    def get_fact(self, key: str, user_id: str = "default_user") -> Optional[Dict[str, Any]]:
        sql = "SELECT key, value, category, tags, confidence, source, memory_type, importance, created_at, updated_at, last_used_at, expires_at, metadata_json FROM memories WHERE user_id = ? AND key = ?"
        rows = self.db.execute_query(sql, (user_id, key.strip().lower()))
        if not rows:
            return None
        row = rows[0]
        if self._is_expired(row):
            return None
        try:
            self.db.execute_update("UPDATE memories SET last_used_at = ? WHERE user_id = ? AND key = ?",
                                   (time.time(), user_id, key.strip().lower()))
        except Exception:
            pass
        return row

    def update_fact(self, key: str, value: Optional[str] = None, category: Optional[str] = None,
                    confidence: Optional[float] = None, importance: Optional[float] = None,
                    expires_at: Optional[float] = None, user_id: str = "default_user") -> bool:
        sets: List[str] = []
        params: List[Any] = []
        if value is not None:
            sets.append("value = ?")
            params.append(value.strip())
        if category is not None:
            sets.append("category = ?")
            params.append(category)
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)
        if importance is not None:
            sets.append("importance = ?")
            params.append(importance)
        if expires_at is not None:
            sets.append("expires_at = ?")
            params.append(expires_at)
        if not sets:
            return False
        sets.append("updated_at = ?")
        params.append(time.time())
        params.extend([user_id, key.strip().lower()])
        sql = f"UPDATE memories SET {', '.join(sets)} WHERE user_id = ? AND key = ?"
        return self.db.execute_update(sql, tuple(params)) > 0

    def search_facts(self, query: str, limit: int = 5, user_id: str = "default_user") -> List[Dict[str, Any]]:
        cleaned = query.strip().lower()
        wildcard = f"%{cleaned}%"
        sql = """
        SELECT key, value, category, tags, confidence, source, memory_type, importance, updated_at, expires_at
        FROM memories
        WHERE user_id = ? AND (key LIKE ? OR value LIKE ? OR category LIKE ? OR tags LIKE ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """
        rows = self.db.execute_query(sql, (user_id, wildcard, wildcard, wildcard, wildcard, limit * 2))
        now = time.time()
        live = [r for r in rows if not self._is_expired(r, now)]
        return live[:limit]

    def delete_fact(self, key: str, user_id: str = "default_user") -> bool:
        sql = "DELETE FROM memories WHERE user_id = ? AND key = ?"
        return self.db.execute_update(sql, (user_id, key.strip().lower())) > 0

    def get_all_facts(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        sql = "SELECT key, value, category, tags, confidence FROM memories WHERE user_id = ? ORDER BY category, key"
        return self.db.execute_query(sql, (user_id,))

    # 2. Preferences (preferences table)
    def set_preference(self, key: str, value: Any, category: str = "general", user_id: str = "default_user") -> None:
        val_str = json.dumps(value) if not isinstance(value, str) else value
        val_type = type(value).__name__
        sql = """
        INSERT INTO preferences (user_id, category, key, value, value_type, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            value_type = excluded.value_type,
            category = excluded.category,
            updated_at = excluded.updated_at
        """
        self.db.execute_update(sql, (user_id, category, key.strip().lower(), val_str, val_type, time.time()))

    def get_preference(self, key: str, default: Any = None, user_id: str = "default_user") -> Any:
        sql = "SELECT value, value_type FROM preferences WHERE user_id = ? AND key = ?"
        rows = self.db.execute_query(sql, (user_id, key.strip().lower()))
        if not rows:
            return default

        val_str = rows[0]["value"]
        val_type = rows[0]["value_type"]
        if val_type in ("int", "float", "bool", "dict", "list"):
            try:
                return json.loads(val_str)
            except Exception:
                return val_str
        return val_str

    def get_all_preferences(self, user_id: str = "default_user") -> Dict[str, Any]:
        sql = "SELECT key, value, value_type FROM preferences WHERE user_id = ?"
        rows = self.db.execute_query(sql, (user_id,))
        prefs = {}
        for r in rows:
            k = r["key"]
            v = r["value"]
            t = r["value_type"]
            if t in ("int", "float", "bool", "dict", "list"):
                try:
                    prefs[k] = json.loads(v)
                except Exception:
                    prefs[k] = v
            else:
                prefs[k] = v
        return prefs
