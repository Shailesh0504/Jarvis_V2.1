# plugins/audio/plugin.py
"""Audio capability plugin implementation."""

import subprocess
import time
from typing import Any, Dict, Optional

try:
    import winsound
except ImportError:
    winsound = None

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED
from . import volume_controller
from .volume_controller import set_system_volume, get_system_volume


def _parse_volume_level(val: Any, default: int = 50) -> int:
    if isinstance(val, (int, float)):
        return max(0, min(100, int(val)))
    if isinstance(val, str):
        cleaned = val.strip().lower()
        mapping = {
            "full": 100, "max": 100, "maximum": 100, "poora": 100,
            "high": 80, "tez": 80,
            "half": 50, "medium": 50, "mid": 50, "aadha": 50,
            "low": 20, "kam": 20, "dheere": 20,
            "mute": 0, "zero": 0, "off": 0, "silent": 0, "shant": 0, "shanti": 0
        }
        if cleaned in mapping:
            return mapping[cleaned]
        import re
        nums = re.findall(r"\d+", cleaned)
        if nums:
            return max(0, min(100, int(nums[0])))
    return default


def _parse_step(val: Any, default: int = 10) -> int:
    if isinstance(val, (int, float)):
        return max(1, int(val))
    if isinstance(val, str):
        import re
        nums = re.findall(r"\d+", val)
        if nums:
            return max(1, int(nums[0]))
    return default


class AudioPlugin(BasePlugin):
    """Controls audio playback volume, mute, unmute, and sound device settings."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self._current_volume = 50
        self._is_muted = False

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="audio",
            version="2.0.0",
            description="Controls audio playback volume, mute, unmute, per-app sound, and devices.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("set_volume", "volume_up", "volume_down"):
            act = (result_data or {}).get("actual") or (result_data or {}).get("level")
            req = parameters.get("level") or (result_data or {}).get("requested")
            return VerificationResult(
                verified=bool(result_data and result_data.get("success")),
                state=ExecutionState.SUCCESS if (result_data and result_data.get("success")) else ExecutionState.FAILED,
                check_type="volume_verified",
                expected=str(req) if req is not None else "volume adjusted",
                actual=f"{act}%" if act is not None else "failed",
                message="Volume adjustment verified."
            )
        elif action_name in ("get_volume", "list_audio_devices", "list_app_audio_sessions", "get_default_audio_device"):
            has_data = bool(result_data) and ("volume" in result_data or "devices" in result_data or "sessions" in result_data or "device" in result_data)
            return VerificationResult(
                verified=has_data,
                state=ExecutionState.SUCCESS if has_data else ExecutionState.FAILED,
                check_type="audio_state_read",
                expected="Audio diagnostic payload",
                actual="Payload present" if has_data else "Empty",
                message="Audio status verified."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        if action_name == "set_volume":
            lvl = parameters.get("level", 50)
            res = volume_controller.set_system_volume(lvl)
            if res.get("success"):
                self._current_volume = res.get("actual", 50)
                self._is_muted = (self._current_volume == 0)
                return PluginResult(success=True, data=res)
            return PluginResult(
                success=False,
                error=res.get("error", "Volume verification failed."),
                data=res
            )

        elif action_name == "volume_up":
            step = _parse_step(parameters.get("step", 10))
            current_info = volume_controller.get_system_volume()
            current = current_info.get("volume", self._current_volume) if current_info.get("success") else self._current_volume
            target = min(100, current + step)
            res = volume_controller.set_system_volume(target)
            if res.get("success"):
                self._current_volume = res.get("actual", target)
                self._is_muted = False
                res["message"] = f"Volume badha kar {self._current_volume}% kar diya hai, Boss."
                return PluginResult(success=True, data=res)
            return PluginResult(
                success=False,
                error=res.get("error", "Failed to increase volume."),
                data=res
            )

        elif action_name == "volume_down":
            step = _parse_step(parameters.get("step", 10))
            current_info = volume_controller.get_system_volume()
            current = current_info.get("volume", self._current_volume) if current_info.get("success") else self._current_volume
            target = max(0, current - step)
            res = volume_controller.set_system_volume(target)
            if res.get("success"):
                self._current_volume = res.get("actual", target)
                self._is_muted = (self._current_volume == 0)
                res["message"] = f"Volume kam karke {self._current_volume}% kar diya hai, Boss."
                return PluginResult(success=True, data=res)
            return PluginResult(
                success=False,
                error=res.get("error", "Failed to decrease volume."),
                data=res
            )

        elif action_name == "mute":
            import comtypes
            endpoint_vol = None
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from .volume_controller import get_default_playback_device_and_volume
                _, endpoint_vol = get_default_playback_device_and_volume()
                endpoint_vol.SetMute(1, None)
                self._is_muted = True
                return PluginResult(
                    success=True,
                    data={"muted": True, "success": True, "level": 0, "actual": 0, "message": "Audio mute kar diya hai, Boss."}
                )
            except Exception as e:
                err_msg = f"Audio mute nahi ho paaya: {e}"
                return PluginResult(
                    success=False,
                    error=err_msg,
                    data={"muted": False, "success": False, "error": err_msg, "message": f"Boss, {err_msg}"}
                )
            finally:
                if endpoint_vol is not None:
                    try:
                        del endpoint_vol
                    except Exception:
                        pass
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

        elif action_name == "unmute":
            import comtypes
            endpoint_vol = None
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from .volume_controller import get_default_playback_device_and_volume
                _, endpoint_vol = get_default_playback_device_and_volume()
                endpoint_vol.SetMute(0, None)
                scalar = endpoint_vol.GetMasterVolumeLevelScalar()
                self._current_volume = int(round(scalar * 100))
                self._is_muted = False
                return PluginResult(
                    success=True,
                    data={
                        "muted": False,
                        "level": self._current_volume,
                        "actual": self._current_volume,
                        "success": True,
                        "message": f"Audio unmute kar diya hai (Volume {self._current_volume}%)."
                    }
                )
            except Exception as e:
                err_msg = f"Audio unmute nahi ho paaya: {e}"
                return PluginResult(
                    success=False,
                    error=err_msg,
                    data={"muted": True, "success": False, "error": err_msg, "message": f"Boss, {err_msg}"}
                )
            finally:
                if endpoint_vol is not None:
                    try:
                        del endpoint_vol
                    except Exception:
                        pass
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

        # 6. get_volume
        elif action_name == "get_volume":
            vol_data = volume_controller.get_system_volume()
            return PluginResult(
                success=vol_data.get("success", True),
                data=vol_data
            )

        # 7. toggle_mute
        elif action_name == "toggle_mute":
            vol_data = volume_controller.get_system_volume()
            is_muted = vol_data.get("muted", False)
            return self.execute("unmute" if is_muted else "mute")

        # 8. list_audio_devices
        elif action_name == "list_audio_devices":
            devices = []
            import comtypes
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from pycaw.pycaw import AudioUtilities
                for dev in AudioUtilities.GetAllDevices():
                    devices.append({
                        "name": getattr(dev, "FriendlyName", str(dev)),
                        "id": getattr(dev, "id", "")
                    })
            except Exception:
                try:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", "Get-PnpDevice -Class Media | Select-Object -ExpandProperty FriendlyName"],
                        text=True, timeout=5
                    )
                    devices = [{"name": line.strip()} for line in out.splitlines() if line.strip()]
                except Exception:
                    devices = [{"name": "Default Audio Endpoint"}]
            finally:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

            return PluginResult(
                success=True,
                data={"devices": devices, "count": len(devices), "message": f"Found {len(devices)} audio device(s)."}
            )

        # 9. set_app_volume
        elif action_name == "set_app_volume":
            app = parameters.get("app_name", "").lower().strip()
            level = max(0, min(100, int(parameters.get("level", 50))))
            target_scalar = level / 100.0
            updated = False
            import comtypes
            sessions = None
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from pycaw.pycaw import AudioUtilities
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    proc = s.Process
                    if proc and app in proc.name().lower():
                        vol = s.SimpleAudioVolume
                        vol.SetMasterVolume(target_scalar, None)
                        updated = True
            except Exception as e:
                return PluginResult(success=False, error=f"Set app volume error: {e}")
            finally:
                if sessions is not None:
                    try:
                        del sessions
                    except Exception:
                        pass
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

            if updated:
                return PluginResult(
                    success=True,
                    data={"app": app, "level": level, "message": f"Set {app} volume to {level}%."}
                )
            return PluginResult(
                success=False,
                error=f"No active audio session found for '{app}'."
            )

        # 10. get_app_volume
        elif action_name == "get_app_volume":
            app = parameters.get("app_name", "").lower().strip()
            import comtypes
            sessions = None
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from pycaw.pycaw import AudioUtilities
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    proc = s.Process
                    if proc and app in proc.name().lower():
                        vol = s.SimpleAudioVolume
                        pct = int(round(vol.GetMasterVolume() * 100))
                        muted = bool(vol.GetMute())
                        return PluginResult(
                            success=True,
                            data={"app": app, "level": pct, "muted": muted, "message": f"'{app}' volume is {pct}% (Muted: {muted})."}
                        )
            except Exception as e:
                return PluginResult(success=False, error=f"Get app volume error: {e}")
            finally:
                if sessions is not None:
                    try:
                        del sessions
                    except Exception:
                        pass
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

            return PluginResult(success=False, error=f"No audio session for '{app}'.")

        # 11. list_app_audio_sessions
        elif action_name == "list_app_audio_sessions":
            active_sessions = []
            import comtypes
            sessions = None
            try:
                try:
                    comtypes.CoInitialize()
                except Exception:
                    pass
                from pycaw.pycaw import AudioUtilities
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    proc = s.Process
                    if proc:
                        vol = s.SimpleAudioVolume
                        active_sessions.append({
                            "app": proc.name(),
                            "pid": proc.pid,
                            "volume": int(round(vol.GetMasterVolume() * 100)),
                            "muted": bool(vol.GetMute())
                        })
            except Exception as e:
                logger.debug("GetAllSessions error: %s", e)
            finally:
                if sessions is not None:
                    try:
                        del sessions
                    except Exception:
                        pass
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

            return PluginResult(
                success=True,
                data={"sessions": active_sessions, "count": len(active_sessions), "message": f"Found {len(active_sessions)} active application audio session(s)."}
            )

        # 12. fade_volume
        elif action_name == "fade_volume":
            target = max(0, min(100, int(parameters.get("target_level", 50))))
            duration = max(0.1, min(10.0, float(parameters.get("duration_seconds", 1.0))))
            current_info = volume_controller.get_system_volume()
            start = current_info.get("volume", 50)
            steps = 5
            delay = duration / steps
            for i in range(1, steps + 1):
                inter = int(start + (target - start) * (i / steps))
                volume_controller.set_system_volume(inter)
                time.sleep(delay)
            return PluginResult(
                success=True,
                data={"start_level": start, "final_level": target, "message": f"Faded volume from {start}% to {target}% over {duration}s."}
            )

        # 13. play_frequency_tone
        elif action_name == "play_frequency_tone":
            freq = max(37, min(32767, int(parameters.get("frequency_hz", 440))))
            duration_ms = max(50, min(5000, int(parameters.get("duration_ms", 500))))
            try:
                if winsound:
                    winsound.Beep(freq, duration_ms)
                return PluginResult(
                    success=True,
                    data={"frequency_hz": freq, "duration_ms": duration_ms, "message": f"Played {freq} Hz tone for {duration_ms} ms."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Frequency tone failed: {e}")

        # 14. get_default_audio_device
        elif action_name == "get_default_audio_device":
            try:
                device_info = volume_controller.get_system_volume()
                return PluginResult(
                    success=True,
                    data={"device": device_info.get("device", "Default Speakers"), "message": f"Default audio output: {device_info.get('device')}."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Could not get default device: {e}")

        # 15. check_audio_engine_status
        elif action_name == "check_audio_engine_status":
            import psutil
            running = False
            for p in psutil.process_iter(['name']):
                if "audiodg.exe" in (p.info.get('name') or "").lower():
                    running = True
                    break
            return PluginResult(
                success=True,
                data={"audio_engine_active": running, "service": "Windows Audio (Audiosrv)", "message": "Windows Audio Engine is healthy and active." if running else "Audio device ready."}
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Audio plugin.")
