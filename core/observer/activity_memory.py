# core/observer/activity_memory.py
"""
Dual-tier Activity & Context Memory for Jarvis V2.
Combines an in-memory short-term sliding context buffer with persistent SQLite
storage for medium and high importance events, providing temporal query semantics.
"""

from collections import deque
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .models import ActivityEvent, ActivityImportance, ActivityType

logger = logging.getLogger("jarvis.core.observer.memory")


class ActivityMemory:
    """
    Thread-safe dual-tier activity memory system:
    1. Short-Term Context Window: Fast in-memory buffer for immediate context and live attention tracking.
    2. Persistent Activity Store: SQLite persistence for meaningful historical interactions.
    """

    def __init__(self, db: Optional[Any] = None, max_history: int = 100):
        self.db = db
        self.max_history = max(1, max_history)
        self._events: deque[ActivityEvent] = deque(maxlen=self.max_history)
        self._active_event: Optional[ActivityEvent] = None
        self._lock = threading.RLock()

    @property
    def active_event(self) -> Optional[ActivityEvent]:
        """Returns the currently active desktop activity event."""
        with self._lock:
            return self._active_event

    def record_event(self, event: ActivityEvent) -> ActivityEvent:
        """
        Records an event into the short-term sliding window and persists
        medium- and high-importance events into SQLite.
        """
        with self._lock:
            self._events.append(event)
            self._active_event = event

            # Persist medium and high importance events to SQLite if database is connected
            if self.db and event.importance in (ActivityImportance.MEDIUM, ActivityImportance.HIGH):
                self._persist_event_to_db(event)

            logger.info(
                "ACTIVITY_RECORDED id=%s type=%s app=%s site=%s title=%r imp=%s",
                event.event_id,
                event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                event.application,
                event.website,
                event.content_title,
                event.importance.value if hasattr(event.importance, "value") else str(event.importance)
            )
            return event

    def _persist_event_to_db(self, event: ActivityEvent) -> None:
        """Saves a structured activity event into the SQLite proactive_activity_events table."""
        try:
            sql = """
            INSERT OR REPLACE INTO proactive_activity_events (
                event_id, event_type, importance, application,
                window_title, content_title, website, url,
                timestamp, confidence, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            meta_str = json.dumps(event.metadata) if event.metadata else "{}"
            type_str = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)
            imp_str = event.importance.value if hasattr(event.importance, "value") else str(event.importance)

            params = (
                event.event_id,
                type_str,
                imp_str,
                event.application,
                event.window_title,
                event.content_title,
                event.website,
                event.url,
                event.timestamp,
                event.confidence,
                meta_str
            )
            if hasattr(self.db, "execute_update"):
                self.db.execute_update(sql, params)
        except Exception as e:
            logger.debug("Failed to persist ActivityEvent to SQLite: %s", e)

    def get_current_context(self) -> Dict[str, Any]:
        """
        Returns a dictionary representing the live desktop context state.
        Used by contextual resolvers and dialogue managers.
        """
        with self._lock:
            if not self._active_event:
                return {
                    "application": "",
                    "window_title": "",
                    "website": None,
                    "content_title": None,
                    "event_type": None,
                    "is_video": False,
                    "is_document": False,
                    "timestamp": 0.0
                }

            ev = self._active_event
            is_video = bool(ev.event_type == ActivityType.VIDEO_PLAYED or (ev.metadata or {}).get("is_video"))
            is_doc = bool(ev.event_type == ActivityType.DOCUMENT_EDITED or (ev.metadata or {}).get("is_document"))

            return {
                "application": ev.application,
                "window_title": ev.window_title,
                "website": ev.website,
                "content_title": ev.content_title,
                "event_type": ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type),
                "is_video": is_video,
                "is_document": is_doc,
                "timestamp": ev.timestamp,
                "confidence": ev.confidence
            }

    def get_recent_events(
        self,
        limit: int = 10,
        min_importance: Optional[ActivityImportance] = None
    ) -> List[ActivityEvent]:
        """Returns recent activity events from the sliding memory buffer."""
        with self._lock:
            candidates = list(self._events)
            if min_importance:
                candidates = [c for c in candidates if c.importance == min_importance]
            return candidates[-limit:]

    def query_temporal(
        self,
        temporal: str = "current",
        offset_minutes: int = 0,
        website: Optional[str] = None,
        application: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> Optional[ActivityEvent]:
        """
        Queries activity events using temporal awareness:
        - "current" / "abhi": Currently active event.
        - "last" / "previous" / "pichla": Most recent completed/switched event.
        - "thodi_der_pehle": Event from 2-15 minutes ago.
        - offset_minutes > 0: Activity active around N minutes ago.
        """
        with self._lock:
            candidates = list(self._events)

            # Filter in-memory candidates
            filtered = self._apply_filters(candidates, website=website, application=application, event_type=event_type)

            now = time.time()

            # 1. Exact minutes ago offset query (e.g. "20 min pehle")
            if offset_minutes and offset_minutes > 0:
                target_time = now - (offset_minutes * 60)

                # Check in-memory window first
                best_mem = self._find_closest_event(filtered, target_time)
                if best_mem and abs(best_mem.timestamp - target_time) < 180:
                    return best_mem

                # Query persistent SQLite storage for older events
                if self.db:
                    db_event = self._query_db_by_time(target_time, website=website, application=application)
                    if db_event:
                        return db_event

                return best_mem

            # 2. "abhi" / "current" / "just_now"
            if temporal.lower() in ("current", "abhi", "just_now", "latest", "now"):
                if self._active_event and self._active_event in filtered:
                    return self._active_event
                return filtered[-1] if filtered else None

            # 3. "last" / "previous" / "pichla" / "pichli"
            if temporal.lower() in ("last", "previous", "pichla", "pichli", "pahle_wala"):
                if len(filtered) >= 2:
                    # Return event immediately preceding the active one
                    return filtered[-2]
                elif filtered:
                    return filtered[0]
                return None

            # 4. "thodi_der_pehle" / "earlier" (5 to 15 minutes ago)
            if temporal.lower() in ("thodi_der_pehle", "earlier", "pehle"):
                target_time = now - (8 * 60)
                best_earlier = self._find_closest_event(filtered, target_time)
                if best_earlier:
                    return best_earlier
                if len(filtered) >= 2:
                    return filtered[-2]
                return filtered[0] if filtered else None

            return filtered[-1] if filtered else None

    @staticmethod
    def _apply_filters(
        events: List[ActivityEvent],
        website: Optional[str] = None,
        application: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> List[ActivityEvent]:
        """Applies website, application, and event_type filters to a candidate list."""
        out = list(events)
        if website:
            w_clean = website.lower().strip()
            out = [e for e in out if e.website and e.website.lower() == w_clean]
        if application:
            a_clean = application.lower().strip()
            out = [e for e in out if e.application and e.application.lower() == a_clean]
        if event_type:
            e_clean = event_type.upper().strip()
            out = [
                e for e in out
                if (e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)).upper() == e_clean
            ]
        return out

    @staticmethod
    def _find_closest_event(events: List[ActivityEvent], target_time: float) -> Optional[ActivityEvent]:
        """Finds the event closest to the given unix timestamp."""
        if not events:
            return None
        return min(events, key=lambda e: abs(e.timestamp - target_time))

    def _query_db_by_time(
        self,
        target_time: float,
        website: Optional[str] = None,
        application: Optional[str] = None
    ) -> Optional[ActivityEvent]:
        """Queries the persistent SQLite database for the event closest to target_time."""
        if not self.db or not hasattr(self.db, "execute_query"):
            return None

        try:
            sql = "SELECT * FROM proactive_activity_events WHERE 1=1"
            params: List[Any] = []
            if website:
                sql += " AND lower(website) = ?"
                params.append(website.lower().strip())
            if application:
                sql += " AND lower(application) = ?"
                params.append(application.lower().strip())

            # Order by absolute distance from target_time
            sql += " ORDER BY abs(timestamp - ?) ASC LIMIT 1"
            params.append(target_time)

            rows = self.db.execute_query(sql, tuple(params))
            if rows:
                r = rows[0]
                meta = {}
                if r.get("metadata_json"):
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                ev_type = ActivityType(r["event_type"]) if r["event_type"] in ActivityType._value2member_map_ else ActivityType.WINDOW_CHANGED
                ev_imp = ActivityImportance(r["importance"]) if r["importance"] in ActivityImportance._value2member_map_ else ActivityImportance.MEDIUM
                return ActivityEvent(
                    event_id=r["event_id"],
                    event_type=ev_type,
                    importance=ev_imp,
                    application=r.get("application") or "",
                    window_title=r.get("window_title") or "",
                    content_title=r.get("content_title"),
                    website=r.get("website"),
                    url=r.get("url"),
                    timestamp=r["timestamp"],
                    confidence=r.get("confidence", 1.0),
                    metadata=meta
                )
        except Exception as e:
            logger.debug("Database temporal query error: %s", e)
        return None

    def prune_history(self, retention_days: int = 7, days: Optional[int] = None) -> int:
        """Deletes persistent activity events older than retention threshold."""
        if days is not None:
            retention_days = days
        if not self.db or not hasattr(self.db, "execute_update"):
            return 0
        try:
            cutoff = time.time() - (retention_days * 86400)
            sql = "DELETE FROM proactive_activity_events WHERE timestamp < ?"
            deleted = self.db.execute_update(sql, (cutoff,))
            logger.info("Pruned %d historical activity records older than %d days", deleted, retention_days)
            return deleted
        except Exception as e:
            logger.debug("History pruning failed: %s", e)
            return 0

    def clear(self) -> None:
        """Clears in-memory buffer."""
        with self._lock:
            self._events.clear()
            self._active_event = None
