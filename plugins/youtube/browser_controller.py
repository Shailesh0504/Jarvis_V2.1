# plugins/youtube/browser_controller.py
"""Browser selection, navigation and coordinate-free media controls."""

from dataclasses import dataclass
import logging
import os
import re
import shutil
import subprocess
import time
import webbrowser
from typing import Optional

import psutil

logger = logging.getLogger("jarvis.plugins.youtube.browser")


@dataclass(frozen=True)
class BrowserOpenResult:
    success: bool
    browser_name: str
    executable: str = ""
    reused: bool = False
    error: str = ""


class YouTubeBrowserController:
    def __init__(self):
        self._brave_checked = False
        self._brave_path: Optional[str] = None

    def detect_brave_path(self) -> Optional[str]:
        path = shutil.which("brave") or shutil.which("brave.exe")
        candidates = [
            path,
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
        return next((item for item in candidates if item and os.path.isfile(item)), None)

    def get_brave_executable(self) -> Optional[str]:
        if not self._brave_checked:
            self._brave_path = self.detect_brave_path()
            self._brave_checked = True
        return self._brave_path

    def open_url(self, url: str) -> BrowserOpenResult:
        brave = self.get_brave_executable()
        if brave:
            try:
                # Brave reuses the existing browser process/profile when running.
                reused = any(
                    (process.info.get("name") or "").casefold() == "brave.exe"
                    for process in psutil.process_iter(["name"])
                )
                subprocess.Popen([brave, url])
                logger.info("BROWSER_SELECTED browser=Brave executable=%r", brave)
                logger.info("WATCH_URL_OPENED url=%s", url)
                return BrowserOpenResult(True, "Brave", brave, reused=reused)
            except OSError as exc:
                logger.warning("Brave launch failed; using default browser: %s", exc)
        try:
            opened = bool(webbrowser.open(url))
            if not opened:
                return BrowserOpenResult(False, "Default Browser", error="Default browser rejected the URL.")
            logger.info("BROWSER_SELECTED browser=Default")
            logger.info("WATCH_URL_OPENED url=%s", url)
            return BrowserOpenResult(True, "Default Browser")
        except Exception as exc:
            return BrowserOpenResult(False, "Default Browser", error=str(exc))

    def send_media_key(self, key: str, presses: int = 1) -> bool:
        """Sends resilient keyboard controls to the active browser without coordinates."""
        try:
            import pyautogui
            for _ in range(max(1, presses)):
                pyautogui.press(key)
                time.sleep(0.03)
            return True
        except Exception as exc:
            logger.warning("Browser media control unavailable: %s", exc)
            return False

    def seek(self, seconds: int) -> bool:
        key = "right" if seconds >= 0 else "left"
        return self.send_media_key(key, max(1, abs(seconds) // 5))
