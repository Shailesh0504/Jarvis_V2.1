"""Persistent, conservative user-learned website knowledge for Jarvis."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import threading
import time
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


class InvalidWebsiteURL(ValueError):
    """Raised when a user-provided website address is not safe to store."""


_NORM_PUNCT_RE = re.compile(r"[^\w\s-]")
_REMOVABLE_WORDS = (
    "open|launch|start|visit|browse|navigate|go|to|kholo|khol|karo|kar|do|"
    "website|webpage|page|site|type|official|please|jarvis|bhai|yaar|zara|"
    "wali|wala|wale|ka|ki|ke|ko|se|mein|me|par|pe|the|a|an"
)
_REMOVABLE_RE = re.compile(rf"\b(?:{_REMOVABLE_WORDS})\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_website_phrase(value: str) -> str:
    """Remove navigation language while preserving the requested website entity with precompiled regexes."""
    text = str(value or "").lower().strip()
    text = _NORM_PUNCT_RE.sub(" ", text)
    # ``type`` is a common STT substitution for ``site`` only in navigation
    # phrases; it is deliberately not removed from arbitrary stored aliases.
    text = _REMOVABLE_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip(" -")


def validate_website_url(url: str) -> str:
    """Return a normalized HTTP(S) URL or reject it before persistence."""
    raw = str(url or "").strip()
    if not raw:
        raise InvalidWebsiteURL("Website URL is required.")
    candidate = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidWebsiteURL("Only HTTP(S) website URLs are allowed.")
    if not host or len(host) > 253 or "." not in host:
        raise InvalidWebsiteURL("Website domain is invalid.")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise InvalidWebsiteURL("Website domain is invalid.")
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


@dataclass(frozen=True)
class WebsiteMatch:
    entry: Dict[str, Any]
    confidence: float
    matched_alias: str
    ambiguous: bool = False


class WebsiteKnowledgeStore:
    """SQLite-backed website records with in-memory caching."""

    def __init__(self, db_path: str = "data/jarvis.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._entries_cache: Optional[List[Dict[str, Any]]] = None
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_table()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def _managed_connection(self):
        conn = self._connection()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_table(self) -> None:
        with self._lock, self._managed_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS website_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    normalized_aliases_json TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source TEXT NOT NULL DEFAULT 'user_learned',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    is_enabled INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_website_knowledge_updated ON website_knowledge(updated_at DESC)")
            try:
                conn.execute("ALTER TABLE website_knowledge ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1")
            except Exception:
                pass

    @staticmethod
    def _display_name(alias: str) -> str:
        return " ".join(part.upper() if re.fullmatch(r"\d+[a-z]+", part, re.IGNORECASE) else part.capitalize() for part in alias.split())

    @staticmethod
    def _generated_aliases(alias: str) -> List[str]:
        """Generate only narrow word-order/entity variations, never single words."""
        base = normalize_website_phrase(alias)
        words = base.split()
        if len(words) < 2:
            return [base] if base else []
        variants = {base, " ".join(reversed(words))}
        # A conservative body-form expansion handles the common spoken form
        # without introducing broad aliases such as "human", "body", or "3d".
        if set(words) == {"human", "3d"}:
            variants.update({"human body 3d", "3d human body"})
        return sorted(v for v in variants if len(v.split()) >= 2)

    def learn(
        self,
        alias: str,
        url: str,
        *,
        canonical_name: str = "",
        source: str = "user_learned",
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        normalized = normalize_website_phrase(alias)
        if len(normalized.split()) < 1:
            raise ValueError("Website ke liye ek naam chahiye.")
        safe_url = validate_website_url(url)
        aliases = self._generated_aliases(alias)
        now = time.time()
        with self._lock, self._managed_connection() as conn:
            rows = [self._decode(dict(row)) for row in conn.execute("SELECT * FROM website_knowledge ORDER BY updated_at DESC")]
            existing = next((row for row in rows if normalized in row["normalized_aliases"]), None)
            if existing:
                merged = sorted(set(existing["aliases"]).union(aliases))
                normalized_aliases = sorted({normalize_website_phrase(item) for item in merged if normalize_website_phrase(item)})
                conn.execute(
                    """UPDATE website_knowledge SET canonical_name=?, url=?, aliases_json=?,
                       normalized_aliases_json=?, confidence=?, source=?, updated_at=? WHERE id=?""",
                    (
                        canonical_name.strip() or existing["canonical_name"], safe_url,
                        json.dumps(merged), json.dumps(normalized_aliases), confidence,
                        source, now, existing["id"],
                    ),
                )
                row_id = existing["id"]
            else:
                display = canonical_name.strip() or self._display_name(alias)
                normalized_aliases = sorted({normalize_website_phrase(item) for item in aliases if normalize_website_phrase(item)})
                cursor = conn.execute(
                    """INSERT INTO website_knowledge
                    (canonical_name, url, aliases_json, normalized_aliases_json, confidence, source, created_at, updated_at, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (display, safe_url, json.dumps(aliases), json.dumps(normalized_aliases), confidence, source, now, now),
                )
                row_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM website_knowledge WHERE id=?", (row_id,)).fetchone()
            self._entries_cache = None
        return self._decode(dict(row))

    @staticmethod
    def _decode(row: Dict[str, Any]) -> Dict[str, Any]:
        row["aliases"] = json.loads(row.pop("aliases_json", "[]"))
        row["normalized_aliases"] = json.loads(row.pop("normalized_aliases_json", "[]"))
        row["is_enabled"] = bool(row.get("is_enabled", 1))
        return row

    def list_entries(self) -> List[Dict[str, Any]]:
        """Returns all website knowledge entries, cached in memory for sub-millisecond lookups."""
        with self._lock:
            if self._entries_cache is not None:
                return [dict(e) for e in self._entries_cache]
            with self._managed_connection() as conn:
                entries = [self._decode(dict(row)) for row in conn.execute("SELECT * FROM website_knowledge ORDER BY updated_at DESC")]
                self._entries_cache = entries
                return [dict(e) for e in entries]

    def get_entry_by_id(self, entry_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific website entry by its primary ID."""
        with self._lock:
            for entry in self.list_entries():
                if entry["id"] == entry_id:
                    return dict(entry)
        return None

    def update_entry(
        self,
        entry_id: int,
        *,
        url: Optional[str] = None,
        canonical_name: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        is_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Updates an existing learned website entry in SQLite and flushes memory cache.
        Also syncs changes to CustomAliasManager for total system consistency.
        """
        existing = self.get_entry_by_id(entry_id)
        if not existing:
            raise KeyError(f"Website knowledge entry {entry_id} not found.")

        safe_url = validate_website_url(url) if url else existing["url"]
        new_name = canonical_name.strip() if canonical_name is not None and canonical_name.strip() else existing["canonical_name"]

        if aliases is not None:
            clean_aliases = [a.strip().lower() for a in aliases if a.strip()]
            norm_aliases = sorted({normalize_website_phrase(a) for a in clean_aliases if normalize_website_phrase(a)})
        else:
            clean_aliases = existing["aliases"]
            norm_aliases = existing["normalized_aliases"]

        enabled_int = (1 if is_enabled else 0) if is_enabled is not None else (1 if existing.get("is_enabled", True) else 0)
        now = time.time()

        with self._lock, self._managed_connection() as conn:
            conn.execute(
                """UPDATE website_knowledge
                SET canonical_name=?, url=?, aliases_json=?, normalized_aliases_json=?,
                    is_enabled=?, updated_at=?
                WHERE id=?""",
                (
                    new_name,
                    safe_url,
                    json.dumps(clean_aliases),
                    json.dumps(norm_aliases),
                    enabled_int,
                    now,
                    entry_id,
                ),
            )
            row = conn.execute("SELECT * FROM website_knowledge WHERE id=?", (entry_id,)).fetchone()
            self._entries_cache = None

        # Synchronize with legacy CustomAliasManager if available
        try:
            from core.alias_manager import get_alias_manager
            alias_mgr = get_alias_manager(db_path=self.db_path)
            for a in clean_aliases:
                if enabled_int:
                    alias_mgr.update_alias(a, safe_url, action_type="OPEN_WEBSITE", description=f"{new_name} alias")
                else:
                    alias_mgr.delete_alias(a)
        except Exception:
            pass

        return self._decode(dict(row))

    def toggle_enabled(self, entry_id: int, is_enabled: Optional[bool] = None) -> bool:
        """Toggles or sets the enabled status of a saved website."""
        existing = self.get_entry_by_id(entry_id)
        if not existing:
            return False
        new_state = (not existing.get("is_enabled", True)) if is_enabled is None else bool(is_enabled)
        self.update_entry(entry_id, is_enabled=new_state)
        return new_state

    def delete_by_id(self, entry_id: int) -> bool:
        """Permanently removes a learned website entry by ID and invalidates cache."""
        existing = self.get_entry_by_id(entry_id)
        if not existing:
            return False

        with self._lock, self._managed_connection() as conn:
            conn.execute("DELETE FROM website_knowledge WHERE id=?", (entry_id,))
            self._entries_cache = None

        # Synchronize deletion in CustomAliasManager
        try:
            from core.alias_manager import get_alias_manager
            alias_mgr = get_alias_manager(db_path=self.db_path)
            for a in existing.get("aliases", []):
                alias_mgr.delete_alias(a)
        except Exception:
            pass

        return True

    def resolve(self, phrase: str) -> Optional[WebsiteMatch]:
        query = normalize_website_phrase(phrase)
        if not query:
            return None
        scored: List[WebsiteMatch] = []
        for entry in self.list_entries():
            # Skip disabled websites
            if not entry.get("is_enabled", True):
                continue
            for alias in entry["normalized_aliases"]:
                if query == alias:
                    scored.append(WebsiteMatch(entry, 1.0, alias))
                    continue
                query_words, alias_words = set(query.split()), set(alias.split())
                overlap = len(query_words & alias_words) / max(len(query_words | alias_words), 1)
                sequence = SequenceMatcher(None, query, alias).ratio()
                score = max(overlap, sequence)
                if score >= 0.75 and len(query_words & alias_words) >= 2:
                    scored.append(WebsiteMatch(entry, round(score, 3), alias))
        if not scored:
            return None
        scored.sort(key=lambda item: (item.confidence, item.entry["updated_at"]), reverse=True)
        best = scored[0]
        distinct_urls = {item.entry["url"] for item in scored if best.confidence - item.confidence < 0.10}
        return WebsiteMatch(best.entry, best.confidence, best.matched_alias, ambiguous=len(distinct_urls) > 1)

    def record_usage(self, entry_id: int) -> None:
        with self._lock, self._managed_connection() as conn:
            conn.execute("UPDATE website_knowledge SET usage_count = usage_count + 1, updated_at=? WHERE id=?", (time.time(), entry_id))

    def delete(self, alias: str) -> bool:
        """Forget a learned website selected by one of its normalized aliases."""
        normalized = normalize_website_phrase(alias)
        if not normalized:
            return False
        with self._lock, self._managed_connection() as conn:
            rows = [self._decode(dict(row)) for row in conn.execute("SELECT * FROM website_knowledge")]
            entry = next((row for row in rows if normalized in row["normalized_aliases"]), None)
            if not entry:
                return False
            return self.delete_by_id(entry["id"])
