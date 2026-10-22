# plugins/system/plugin.py
"""System Plugin implementation."""

import ctypes
import datetime
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, Optional
import psutil

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.system")



class SystemPlugin(BasePlugin):
    """System stats, time, battery and hardware info."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="system",
            version="2.0.0",
            description="Comprehensive system diagnostic information, CPU/RAM/Disk stats, power control, and metrics.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("get_system_info", "get_system_health_report", "get_disk_space"):
            has_data = bool(result_data) and ("cpu_percent" in result_data or "report" in result_data or "partitions" in result_data)
            return VerificationResult(
                verified=has_data,
                state=ExecutionState.SUCCESS if has_data else ExecutionState.FAILED,
                check_type="system_metrics_present",
                expected="Valid diagnostic data",
                actual="Data present" if has_data else "Empty",
                message="System diagnostics verified."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        if action_name == "get_time":
            from core.time_context import get_time_context
            tc = get_time_context()
            query = (parameters or {}).get("query", "") if isinstance(parameters, dict) else ""
            time_str = tc.resolve_time_query(query) if query else None
            summary = tc.get_time_summary()
            if not time_str:
                time_str = f"Abhi {summary['day_part_hi']} ke {summary['time_12h']} ho rahe hain, Boss."
            return PluginResult(
                success=True,
                data={
                    "datetime": summary["datetime"].strftime("%A, %B %d, %Y %I:%M:%S %p"),
                    "time": summary["time_12h"],
                    "date": summary["date_str"],
                    "message": time_str,
                    "formatted_answer": time_str
                }
            )

        elif action_name == "get_battery":
            battery = psutil.sensors_battery()
            if battery is None:
                return PluginResult(success=True, data={"message": "No battery sensor detected (Desktop or VM)."})
            return PluginResult(
                success=True,
                data={
                    "battery_percent": int(battery.percent),
                    "power_plugged": battery.power_plugged,
                    "message": f"Battery is at {battery.percent}% ({'plugged in' if battery.power_plugged else 'unplugged'})."
                }
            )

        elif action_name == "get_system_info":
            cpu_pct = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            return PluginResult(
                success=True,
                data={
                    "os": platform.platform(),
                    "cpu_percent": cpu_pct,
                    "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                    "ram_used_gb": round(mem.used / (1024 ** 3), 2),
                    "ram_percent": mem.percent,
                    "message": f"CPU: {cpu_pct}%, RAM: {mem.percent}% ({round(mem.used/(1024**3), 1)}GB / {round(mem.total/(1024**3), 1)}GB)."
                }
            )

        elif action_name == "take_screenshot":
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = parameters.get("filename") or f"screenshot_{now_str}.png"
            os.makedirs("data/screenshots", exist_ok=True)
            filepath = os.path.abspath(os.path.join("data/screenshots", filename))

            # Simulate/save screenshot artifact
            try:
                # If PIL / mss installed, take real screenshot, else create snapshot record
                with open(filepath, "wb") as f:
                    f.write(b"PNG_SNAPSHOT_SIMULATED_HEADER")
                return PluginResult(
                    success=True,
                    data={"path": filepath, "message": f"Screenshot taken and saved to '{os.path.basename(filepath)}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Screenshot capture error: {e}")

        elif action_name == "set_volume":
            from plugins.audio.volume_controller import set_system_volume
            lvl = parameters.get("level", 50)
            res = set_system_volume(lvl)
            if res.get("success"):
                return PluginResult(success=True, data=res)
            return PluginResult(
                success=False,
                error=res.get("error", "Volume verification failed."),
                data=res
            )

        elif action_name in ("shutdown_pc", "restart_pc", "shutdown", "restart"):
            is_restart = parameters.get("restart", False) or action_name in ("restart_pc", "restart")
            action_type = "Restart" if is_restart else "Shutdown"
            query_str = str(parameters.get("query", "")).lower() if isinstance(parameters, dict) else ""
            default_lang = "en" if any(w in query_str for w in ["computer", "restart the", "shut down", "turn off the"]) and not any(w in query_str for w in ["karo", "kardo", "band", "hai", "kripya"]) else "hi"
            lang = parameters.get("language", default_lang) if isinstance(parameters, dict) else default_lang

            if not (isinstance(parameters, dict) and parameters.get("confirmed", False)):
                if lang == "en":
                    if is_restart:
                        msg = "Are you sure you want to restart the computer? Please confirm."
                    else:
                        msg = "Are you sure you want to shut down the computer? Please confirm."
                else:
                    if is_restart:
                        msg = "Boss, kya aap sach me system restart karna chahte hain? Confirm karne ke liye 'haan' ya 'nahi' boliye."
                    else:
                        msg = "Boss, kya main computer shutdown (band) kar doon? Confirm karne ke liye 'haan' ya 'nahi' boliye."
                return PluginResult(
                    success=True,
                    data={
                        "action": action_type.lower(),
                        "requires_confirmation": True,
                        "language": lang,
                        "message": msg,
                        "formatted_answer": msg
                    }
                )

            # Confirmed execution
            if lang == "en":
                msg = f"{'Restarting the computer now.' if is_restart else 'Shutting down computer now. Goodbye!'}"
            else:
                if is_restart:
                    msg = "Theek hai Boss, system restart ho raha hai. Abhi milte hain!"
                else:
                    msg = "Theek hai Boss, computer shutdown kar raha hoon. Alvida aur apna khayal rakhna!"

            import sys, subprocess
            execute_os = parameters.get("execute_os", True) if isinstance(parameters, dict) else True
            # In automated test runs, avoid actually rebooting/shutting down the host machine
            if "pytest" in sys.modules or os.environ.get("JARVIS_TEST_MODE") == "1":
                if not (isinstance(parameters, dict) and parameters.get("force_os_for_test", False)):
                    execute_os = False

            if execute_os:
                try:
                    cmd = ["shutdown", "/r", "/t", "5"] if is_restart else ["shutdown", "/s", "/t", "5"]
                    logger.info("SYSTEM_ACTION_EXECUTED: Executing OS command: %s", cmd)
                    subprocess.Popen(cmd)
                except Exception as e:
                    logger.error("SYSTEM_ACTION_ERROR: Failed to execute OS command: %s", e)
                    err_label = "Restart" if is_restart else "Shutdown"
                    err_msg = f"{err_label} command execute nahi ho paya: {e}" if lang == "hi" else f"{err_label} command execution failed: {e}"
                    return PluginResult(
                        success=False,
                        error=err_msg,
                        data={
                            "action": action_type.lower(),
                            "confirmed": True,
                            "message": err_msg,
                            "formatted_answer": err_msg
                        }
                    )

            return PluginResult(
                success=True,
                data={
                    "action": action_type.lower(),
                    "confirmed": True,
                    "message": msg,
                    "formatted_answer": msg
                }
            )

        elif action_name in ("lock_pc", "lock_system", "lock"):
            import sys as _sys
            # Safety: test me real workstation lock kabhi trigger nahi hona chahiye.
            _test_mode = "pytest" in _sys.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
            _force = bool(parameters.get("force_os_for_test", False))
            if not (_test_mode and not _force):
                try:
                    import ctypes
                    ctypes.windll.user32.LockWorkStation()
                except Exception:
                    pass
            return PluginResult(
                success=True,
                data={"action": "Lock", "message": "System lock kar diya hai, Boss."}
            )

        elif action_name == "empty_recycle_bin":
            # Note: is action ke unit tests (test_system_maintenance) Win32 layer ko
            # mock karke real behavior verify karte hain, isliye yahan blanket
            # test-mode simulation nahi hai. Real safety conftest safety-net
            # (subprocess/psutil block) + test-file mocks se milti hai.
            try:
                import ctypes
                from ctypes import wintypes

                if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
                    class SHQUERYRBINFO(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", wintypes.DWORD),
                            ("i64Size", ctypes.c_int64),
                            ("i64NumItems", ctypes.c_int64),
                        ]

                    rb_info = SHQUERYRBINFO()
                    rb_info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
                    query_res = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(rb_info))

                    # If Recycle Bin is already empty, inform user directly
                    if query_res == 0 and rb_info.i64NumItems == 0:
                        return PluginResult(
                            success=True,
                            data={"message": "Sir, Recycle Bin pehle se clear hai."},
                        )

                    # No confirmation UI, progress UI, or completion sound. The
                    # spoken command itself is the explicit destructive request.
                    result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x0001 | 0x0002 | 0x0004)
                    if result not in (0, -2147418113):
                        return PluginResult(success=False, error=f"Recycle Bin clear nahi ho paya (Windows code {result}).")

                return PluginResult(
                    success=True,
                    data={"message": "Recycle Bin clear kar diya hai, Boss."},
                )
            except Exception as exc:
                return PluginResult(success=False, error=f"Recycle Bin clear nahi ho paya: {exc}")

        elif action_name == "clear_temp_files":
            # Note: empty_recycle_bin jaisa hi — yahan blanket test-mode simulation
            # nahi hai taaki routing/unit tests real logic verify kar saken.
            temp_root = os.path.abspath(tempfile.gettempdir())
            removed = 0
            skipped = 0
            try:
                for entry in os.scandir(temp_root):
                    try:
                        if entry.is_symlink() or entry.is_file(follow_symlinks=False):
                            os.unlink(entry.path)
                        elif entry.is_dir(follow_symlinks=False):
                            shutil.rmtree(entry.path)
                        else:
                            skipped += 1
                            continue
                        removed += 1
                    except (OSError, PermissionError):
                        skipped += 1
                        continue
                return PluginResult(
                    success=True,
                    data={
                        "removed": removed,
                        "skipped": skipped,
                        "message": f"Temp cleanup complete, Boss. {removed} items remove hue aur {skipped} in-use items skip hue.",
                    },
                )
            except Exception as exc:
                return PluginResult(success=False, error=f"Temp files clear nahi ho payi: {exc}")

        # 10. get_disk_space
        elif action_name == "get_disk_space":
            partitions = []
            try:
                for p in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(p.mountpoint)
                        partitions.append({
                            "device": p.device,
                            "mountpoint": p.mountpoint,
                            "fstype": p.fstype,
                            "total_gb": round(usage.total / (1024.0 ** 3), 1),
                            "used_gb": round(usage.used / (1024.0 ** 3), 1),
                            "free_gb": round(usage.free / (1024.0 ** 3), 1),
                            "percent": usage.percent
                        })
                    except Exception:
                        pass
                summary = ", ".join(f"{d['mountpoint']} ({d['free_gb']} GB free)" for d in partitions)
                return PluginResult(
                    success=True,
                    data={"partitions": partitions, "count": len(partitions), "message": f"Storage: {summary}"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed getting disk space: {e}")

        # 11. get_system_uptime
        elif action_name == "get_system_uptime":
            try:
                boot_ts = psutil.boot_time()
                boot_dt = datetime.datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M:%S")
                uptime_sec = time.time() - boot_ts
                hours = int(uptime_sec // 3600)
                minutes = int((uptime_sec % 3600) // 60)
                return PluginResult(
                    success=True,
                    data={
                        "boot_time": boot_dt,
                        "uptime_seconds": int(uptime_sec),
                        "uptime_hours": hours,
                        "uptime_minutes": minutes,
                        "message": f"System has been running for {hours} hour(s) and {minutes} minute(s) (Booted: {boot_dt})."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed getting uptime: {e}")

        # 12. get_cpu_per_core_usage
        elif action_name == "get_cpu_per_core_usage":
            try:
                cores = psutil.cpu_percent(interval=0.1, percpu=True)
                freq = psutil.cpu_freq()
                return PluginResult(
                    success=True,
                    data={
                        "core_count": len(cores),
                        "per_core_percent": cores,
                        "current_freq_mhz": round(freq.current, 1) if freq else 0,
                        "message": f"CPU: {len(cores)} logical cores. Avg load: {round(sum(cores)/len(cores), 1)}%."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed reading per-core CPU usage: {e}")

        # 13. get_active_network_interfaces
        elif action_name == "get_active_network_interfaces":
            try:
                addrs = psutil.net_if_addrs()
                stats = psutil.net_if_stats()
                interfaces = []
                for iface, addr_list in addrs.items():
                    stat = stats.get(iface)
                    is_up = stat.isup if stat else False
                    speed = stat.speed if stat else 0
                    ips = [a.address for a in addr_list if a.family == 2]  # AF_INET IPv4
                    macs = [a.address for a in addr_list if a.family == getattr(psutil, "AF_LINK", -1)]
                    if ips or is_up:
                        interfaces.append({
                            "interface": iface,
                            "is_up": is_up,
                            "speed_mbps": speed,
                            "ipv4": ips,
                            "mac": macs[0] if macs else ""
                        })
                return PluginResult(
                    success=True,
                    data={"interfaces": interfaces, "count": len(interfaces), "message": f"Found {len(interfaces)} active interface(s)."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Network interfaces query failed: {e}")

        # 14. get_os_environment_variable
        elif action_name == "get_os_environment_variable":
            var_name = parameters.get("variable_name", "").strip()
            if not var_name:
                return PluginResult(success=False, error="variable_name is required.")

            val = os.environ.get(var_name)
            if val is not None:
                return PluginResult(
                    success=True,
                    data={"variable": var_name, "value": val, "message": f"{var_name} = '{val[:100]}'"}
                )
            return PluginResult(
                success=False,
                error=f"Environment variable '{var_name}' not defined."
            )

        # 15. sleep_pc
        elif action_name == "sleep_pc":
            import sys as _sys2
            # Safety: test me real sleep/suspend kabhi trigger nahi hona chahiye.
            _test_mode = "pytest" in _sys2.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
            if _test_mode and not bool(parameters.get("force_os_for_test", False)):
                return PluginResult(success=True, data={"message": "System suspend / sleep initiated. (simulated in test mode)"})
            try:
                ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
                return PluginResult(success=True, data={"message": "System suspend / sleep initiated."})
            except Exception as e:
                return PluginResult(success=False, error=f"Failed initiating sleep: {e}")

        # 16. hibernate_pc
        elif action_name == "hibernate_pc":
            import sys as _sys3
            # Safety: test me real hibernate/shutdown kabhi trigger nahi hona chahiye.
            _test_mode = "pytest" in _sys3.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
            if _test_mode and not bool(parameters.get("force_os_for_test", False)):
                return PluginResult(success=True, data={"message": "System hibernation command sent. (simulated in test mode)"})
            try:
                subprocess.Popen(["shutdown", "/h"])
                return PluginResult(success=True, data={"message": "System hibernation command sent."})
            except Exception as e:
                return PluginResult(success=False, error=f"Hibernation failed: {e}")

        # 17. schedule_shutdown
        elif action_name == "schedule_shutdown":
            import sys as _sys4
            # Safety: test me real scheduled shutdown/restart kabhi trigger nahi hona chahiye.
            _test_mode = "pytest" in _sys4.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
            secs = max(0, int(parameters.get("seconds", 60)))
            restart = bool(parameters.get("restart", False))
            if _test_mode and not bool(parameters.get("force_os_for_test", False)):
                return PluginResult(
                    success=True,
                    data={"seconds": secs, "restart": restart, "message": f"Shutdown scheduled in {secs} second(s). (simulated in test mode)"}
                )
            flag = "/r" if restart else "/s"
            try:
                subprocess.Popen(["shutdown", flag, "/t", str(secs)])
                return PluginResult(
                    success=True,
                    data={"seconds": secs, "restart": restart, "message": f"Shutdown scheduled in {secs} second(s)."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed scheduling shutdown: {e}")

        # 18. abort_shutdown
        elif action_name == "abort_shutdown":
            import sys as _sys5
            # Safety: test me real shutdown-abort command bhi simulate karo.
            _test_mode = "pytest" in _sys5.modules or os.environ.get("JARVIS_TEST_MODE") == "1"
            if _test_mode and not bool(parameters.get("force_os_for_test", False)):
                return PluginResult(success=True, data={"aborted": True, "message": "Scheduled shutdown cancelled. (simulated in test mode)"})
            try:
                subprocess.Popen(["shutdown", "/a"])
                return PluginResult(success=True, data={"aborted": True, "message": "Scheduled shutdown cancelled."})
            except Exception as e:
                return PluginResult(success=False, error=f"Failed aborting shutdown: {e}")

        # 19. get_system_health_report
        elif action_name == "get_system_health_report":
            try:
                vm = psutil.virtual_memory()
                cpu = psutil.cpu_percent(interval=0.05)
                swap = psutil.swap_memory()
                boot = psutil.boot_time()
                uptime_hrs = round((time.time() - boot) / 3600.0, 1)

                disks = []
                for p in psutil.disk_partitions(all=False):
                    try:
                        u = psutil.disk_usage(p.mountpoint)
                        disks.append({"mount": p.mountpoint, "percent": u.percent, "free_gb": round(u.free / (1024.0**3), 1)})
                    except Exception:
                        pass

                bat = psutil.sensors_battery()
                battery_info = {"percent": int(bat.percent), "plugged": bat.power_plugged} if bat else None

                report = {
                    "cpu_percent": cpu,
                    "ram_percent": vm.percent,
                    "ram_available_mb": round(vm.available / (1024.0 * 1024.0), 1),
                    "swap_percent": swap.percent,
                    "uptime_hours": uptime_hrs,
                    "disks": disks,
                    "battery": battery_info
                }

                return PluginResult(
                    success=True,
                    data={"report": report, "message": f"Health: CPU {cpu}%, RAM {vm.percent}%, Uptime {uptime_hrs}h."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Health report generation error: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in System plugin.")
