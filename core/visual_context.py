# core/visual_context.py
"""
Visual Context Engine: Live Focused Window, Process, Active Tab & Viewport Capture.

Authoritative manager for capturing the active application state before Jarvis
UI/overlay takes focus:
1. Identifies foreground HWND, process name, window title, and bounding rectangle.
2. Strict Jarvis Self-Exclusion: Jarvis GUI, notification overlays, and toasts are
   never targeted for visual interaction.
3. Browser Context: Identifies active browser (Chrome, Brave, Edge, Firefox) and tab title.
4. Modal / Dialog Priority: Detects if the focused window is a modal popup or child dialog.
5. DPI Awareness: Computes monitor DPI scale factor for coordinate conversions.
"""

from dataclasses import dataclass, field
import logging
import os
import psutil
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.visual_context")


@dataclass
class VisualContext:
    hwnd: int = 0
    title: str = ""
    process_name: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    is_browser: bool = False
    browser_name: str = ""
    active_tab: str = ""
    is_dialog: bool = False
    dpi_scale: float = 1.0
    client_rect: Tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def left(self) -> int:
        return self.rect[0]

    @property
    def top(self) -> int:
        return self.rect[1]

    @property
    def right(self) -> int:
        return self.rect[2]

    @property
    def bottom(self) -> int:
        return self.rect[3]

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "process_name": self.process_name,
            "rect": self.rect,
            "is_browser": self.is_browser,
            "browser_name": self.browser_name,
            "active_tab": self.active_tab,
            "is_dialog": self.is_dialog,
            "dpi_scale": self.dpi_scale
        }


class VisualContextManager:
    """Manages active viewport context and window inspection targeting."""

    _instance = None

    # Known browser executable names
    KNOWN_BROWSERS = {
        "chrome.exe": "chrome",
        "brave.exe": "brave",
        "msedge.exe": "edge",
        "firefox.exe": "firefox",
        "opera.exe": "opera",
        "vivaldi.exe": "vivaldi"
    }

    # Jarvis self-exclusion process and window title patterns
    JARVIS_EXCLUSION_PATTERNS = [
        re.compile(r"^jarvis", re.IGNORECASE),
        re.compile(r"jarvis\s+assistant", re.IGNORECASE),
        re.compile(r"jarvis_v2", re.IGNORECASE),
        re.compile(r"antigravity", re.IGNORECASE),
        re.compile(r"pythonw?\.exe$", re.IGNORECASE)
    ]

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._current_pid = os.getpid()

    def is_jarvis_window(self, hwnd: int, title: str, proc_name: str, pid: int = 0) -> bool:
        """Returns True if the given window belongs to Jarvis itself or the assistant GUI."""
        if pid and pid == self._current_pid:
            return True
        p_lower = proc_name.lower().strip()
        t_lower = title.lower().strip()

        if t_lower in ("jarvis", "jarvis assistant", "jarvis v2", "jarvis hud", "jarvis ui"):
            return True

        if "jarvis" in t_lower and ("assistant" in t_lower or "dashboard" in t_lower):
            return True

        return False

    def get_dpi_scale_for_window(self, hwnd: int) -> float:
        """Returns DPI scaling factor for the specified window (e.g. 1.0, 1.25, 1.5, 2.0)."""
        try:
            import ctypes
            # GetDpiForWindow is available on Windows 10 (version 1607) and Windows 11
            if hasattr(ctypes.windll.user32, "GetDpiForWindow") and hwnd:
                dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                if dpi > 0:
                    return round(dpi / 96.0, 2)
        except Exception:
            pass
        return 1.0

    def capture_focused_context(self, explicit_hwnd: Optional[int] = None) -> VisualContext:
        """
        Captures the live user-focused window before Jarvis takes focus.
        If the foreground window is Jarvis itself, walks the window Z-order to find
        the most recent user application.
        """
        ctx = VisualContext()

        try:
            import win32gui
            import win32process
        except ImportError:
            # Headless / mock environment
            ctx.title = "Mock Application"
            ctx.process_name = "app.exe"
            ctx.rect = (0, 0, 1920, 1080)
            return ctx

        hwnd = explicit_hwnd or win32gui.GetForegroundWindow()

        # Check if the foreground window is valid and not Jarvis itself
        if hwnd:
            try:
                title = (win32gui.GetWindowText(hwnd) or "").strip()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = ""
                try:
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    pass

                # If the foreground window is Jarvis's own UI or invisible, find previous window in Z-order
                if self.is_jarvis_window(hwnd, title, proc_name, pid):
                    hwnd = self._find_underlying_user_window()
            except Exception as ex:
                logger.debug(f"Error inspecting initial foreground window: {ex}")
                hwnd = self._find_underlying_user_window()

        if not hwnd:
            hwnd = self._find_underlying_user_window()

        if not hwnd:
            # Desktop fallback
            ctx.title = "Desktop"
            ctx.rect = (0, 0, 1920, 1080)
            return ctx

        # Populate context from resolved HWND
        try:
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            rect = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = ""
            try:
                proc_name = psutil.Process(pid).name()
            except Exception:
                pass

            p_lower = proc_name.lower()
            is_browser = p_lower in self.KNOWN_BROWSERS
            browser_name = self.KNOWN_BROWSERS.get(p_lower, "")
            dpi = self.get_dpi_scale_for_window(hwnd)

            # Check if modal or child dialog
            parent = win32gui.GetParent(hwnd)
            is_dialog = bool(parent and parent != 0)

            # Active browser tab extraction
            active_tab = ""
            if is_browser and title:
                # Strip browser suffix (e.g. " - Google Chrome")
                active_tab = re.sub(r'\s*-\s*(Google Chrome|Brave|Microsoft Edge|Mozilla Firefox|Opera)$', '', title, flags=re.IGNORECASE).strip()

            ctx.hwnd = hwnd
            ctx.title = title
            ctx.process_name = proc_name
            ctx.rect = rect
            ctx.is_browser = is_browser
            ctx.browser_name = browser_name
            ctx.active_tab = active_tab
            ctx.is_dialog = is_dialog
            ctx.dpi_scale = dpi

            logger.info(
                f"[VISUAL_CONTEXT] Captured focused window: hwnd={hwnd} title='{title[:35]}' "
                f"proc='{proc_name}' browser={is_browser} dpi={dpi}"
            )
        except Exception as e:
            logger.debug(f"Error reading window details for hwnd={hwnd}: {e}")

        return ctx

    def _find_underlying_user_window(self) -> Optional[int]:
        """Finds the top-most visible user window that is NOT Jarvis and NOT the desktop background."""
        try:
            import win32gui
            import win32process

            found_hwnd = None

            def enum_proc(hwnd, _):
                nonlocal found_hwnd
                if found_hwnd:
                    return
                if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                    return
                if win32gui.IsIconic(hwnd):
                    return

                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w < 100 or h < 100:
                    return

                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if not title:
                    return
                if title in ("Program Manager", "Settings", "Task Switching", "Windows Input Experience"):
                    return

                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    proc_name = ""
                    pid = 0

                if self.is_jarvis_window(hwnd, title, proc_name, pid):
                    return

                found_hwnd = hwnd

            win32gui.EnumWindows(enum_proc, None)
            return found_hwnd
        except Exception as e:
            logger.debug(f"Error finding underlying user window: {e}")
            return None


_visual_context_instance: Optional[VisualContextManager] = None


def get_visual_context_manager() -> VisualContextManager:
    """Returns singleton instance of VisualContextManager."""
    global _visual_context_instance
    if _visual_context_instance is None:
        _visual_context_instance = VisualContextManager()
    return _visual_context_instance
