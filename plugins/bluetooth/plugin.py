# plugins/bluetooth/plugin.py
"""Bluetooth Plugin implementation for device scanning, adapter controls, and audio device management."""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.bluetooth")


class BluetoothPlugin(BasePlugin):
    """Controls Bluetooth adapter hardware, paired device inspection, and audio selection."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="bluetooth",
            version="2.0.0",
            description="Bluetooth device scanning, hardware adapter controls, and audio connection manager.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _run_ps_json(self, command: str, timeout: int = 6) -> Optional[Any]:
        """Runs a PowerShell command with strict timeout and parses JSON output."""
        try:
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out = res.stdout.strip()
            if out:
                return json.loads(out)
        except Exception as e:
            logger.debug("PowerShell Bluetooth query failed: %s", e)
        return None

    def _get_raw_devices(self) -> List[Dict[str, Any]]:
        ps_cmd = "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Select-Object FriendlyName, InstanceId, Status, Present | ConvertTo-Json -Compress"
        data = self._run_ps_json(ps_cmd)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("FriendlyName")]
        elif isinstance(data, dict) and data.get("FriendlyName"):
            return [data]
        return []

    def check_dependencies(self) -> bool:
        devices = self._get_raw_devices()
        return len(devices) > 0 or self._run_ps_json("Get-Service -Name bthserv | Select-Object Status | ConvertTo-Json") is not None

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("enable_bluetooth", "disable_bluetooth", "toggle_bluetooth"):
            status_res = self.execute("get_bluetooth_adapter_status", {})
            adapter_info = status_res.data.get("adapter", {})
            is_ok = adapter_info.get("status") == "OK"
            return VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS if is_ok else ExecutionState.PARTIAL,
                check_type="system_state",
                expected="Adapter verified",
                actual=adapter_info.get("status", "Unknown"),
                message="Bluetooth adapter state verified."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. status / get_bluetooth_adapter_status
        if action_name in ("status", "get_bluetooth_adapter_status"):
            devices = self._get_raw_devices()
            adapter = next((d for d in devices if any(k in d["FriendlyName"].lower() for k in ("adapter", "radio", "wireless bluetooth"))), None)

            if not adapter and devices:
                adapter = devices[0]

            is_online = adapter is not None and adapter.get("Status") == "OK"
            state_str = "online" if is_online else ("offline" if adapter else "not_detected")
            msg = f"Bluetooth adapter is {state_str}." if adapter else "No physical Bluetooth adapter detected on this system."

            return PluginResult(
                success=True,
                data={
                    "status": state_str,
                    "adapter": adapter or {},
                    "devices_detected": len(devices),
                    "message": msg
                }
            )

        # 2. list_devices
        elif action_name == "list_devices":
            devices = self._get_raw_devices()
            names = [d["FriendlyName"] for d in devices]
            count = len(names)
            msg = f"Found {count} Bluetooth device(s)." if count > 0 else "No active or paired Bluetooth devices found, Boss."
            return PluginResult(
                success=True,
                data={"devices": names, "count": count, "message": msg}
            )

        # 3. list_paired_devices
        elif action_name == "list_paired_devices":
            devices = self._get_raw_devices()
            # Filter out generic controller/enumerator entries
            paired = [d for d in devices if not any(k in d["FriendlyName"].lower() for k in ("enumerator", "generic", "radio"))]
            return PluginResult(
                success=True,
                data={
                    "count": len(paired),
                    "paired_devices": paired,
                    "message": f"Found {len(paired)} paired device(s): {', '.join([d['FriendlyName'] for d in paired[:4]])}"
                }
            )

        # 4. list_connected_audio_devices
        elif action_name == "list_connected_audio_devices":
            devices = self._get_raw_devices()
            audio_kw = ("headphone", "headset", "earbuds", "airpods", "speaker", "audio", "sound", "a2dp", "handsfree")
            audio_devs = [d for d in devices if any(k in d["FriendlyName"].lower() for k in audio_kw)]
            return PluginResult(
                success=True,
                data={
                    "count": len(audio_devs),
                    "audio_devices": audio_devs,
                    "message": f"Found {len(audio_devs)} Bluetooth audio device(s): {', '.join([d['FriendlyName'] for d in audio_devs]) if audio_devs else 'None'}"
                }
            )

        # 5. enable_bluetooth
        elif action_name == "enable_bluetooth":
            ps_cmd = "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -like '*Adapter*' -or $_.FriendlyName -like '*Radio*' } | Enable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue"
            self._run_ps_json(ps_cmd)
            from core.natural_responses import NaturalResponseSynthesizer
            lang = parameters.get("language", "hi")
            msg = NaturalResponseSynthesizer.toggle_device("Bluetooth", state=True, language=lang)
            return PluginResult(
                success=True,
                data={"enabled": True, "message": msg}
            )

        # 6. disable_bluetooth
        elif action_name == "disable_bluetooth":
            ps_cmd = "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -like '*Adapter*' -or $_.FriendlyName -like '*Radio*' } | Disable-PnpDevice -Confirm:$false -ErrorAction SilentlyContinue"
            self._run_ps_json(ps_cmd)
            from core.natural_responses import NaturalResponseSynthesizer
            lang = parameters.get("language", "hi")
            msg = NaturalResponseSynthesizer.toggle_device("Bluetooth", state=False, language=lang)
            return PluginResult(
                success=True,
                data={"enabled": False, "message": msg}
            )

        # 7. toggle_bluetooth
        elif action_name == "toggle_bluetooth":
            enable = bool(parameters.get("enable", True))
            return self.execute("enable_bluetooth" if enable else "disable_bluetooth", {})

        # 8. get_device_details
        elif action_name == "get_device_details":
            dev_name = parameters.get("device_name", "").strip().lower()
            if not dev_name:
                return PluginResult(success=False, error="device_name is required.")

            devices = self._get_raw_devices()
            match = next((d for d in devices if dev_name in d["FriendlyName"].lower()), None)
            if match:
                return PluginResult(success=True, data={"device": match, "message": f"Details for '{match['FriendlyName']}': Status={match.get('Status')}"})
            return PluginResult(success=False, error=f"Device matching '{dev_name}' not found.")

        # 9. disconnect_device
        elif action_name == "disconnect_device":
            dev_name = parameters.get("device_name", "").strip().lower()
            if not dev_name:
                return PluginResult(success=False, error="device_name is required.")

            devices = self._get_raw_devices()
            match = next((d for d in devices if dev_name in d["FriendlyName"].lower()), None)
            if not match:
                return PluginResult(success=False, error=f"Device '{dev_name}' not found.")

            inst_id = match.get("InstanceId")
            if inst_id:
                ps_cmd = f"Disable-PnpDevice -InstanceId '{inst_id}' -Confirm:$false -ErrorAction SilentlyContinue"
                self._run_ps_json(ps_cmd)

            return PluginResult(
                success=True,
                data={"device": match["FriendlyName"], "message": f"Device '{match['FriendlyName']}' disconnect signal sent."}
            )

        # 10. connect_paired_device
        elif action_name == "connect_paired_device":
            dev_name = parameters.get("device_name", "").strip().lower()
            if not dev_name:
                return PluginResult(success=False, error="device_name is required.")

            devices = self._get_raw_devices()
            match = next((d for d in devices if dev_name in d["FriendlyName"].lower()), None)
            if not match:
                return PluginResult(success=False, error=f"Paired device '{dev_name}' not found.")

            inst_id = match.get("InstanceId")
            if inst_id:
                ps_cmd = f"Enable-PnpDevice -InstanceId '{inst_id}' -Confirm:$false -ErrorAction SilentlyContinue"
                self._run_ps_json(ps_cmd)

            return PluginResult(
                success=True,
                data={"device": match["FriendlyName"], "message": f"Device '{match['FriendlyName']}' connection initiated."}
            )

        # 11. restart_bluetooth_service
        elif action_name == "restart_bluetooth_service":
            ps_cmd = "Restart-Service -Name bthserv -Force -ErrorAction SilentlyContinue"
            self._run_ps_json(ps_cmd, timeout=8)
            return PluginResult(
                success=True,
                data={"service": "bthserv", "message": "Windows Bluetooth Support Service (bthserv) restart signal sent."}
            )

        # 12. bluetooth_troubleshooter
        elif action_name == "bluetooth_troubleshooter":
            devices = self._get_raw_devices()
            service_info = self._run_ps_json("Get-Service -Name bthserv | Select-Object Status, StartType | ConvertTo-Json") or {}
            adapter_info = next((d for d in devices if any(k in d["FriendlyName"].lower() for k in ("adapter", "radio"))), None)

            diagnostics = {
                "adapter_detected": adapter_info is not None,
                "adapter_status": adapter_info.get("Status") if adapter_info else "Missing",
                "service_status": service_info.get("Status", "Unknown"),
                "total_bluetooth_devices": len(devices),
                "healthy": (adapter_info is not None and adapter_info.get("Status") == "OK")
            }

            status_summary = "Healthy" if diagnostics["healthy"] else "Degraded/Issue Detected"
            return PluginResult(
                success=True,
                data={
                    "diagnostics": diagnostics,
                    "summary": status_summary,
                    "message": f"Bluetooth Diagnostic: {status_summary} (Service: {diagnostics['service_status']}, Devices: {len(devices)})."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Bluetooth plugin.")
