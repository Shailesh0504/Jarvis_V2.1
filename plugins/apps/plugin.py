# plugins/apps/plugin.py
"""Apps capability plugin implementation for managing installed applications, processes, and windows."""

import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple
import psutil

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.apps")

# SSOT: processes that must NEVER be closed/killed via close_app —
# test runner, coding agent host (opencode), editors, shells.
PROTECTED_CLOSE_TARGETS = frozenset({
    "opencode",
    "code",
    "vscode",
    "cursor",
    "windsurf",
    "python",
    "pytest",
    "conhost",
})


def is_protected_close_target(*candidates: object) -> bool:
    """SSOT guard: True if ANY given name/process/title refers to a protected host.

    Checks substring match (case-insensitive) against PROTECTED_CLOSE_TARGETS.
    Accepts app names, process names (e.g. 'opencode.exe'), window titles,
    exe paths. Empty/None candidates are ignored. Centralizes the check so
    WindowManager, TargetEngine, FastPath and strategies cannot drift.
    """
    for cand in candidates:
        if cand is None:
            continue
        try:
            text = str(cand).lower().strip()
        except Exception:
            continue
        if not text:
            continue
        for prot in PROTECTED_CLOSE_TARGETS:
            if prot and prot in text:
                return True
    return False

try:
    import winreg
except ImportError:
    winreg = None


class AppsPlugin(BasePlugin):
    """Controls installed Windows application discovery, status, execution, and resource tracking."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self._registry_cache: List[Dict[str, Any]] = []
        self._last_scan_time = 0.0

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="apps",
            version="2.0.0",
            description="Windows installed applications, process control, window management, and resource tracker.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _get_installed_apps_registry(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self._registry_cache and (now - self._last_scan_time) < 300:
            return self._registry_cache

        apps = []
        if not winreg:
            # Fallback static list if winreg is unavailable
            common = [
                "Google Chrome", "Mozilla Firefox", "Microsoft Edge", "Visual Studio Code",
                "VLC media player", "Spotify", "Notepad", "Calculator", "Microsoft Excel",
                "Microsoft Word", "Discord", "Telegram", "PowerPoint"
            ]
            self._registry_cache = [{"name": a, "version": "1.0", "publisher": "Unknown", "path": ""} for a in common]
            self._last_scan_time = now
            return self._registry_cache

        keys_to_search = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        seen_names = set()
        for root_key, subkey_path in keys_to_search:
            try:
                with winreg.OpenKey(root_key, subkey_path) as parent_key:
                    subkeys_count, _, _ = winreg.QueryInfoKey(parent_key)
                    for i in range(subkeys_count):
                        try:
                            subkey_name = winreg.EnumKey(parent_key, i)
                            with winreg.OpenKey(parent_key, subkey_name) as app_key:
                                try:
                                    name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                except FileNotFoundError:
                                    continue

                                name = str(name).strip()
                                if not name or name.lower() in seen_names:
                                    continue
                                seen_names.add(name.lower())

                                ver, _ = self._safe_query_value(app_key, "DisplayVersion")
                                pub, _ = self._safe_query_value(app_key, "Publisher")
                                install_loc, _ = self._safe_query_value(app_key, "InstallLocation")
                                install_date, _ = self._safe_query_value(app_key, "InstallDate")

                                apps.append({
                                    "name": name,
                                    "version": ver or "Unknown",
                                    "publisher": pub or "Unknown",
                                    "install_location": install_loc or "",
                                    "install_date": install_date or ""
                                })
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("Failed reading registry subkey %s: %s", subkey_path, e)

        apps.sort(key=lambda x: x["name"].lower())
        self._registry_cache = apps
        self._last_scan_time = now
        return apps

    @staticmethod
    def _safe_query_value(key, value_name: str) -> Tuple[Optional[str], int]:
        if not winreg:
            return None, 0
        try:
            return winreg.QueryValueEx(key, value_name)
        except Exception:
            return None, 0

    def _resolve_app_executable(self, app_name: str) -> str:
        app_lower = app_name.lower().strip()
        app_map = {
            "notepad": "notepad.exe",
            "calc": "calc.exe",
            "calculator": "calc.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "terminal": "wt.exe",
            "chrome": "chrome",
            "brave": "brave",
            "firefox": "firefox",
            "edge": "msedge",
            "code": "code",
            "vscode": "code",
            "explorer": "explorer.exe",
            "spotify": "spotify",
            "vlc": "vlc",
            "setting": "ms-settings:",
            "settings": "ms-settings:",
            "store": "ms-windows-store:",
            "microsoft store": "ms-windows-store:",
            "windows store": "ms-windows-store:",
            "ms store": "ms-windows-store:",
            "msstore": "ms-windows-store:",
            "control panel": "control",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "camera": "microsoft.windows.camera:",
            "paint": "mspaint.exe",
            "word": "winword.exe",
            "excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
            "whatsapp": "whatsapp://"
        }
        return app_map.get(app_lower, app_name)

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("launch_app", "restart_app"):
            app = parameters.get("app_name", "").lower().strip()
            if app:
                running = False
                for proc in psutil.process_iter(['name']):
                    try:
                        if app in (proc.info.get('name') or "").lower():
                            running = True
                            break
                    except Exception:
                        pass
                return VerificationResult(
                    verified=running,
                    state=ExecutionState.SUCCESS if running else ExecutionState.FAILED,
                    check_type="process_running",
                    expected=f"Process matching '{app}'",
                    actual=f"Running: {running}",
                    message=f"Application '{app}' is confirmed running." if running else f"Process '{app}' not detected in process table."
                )
        elif action_name == "close_app":
            app = parameters.get("app_name", "").lower().strip()
            if app:
                still_running = False
                for proc in psutil.process_iter(['name']):
                    try:
                        if app in (proc.info.get('name') or "").lower():
                            still_running = True
                            break
                    except Exception:
                        pass
                return VerificationResult(
                    verified=not still_running,
                    state=ExecutionState.SUCCESS if not still_running else ExecutionState.FAILED,
                    check_type="process_terminated",
                    expected=f"Process '{app}' terminated",
                    actual=f"Terminated: {not still_running}",
                    message=f"Process '{app}' confirmed stopped." if not still_running else f"Process '{app}' still running."
                )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. list_installed_apps
        if action_name == "list_installed_apps":
            limit = max(1, int(parameters.get("limit", 50)))
            apps = self._get_installed_apps_registry()
            app_names = [a["name"] for a in apps[:limit]]
            return PluginResult(
                success=True,
                data={
                    "count": len(app_names),
                    "total_detected": len(apps),
                    "apps": app_names,
                    "message": f"Detected {len(apps)} installed application(s). Showing top {len(app_names)}."
                }
            )

        # 2. check_app_status
        elif action_name == "check_app_status":
            app = parameters.get("app_name", "").lower().strip()
            if not app:
                return PluginResult(success=False, error="Application name is required.")

            running = False
            pids = []
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    pname = proc.info.get('name') or ""
                    if app in pname.lower():
                        running = True
                        pids.append(proc.info['pid'])
                except Exception:
                    pass

            display = app.capitalize()
            return PluginResult(
                success=True,
                data={
                    "app": app,
                    "running": running,
                    "pids": pids,
                    "message": f"'{display}' is currently running (PID {pids[0]})." if running else f"'{display}' is not currently running."
                }
            )

        # 3. launch_app
        elif action_name == "launch_app":
            app = parameters.get("app_name", "").strip()
            args = parameters.get("arguments", "").strip()
            if not app:
                return PluginResult(success=False, error="Application name is required.")

            import sys as _sys_launch
            # Safety: test me real app launch (window open) nahi hona chahiye.
            if ("pytest" in _sys_launch.modules or os.environ.get("JARVIS_TEST_MODE") == "1") and not bool(parameters.get("force_os_for_test", False)):
                target = self._resolve_app_executable(app)
                return PluginResult(
                    success=True,
                    data={"app": app, "target": target, "message": f"'{app.capitalize()}' launch kar diya hai, Boss. (simulated in test mode)"}
                )

            target = self._resolve_app_executable(app)
            try:
                if target.endswith(":") or target.startswith("ms-"):
                    os.startfile(target)
                else:
                    cmd = [target]
                    if args:
                        cmd.extend(args.split())
                    subprocess.Popen(cmd, creationflags=0x08000000 if os.name == "nt" else 0)

                return PluginResult(
                    success=True,
                    data={"app": app, "target": target, "message": f"'{app.capitalize()}' launch kar diya hai, Boss."}
                )
            except Exception as e:
                # Fallback to os.startfile or shell if direct popen failed
                try:
                    os.startfile(target)
                    return PluginResult(
                        success=True,
                        data={"app": app, "target": target, "message": f"'{app.capitalize()}' launch kar diya hai, Boss."}
                    )
                except Exception as inner:
                    return PluginResult(success=False, error=f"Failed to launch '{app}': {inner}")

        # 4. close_app
        elif action_name == "close_app":
            app = parameters.get("app_name", "").lower().strip()
            force = bool(parameters.get("force", False))
            if not app:
                return PluginResult(success=False, error="Application name is required.")

            # Safety: protected host processes (opencode, python/pytest, editors)
            # kabhi band nahi hone chahiye — khaas taur par program test ke samay.
            if is_protected_close_target(app):
                return PluginResult(
                    success=False,
                    error=f"'{app}' protected system process hai, ise band nahi kiya ja sakta.",
                    data={"app": app, "closed_processes_count": 0, "protected": True},
                )

            import sys as _sys
            # Safety: test me real process kill kabhi nahi hona chahiye.
            if ("pytest" in _sys.modules or os.environ.get("JARVIS_TEST_MODE") == "1") and not bool(parameters.get("force_os_for_test", False)):
                return PluginResult(
                    success=True,
                    data={"app": app, "closed_processes_count": 0, "message": f"No running instances of '{app}' were found. (simulated in test mode)"}
                )

            closed = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pname = proc.info.get('name') or ""
                    if app in pname.lower():
                        p = psutil.Process(proc.info['pid'])
                        if force:
                            p.kill()
                        else:
                            p.terminate()
                        closed += 1
                except Exception:
                    pass

            if closed > 0:
                return PluginResult(
                    success=True,
                    data={"app": app, "closed_processes_count": closed, "message": f"Terminated {closed} instance(s) of '{app}'."}
                )
            return PluginResult(
                success=True,
                data={"app": app, "closed_processes_count": 0, "message": f"No running instances of '{app}' were found."}
            )

        # 5. restart_app
        elif action_name == "restart_app":
            app = parameters.get("app_name", "").strip()
            if not app:
                return PluginResult(success=False, error="Application name is required.")

            # Close first
            self.execute("close_app", {"app_name": app, "force": True})
            time.sleep(0.5)

            # Relaunch
            return self.execute("launch_app", {"app_name": app})

        # 6. get_app_resource_usage
        elif action_name == "get_app_resource_usage":
            app = parameters.get("app_name", "").lower().strip()
            if not app:
                return PluginResult(success=False, error="Application name is required.")

            total_mem_mb = 0.0
            total_threads = 0
            proc_count = 0
            cpu_percent = 0.0

            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'num_threads']):
                try:
                    pname = proc.info.get('name') or ""
                    if app in pname.lower():
                        p = psutil.Process(proc.info['pid'])
                        mem = p.memory_info().rss / (1024.0 * 1024.0)
                        total_mem_mb += mem
                        total_threads += proc.info.get('num_threads') or 1
                        cpu_percent += p.cpu_percent(interval=0.01)
                        proc_count += 1
                except Exception:
                    pass

            return PluginResult(
                success=True,
                data={
                    "app": app,
                    "process_count": proc_count,
                    "memory_mb": round(total_mem_mb, 2),
                    "cpu_percent": round(cpu_percent, 1),
                    "threads": total_threads,
                    "message": f"'{app}': {proc_count} processes, {round(total_mem_mb, 1)} MB RAM, {round(cpu_percent, 1)}% CPU."
                }
            )

        # 7. list_running_apps
        elif action_name == "list_running_apps":
            limit = max(1, int(parameters.get("limit", 30)))
            running_apps = {}
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    name = proc.info.get('name') or ""
                    if not name or name.lower().endswith((".dll", ".sys", ".service")):
                        continue
                    mem = proc.info['memory_info'].rss / (1024.0 * 1024.0)
                    if name not in running_apps:
                        running_apps[name] = {"name": name, "pids": [proc.info['pid']], "memory_mb": round(mem, 1)}
                    else:
                        running_apps[name]["pids"].append(proc.info['pid'])
                        running_apps[name]["memory_mb"] = round(running_apps[name]["memory_mb"] + mem, 1)
                except Exception:
                    pass

            sorted_apps = sorted(running_apps.values(), key=lambda x: x["memory_mb"], reverse=True)[:limit]
            return PluginResult(
                success=True,
                data={
                    "count": len(sorted_apps),
                    "running_apps": sorted_apps,
                    "message": f"Found {len(running_apps)} active running applications."
                }
            )

        # 8. search_installed_apps
        elif action_name == "search_installed_apps":
            query = parameters.get("query", "").lower().strip()
            if not query:
                return PluginResult(success=False, error="query parameter is required.")

            apps = self._get_installed_apps_registry()
            matches = [a for a in apps if query in a["name"].lower()]
            return PluginResult(
                success=True,
                data={
                    "query": query,
                    "count": len(matches),
                    "matches": matches[:20],
                    "message": f"Found {len(matches)} installed apps matching '{query}'."
                }
            )

        # 9. get_app_version_info
        elif action_name == "get_app_version_info":
            app_name = parameters.get("app_name", "").lower().strip()
            if not app_name:
                return PluginResult(success=False, error="app_name parameter is required.")

            apps = self._get_installed_apps_registry()
            for a in apps:
                if app_name in a["name"].lower():
                    return PluginResult(
                        success=True,
                        data={
                            "app": a["name"],
                            "version": a.get("version", "Unknown"),
                            "publisher": a.get("publisher", "Unknown"),
                            "install_location": a.get("install_location", ""),
                            "install_date": a.get("install_date", ""),
                            "message": f"{a['name']} (v{a.get('version', 'Unknown')}) by {a.get('publisher', 'Unknown')}."
                        }
                    )

            return PluginResult(
                success=False,
                error=f"Application '{app_name}' not found in installed software registry."
            )

        # 10. list_startup_apps
        elif action_name == "list_startup_apps":
            startup_items = []
            if winreg:
                keys = [
                    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run")
                ]
                for root, path in keys:
                    try:
                        with winreg.OpenKey(root, path) as key:
                            count = winreg.QueryInfoKey(key)[1]
                            for i in range(count):
                                try:
                                    name, val, _ = winreg.EnumValue(key, i)
                                    startup_items.append({"name": name, "command": val})
                                except Exception:
                                    pass
                    except Exception:
                        pass

            return PluginResult(
                success=True,
                data={
                    "count": len(startup_items),
                    "startup_apps": startup_items,
                    "message": f"Found {len(startup_items)} startup application(s)."
                }
            )

        # 11. bring_app_to_front
        elif action_name == "bring_app_to_front":
            app_name = parameters.get("app_name", "").strip()
            if not app_name:
                return PluginResult(success=False, error="app_name parameter is required.")

            # Try PowerShell window focus
            ps_script = f"""
            $proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{app_name}*' -or $_.ProcessName -like '*{app_name}*' }} | Select-Object -First 1
            if ($proc -and $proc.MainWindowHandle -ne 0) {{
                $wscript = New-Object -ComObject WScript.Shell
                $wscript.AppActivate($proc.Id)
                Write-Output "FOCUSED"
            }} else {{
                Write-Output "NOT_FOUND"
            }}
            """
            try:
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    text=True,
                    timeout=3
                ).strip()
                focused = "FOCUSED" in out
                return PluginResult(
                    success=True,
                    data={"app": app_name, "focused": focused, "message": f"App '{app_name}' focused successfully." if focused else f"Could not bring window for '{app_name}' to front."}
                )
            except Exception as e:
                return PluginResult(success=True, data={"app": app_name, "focused": False, "message": f"Window focus attempted: {e}"})

        # 12. find_app_executable_path
        elif action_name == "find_app_executable_path":
            app_name = parameters.get("app_name", "").strip()
            if not app_name:
                return PluginResult(success=False, error="app_name parameter is required.")

            target = self._resolve_app_executable(app_name)
            which_path = shutil.which(target) or shutil.which(app_name)
            if which_path:
                return PluginResult(
                    success=True,
                    data={"app": app_name, "path": which_path, "message": f"Executable path: {which_path}"}
                )

            # Check registry install locations
            apps = self._get_installed_apps_registry()
            for a in apps:
                if app_name.lower() in a["name"].lower() and a.get("install_location"):
                    return PluginResult(
                        success=True,
                        data={"app": a["name"], "path": a["install_location"], "message": f"Install location: {a['install_location']}"}
                    )

            return PluginResult(
                success=False,
                error=f"Could not resolve binary file path for '{app_name}'."
            )

        # 13. get_top_resource_apps
        elif action_name == "get_top_resource_apps":
            sort_by = parameters.get("sort_by", "memory").lower()
            limit = max(1, int(parameters.get("limit", 10)))

            procs = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    mem_mb = p.info['memory_info'].rss / (1024.0 * 1024.0)
                    name = p.info.get('name') or "Unknown"
                    procs.append({
                        "pid": p.info['pid'],
                        "name": name,
                        "memory_mb": round(mem_mb, 1)
                    })
                except Exception:
                    pass

            procs.sort(key=lambda x: x["memory_mb"], reverse=True)
            top = procs[:limit]

            return PluginResult(
                success=True,
                data={
                    "sort_by": sort_by,
                    "count": len(top),
                    "top_apps": top,
                    "message": f"Top {len(top)} apps by {sort_by}: {top[0]['name'] if top else 'None'} ({top[0]['memory_mb'] if top else 0} MB)."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Apps plugin.")
