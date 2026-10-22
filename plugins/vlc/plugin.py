# plugins/vlc/plugin.py
"""VLC Plugin implementation for controlling VLC media player playback, volume, and hotkeys."""

import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional
import psutil

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.vlc")


class VLCPlugin(BasePlugin):
    """Controls VLC Media playback, process lifecycle, and hotkey actions."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="vlc",
            version="2.0.0",
            description="Controls VLC media player launch, playback, window, and audio controls.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def check_dependencies(self) -> bool:
        return self._locate_vlc() is not None or self._get_vlc_pids() != []

    def _locate_vlc(self) -> Optional[str]:
        """Discovers VLC executable path across common Windows locations and PATH."""
        candidates = [
            shutil.which("vlc"),
            os.path.expandvars(r"%ProgramFiles%\VideoLAN\VLC\vlc.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"),
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def _get_vlc_pids(self) -> List[int]:
        """Returns PIDs of all actively running VLC instances."""
        pids = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if (proc.info.get("name") or "").lower() in ("vlc.exe", "vlc"):
                    pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return pids

    def _focus_vlc_window(self) -> bool:
        """Finds and brings the VLC window to the foreground."""
        try:
            import win32gui
            import win32con

            target_hwnd = None

            def enum_cb(hwnd, _):
                nonlocal target_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if "vlc media player" in title.lower():
                        target_hwnd = hwnd

            win32gui.EnumWindows(enum_cb, None)
            if target_hwnd:
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(target_hwnd)
                time.sleep(0.1)
                return True
        except Exception as e:
            logger.debug("Could not focus VLC window via Win32: %s", e)
        return False

    def _send_vlc_hotkey(self, keys: List[str]) -> bool:
        """Sends keystroke combination to VLC player."""
        self._focus_vlc_window()
        try:
            import pyautogui
            if len(keys) == 1:
                pyautogui.press(keys[0])
            else:
                pyautogui.hotkey(*keys)
            return True
        except Exception as e:
            logger.debug("Failed sending hotkey %s: %s", keys, e)
            return False

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "stop_playback":
            running = len(self._get_vlc_pids()) > 0
            return VerificationResult(
                verified=not running,
                state=ExecutionState.SUCCESS if not running else ExecutionState.FAILED,
                check_type="process_stopped",
                expected="vlc terminated",
                actual="stopped" if not running else "still running",
                message="VLC process termination verified." if not running else "VLC process still active."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. play_file
        if action_name == "play_file":
            media_path = parameters.get("path", "").strip()
            vlc_exe = self._locate_vlc()

            if media_path and not os.path.exists(media_path):
                return PluginResult(success=False, error=f"Media file not found: '{media_path}'")

            try:
                if vlc_exe:
                    cmd = [vlc_exe]
                    if media_path:
                        cmd.append(media_path)
                    subprocess.Popen(cmd)
                else:
                    if media_path:
                        subprocess.Popen(f'start "" "{media_path}"', shell=True)
                    else:
                        subprocess.Popen("start vlc", shell=True)

                filename = os.path.basename(media_path) if media_path else "VLC Media Player"
                return PluginResult(
                    success=True,
                    data={"path": media_path, "message": f"Playing '{filename}' in VLC."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Could not open VLC: {e}")

        # 2. stop_playback
        elif action_name == "stop_playback":
            pids = self._get_vlc_pids()
            if not pids:
                return PluginResult(
                    success=True,
                    data={"stopped_count": 0, "message": "VLC media player is not currently running."}
                )

            stopped = 0
            for pid in pids:
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                    stopped += 1
                except Exception:
                    pass

            time.sleep(0.3)
            remaining = self._get_vlc_pids()
            for pid in remaining:
                try:
                    psutil.Process(pid).kill()
                except Exception:
                    pass

            return PluginResult(
                success=True,
                data={"stopped_count": stopped, "message": f"Stopped {stopped} VLC media player process(es)."}
            )

        # 3. is_vlc_running
        elif action_name == "is_vlc_running":
            pids = self._get_vlc_pids()
            is_running = len(pids) > 0
            return PluginResult(
                success=True,
                data={
                    "running": is_running,
                    "count": len(pids),
                    "pids": pids,
                    "message": f"VLC is currently {'running with ' + str(len(pids)) + ' process(es)' if is_running else 'stopped'}."
                }
            )

        # 4. find_vlc_executable
        elif action_name == "find_vlc_executable":
            vlc_path = self._locate_vlc()
            return PluginResult(
                success=vlc_path is not None,
                data={"vlc_path": vlc_path, "message": f"VLC executable found at: {vlc_path}" if vlc_path else "VLC executable not found on this system."},
                error=None if vlc_path else "VLC executable could not be found."
            )

        # 5. pause_resume_vlc
        elif action_name == "pause_resume_vlc":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["space"])
            return PluginResult(success=ok, data={"action": "pause_resume", "message": "Toggled VLC playback pause/resume."})

        # 6. vlc_fullscreen_toggle
        elif action_name == "vlc_fullscreen_toggle":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["f"])
            return PluginResult(success=ok, data={"action": "fullscreen_toggle", "message": "Toggled VLC fullscreen mode."})

        # 7. vlc_volume_up
        elif action_name == "vlc_volume_up":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            steps = int(parameters.get("steps", 1))
            for _ in range(min(steps, 10)):
                self._send_vlc_hotkey(["ctrl", "up"])
            return PluginResult(success=True, data={"steps": steps, "message": f"Increased VLC volume by {steps} step(s)."})

        # 8. vlc_volume_down
        elif action_name == "vlc_volume_down":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            steps = int(parameters.get("steps", 1))
            for _ in range(min(steps, 10)):
                self._send_vlc_hotkey(["ctrl", "down"])
            return PluginResult(success=True, data={"steps": steps, "message": f"Decreased VLC volume by {steps} step(s)."})

        # 9. vlc_mute_toggle
        elif action_name == "vlc_mute_toggle":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["m"])
            return PluginResult(success=ok, data={"action": "mute_toggle", "message": "Toggled VLC audio mute."})

        # 10. vlc_seek_forward
        elif action_name == "vlc_seek_forward":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["right"])
            return PluginResult(success=ok, data={"action": "seek_forward", "message": "Seeked forward 10 seconds in VLC."})

        # 11. vlc_seek_backward
        elif action_name == "vlc_seek_backward":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["left"])
            return PluginResult(success=ok, data={"action": "seek_backward", "message": "Seeked backward 10 seconds in VLC."})

        # 12. vlc_next_track
        elif action_name == "vlc_next_track":
            if not self._get_vlc_pids():
                return PluginResult(success=False, error="VLC is not currently running.")
            ok = self._send_vlc_hotkey(["n"])
            return PluginResult(success=ok, data={"action": "next_track", "message": "Skipped to next track in VLC."})

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in VLC plugin.")
