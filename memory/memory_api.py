# memory/memory_api.py
"""Unified offline Memory facade (Phase 8).

Single authoritative adapter over the existing memory tiers — creates NO new
database and NO parallel memory system. Delegates persistence to
LongTermMemory (`memories` table, extended in place) and session state to a
lightweight in-process TTL store.

Pipeline position (no coupling into Laya intelligence logic):
    Semantic Parser -> Laya (advisory only) -> memory.get_relevant (read)
    -> Decision/Execution -> Response -> memory.observe_turn_async (write)

Privacy: values NEVER appear in logs; debug lines carry type/key only.
"""

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.memory.unified")

# Memory types (spec)
PROFILE = "PROFILE"
PREFERENCE = "PREFERENCE"
FACT = "FACT"
CONTEXT = "CONTEXT"
TASK = "TASK"
EVENT = "EVENT"
VALID_TYPES = frozenset({PROFILE, PREFERENCE, FACT, CONTEXT, TASK, EVENT})

# Confidence gating (spec)
AUTO_PERSIST_MIN = 0.90
SESSION_MIN = 0.60

# Session TTL (short-lived working state)
SESSION_TTL_SECONDS = 30 * 60.0

# Never auto-persist these, even at high confidence
_SENSITIVE_RE = None


def _sensitive_re():
    global _SENSITIVE_RE
    if _SENSITIVE_RE is None:
        import re
        _SENSITIVE_RE = re.compile(
            r"\b(password|passwd|otp|pin\b|secret|token|api[_-]?key|bank|account\s*(no|number)|"
            r"credit\s*card|cvv|aadhaar|pan\s*card)\b",
            re.IGNORECASE,
        )
    return _SENSITIVE_RE


def is_sensitive(text: str) -> bool:
    try:
        return bool(_sensitive_re().search(text or ""))
    except Exception:
        return False


def _now() -> float:
    return time.time()


class UnifiedMemory:
    """Thin, fast facade. All heavy lifting stays with existing tiers."""

    def __init__(self, memory_manager: Any = None, db_path: str = "data/jarvis.db"):
        self._manager = memory_manager
        self._db_path = db_path
        self._session: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    # -- internal helpers -------------------------------------------------
    def _mgr(self) -> Any:
        if self._manager is not None:
            return self._manager
        from .memory_manager import MemoryManager
        self._manager = MemoryManager(db_path=self._db_path)
        return self._manager

    @staticmethod
    def _norm_key(key: str) -> str:
        return (key or "").strip().lower()

    def _log_hit(self, matched: bool, mtype: str = "", key: str = "") -> None:
        # Values never logged.
        logger.debug("memory_retrieval: matched=%s type=%s key=%s",
                     str(matched).lower(), mtype or "-", key or "-")

    # -- READ -------------------------------------------------------------
    def get(self, key: str, user_id: str = "default_user") -> Optional[Dict[str, Any]]:
        """Exact key match: session first, then persistent store."""
        nk = self._norm_key(key)
        if not nk:
            self._log_hit(False)
            return None
        with self._lock:
            sess = self._session.get(nk)
            if sess and sess.get("expires_at", 0) > _now():
                self._log_hit(True, sess.get("memory_type", "CONTEXT"), nk)
                return dict(sess.get("record", {}))
            elif sess:
                self._session.pop(nk, None)
        try:
            row = self._mgr().long_term.get_fact(nk, user_id=user_id)
        except Exception:
            logger.debug("memory get unavailable", exc_info=True)
            self._log_hit(False)
            return None
        if row:
            self._log_hit(True, str(row.get("memory_type", "FACT")), nk)
            return dict(row)
        # preferences table fallback (explicit preference reads)
        try:
            pref = self._mgr().long_term.get_preference(nk, default=None, user_id=user_id)
        except Exception:
            pref = None
        if pref is not None:
            self._log_hit(True, PREFERENCE, nk)
            return {"key": nk, "value": pref, "memory_type": PREFERENCE,
                    "category": "preferences", "confidence": 1.0}
        self._log_hit(False)
        return None

    def search(self, query: str, limit: int = 5,
               user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Lightweight LIKE search over persistent store only (no full dump)."""
        q = (query or "").strip()
        if not q:
            return []
        try:
            rows = self._mgr().long_term.search_facts(q, limit=limit, user_id=user_id)
        except Exception:
            logger.debug("memory search unavailable", exc_info=True)
            return []
        self._log_hit(bool(rows), "SEARCH", q[:40])
        return [dict(r) for r in rows]

    def get_relevant(self, context: str, limit: int = 3,
                     user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Priority: exact key > context-token match > preference/profile > recent."""
        ctx = (context or "").strip().lower()
        if not ctx:
            self._log_hit(False)
            return []
        # 1. exact key
        exact = self.get(ctx, user_id=user_id)
        if exact:
            return [exact]
        # 2. context-token match (first meaningful token hit wins, capped)
        tokens = [t for t in ctx.split() if len(t) > 2][:6]
        for tok in tokens:
            hit = self.get(tok, user_id=user_id)
            if hit:
                return [hit]
        # 3/4. preference/profile + recent relevant via bounded search
        try:
            rows = self.search(ctx, limit=limit, user_id=user_id)
        except Exception:
            rows = []
        self._log_hit(bool(rows), "RELEVANT", ctx[:40])
        return rows

    def get_recent(self, limit: int = 5,
                   user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Recent episodic interactions (conservative, bounded)."""
        try:
            rows = self._mgr().get_recent_interactions(limit=limit)
        except Exception:
            logger.debug("memory recent unavailable", exc_info=True)
            return []
        return [dict(r) for r in (rows or [])][:limit]

    def get_preferences(self, user_id: str = "default_user") -> Dict[str, Any]:
        try:
            prefs = self._mgr().long_term.get_all_preferences(user_id=user_id)
        except Exception:
            logger.debug("memory preferences unavailable", exc_info=True)
            return {}
        self._log_hit(bool(prefs), PREFERENCE, "all")
        return dict(prefs or {})

    def list_memories(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """User-controlled listing (keys + types, values included for own data)."""
        try:
            rows = self._mgr().long_term.get_all_facts(user_id=user_id)
        except Exception:
            return []
        now = _now()
        live = []
        for r in rows or []:
            try:
                if r.get("expires_at") is not None and float(r["expires_at"]) <= now:
                    continue
            except Exception:
                pass
            live.append(dict(r))
        return live

    # -- WRITE ------------------------------------------------------------
    def remember(self, key: str, value: str, memory_type: str = FACT,
                 confidence: float = 1.0, importance: float = 0.5,
                 expires_in: Optional[float] = None, explicit: bool = False,
                 category: str = "facts", user_id: str = "default_user",
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Create/update memory. Explicit user requests bypass confidence gating
        (but never bypass the sensitive guard for auto paths; explicit sensitive
        values are stored only when the user explicitly asked)."""
        nk = self._norm_key(key)
        val = (value or "").strip()
        if not nk or not val:
            return False
        mt = (memory_type or FACT).upper()
        if mt not in VALID_TYPES:
            mt = FACT
        if not explicit:
            if is_sensitive(nk + " " + val):
                logger.debug("memory_retrieval: matched=false type=BLOCKED key=%s", nk)
                return False
            if confidence < SESSION_MIN:
                logger.debug("memory_retrieval: matched=false type=DROPPED key=%s", nk)
                return False
            if confidence < AUTO_PERSIST_MIN:
                # temporary/context memory only
                with self._lock:
                    self._session[nk] = {
                        "expires_at": _now() + SESSION_TTL_SECONDS,
                        "memory_type": mt,
                        "record": {"key": nk, "value": val, "memory_type": mt,
                                   "confidence": confidence, "session_only": True},
                    }
                logger.debug("memory_retrieval: matched=true type=%s key=%s", mt, nk)
                return True
        exp_at = (_now() + expires_in) if expires_in else None
        try:
            mgr = self._mgr()
            mgr.long_term.store_fact(nk, val, category=category, confidence=confidence,
                                     user_id=user_id, memory_type=mt, importance=importance,
                                     expires_at=exp_at, metadata=metadata or {"explicit": explicit})
            if mt == PREFERENCE:
                try:
                    mgr.long_term.set_preference(nk, val, user_id=user_id)
                except Exception:
                    pass
            # opportunistic expiry sweep (cheap, bounded)
            try:
                mgr.db.execute_update("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                                      (_now(),))
            except Exception:
                pass
        except Exception:
            logger.warning("memory remember unavailable", exc_info=True)
            return False
        logger.debug("memory_retrieval: matched=true type=%s key=%s", mt, nk)
        return True

    def update(self, key: str, value: Optional[str] = None,
               confidence: Optional[float] = None, importance: Optional[float] = None,
               user_id: str = "default_user") -> bool:
        nk = self._norm_key(key)
        if not nk:
            return False
        with self._lock:
            if nk in self._session:
                rec = self._session[nk].get("record", {})
                if value is not None:
                    rec["value"] = value.strip()
                if confidence is not None:
                    rec["confidence"] = confidence
                self._session[nk]["expires_at"] = _now() + SESSION_TTL_SECONDS
                return True
        try:
            ok = self._mgr().long_term.update_fact(nk, value=value, confidence=confidence,
                                                   importance=importance, user_id=user_id)
        except Exception:
            logger.warning("memory update unavailable", exc_info=True)
            return False
        logger.debug("memory_retrieval: matched=%s type=UPDATE key=%s", str(bool(ok)).lower(), nk)
        return bool(ok)

    def forget(self, key: str, user_id: str = "default_user") -> bool:
        nk = self._norm_key(key)
        if not nk:
            return False
        removed = False
        with self._lock:
            if self._session.pop(nk, None) is not None:
                removed = True
        try:
            if self._mgr().long_term.delete_fact(nk, user_id=user_id):
                removed = True
        except Exception:
            logger.warning("memory forget unavailable", exc_info=True)
        try:
            # also drop mirrored preference row if present
            self._mgr().db.execute_update("DELETE FROM preferences WHERE user_id = ? AND key = ?",
                                          (user_id, nk))
        except Exception:
            pass
        logger.debug("memory_retrieval: matched=%s type=FORGET key=%s", str(removed).lower(), nk)
        return removed

    def clear_session(self) -> int:
        with self._lock:
            n = len(self._session)
            self._session.clear()
        logger.debug("memory session cleared: count=%d", n)
        return n

    # -- post-response async extraction -----------------------------------
    def observe_turn_async(self, raw_input: str, response: str = "",
                           intent: str = "", user_id: str = "default_user") -> None:
        """Fire-and-forget stable-fact extraction. Never raises, never blocks."""

        def _run():
            try:
                self._extract_stable(raw_input, user_id=user_id)
            except Exception:
                logger.debug("memory background extraction note", exc_info=True)

        try:
            t = threading.Thread(target=_run, name="jarvis-memory-extract", daemon=True)
            t.start()
        except Exception:
            logger.debug("memory background thread unavailable", exc_info=True)

    def _extract_stable(self, text: str, user_id: str = "default_user") -> None:
        """Conservative auto-extract: only clearly stable preference/profile
        signals at high confidence; sensitive content never persisted."""
        import re
        low = (text or "").strip().lower()
        if not low or len(low) > 200 or "?" in text:
            return
        if is_sensitive(low):
            return
        # Stable reply-language preference (high confidence, narrow patterns)
        m = re.fullmatch(r"(?:mujhe\s+)?(hinglish|hindi|english)\s+mein\s+(?:reply|jawab|baat)\s+karo", low)
        if m:
            self.remember("response_language", m.group(1), memory_type=PREFERENCE,
                          confidence=0.95, importance=0.7, explicit=False,
                          category="preferences", user_id=user_id)
            return
        m = re.fullmatch(r"reply\s+(?:in|mein)\s+(hinglish|hindi|english)", low)
        if m:
            self.remember("response_language", m.group(1), memory_type=PREFERENCE,
                          confidence=0.95, importance=0.7, explicit=False,
                          category="preferences", user_id=user_id)
            return


_unified_singleton: Optional[UnifiedMemory] = None
_singleton_lock = threading.RLock()


def get_unified_memory(memory_manager: Any = None,
                       db_path: str = "data/jarvis.db") -> UnifiedMemory:
    """Process-wide singleton accessor (adapter boundary for future semantic backends)."""
    global _unified_singleton
    with _singleton_lock:
        if _unified_singleton is None:
            _unified_singleton = UnifiedMemory(memory_manager=memory_manager, db_path=db_path)
        elif memory_manager is not None and _unified_singleton._manager is None:
            _unified_singleton._manager = memory_manager
        return _unified_singleton


def get_unified_memory_for(core: Any) -> UnifiedMemory:
    """Core-scoped accessor: reuses a cached adapter per JarvisCore so session
    state survives across turns but never leaks across cores/tests."""
    try:
        mgr = getattr(core, "memory_manager", None)
        cached = getattr(core, "_unified_memory", None)
        if cached is not None and getattr(cached, "_manager", None) is mgr:
            return cached
        inst = UnifiedMemory(memory_manager=mgr,
                             db_path=getattr(getattr(mgr, "db", None), "db_path", "data/jarvis.db"))
        try:
            core._unified_memory = inst
        except Exception:
            pass
        return inst
    except Exception:
        return UnifiedMemory(memory_manager=getattr(core, "memory_manager", None))
