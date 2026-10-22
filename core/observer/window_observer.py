# core/observer/window_observer.py
"""
Safe, throttled Windows foreground window observer.
Extracts active window details, process names, and normalized application identities
without polling heavy UI trees or causing thread blocking.
"""

import ctypes
from ctypes import wintypes
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from .models import DesktopSnapshot

logger = logging.getLogger("jarvis.core.observer.window")

# Common process name normalization mappings
PROCESS_APP_MAP: Dict[str, str] = {
    "chrome.exe": "chrome",
    "brave.exe": "brave",
    "msedge.exe": "edge",
    "firefox.exe": "firefox",
    "code.exe": "vscode",
    "notepad.exe": "notepad",
    "excel.exe": "excel",
    "winword.exe": "word",
    "powerpnt.exe": "powerpoint",
    "vlc.exe": "vlc",
    "spotify.exe": "spotify",
    "windowsterminal.exe": "terminal",
    "powershell.exe": "powershell",
    "cmd.exe": "cmd",
    "explorer.exe": "explorer",
    "calculatorapp.exe": "calculator",
    "calculator.exe": "calculator",
}

BROWSER_PROCESSES = {"chrome", "brave", "edge", "firefox"}


class WindowObserver:
    """
    Lightweight Win32 foreground window observer.
    Extracts current hwnd, title, process, and application identity.
    """

    def __init__(self, window_manager: Optional[Any] = None):
        self.window_manager = window_manager
        self._user32 = None
        self._init_win32()

    def _init_win32(self) -> None:
        """Initializes Win32 user32 handle safely."""
        try:
            self._user32 = ctypes.windll.user32
        except Exception as e:
            logger.debug("Win32 ctypes initialization failed: %s", e)
            self._user32 = None

    def normalize_process_name(self, raw_process: str) -> str:
        """Maps executable filenames to standardized application identifiers."""
        if not raw_process:
            return ""
        low = raw_process.lower().strip()
        if low in PROCESS_APP_MAP:
            return PROCESS_APP_MAP[low]
        # Strip .exe if present
        clean = re.sub(r"\.exe$", "", low, flags=re.IGNORECASE)
        return clean

    def get_foreground_snapshot(self) -> Optional[DesktopSnapshot]:
        """
        Retrieves the current foreground window snapshot.
        Returns DesktopSnapshot if an active window exists, or None.
        """
        # Try custom WindowManager if injected
        if self.window_manager and hasattr(self.window_manager, "get_foreground_window"):
            try:
                win = self.window_manager.get_foreground_window()
                if win and getattr(win, "hwnd", 0):
                    hwnd = getattr(win, "hwnd", 0)
                    raw_title = getattr(win, "title", "").strip()
                    proc = getattr(win, "process_name", "")
                    norm_app = self.normalize_process_name(proc)
                    rect = getattr(win, "rect", (0, 0, 0, 0))
                    return DesktopSnapshot(
                        hwnd=hwnd,
                        title=raw_title,
                        process_name=norm_app or proc,
                        rect=rect if isinstance(rect, tuple) else (0, 0, 0, 0)
                    )
            except Exception as wm_err:
                logger.debug("WindowManager foreground inspection failed: %s", wm_err)

        # Fallback to direct Win32 ctypes
        if not self._user32:
            return None

        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = self._user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

            pname = ""
            try:
                import psutil
                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    proc_obj = psutil.Process(pid.value)
                    pname = proc_obj.name()
            except Exception:
                pass

            norm_app = self.normalize_process_name(pname)
            return DesktopSnapshot(
                hwnd=hwnd,
                title=title,
                process_name=norm_app or pname
            )

        except Exception as e:
            logger.debug("Direct Win32 foreground inspection error: %s", e)
            return None
