# plugins/activity_monitor/observer.py
"""
Silent Background Activity Observer for Jarvis V2.
Periodically polls the active foreground window, detects media/content changes,
and records activities into ActivityMemory without speaking or interrupting the user.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .extractors import YouTubeTitleExtractor
from .memory import ActivityEvent, ActivityMemory

logger = logging.getLogger("jarvis.plugins.activity_monitor.observer")


class ActivityObserver(threading.Thread):
    """
    Daemon thread that passively monitors active foreground windows and media.
    Strictly silent: Never speaks, beeps, or disrupts voice listener or user workflow.
    """

    def __init__(
        self,
        memory: ActivityMemory,
        extractor: Optional[YouTubeTitleExtractor] = None,
        poll_interval: float = 3.0,
        window_manager: Optional[Any] = None,
        on_activity_callback: Optional[Callable[[ActivityEvent], None]] = None
    ):
        super().__init__(name="JarvisActivityObserver", daemon=True)
        self.memory = memory
        self.extractor = extractor or YouTubeTitleExtractor()
        self.poll_interval = max(0.5, poll_interval)
        self.window_manager = window_manager
        self.on_activity_callback = on_activity_callback

        self._running = False
        self._stop_event = threading.Event()
        self._last_hwnd: Optional[int] = None
        self._last_title: str = ""

    @property
    def is_active(self) -> bool:
        return self._running and not self._stop_event.is_set()

    def get_active_window_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves active window details via WindowManager or native Win32 ctypes.
        """
        # Try custom WindowManager if injected
        if self.window_manager and hasattr(self.window_manager, "get_foreground_window"):
            try:
                win = self.window_manager.get_foreground_window()
                if win:
                    return {
                        "hwnd": getattr(win, "hwnd", 0),
                        "title": getattr(win, "title", ""),
                        "process_name": getattr(win, "process_name", "")
                    }
            except Exception as e:
                logger.debug("WindowManager get_foreground_window failed: %s", e)

        # Fallback to direct Win32 ctypes
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

            pname = ""
            try:
                import psutil
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pname = psutil.Process(pid.value).name()
            except Exception:
                pass

            return {
                "hwnd": hwnd,
                "title": title,
                "process_name": pname
            }
        except Exception as e:
            logger.debug("Direct Win32 foreground inspection failed: %s", e)
            return None

    def poll_once(self) -> Optional[ActivityEvent]:
        """
        Performs a single observation cycle.
        Extracts activity details, updates ActivityMemory, and triggers callbacks.
        Returns the recorded ActivityEvent or None.
        """
        try:
            info = self.get_active_window_info()
            if not info or not info.get("title"):
                # No active window detected; finalize active event if present
                if self.memory.active_event:
                    self.memory.finalize_active(reason="no_active_window")
                self._last_hwnd = None
                self._last_title = ""
                return None

            hwnd = info.get("hwnd", 0)
            raw_title = info.get("title", "")
            process_name = info.get("process_name", "")

            # Perform multi-tier media and content extraction
            extracted = self.extractor.extract(
                raw_title=raw_title,
                process_name=process_name,
                hwnd=hwnd
            )

            app = extracted.get("application", "")
            site = extracted.get("website", "")
            content_title = extracted.get("content_title")
            conf = extracted.get("confidence", 0.0)
            src = extracted.get("source", "window_title")
            url = extracted.get("url")
            is_video = extracted.get("is_video", False)

            if is_video and content_title:
                event_type = "youtube_video_watched" if site == "youtube" else "video_watched"
            elif site:
                event_type = f"{site}_activity"
            else:
                event_type = "app_activity"

            # Record or update in structured memory
            event = self.memory.record_or_update(
                application=app,
                website=site,
                content_title=content_title,
                url=url,
                event_type=event_type,
                source=src,
                confidence=conf,
                metadata={"hwnd": hwnd, "raw_title": raw_title}
            )

            self._last_hwnd = hwnd
            self._last_title = raw_title

            if self.on_activity_callback and event:
                try:
                    self.on_activity_callback(event)
                except Exception as cb_err:
                    logger.debug("on_activity_callback error: %s", cb_err)

            return event

        except Exception as e:
            logger.debug("ActivityObserver poll_once error: %s", e)
            return None

    def run(self) -> None:
        """Background thread execution loop."""
        self._running = True
        logger.info("ActivityObserver background daemon started (poll_interval=%.1fs)", self.poll_interval)
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval)
        self._running = False
        logger.info("ActivityObserver background daemon stopped")

    def stop(self) -> None:
        """Signals the observer to terminate cleanly."""
        self._stop_event.set()
