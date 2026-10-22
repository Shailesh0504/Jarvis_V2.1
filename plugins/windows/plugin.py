# plugins/windows/plugin.py
"""Windows Plugin implementation with Generic WindowManager integration."""

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional
import psutil

try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    win32gui = None
    win32con = None
    win32process = None

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED
from .window_manager import WindowManager

logger = logging.getLogger("jarvis.plugins.windows")


class WindowsPlugin(BasePlugin):
    """Windows application launcher, process monitoring, and generic window management."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self.window_manager = WindowManager()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="windows",
            version="2.0.0",
            description="Controls Windows OS applications, generic window operations, layouts, and process management.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("get_active_window_info", "get_windows", "find_window"):
            has_data = bool(result_data) and ("hwnd" in result_data or "windows" in result_data or "window" in result_data)
            return VerificationResult(
                verified=has_data,
                state=ExecutionState.SUCCESS if has_data else ExecutionState.FAILED,
                check_type="window_detected",
                expected="Window data",
                actual="Found" if has_data else "Empty",
                message="Window state verified."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        act = str(action_name or "").lower().strip()
        if act == "open_path":
            path = str(parameters.get("path", "")).strip()
            if not path:
                return PluginResult(success=False, error="Path is required.")
            if path.startswith("\\\\") and path.count("\\") < 3:
                return PluginResult(success=False, error="A network share name is required.")
            try:
                # Argument-list invocation is intentional: never send a user
                # supplied network path through cmd.exe or shell parsing.
                subprocess.Popen(["explorer.exe", path])
                return PluginResult(
                    success=True,
                    data={"path": path, "message": f"File Explorer mein '{path}' open kar diya."},
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Path open nahi ho paya: {e}")

        # 1. Launch Application
        if act == "launch_app":
            app = parameters.get("app_name") or parameters.get("app", "")
            app = str(app).strip()
            file_path = parameters.get("file_path", "")
            is_new = bool(parameters.get("is_new", False))

            from core.apps import get_application_registry, get_installed_app_detector
            app_reg = get_application_registry()
            app_def = app_reg.get_app(app) or app_reg.find_by_alias(app)
            detector = get_installed_app_detector()

            if app_def:
                launch_cmd = detector.get_launch_command(app_def, is_new=is_new, file_path=file_path)
                if launch_cmd:
                    target_cmd, args, strategy = launch_cmd
                    try:
                        if strategy == "executable":
                            full_cmd = [target_cmd] + args
                            subprocess.Popen(full_cmd, cwd=os.path.dirname(target_cmd))
                        elif strategy == "shortcut":
                            os.startfile(target_cmd)
                        elif strategy == "protocol":
                            subprocess.Popen(f'start "" "{target_cmd}"', shell=True)
                        else:
                            subprocess.Popen(f'start "" "{target_cmd}"', shell=True)

                        msg = f"Launched '{app}' successfully."
                        if is_new and app_def.app_id == "excel":
                            msg = "Bilkul ek nayi blank Excel workbook khol di hai."
                        return PluginResult(
                            success=True,
                            data={
                                "app": app,
                                "app_id": app_def.app_id,
                                "display_name": app_def.display_name,
                                "message": msg
                            }
                        )
                    except Exception as e:
                        return PluginResult(success=False, error=f"Failed to launch '{app}': {e}")
                else:
                    return PluginResult(
                        success=False,
                        error=f"Application '{app_def.display_name}' is not installed on this system.",
                        data={"app": app, "not_installed": True, "display_name": app_def.display_name}
                    )

            app_map = {
                "notepad": "notepad.exe",
                "calc": "calc.exe",
                "calculator": "calc.exe",
                "cmd": "cmd.exe",
                "command prompt": "cmd.exe",
                "powershell": "powershell.exe",
                "terminal": "wt.exe",
                "chrome": "chrome",
                "google chrome": "chrome",
                "chrome browser": "chrome",
                "brave": "brave",
                "brave browser": "brave",
                "firefox": "firefox",
                "edge": "msedge",
                "browser": "chrome",
                "code": "code",
                "vs code": "code",
                "vscode": "code",
                "antigravity": "Antigravity.exe",
                "antigravity_ide": "Antigravity IDE.exe",
                "antigravity ide": "Antigravity IDE.exe",
                "explorer": "explorer.exe",
                "file explorer": "explorer.exe",
                "spotify": "spotify",
                "vlc": "vlc",
                "setting": "ms-settings:",
                "settings": "ms-settings:",
                "windows settings": "ms-settings:",
                "system settings": "ms-settings:",
                "control panel": "control",
                "task manager": "taskmgr",
                "taskmgr": "taskmgr",
                "store": "ms-windows-store:",
                "microsoft store": "ms-windows-store:",
                "windows store": "ms-windows-store:",
                "ms store": "ms-windows-store:",
                "msstore": "ms-windows-store:",
                "discord": "discord",
                "telegram": "telegram",
                "photos": "ms-photos:",
                "snipping tool": "snippingtool.exe",
                "clock": "ms-clock:",
                "weather": "bingweather:",
                "maps": "bingmaps:",
                "camera": "microsoft.windows.camera:",
                "paint": "mspaint.exe",
                "word": "winword.exe",
                "excel": "excel.exe",
                "powerpoint": "powerpnt.exe",
                "ppt": "powerpnt.exe",
                "power point": "powerpnt.exe",
                "access": "msaccess.exe",
                "publisher": "mspub.exe",
                "whatsapp": "whatsapp://",
                "chess": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "games", "Chess", "chess.exe")),
                "chess game": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "games", "Chess", "chess.exe")),
            }
            target = app_map.get(app.lower(), app)
            try:
                if os.path.isabs(target) and os.path.exists(target):
                    subprocess.Popen([target], cwd=os.path.dirname(target))
                elif file_path:
                    subprocess.Popen([target, file_path])
                else:
                    subprocess.Popen(f'start "" "{target}"', shell=True)
                return PluginResult(success=True, data={"app": app, "message": f"Launched '{app}' successfully."})
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to launch '{app}': {e}")

        # 2. Window Operations (Maximize, Minimize, Restore, Focus, Move, Resize, Manage)
        elif act in (
            "maximize_window", "minimize_window", "restore_window",
            "focus_window", "move_window", "resize_window", "manage_window"
        ):
            app = parameters.get("app_name") or parameters.get("app") or parameters.get("target") or "current"
            app = str(app).strip()

            op = parameters.get("operation", "")
            if not op:
                if act == "maximize_window":
                    op = "maximize"
                elif act == "minimize_window":
                    op = "minimize"
                elif act == "restore_window":
                    op = "restore"
                elif act == "focus_window":
                    op = "focus"
                elif act == "move_window":
                    op = "move"
                elif act == "resize_window":
                    op = "resize"
                else:
                    op = "maximize"

            res = self.window_manager.execute_operation(
                operation=op,
                app_name=app,
                x=parameters.get("x", 100),
                y=parameters.get("y", 100),
                width=parameters.get("width", 1024),
                height=parameters.get("height", 768)
            )

            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error=res.get("error", "Window operation failed."), data=res)

        # 2a. Reusable Window Discovery Actions (GET_WINDOWS, FIND_WINDOW)
        elif act == "get_windows":
            app = parameters.get("app_name") or parameters.get("app")
            res = self.window_manager.get_windows(app_name=app, include_hidden=bool(parameters.get("include_hidden", False)))
            return PluginResult(success=res.get("success", True), data=res)

        elif act == "find_window":
            app = parameters.get("app_name") or parameters.get("app") or "current"
            prefer_active = bool(parameters.get("prefer_active", True))
            res = self.window_manager.find_window(app_name=str(app).strip(), prefer_active=prefer_active)
            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error=res.get("error", f"Window '{app}' nahi mili, Boss."), data=res)

        # 2b. Reusable Window Positioning & Snapping (SNAP_LEFT, SNAP_RIGHT, POSITION_WINDOW)
        elif act in ("snap_left", "snap_right"):
            pos = "left" if act == "snap_left" else "right"
            app = parameters.get("app_name") or parameters.get("app") or ""
            hwnd = parameters.get("hwnd") or parameters.get("selected_hwnd") or 0
            launch = parameters.get("launch_if_needed", False)
            res = self.window_manager.snap_window(
                hwnd_or_app=hwnd or app,
                position=pos,
                launch_if_needed=bool(launch),
                app_name=str(app).strip()
            )
            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error=res.get("error", f"Failed to snap window to {pos}."), data=res)

        elif act == "verify_window_position":
            hwnd = parameters.get("hwnd") or parameters.get("selected_hwnd") or 0
            pos = parameters.get("expected_position") or parameters.get("position")
            rect = parameters.get("expected_rect") or parameters.get("rect")
            tol = parameters.get("tolerance", 25)
            res = self.window_manager.verify_window_position(
                hwnd=int(hwnd),
                expected_position=pos,
                expected_rect=rect,
                tolerance=int(tol)
            )
            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error="Window position verification failed.", data=res)

        elif act == "position_window":
            app = parameters.get("app_name") or parameters.get("app") or "current"
            pos = parameters.get("position") or "left"
            launch = parameters.get("launch_if_needed", False)

            res = self.window_manager.position_window(
                app_name=str(app).strip(),
                position=str(pos).strip(),
                launch_if_needed=bool(launch)
            )
            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error=res.get("error", "Positioning failed."), data=res)

        # 2c. Multi-Window Layout / Tiling
        elif act == "layout_windows":
            items = parameters.get("items")
            if items and isinstance(items, list):
                res = self.window_manager.layout_multiple_windows(items)
            else:
                res = self.window_manager.side_by_side_layout()

            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                return PluginResult(success=False, error=res.get("error", "Layout arrangement failed."), data=res)

        # 3. Close Application / Kill Process
        elif act in ("kill_process", "close_app", "terminate", "close"):
            app = parameters.get("process_name") or parameters.get("app_name") or parameters.get("app", "")
            app = str(app).strip()
            if not app:
                return PluginResult(success=False, error="Application or process name is required to close.")

            res = self.window_manager.execute_operation(operation="close", app_name=app)
            if res.get("success"):
                return PluginResult(success=True, data=res)
            else:
                # Fallback to direct process kill
                process_map = {
                    "excel": ["excel.exe", "EXCEL.EXE"],
                    "chrome": ["chrome.exe"],
                    "brave": ["brave.exe"],
                    "notepad": ["notepad.exe", "Notepad.exe"],
                    "vlc": ["vlc.exe"],
                    "calc": ["CalculatorApp.exe", "calc.exe", "Calculator.exe"],
                    "calculator": ["CalculatorApp.exe", "calc.exe", "Calculator.exe"],
                    "code": ["Code.exe", "code.exe"],
                    "vs code": ["Code.exe", "code.exe"],
                    "vscode": ["Code.exe", "code.exe"],
                    "spotify": ["Spotify.exe"],
                    "firefox": ["firefox.exe"],
                    "edge": ["msedge.exe"]
                }
                targets = process_map.get(app.lower(), [f"{app}.exe" if not app.endswith(".exe") else app])
                killed = False
                for proc in psutil.process_iter(['name']):
                    try:
                        pname = proc.info.get('name') or ""
                        if any(t.lower() == pname.lower() for t in targets):
                            proc.kill()
                            killed = True
                    except Exception:
                        pass

                display_name = app.capitalize()
                if killed:
                    return PluginResult(
                        success=True,
                        data={"app": app, "running": True, "message": f"{display_name} band kar diya hai, Boss."}
                    )
                else:
                    return PluginResult(
                        success=True,
                        data={"app": app, "running": False, "message": f"{display_name} open nahi hai (already band hai), Boss."}
                    )

        # 4. List Active Processes
        elif act == "list_processes":
            try:
                procs = []
                for p in sorted(psutil.process_iter(['name', 'memory_percent']), key=lambda x: x.info['memory_percent'] or 0, reverse=True)[:8]:
                    procs.append(f"{p.info['name']} ({round(p.info['memory_percent'] or 0, 1)}% RAM)")
                return PluginResult(
                    success=True,
                    data={"processes": procs, "message": f"Top active processes: {', '.join(procs[:5])}"}
                )
            except Exception as e:
                return PluginResult(success=False, error=str(e))

        # 5. get_active_window_info
        elif act == "get_active_window_info":
            if not win32gui:
                return PluginResult(success=False, error="win32gui not available.")
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) if hwnd else ""
                rect = list(win32gui.GetWindowRect(hwnd)) if hwnd else [0, 0, 0, 0]
                pid = 0
                pname = ""
                if hwnd and win32process:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    try:
                        pname = psutil.Process(pid).name()
                    except Exception:
                        pass
                return PluginResult(
                    success=True,
                    data={
                        "hwnd": hwnd,
                        "title": title,
                        "pid": pid,
                        "process_name": pname,
                        "rect": {"left": rect[0], "top": rect[1], "right": rect[2], "bottom": rect[3]},
                        "message": f"Active window: '{title}' ({pname}, HWND {hwnd})."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed getting active window: {e}")

        # 6. set_window_transparency
        elif act == "set_window_transparency":
            app = parameters.get("app_name", "current")
            opacity = max(10, min(100, int(parameters.get("opacity_percent", 100))))
            alpha = int((opacity / 100.0) * 255)
            hwnd = 0
            if app == "current" and win32gui:
                hwnd = win32gui.GetForegroundWindow()
            else:
                w = self.window_manager.find_window(app)
                hwnd = w.hwnd if w else 0

            if not hwnd or not win32gui:
                return PluginResult(success=False, error=f"Window '{app}' not found.")

            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                LWA_ALPHA = 0x00000002
                user32 = ctypes.windll.user32
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
                return PluginResult(
                    success=True,
                    data={"hwnd": hwnd, "opacity_percent": opacity, "message": f"Set transparency of window to {opacity}%."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed setting transparency: {e}")

        # 7. set_window_always_on_top
        elif act == "set_window_always_on_top":
            app = parameters.get("app_name", "current")
            topmost = bool(parameters.get("always_on_top", True))
            hwnd = 0
            if app == "current" and win32gui:
                hwnd = win32gui.GetForegroundWindow()
            else:
                w = self.window_manager.find_window(app)
                hwnd = w.hwnd if w else 0

            if not hwnd or not win32gui:
                return PluginResult(success=False, error=f"Window '{app}' not found.")

            try:
                import ctypes
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                flag = HWND_TOPMOST if topmost else HWND_NOTOPMOST
                ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                return PluginResult(
                    success=True,
                    data={"hwnd": hwnd, "always_on_top": topmost, "message": f"Window always-on-top set to {topmost}."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Always on top failed: {e}")

        # 8. hide_window
        elif act == "hide_window":
            app = parameters.get("app_name", "")
            w = self.window_manager.find_window(app)
            if not w or not win32gui:
                return PluginResult(success=False, error=f"Window for '{app}' not found.")
            win32gui.ShowWindow(w.hwnd, 0)
            return PluginResult(success=True, data={"hwnd": w.hwnd, "app": app, "message": f"Window '{app}' hidden."})

        # 9. show_window
        elif act == "show_window":
            app = parameters.get("app_name", "")
            w = self.window_manager.find_window(app)
            if not w or not win32gui:
                return PluginResult(success=False, error=f"Window for '{app}' not found.")
            win32gui.ShowWindow(w.hwnd, 5)
            return PluginResult(success=True, data={"hwnd": w.hwnd, "app": app, "message": f"Window '{app}' displayed."})

        # 10. cascade_windows
        elif act == "cascade_windows":
            try:
                import ctypes
                ctypes.windll.user32.CascadeWindows(0, 0, None, 0, None)
                return PluginResult(success=True, data={"message": "Desktop windows cascaded."})
            except Exception as e:
                return PluginResult(success=False, error=f"Cascade windows failed: {e}")

        # 11. tile_windows_horizontally
        elif act == "tile_windows_horizontally":
            try:
                import ctypes
                MDITILE_HORIZONTAL = 0x0001
                ctypes.windll.user32.TileWindows(0, MDITILE_HORIZONTAL, None, 0, None)
                return PluginResult(success=True, data={"message": "Windows tiled horizontally."})
            except Exception as e:
                return PluginResult(success=False, error=f"Tile horizontal failed: {e}")

        # 12. tile_windows_vertically
        elif act == "tile_windows_vertically":
            try:
                import ctypes
                MDITILE_VERTICAL = 0x0000
                ctypes.windll.user32.TileWindows(0, MDITILE_VERTICAL, None, 0, None)
                return PluginResult(success=True, data={"message": "Windows tiled vertically."})
            except Exception as e:
                return PluginResult(success=False, error=f"Tile vertical failed: {e}")

        # 13. minimize_all_windows
        elif act == "minimize_all_windows":
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"])
                return PluginResult(success=True, data={"message": "All windows minimized (Desktop shown)."})
            except Exception as e:
                return PluginResult(success=False, error=f"Minimize all failed: {e}")

        # 14. restore_all_windows
        elif act == "restore_all_windows":
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", "(New-Object -ComObject Shell.Application).UndoMinimizeALL()"])
                return PluginResult(success=True, data={"message": "All windows restored."})
            except Exception as e:
                return PluginResult(success=False, error=f"Restore all failed: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Windows plugin.")
