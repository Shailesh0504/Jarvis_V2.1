# core/observer/activity_observer.py
"""
Unified Proactive Activity Observer Daemon for Jarvis V2.
Coordinates WindowObserver, ScreenObserver, ContentExtractor, and VolumeObserver
in a non-blocking background thread with content-level deduplication.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .content_extractor import ContentExtractor
from .models import ActivityEvent, ActivityImportance, ActivityType, DesktopSnapshot
from .screen_observer import ScreenObserver
from .volume_observer import VolumeObserver
from .window_observer import WindowObserver

logger = logging.getLogger("jarvis.core.observer.activity")


class ProactiveActivityObserver(threading.Thread):
    """
    Continuous background observer that tracks foreground window shifts,
    application transitions, web and media content, volume alterations,
    and user idle/attention states with multi-level deduplication.
    Strictly non-intrusive and resilient against Win32 errors.
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        idle_threshold_sec: float = 5.0,
        window_manager: Optional[Any] = None,
        content_extractor: Optional[ContentExtractor] = None,
        volume_observer: Optional[VolumeObserver] = None,
        memory: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        on_activity_callback: Optional[Callable[[ActivityEvent], None]] = None,
        enabled: bool = True
    ):
        super().__init__(name="JarvisProactiveActivityObserver", daemon=True)
        self.poll_interval = max(0.5, poll_interval)
        self.enabled = enabled
        self.memory = memory
        self.event_bus = event_bus
        self.on_activity_callback = on_activity_callback

        self.window_observer = WindowObserver(window_manager=window_manager)
        self.screen_observer = ScreenObserver(idle_threshold_sec=idle_threshold_sec)
        self.content_extractor = content_extractor or ContentExtractor()
        self.volume_observer = volume_observer or VolumeObserver()

        self._running = False
        self._stop_event = threading.Event()
        self._listeners: List[Callable[[ActivityEvent], None]] = []
        if on_activity_callback:
            self._listeners.append(on_activity_callback)

        # State tracking for deduplication
        self._last_snapshot: Optional[DesktopSnapshot] = None
        self._last_content_title: Optional[str] = None
        self._last_website: Optional[str] = None
        self._last_event: Optional[ActivityEvent] = None
        self._lock = threading.RLock()

    @property
    def is_active(self) -> bool:
        """Returns True if the background observer loop is running."""
        return self._running and not self._stop_event.is_set()

    @property
    def is_running(self) -> bool:
        """Returns True if the background observer loop is running."""
        return self.is_active

    def add_listener(self, callback: Callable[[ActivityEvent], None]) -> None:
        """Registers a listener callback for activity events."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ActivityEvent], None]) -> None:
        """Removes a registered listener callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def dispatch_event(self, event: ActivityEvent) -> None:
        """Dispatches an ActivityEvent to memory, registered listeners, and EventBus."""
        self._last_event = event

        # Auto-record in ActivityMemory if connected
        if self.memory and hasattr(self.memory, "record_event"):
            try:
                self.memory.record_event(event)
            except Exception as mem_err:
                logger.debug("Activity observer memory record error: %s", mem_err)

        with self._lock:
            listeners_snapshot = list(self._listeners)

        for listener in listeners_snapshot:
            try:
                listener(event)
            except Exception as e:
                logger.debug("Activity observer listener callback error: %s", e)

        if self.event_bus and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("activity.observed", event.to_dict())
            except Exception as bus_err:
                logger.debug("Activity observer EventBus emit error: %s", bus_err)

    def poll_once(self) -> Optional[ActivityEvent]:
        """
        Executes a single observation cycle.
        Checks for volume changes, attention transitions, and window/content switches.
        Returns the emitted ActivityEvent if state changed, or None.
        """
        if not self.enabled:
            return None

        try:
            # 1. Check for Hardware Master Volume Alterations
            vol_changed, old_vol, new_vol, is_muted = self.volume_observer.check_volume_change()
            if vol_changed:
                app_name = self._last_snapshot.process_name if self._last_snapshot else "system"
                win_title = self._last_snapshot.title if self._last_snapshot else ""
                vol_event = ActivityEvent(
                    event_type=ActivityType.VOLUME_CHANGED,
                    importance=ActivityImportance.MEDIUM,
                    application=app_name,
                    window_title=win_title,
                    metadata={"old_volume": old_vol, "new_volume": new_vol, "muted": is_muted}
                )
                self.dispatch_event(vol_event)
                return vol_event

            # 2. Check Attention / Idle Transitions
            idle_secs, is_idle, transition = self.screen_observer.check_attention_state()
            if transition == "became_idle":
                idle_event = ActivityEvent(
                    event_type=ActivityType.USER_IDLE,
                    importance=ActivityImportance.LOW,
                    application=self._last_snapshot.process_name if self._last_snapshot else "",
                    window_title=self._last_snapshot.title if self._last_snapshot else "",
                    metadata={"idle_seconds": round(idle_secs, 1)}
                )
                self.dispatch_event(idle_event)
                return idle_event

            elif transition == "became_active":
                active_event = ActivityEvent(
                    event_type=ActivityType.USER_ACTIVE,
                    importance=ActivityImportance.LOW,
                    application=self._last_snapshot.process_name if self._last_snapshot else "",
                    window_title=self._last_snapshot.title if self._last_snapshot else "",
                    metadata={"resumed_from_idle": True}
                )
                self.dispatch_event(active_event)
                return active_event

            # 3. Inspect Foreground Window
            snapshot = self.window_observer.get_foreground_snapshot()
            if not snapshot or not snapshot.is_valid:
                return None

            # 4. Extract Semantic Content (Website, Video, Document, Query)
            content_info = self.content_extractor.extract(snapshot.title, snapshot.process_name)
            content_title = content_info.get("content_title")
            website = content_info.get("website")

            # 5. Content-Level Deduplication
            if self._last_snapshot and (
                self._last_snapshot.hwnd == snapshot.hwnd
                and self._last_snapshot.title == snapshot.title
                and self._last_snapshot.process_name == snapshot.process_name
                and self._last_content_title == content_title
                and self._last_website == website
            ):
                return None

            # 6. Event Classification & Importance Tagging
            app_changed = bool(
                not self._last_snapshot
                or self._last_snapshot.process_name != snapshot.process_name
            )

            is_video = content_info.get("is_video", False)
            is_doc = content_info.get("is_document", False)

            if is_video and content_title:
                event_type = ActivityType.VIDEO_PLAYED
                importance = ActivityImportance.HIGH
            elif is_doc and content_title:
                event_type = ActivityType.DOCUMENT_EDITED
                importance = ActivityImportance.MEDIUM
            elif website:
                if app_changed or self._last_website != website:
                    event_type = ActivityType.WEBSITE_OPENED
                else:
                    event_type = ActivityType.PAGE_CHANGED
                importance = ActivityImportance.MEDIUM
            elif app_changed:
                event_type = ActivityType.APPLICATION_OPENED
                importance = ActivityImportance.MEDIUM
            else:
                event_type = ActivityType.WINDOW_CHANGED
                importance = ActivityImportance.LOW

            event = ActivityEvent(
                event_type=event_type,
                importance=importance,
                application=snapshot.process_name,
                window_title=snapshot.title,
                content_title=content_title,
                website=website,
                confidence=content_info.get("confidence", 1.0),
                metadata={
                    "hwnd": snapshot.hwnd,
                    "previous_app": self._last_snapshot.process_name if self._last_snapshot else "",
                    "category": content_info.get("category", "app"),
                    "app_changed": app_changed
                }
            )

            self._last_snapshot = snapshot
            self._last_content_title = content_title
            self._last_website = website
            self.dispatch_event(event)
            return event

        except Exception as exc:
            logger.debug("ProactiveActivityObserver poll_once error: %s", exc)
            return None

    def run(self) -> None:
        """Background daemon polling loop."""
        self._running = True
        logger.info(
            "ProactiveActivityObserver daemon started (poll_interval=%.1fs, idle_thresh=%.1fs)",
            self.poll_interval,
            self.screen_observer.idle_threshold_sec
        )
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval)
        self._running = False
        logger.info("ProactiveActivityObserver daemon stopped cleanly")

    def stop(self) -> None:
        """Signals the background thread to terminate."""
        self._stop_event.set()
