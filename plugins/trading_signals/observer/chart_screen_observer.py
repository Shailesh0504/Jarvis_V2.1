# plugins/trading_signals/observer/chart_screen_observer.py
"""
Dedicated Desktop Screen & Window Observer for Trading Charts.
Operates as a non-blocking background daemon capturing target chart bounding boxes.
"""

from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable, Optional, Tuple

try:
    import cv2
    import numpy as np
    from PIL import ImageGrab
except ImportError:
    cv2 = None
    np = None
    ImageGrab = None

try:
    import win32gui
except ImportError:
    win32gui = None

logger = logging.getLogger("jarvis.trading.observer.screen")


class ChartScreenObserver(threading.Thread):
    """
    Background daemon continuously capturing the trading chart window
    and dispatching frames to visual extraction pipelines.
    """

    def __init__(
        self,
        window_title_filter: str = "tv.dhan.co",
        poll_interval: float = 0.5,
        on_frame_callback: Optional[Callable[["np.ndarray"], None]] = None
    ):
        super().__init__(name="JarvisChartScreenObserver", daemon=True)
        self.window_title_filter = window_title_filter.lower()
        self.poll_interval = max(0.2, float(poll_interval))
        self.on_frame_callback = on_frame_callback
        self._running = False
        self._stop_event = threading.Event()
        self._target_hwnd: Optional[int] = None

    def find_target_window(self) -> Optional[int]:
        """
        Locates the top-level window matching the trading URL or title filter.
        """
        if win32gui is None:
            return None

        found_hwnd: Optional[int] = None

        def enum_handler(hwnd, _):
            nonlocal found_hwnd
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if self.window_title_filter in title:
                    found_hwnd = hwnd

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception as e:
            logger.debug("[WINDOW_ENUM_FAIL] %s", e)

        # Fallback to foreground window if title contains filter
        if not found_hwnd:
            try:
                fg_hwnd = win32gui.GetForegroundWindow()
                if fg_hwnd:
                    title = win32gui.GetWindowText(fg_hwnd).lower()
                    if self.window_title_filter in title:
                        found_hwnd = fg_hwnd
            except Exception:
                pass

        self._target_hwnd = found_hwnd
        return found_hwnd

    def is_target_window_foreground(self) -> bool:
        """
        True if the target trading window is currently in foreground and not minimized.
        """
        if win32gui is None or not self._target_hwnd:
            # If Win32 is unavailable (e.g. testing), return True
            return True

        try:
            if win32gui.IsIconic(self._target_hwnd):
                return False
            fg = win32gui.GetForegroundWindow()
            return fg == self._target_hwnd
        except Exception:
            return False

    def capture_frame(self) -> Optional["np.ndarray"]:
        """
        Captures the active bounding box of the trading window.
        Returns: NumPy array in BGR format (ready for OpenCV), or None.
        """
        if ImageGrab is None or cv2 is None or np is None:
            return None

        hwnd = self.find_target_window()
        bbox = None

        if hwnd and win32gui:
            try:
                rect = win32gui.GetWindowRect(hwnd)
                # left, top, right, bottom
                if rect[2] > rect[0] and rect[3] > rect[1]:
                    bbox = rect
            except Exception as e:
                logger.debug("[WINDOW_RECT_FAIL] %s", e)

        try:
            # Grab window area if found, otherwise full screen
            pil_img = ImageGrab.grab(bbox=bbox)
            if pil_img:
                rgb_arr = np.array(pil_img)
                bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
                return bgr_arr
        except Exception as exc:
            logger.debug("[SCREEN_GRAB_FAIL] %s", exc)

        return None

    def poll_once(self) -> Optional["np.ndarray"]:
        """Executes a single frame capture and invokes registered callback."""
        frame = self.capture_frame()
        if frame is not None and self.on_frame_callback:
            try:
                self.on_frame_callback(frame)
            except Exception as e:
                logger.debug("[ON_FRAME_CALLBACK_ERROR] %s", e)
        return frame

    def run(self) -> None:
        """Background polling loop."""
        self._running = True
        logger.info(
            "ChartScreenObserver daemon started (filter='%s', poll_interval=%.2fs)",
            self.window_title_filter,
            self.poll_interval
        )
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval)
        self._running = False
        logger.info("ChartScreenObserver daemon stopped cleanly.")

    def stop(self) -> None:
        """Signals background thread to terminate."""
        self._stop_event.set()
