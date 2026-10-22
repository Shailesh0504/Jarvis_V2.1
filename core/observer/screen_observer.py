# core/observer/screen_observer.py
"""
Lightweight Windows Screen & Attention Observer.
Tracks system-wide user idle time and input activity via Win32 GetLastInputInfo.
Operates with zero screen captures, zero OCR, and negligible CPU overhead.
"""

import ctypes
from ctypes import wintypes
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.core.observer.screen")


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class ScreenObserver:
    """
    Monitors user activity and attention state via Win32 GetLastInputInfo.
    Detects transitions between active user engagement and idle states.
    """

    def __init__(self, idle_threshold_sec: float = 5.0):
        self.idle_threshold_sec = max(1.0, idle_threshold_sec)
        self._user32 = None
        self._kernel32 = None
        self._was_idle = False
        self._last_input_time = time.time()
        self._init_win32()

    def _init_win32(self) -> None:
        """Initializes Win32 library references safely."""
        try:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
        except Exception as e:
            logger.debug("Win32 ctypes initialization failed: %s", e)
            self._user32 = None
            self._kernel32 = None

    def get_idle_seconds(self) -> float:
        """
        Calculates seconds elapsed since the last system-wide keyboard or mouse input.
        Returns 0.0 if Win32 APIs are unavailable.
        """
        if not self._user32 or not self._kernel32:
            return 0.0

        try:
            plii = LASTINPUTINFO()
            plii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if self._user32.GetLastInputInfo(ctypes.byref(plii)):
                # GetTickCount returns milliseconds since system startup
                millis = self._kernel32.GetTickCount() - plii.dwTime
                return max(0.0, float(millis) / 1000.0)
            return 0.0
        except Exception as e:
            logger.debug("GetLastInputInfo query failed: %s", e)
            return 0.0

    def check_attention_state(self) -> Tuple[float, bool, Optional[str]]:
        """
        Evaluates current user attention state.

        Returns:
            Tuple of (idle_seconds, is_idle, transition)
            transition is 'became_idle', 'became_active', or None.
        """
        idle_secs = self.get_idle_seconds()
        is_idle = idle_secs >= self.idle_threshold_sec
        transition: Optional[str] = None

        if is_idle and not self._was_idle:
            transition = "became_idle"
            self._was_idle = True
        elif not is_idle and self._was_idle:
            transition = "became_active"
            self._was_idle = False

        return idle_secs, is_idle, transition

    def reset_state(self) -> None:
        """Resets the internal transition state."""
        self._was_idle = False
