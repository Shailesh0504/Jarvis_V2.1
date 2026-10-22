# plugins/activity_monitor/memory.py
"""
Structured Activity and Event Memory.
Tracks active, switched, and closed application and media playback events with
temporal awareness and non-destructive finalization.
"""

from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("jarvis.plugins.activity_monitor.memory")


@dataclass
class ActivityEvent:
    """Structured record of an active or finalized user screen activity."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: str = "app_activity"          # "youtube_video_watched", "app_activity", "web_browsing"
    application: str = ""                      # e.g. "chrome", "brave", "msedge", "firefox", "vlc"
    website: str = ""                          # e.g. "youtube", "google"
    content_title: Optional[str] = None        # e.g. "Building an AI Assistant from Scratch"
    url: Optional[str] = None                  # e.g. "https://www.youtube.com/watch?v=..."
    start_time: float = field(default_factory=time.time)
    last_seen_time: float = field(default_factory=time.time)
    state: str = "active"                      # "active" or "closed"
    confidence: float = 1.0                    # 0.0 to 1.0
    source: str = "window_title"               # "window_title", "accessibility", "ocr", "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.last_seen_time - self.start_time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "application": self.application,
            "website": self.website,
            "content_title": self.content_title,
            "url": self.url,
            "start_time": self.start_time,
            "last_seen_time": self.last_seen_time,
            "duration_seconds": round(self.duration_seconds, 1),
            "state": self.state,
            "confidence": self.confidence,
            "source": self.source,
            "metadata": dict(self.metadata)
        }


class ActivityMemory:
    """
    Thread-safe structured activity and event store.
    Finalizes events on focus shifts / app closures instead of deleting them.
    """

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self._events: List[ActivityEvent] = []
        self._active_event: Optional[ActivityEvent] = None
        self._lock = threading.RLock()

    @property
    def active_event(self) -> Optional[ActivityEvent]:
        with self._lock:
            return self._active_event

    def record_or_update(
        self,
        application: str,
        website: str = "",
        content_title: Optional[str] = None,
        url: Optional[str] = None,
        event_type: str = "app_activity",
        source: str = "window_title",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ActivityEvent:
        """
        Updates the active event if application, site, and content title match.
        Otherwise finalizes previous active event and creates a new one.
        """
        with self._lock:
            now = time.time()
            app_clean = (application or "").lower().strip()
            site_clean = (website or "").lower().strip()
            title_clean = content_title.strip() if content_title else None

            # Check if active event continues the exact same content/app
            if (
                self._active_event
                and self._active_event.state == "active"
                and self._active_event.application.lower() == app_clean
                and self._active_event.website.lower() == site_clean
                and self._active_event.content_title == title_clean
            ):
                self._active_event.last_seen_time = now
                if url and not self._active_event.url:
                    self._active_event.url = url
                if confidence > self._active_event.confidence:
                    self._active_event.confidence = confidence
                    self._active_event.source = source
                if metadata:
                    self._active_event.metadata.update(metadata)
                return self._active_event

            # Content or application changed: finalize previous active event
            if self._active_event and self._active_event.state == "active":
                self._finalize_event_internal(self._active_event, reason="content_switched")

            # Create new active event
            new_event = ActivityEvent(
                event_type=event_type,
                application=app_clean,
                website=site_clean,
                content_title=title_clean,
                url=url,
                start_time=now,
                last_seen_time=now,
                state="active",
                confidence=confidence,
                source=source,
                metadata=metadata or {}
            )
            self._events.append(new_event)
            self._active_event = new_event

            if len(self._events) > self.max_history:
                self._events.pop(0)

            logger.info(
                "ACTIVITY_EVENT_CREATED event_id=%s type=%s app=%s site=%s title=%r source=%s conf=%.2f",
                new_event.event_id, new_event.event_type, app_clean, site_clean, title_clean, source, confidence
            )
            return new_event

    def finalize_active(self, reason: str = "app_closed") -> Optional[ActivityEvent]:
        """Finalizes the active activity event without deleting it."""
        with self._lock:
            if self._active_event and self._active_event.state == "active":
                finalized = self._finalize_event_internal(self._active_event, reason=reason)
                self._active_event = None
                return finalized
            return None

    def _finalize_event_internal(self, event: ActivityEvent, reason: str = "") -> ActivityEvent:
        event.state = "closed"
        event.last_seen_time = time.time()
        if reason:
            event.metadata["finalize_reason"] = reason
        logger.info(
            "ACTIVITY_EVENT_FINALIZED event_id=%s app=%s site=%s title=%r duration=%.1fs reason=%s",
            event.event_id, event.application, event.website, event.content_title, event.duration_seconds, reason
        )
        return event

    def query_temporal(
        self,
        website: Optional[str] = None,
        event_type: Optional[str] = None,
        temporal: str = "current",
        offset_minutes: int = 0
    ) -> Optional[ActivityEvent]:
        """
        Queries activity events using temporal awareness (abhi, last, thodi_der_pehle, N min ago).
        """
        with self._lock:
            candidates = list(self._events)
            if not candidates:
                return None

            # Filter by website or application if requested
            if website:
                w_lower = website.lower().strip()
                candidates = [
                    e for e in candidates
                    if e.website.lower() == w_lower
                    or w_lower in (e.website.lower(), e.application.lower())
                ]
            if event_type:
                candidates = [e for e in candidates if e.event_type == event_type]

            if not candidates:
                return None

            now = time.time()

            # 1. Exact minutes ago offset query (e.g. "20 minute pehle")
            if offset_minutes and offset_minutes > 0:
                target_time = now - (offset_minutes * 60)
                # Find event active around target_time
                best_event = None
                min_diff = float("inf")
                for e in candidates:
                    # Check overlap with [start_time, last_seen_time]
                    if (e.start_time - 120) <= target_time <= (e.last_seen_time + 120):
                        diff = abs(((e.start_time + e.last_seen_time) / 2) - target_time)
                        if diff < min_diff:
                            min_diff = diff
                            best_event = e
                if best_event:
                    return best_event
                # Fallback to closest event overall
                return min(candidates, key=lambda e: abs(e.last_seen_time - target_time))

            # 2. "abhi" / "current" / "just_now"
            if temporal in ("current", "abhi", "just_now", "latest"):
                # If currently active event matches
                if self._active_event and self._active_event in candidates:
                    return self._active_event
                # Or the most recently closed candidate
                return candidates[-1]

            # 3. "last" / "previous" / "pichla"
            if temporal in ("last", "previous", "pichla", "pichli"):
                if self._active_event and self._active_event in candidates:
                    # Return the event immediately preceding the active one
                    idx = candidates.index(self._active_event)
                    if idx > 0:
                        return candidates[idx - 1]
                    return self._active_event
                # If no active event, return the event before the most recent one, or the most recent
                if len(candidates) >= 2:
                    return candidates[-2]
                return candidates[-1]

            # 4. "thodi_der_pehle" / "a_while_ago"
            if temporal in ("thodi_der_pehle", "a_while_ago", "earlier"):
                if len(candidates) >= 2:
                    return candidates[-2]
                return candidates[-1]

            # 5. Default: most recent candidate
            return candidates[-1]

    def get_recent_events(self, limit: int = 10) -> List[ActivityEvent]:
        with self._lock:
            return list(self._events)[-limit:]

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._events[-limit:]]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._active_event = None
