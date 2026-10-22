"""Agent Observation Layer capturing ground truth OS state (processes, HWNDs, window states, files).
===================================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from typing import Any, Dict, List, Optional

from core.universal_window_resolver import get_universal_window_resolver

logger = logging.getLogger("jarvis.agent.observer")


@dataclass
class SystemObservation:
    """Snapshot of relevant OS state observed after tool execution."""
    foreground_hwnd: Optional[int] = None
    foreground_title: str = ""
    foreground_process: str = ""
    matching_windows: List[Dict[str, Any]] = field(default_factory=list)
    matching_processes: List[Dict[str, Any]] = field(default_factory=list)
    is_target_running: bool = False
    is_target_visible: bool = False
    is_target_minimized: bool = False
    is_target_maximized: bool = False
    file_exists: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "foreground_hwnd": self.foreground_hwnd,
            "foreground_title": self.foreground_title,
            "foreground_process": self.foreground_process,
            "matching_windows": self.matching_windows,
            "matching_processes": self.matching_processes,
            "is_target_running": self.is_target_running,
            "is_target_visible": self.is_target_visible,
            "is_target_minimized": self.is_target_minimized,
            "is_target_maximized": self.is_target_maximized,
            "file_exists": self.file_exists,
            "metadata": self.metadata,
        }


class AgentObserver:
    """Observes real-world operating system state, capturing process and window properties
    so the Agent operates on verified ground truth rather than blind assumptions.
    """

    def __init__(self):
        try:
            from plugins.windows.window_manager import WindowManager
            self.wm = WindowManager()
        except Exception:
            self.wm = None
        try:
            self.window_resolver = get_universal_window_resolver()
        except Exception:
            self.window_resolver = None

    def observe(self, target: Optional[str] = None) -> SystemObservation:
        """General observation method capturing target properties."""
        if target and (os.path.sep in target or "/" in target or ("." in target and not target.endswith(".exe"))):
            if os.path.exists(target):
                return self.observe_file(target)
        return self.observe_desktop(target_app_or_window=target)

    def observe_desktop(self, target_app_or_window: Optional[str] = None) -> SystemObservation:
        """Captures active foreground window and target application properties."""
        obs = SystemObservation()
        if not self.wm:
            return obs

        try:
            fg = self.wm.get_current_foreground_window()
            if fg:
                obs.foreground_hwnd = fg.hwnd
                obs.foreground_title = fg.title
                obs.foreground_process = fg.process_name
        except Exception as e:
            logger.debug("Failed to get foreground window: %s", e)

        if target_app_or_window and self.window_resolver:
            try:
                # 1. Inspect running windows
                windows = self.wm.list_all_windows()
                matched = self.window_resolver.match_windows(windows, target_app_or_window)
                for w in matched:
                    obs.matching_windows.append({
                        "hwnd": w.hwnd,
                        "title": w.title,
                        "process_name": w.process_name,
                        "minimized": w.minimized,
                        "visible": w.visible,
                    })

                if obs.matching_windows:
                    obs.is_target_running = True
                    obs.is_target_visible = any(w["visible"] for w in obs.matching_windows)
                    obs.is_target_minimized = all(w["minimized"] for w in obs.matching_windows)
                else:
                    # 2. Check if process is running without a visible window
                    obs.is_target_running = self.wm.is_process_running(target_app_or_window)
            except Exception as e:
                logger.error("Error observing target '%s': %s", target_app_or_window, e)

        return obs

    def observe_file(self, file_path: str) -> SystemObservation:
        """Observes filesystem state for a specified path."""
        obs = SystemObservation()
        exists = os.path.exists(file_path)
        obs.file_exists = exists
        if exists:
            obs.metadata = {
                "size_bytes": os.path.getsize(file_path),
                "is_dir": os.path.isdir(file_path),
            }
        return obs
