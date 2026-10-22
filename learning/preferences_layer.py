# learning/preferences_layer.py
"""Layer 1: User Preferences Learning & Persistence."""

import json
import logging
import time
from typing import Any, Dict, Optional
from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.preferences")


class PreferencesLayer:
    """Layer 1: Manages user preferences (language style, conciseness, default apps)."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._defaults = {
            "preferred_browser": "chrome",
            "preferred_media_player": "vlc",
            "preferred_code_editor": "code",
            "language_style": "hinglish",
            "conciseness": "concise",
            "user_title": "Boss"
        }
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Seed default preferences if not already set."""
        for k, v in self._defaults.items():
            if self.get(k) is None:
                self.set(k, v)

    def set(self, key: str, value: Any) -> None:
        key_clean = key.strip().lower()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        val_type = type(value).__name__
        sql = """
        INSERT INTO preferences (user_id, category, key, value, value_type, updated_at)
        VALUES ('default_user', 'general', ?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            value_type = excluded.value_type,
            updated_at = excluded.updated_at
        """
        self.db.execute_update(sql, (key_clean, val_str, val_type, time.time()))
        logger.info(f"Layer 1 Preference updated: '{key_clean}' = {value}")

    def get(self, key: str, default: Any = None) -> Any:
        key_clean = key.strip().lower()
        sql = "SELECT value, value_type FROM preferences WHERE user_id = 'default_user' AND key = ?"
        rows = self.db.execute_query(sql, (key_clean,))
        if not rows:
            return self._defaults.get(key_clean, default)

        val_str = rows[0]["value"]
        val_type = rows[0]["value_type"]
        if val_type in ("int", "float", "bool", "dict", "list"):
            try:
                return json.loads(val_str)
            except Exception:
                return val_str
        return val_str

    def get_all(self) -> Dict[str, Any]:
        sql = "SELECT key, value, value_type FROM preferences WHERE user_id = 'default_user'"
        rows = self.db.execute_query(sql)
        prefs = dict(self._defaults)
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
