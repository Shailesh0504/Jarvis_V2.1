# core/alias_manager.py
"""
User-Learned Website & Application Alias Management System for Jarvis V2.
Provides persistent storage, fuzzy resolution, and CRUD operations for custom user-taught aliases.
"""

import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.alias_manager")


class CustomAliasManager:
    """
    Manages user-taught aliases for websites, applications, and custom commands.
    Backed by SQLite 'custom_aliases' table in data/jarvis.db.
    """

    def __init__(self, db_path: str = "data/jarvis.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ensure_db_dir()
        self._init_table()
        self._load_cache()

    def _ensure_db_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_table(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    target TEXT NOT NULL,
                    action_type TEXT DEFAULT 'OPEN_WEBSITE',
                    description TEXT,
                    created_by TEXT DEFAULT 'user',
                    created_at REAL NOT NULL,
                    last_used REAL
                );
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_name ON custom_aliases(alias COLLATE NOCASE);")
                conn.commit()

    def _load_cache(self) -> None:
        """Loads all custom aliases into memory for O(1) instantaneous lookup."""
        with self._lock:
            self._cache.clear()
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM custom_aliases ORDER BY created_at DESC")
                    for row in cursor.fetchall():
                        item = dict(row)
                        self._cache[item["alias"].lower()] = item
            except Exception as e:
                logger.warning("Failed to preload custom alias cache: %s", e)

    _PREFIX_STRIP_RE = re.compile(r'^(?:open|launch|start|visit|kholo|jarvis)\s+', re.IGNORECASE)
    _SUFFIX_STRIP_RE = re.compile(r'\s+(?:open|launch|start|visit|kholo|website|site|app|khol\s+do|open\s+karo)$', re.IGNORECASE)

    def add_alias(
        self,
        alias: str,
        target: str,
        action_type: str = "OPEN_WEBSITE",
        description: str = "",
        created_by: str = "user"
    ) -> bool:
        """Adds a new custom alias or updates if it already exists."""
        clean_alias = alias.strip().lower()
        clean_target = target.strip()
        if not clean_alias or not clean_target:
            return False

        now = time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO custom_aliases (alias, target, action_type, description, created_by, created_at, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET
                    target = excluded.target,
                    action_type = excluded.action_type,
                    description = excluded.description,
                    created_at = excluded.created_at
                """, (clean_alias, clean_target, action_type, description or f"{alias} alias", created_by, now, None))
                conn.commit()
                # Update in-memory cache
                self._cache[clean_alias] = {
                    "alias": clean_alias,
                    "target": clean_target,
                    "action_type": action_type,
                    "description": description or f"{alias} alias",
                    "created_by": created_by,
                    "created_at": now,
                    "last_used": None
                }
                logger.info("ALIAS_LEARNED alias=%r target=%r action_type=%s", clean_alias, clean_target, action_type)
                return True

    def update_alias(
        self,
        alias: str,
        target: str,
        action_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """Updates an existing custom alias."""
        clean_alias = alias.strip().lower()
        clean_target = target.strip()
        if not clean_alias or not clean_target:
            return False

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if action_type:
                    cursor.execute("""
                    UPDATE custom_aliases 
                    SET target = ?, action_type = ?, description = COALESCE(?, description)
                    WHERE LOWER(alias) = LOWER(?)
                    """, (clean_target, action_type, description, clean_alias))
                else:
                    cursor.execute("""
                    UPDATE custom_aliases 
                    SET target = ?, description = COALESCE(?, description)
                    WHERE LOWER(alias) = LOWER(?)
                    """, (clean_target, description, clean_alias))
                conn.commit()
                updated = cursor.rowcount > 0
                if not updated:
                    # If not exists, insert it
                    return self.add_alias(alias, target, action_type or "OPEN_WEBSITE", description or "")
                
                # Update in-memory cache
                if clean_alias in self._cache:
                    self._cache[clean_alias]["target"] = clean_target
                    if action_type:
                        self._cache[clean_alias]["action_type"] = action_type
                    if description is not None:
                        self._cache[clean_alias]["description"] = description
                else:
                    self._load_cache()
                logger.info("ALIAS_UPDATED alias=%r target=%r", clean_alias, clean_target)
                return True

    def delete_alias(self, alias: str) -> bool:
        """Deletes a custom alias."""
        clean_alias = alias.strip().lower()
        if not clean_alias:
            return False

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM custom_aliases WHERE LOWER(alias) = LOWER(?)", (clean_alias,))
                conn.commit()
                deleted = cursor.rowcount > 0
                self._cache.pop(clean_alias, None)
                logger.info("ALIAS_DELETED alias=%r success=%s", clean_alias, deleted)
                return deleted

    def get_alias(self, alias: str) -> Optional[Dict[str, Any]]:
        """Retrieves alias record by exact or case-insensitive match (O(1) in-memory)."""
        clean_alias = alias.strip().lower()
        if not clean_alias:
            return None
        cached = self._cache.get(clean_alias)
        return dict(cached) if cached else None

    def resolve_alias(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a user query against learned custom aliases.
        Checks exact match first, then clean phrase match, in O(1) time.
        """
        clean_q = query.strip().lower()
        if not clean_q:
            return None

        # 1. Exact match in-memory
        exact = self.get_alias(clean_q)
        if exact:
            return exact

        # 2. Normalized query (strip open/kholo/website verbs)
        stripped = self._PREFIX_STRIP_RE.sub('', clean_q)
        stripped = self._SUFFIX_STRIP_RE.sub('', stripped).strip()
        if stripped:
            norm_match = self.get_alias(stripped)
            if norm_match:
                return norm_match

        # 3. Fast substring search in in-memory aliases
        for alias_name, item in self._cache.items():
            if re.search(rf'\b{re.escape(alias_name)}\b', clean_q):
                return dict(item)

        return None

    def list_aliases(self) -> List[Dict[str, Any]]:
        """Returns all registered custom aliases (instant in-memory)."""
        return [dict(v) for v in self._cache.values()]

    def record_usage(self, alias: str) -> None:
        """Records last_used timestamp for an alias."""
        clean_alias = alias.strip().lower()
        now = time.time()
        with self._lock:
            if clean_alias in self._cache:
                self._cache[clean_alias]["last_used"] = now
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE custom_aliases SET last_used = ? WHERE LOWER(alias) = LOWER(?)", (now, clean_alias))
                conn.commit()


_global_alias_manager: Optional[CustomAliasManager] = None
_alias_lock = threading.Lock()


def get_alias_manager(db_path: str = "data/jarvis.db") -> CustomAliasManager:
    """Returns the singleton CustomAliasManager instance."""
    global _global_alias_manager
    if _global_alias_manager is None:
        with _alias_lock:
            if _global_alias_manager is None:
                _global_alias_manager = CustomAliasManager(db_path=db_path)
    return _global_alias_manager
