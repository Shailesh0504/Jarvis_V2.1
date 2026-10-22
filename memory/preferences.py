# memory/preferences.py
"""User preferences management and persistence."""

import json
import logging
import time
from typing import Any, Dict, Optional

from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.preferences")


class PreferencesMemory:
    """Stores user preferences, environment preferences, and defaults."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        try:
            self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT DEFAULT 'str',
                updated_at REAL NOT NULL
            )
            """)
        except Exception:
            pass

    def set(self, key: str, value: Any) -> None:
        val_str = json.dumps(value) if not isinstance(value, str) else value
        val_type = type(value).__name__
        sql = """
        INSERT INTO user_preferences (key, value, value_type, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            value_type = excluded.value_type,
            updated_at = excluded.updated_at
        """
        self.db.execute_update(sql, (key.strip().lower(), val_str, val_type, time.time()))

    def get(self, key: str, default: Any = None) -> Any:
        sql = "SELECT value, value_type FROM user_preferences WHERE key = ?"
        rows = self.db.execute_query(sql, (key.strip().lower(),))
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

    def get_all(self) -> Dict[str, Any]:
        sql = "SELECT key, value, value_type FROM user_preferences"
        rows = self.db.execute_query(sql)
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
