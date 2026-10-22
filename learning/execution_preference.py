# learning/execution_preference.py
"""
ExecutionPreferenceManager — Generic per-target execution preference storage.

Stores and retrieves user preferences for *how* a target should be opened
(e.g., "YouTube → Brave", "Gmail → Chrome").  Backed by the existing
SQLite `preferences` table (category='execution') so preferences survive
restarts.  An optional in-memory session scope allows one-turn overrides
without writing to the database.

Design rules
------------
* Single authoritative owner of execution-preference CRUD — nothing else
  writes these keys directly.
* Explicit container specified in the current command always wins over any
  saved preference (enforced by the caller, not this class).
* Preferences are stored silently; this class emits no user-facing messages.
* Ambiguous commands must NOT call set_target_preference — the caller is
  responsible for verifying explicit user intent before writing.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.exec_pref")

# SQLite key prefix used so execution prefs are easily distinguishable
# from other generic preference keys.
_KEY_PREFIX = "exec_pref:"
_CATEGORY = "execution"
_USER_ID = "default_user"


class ExecutionPreferenceManager:
    """Manages per-target execution environment (container/browser) preferences.

    Storage layout in `preferences` table:
        user_id  = 'default_user'
        category = 'execution'
        key      = 'exec_pref:<normalized_target>'   e.g. 'exec_pref:youtube'
        value    = '<container>'                      e.g. 'brave'
        value_type = 'string'
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        # In-memory session overrides: {target: container}  (not persisted)
        self._session_overrides: Dict[str, str] = {}
        # In-memory cache of permanent prefs for fast reads
        self._cache: Dict[str, str] = {}
        self._load_cache()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(target: str) -> str:
        """Normalize a target name to a consistent lowercase key."""
        return target.strip().lower()

    @staticmethod
    def _make_key(target: str) -> str:
        return _KEY_PREFIX + ExecutionPreferenceManager._normalize(target)

    def _load_cache(self) -> None:
        """Load all permanent execution preferences into the in-memory cache."""
        try:
            sql = (
                "SELECT key, value FROM preferences "
                "WHERE user_id = ? AND category = ?"
            )
            rows = self.db.execute_query(sql, (_USER_ID, _CATEGORY))
            for r in rows:
                key: str = r["key"]
                if key.startswith(_KEY_PREFIX):
                    target = key[len(_KEY_PREFIX):]
                    self._cache[target] = r["value"]
            logger.debug(
                "ExecutionPreferenceManager: loaded %d persistent preferences.",
                len(self._cache),
            )
        except Exception as exc:
            logger.error("Error loading execution preference cache: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_target_preference(
        self,
        target: str,
        container: str,
        scope: str = "permanent",
    ) -> None:
        """Store a container preference for *target*.

        Parameters
        ----------
        target:
            The entity name, e.g. ``"youtube"``, ``"gmail"``, ``"google"``.
        container:
            The preferred execution environment, e.g. ``"brave"``, ``"chrome"``.
        scope:
            ``"permanent"`` (default) — persisted to SQLite; survives restarts.
            ``"session"``            — stored in-memory only; lost on restart.
        """
        norm_target = self._normalize(target)
        norm_container = self._normalize(container)

        if scope == "session":
            self._session_overrides[norm_target] = norm_container
            logger.info(
                "Execution preference (SESSION): '%s' → '%s'",
                norm_target, norm_container,
            )
            return

        # Permanent — upsert into SQLite
        sql = """
        INSERT INTO preferences (user_id, category, key, value, value_type, updated_at)
        VALUES (?, ?, ?, ?, 'string', ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value      = excluded.value,
            category   = excluded.category,
            value_type = excluded.value_type,
            updated_at = excluded.updated_at
        """
        try:
            self.db.execute_update(
                sql,
                (
                    _USER_ID,
                    _CATEGORY,
                    self._make_key(norm_target),
                    norm_container,
                    time.time(),
                ),
            )
            self._cache[norm_target] = norm_container
            logger.info(
                "Execution preference (PERMANENT): '%s' → '%s'",
                norm_target, norm_container,
            )
        except Exception as exc:
            logger.error(
                "Failed to persist execution preference '%s' → '%s': %s",
                norm_target, norm_container, exc,
            )

    def get_target_preference(self, target: str) -> Optional[str]:
        """Return the saved container preference for *target*, or ``None``.

        Session overrides take priority over permanent preferences.
        """
        norm_target = self._normalize(target)
        # 1. Check session override first
        if norm_target in self._session_overrides:
            return self._session_overrides[norm_target]
        # 2. Check in-memory cache (populated from SQLite on init)
        return self._cache.get(norm_target)

    def clear_target_preference(self, target: str, scope: str = "permanent") -> None:
        """Remove a saved preference for *target*.

        Parameters
        ----------
        scope:
            ``"permanent"`` — removes from SQLite and cache.
            ``"session"``   — removes only the in-memory session override.
            ``"all"``       — removes both.
        """
        norm_target = self._normalize(target)

        if scope in ("session", "all"):
            self._session_overrides.pop(norm_target, None)

        if scope in ("permanent", "all"):
            try:
                sql = (
                    "DELETE FROM preferences "
                    "WHERE user_id = ? AND category = ? AND key = ?"
                )
                self.db.execute_update(
                    sql, (_USER_ID, _CATEGORY, self._make_key(norm_target))
                )
                self._cache.pop(norm_target, None)
                logger.info(
                    "Execution preference cleared (PERMANENT): '%s'", norm_target
                )
            except Exception as exc:
                logger.error(
                    "Failed to clear execution preference for '%s': %s",
                    norm_target, exc,
                )

    def get_all_target_preferences(self) -> Dict[str, str]:
        """Return a snapshot of all permanent execution preferences (for debug/display)."""
        result = dict(self._cache)
        # Session overrides on top
        result.update(self._session_overrides)
        return result
