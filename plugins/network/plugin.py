# plugins/network/plugin.py
"""Network capability plugin implementation for checking connectivity, IP address, and ping."""

import json
import logging
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

import psutil

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.network")


class NetworkPlugin(BasePlugin):
    """Controls network status, latency pinging, and IP diagnostics."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="network",
            version="1.0.0",
            description="Network connectivity, IP address, ping, and internet diagnostic tools.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        if action_name == "list_saved_wifi_passwords":
            try:
                credentials = [
                    {"ssid": ssid, "password": self._get_saved_wifi_password(ssid) or "Not saved / Open network"}
                    for ssid in self._get_saved_wifi_profiles()
                ]
                if not credentials:
                    return PluginResult(success=False, error="Laptop mein koi saved Wi-Fi profile nahi mila, Boss.")
                return PluginResult(
                    success=True,
                    data={
                        "count": len(credentials),
                        "sensitive_display": {"type": "wifi_credentials", "items": credentials},
                        "message": f"{len(credentials)} saved Wi-Fi profiles mil gaye. Details chatbox mein dikha di hain, Boss.",
                    },
                )
            except Exception as exc:
                logger.warning("Saved Wi-Fi profile recovery failed: %s", exc)
                return PluginResult(success=False, error="Saved Wi-Fi profiles retrieve nahi ho paaye, Boss.")

        if action_name == "copy_wifi_password":
            requested_ssid = str(parameters.get("ssid", "")).strip()
            try:
                ssid = requested_ssid or self._get_connected_wifi_ssid()
                if not ssid:
                    return PluginResult(
                        success=False,
                        error="Abhi koi Wi-Fi connected nahi hai. Network connect karke dobara try kijiye, Boss.",
                    )
                password = self._get_saved_wifi_password(ssid)
                if not password:
                    return PluginResult(
                        success=False,
                        error=f"'{ssid}' ka saved password nahi mila. Ho sakta hai profile open network ho ya Windows mein key saved na ho.",
                    )
                self._copy_secret_to_clipboard(password)
                # The secret travels only through the UI-sensitive channel. The
                # normal message is safe for logs and TTS.
                return PluginResult(
                    success=True,
                    data={
                        "ssid": ssid,
                        "copied_to_clipboard": True,
                        "sensitive_display": {
                            "type": "wifi_credentials",
                            "items": [{"ssid": ssid, "password": password}],
                        },
                        "message": f"'{ssid}' ka Wi-Fi password chatbox mein dikha diya hai aur clipboard mein bhi copy kar diya hai, Boss.",
                    },
                )
            except Exception as exc:
                logger.warning("Wi-Fi password recovery failed: %s", exc)
                return PluginResult(
                    success=False,
                    error="Wi-Fi password retrieve nahi ho paaya. Jarvis ko normal Windows user session mein run karke dobara try kijiye.",
                )

        if action_name == "measure_speed":
            try:
                latency_ms = self._measure_latency_ms()
                download_mbps = self._measure_download_mbps()
                upload_mbps = self._measure_upload_mbps()
                message = (
                    f"Abhi internet speed lagbhag {download_mbps:.1f} Mbps download "
                    f"aur {upload_mbps:.1f} Mbps upload hai. Ping {latency_ms:.0f} milliseconds hai, Boss."
                )
                return PluginResult(
                    success=True,
                    data={
                        "download_mbps": round(download_mbps, 1),
                        "upload_mbps": round(upload_mbps, 1),
                        "ping_ms": round(latency_ms, 1),
                        "message": message,
                    },
                )
            except Exception as exc:
                logger.warning("Internet speed measurement failed: %s", exc)
                return PluginResult(
                    success=False,
                    error="Internet speed test complete nahi ho paaya. Connection check karke dobara try kijiye, Boss.",
                )

        elif action_name == "check_connection":
            connected = False
            try:
                # Fast socket connection to Google DNS
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                connected = True
            except OSError:
                pass

            if connected:
                return PluginResult(
                    success=True,
                    data={"connected": True, "message": "Internet connection active and online hai, Boss! 🌐"}
                )
            else:
                return PluginResult(
                    success=True,
                    data={"connected": False, "message": "Internet offline hai, Boss. Please check your network connection."}
                )

        elif action_name == "get_ip_address":
            local_ip = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass

            return PluginResult(
                success=True,
                data={"local_ip": local_ip, "message": f"Aapka Local IP Address: {local_ip}"}
            )

        elif action_name == "ping_host":
            host = parameters.get("host", "8.8.8.8").strip() or "8.8.8.8"
            try:
                res = subprocess.run(["ping", "-n", "1", "-w", "1000", host], capture_output=True, text=True)
                success = (res.returncode == 0)
                if success:
                    return PluginResult(
                        success=True,
                        data={"host": host, "reachable": True, "message": f"Ping to '{host}' successful (Host reachable)."}
                    )
                else:
                    return PluginResult(
                        success=True,
                        data={"host": host, "reachable": False, "message": f"Ping to '{host}' failed (Request timed out)."}
                    )
            except Exception as e:
                return PluginResult(success=False, error=f"Ping error: {e}")

        elif action_name == "dns_lookup":
            domain = str(parameters.get("domain", "")).strip()
            if not domain:
                return PluginResult(success=False, error="Domain parameter is required for DNS lookup.")
            try:
                cleaned_domain = re.sub(r"^https?://", "", domain).split("/")[0].split(":")[0]
                addr_info = socket.getaddrinfo(cleaned_domain, None)
                ips = list({res[4][0] for res in addr_info if res and res[4]})
                return PluginResult(
                    success=True,
                    data={
                        "domain": domain,
                        "cleaned_domain": cleaned_domain,
                        "ip_addresses": ips,
                        "count": len(ips),
                        "message": f"Resolved '{domain}' to {len(ips)} IP address(es): {', '.join(ips)}"
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"DNS lookup failed for '{domain}': {e}")

        elif action_name == "get_bandwidth_stats":
            try:
                io_counters = psutil.net_io_counters()
                per_nic = psutil.net_io_counters(pernic=True)
                nic_stats = {}
                for nic, stats in per_nic.items():
                    nic_stats[nic] = {
                        "bytes_sent": stats.bytes_sent,
                        "bytes_recv": stats.bytes_recv,
                        "packets_sent": stats.packets_sent,
                        "packets_recv": stats.packets_recv,
                        "errin": stats.errin,
                        "errout": stats.errout,
                    }
                return PluginResult(
                    success=True,
                    data={
                        "total_bytes_sent": io_counters.bytes_sent,
                        "total_bytes_recv": io_counters.bytes_recv,
                        "total_packets_sent": io_counters.packets_sent,
                        "total_packets_recv": io_counters.packets_recv,
                        "errin": io_counters.errin,
                        "errout": io_counters.errout,
                        "dropin": io_counters.dropin,
                        "dropout": io_counters.dropout,
                        "adapters": nic_stats,
                        "message": f"Total Network I/O: Sent {io_counters.bytes_sent / (1024*1024):.2f} MB, Recv {io_counters.bytes_recv / (1024*1024):.2f} MB"
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to get bandwidth stats: {e}")

        elif action_name == "scan_local_network":
            try:
                res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
                devices = []
                for line in res.stdout.splitlines():
                    match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]+)\s+(\w+)", line)
                    if match:
                        ip, mac, dev_type = match.groups()
                        if not ip.endswith(".255") and not ip.startswith("224.") and not ip.startswith("239."):
                            devices.append({"ip": ip, "mac": mac, "type": dev_type})
                return PluginResult(
                    success=True,
                    data={
                        "devices": devices,
                        "count": len(devices),
                        "message": f"Found {len(devices)} active device(s) on the local network."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to scan local network: {e}")

        elif action_name == "check_port_open":
            host = str(parameters.get("host", "")).strip()
            port = parameters.get("port")
            timeout = float(parameters.get("timeout", 3.0))
            if not host or port is None:
                return PluginResult(success=False, error="Both 'host' and 'port' parameters are required.")
            try:
                port_num = int(port)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                t_start = time.perf_counter()
                result_code = s.connect_ex((host, port_num))
                latency = round((time.perf_counter() - t_start) * 1000, 2)
                s.close()
                is_open = (result_code == 0)
                status_msg = "OPEN" if is_open else "CLOSED/FILTERED"
                return PluginResult(
                    success=True,
                    data={
                        "host": host,
                        "port": port_num,
                        "is_open": is_open,
                        "latency_ms": latency,
                        "status_code": result_code,
                        "message": f"Port {port_num} on {host} is {status_msg} ({latency}ms)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Port check failed: {e}")

        elif action_name == "flush_dns_cache":
            try:
                res = subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=8)
                success = (res.returncode == 0)
                return PluginResult(
                    success=success,
                    data={
                        "output": res.stdout.strip(),
                        "message": "Windows DNS Resolver Cache successfully flushed." if success else "Failed to flush DNS."
                    },
                    error=None if success else res.stderr.strip()
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to execute flushdns: {e}")

        elif action_name == "list_active_connections":
            try:
                limit = int(parameters.get("limit", 25))
                connections = psutil.net_connections(kind="inet")
                results = []
                for conn in connections:
                    laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
                    raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
                    results.append({
                        "fd": conn.fd,
                        "family": "IPv4" if conn.family == socket.AF_INET else "IPv6",
                        "type": "TCP" if conn.type == socket.SOCK_STREAM else "UDP",
                        "local_address": laddr,
                        "remote_address": raddr,
                        "status": conn.status,
                        "pid": conn.pid
                    })
                    if len(results) >= limit:
                        break
                return PluginResult(
                    success=True,
                    data={
                        "connections": results,
                        "count": len(results),
                        "total_detected": len(connections),
                        "message": f"Retrieved {len(results)} active network connection(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to list connections: {e}")

        elif action_name == "get_network_adapter_details":
            try:
                addrs = psutil.net_if_addrs()
                stats = psutil.net_if_stats()
                adapters = []
                for iface_name, addr_list in addrs.items():
                    stat = stats.get(iface_name)
                    ipv4_list = [a.address for a in addr_list if a.family == socket.AF_INET]
                    ipv6_list = [a.address for a in addr_list if hasattr(socket, "AF_INET6") and a.family == socket.AF_INET6]
                    mac_list = [a.address for a in addr_list if a.family == getattr(psutil, "AF_LINK", -1)]
                    adapters.append({
                        "name": iface_name,
                        "is_up": stat.isup if stat else False,
                        "duplex": str(stat.duplex) if stat else "unknown",
                        "speed_mbps": stat.speed if stat else 0,
                        "mtu": stat.mtu if stat else 0,
                        "ipv4": ipv4_list,
                        "ipv6": ipv6_list,
                        "mac": mac_list[0] if mac_list else ""
                    })
                return PluginResult(
                    success=True,
                    data={
                        "adapters": adapters,
                        "count": len(adapters),
                        "message": f"Retrieved configuration for {len(adapters)} network adapter(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to get adapter details: {e}")

        elif action_name == "get_public_ip_details":
            try:
                req = Request("https://api.ipify.org?format=json", headers={"User-Agent": "Jarvis-Network/2.1"})
                with urlopen(req, timeout=5) as response:
                    raw_data = response.read().decode("utf-8")
                    ip_data = json.loads(raw_data)
                    pub_ip = ip_data.get("ip", "unknown")
                return PluginResult(
                    success=True,
                    data={
                        "public_ip": pub_ip,
                        "message": f"Public IP Address: {pub_ip}"
                    }
                )
            except Exception as e:
                return PluginResult(
                    success=True,
                    data={
                        "public_ip": "unavailable_offline",
                        "fallback": True,
                        "message": f"Could not determine public IP: {e}"
                    }
                )

        elif action_name == "traceroute":
            host = str(parameters.get("host", "")).strip()
            max_hops = int(parameters.get("max_hops", 15))
            if not host:
                return PluginResult(success=False, error="Host parameter is required for traceroute.")
            try:
                res = subprocess.run(
                    ["tracert", "-d", "-h", str(max_hops), "-w", "1000", host],
                    capture_output=True,
                    text=True,
                    timeout=25
                )
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                return PluginResult(
                    success=True,
                    data={
                        "host": host,
                        "max_hops": max_hops,
                        "output": lines,
                        "message": f"Traceroute to '{host}' finished with {len(lines)} log lines."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Traceroute failed: {e}")

        elif action_name == "get_wifi_network_list":
            try:
                res = subprocess.run(
                    ["netsh", "wlan", "show", "networks", "mode=bssid"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                networks = []
                for line in res.stdout.splitlines():
                    ssid_match = re.search(r"^SSID\s+\d+\s+:\s+(.*)$", line)
                    if ssid_match:
                        current_ssid = ssid_match.group(1).strip()
                        networks.append({"ssid": current_ssid, "signals": []})
                    sig_match = re.search(r"Signal\s+:\s+(\d+)%", line)
                    if sig_match and networks:
                        networks[-1]["signals"].append(int(sig_match.group(1)))
                return PluginResult(
                    success=True,
                    data={
                        "networks": networks,
                        "count": len(networks),
                        "message": f"Found {len(networks)} nearby Wi-Fi network(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to scan nearby Wi-Fi: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Network plugin.")

    @staticmethod
    def _get_connected_wifi_ssid() -> str:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return ""
        match = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", result.stdout, flags=re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _get_saved_wifi_profiles() -> list[str]:
        result = subprocess.run(
            ["netsh", "wlan", "show", "profiles"], capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=8, check=False,
        )
        if result.returncode != 0:
            return []
        return [
            value.strip()
            for value in re.findall(
                r"^\s*All\s+User\s+Profile\s*:\s*(.+?)\s*$",
                result.stdout, flags=re.MULTILINE | re.IGNORECASE,
            )
            if value.strip()
        ]

    @staticmethod
    def _get_saved_wifi_password(ssid: str) -> str:
        result = subprocess.run(
            ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return ""
        match = re.search(r"^\s*Key\s+Content\s*:\s*(.+?)\s*$", result.stdout, flags=re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _copy_secret_to_clipboard(secret: str) -> None:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=secret,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError("Clipboard command failed")

    @staticmethod
    def _measure_latency_ms() -> float:
        started = time.perf_counter()
        with socket.create_connection(("1.1.1.1", 443), timeout=4):
            pass
        return max((time.perf_counter() - started) * 1000, 0.1)

    @staticmethod
    def _measure_download_mbps() -> float:
        requested_bytes = 5_000_000
        request = Request(
            f"https://speed.cloudflare.com/__down?bytes={requested_bytes}",
            headers={"User-Agent": "Jarvis-V2-Speed-Test"},
        )
        received = 0
        started = time.perf_counter()
        with urlopen(request, timeout=15) as response:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
        elapsed = time.perf_counter() - started
        if received < 100_000 or elapsed <= 0:
            raise RuntimeError("Insufficient download sample")
        return (received * 8) / elapsed / 1_000_000

    @staticmethod
    def _measure_upload_mbps() -> float:
        payload = b"0" * 1_000_000
        request = Request(
            "https://speed.cloudflare.com/__up",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/octet-stream",
                "User-Agent": "Jarvis-V2-Speed-Test",
            },
        )
        started = time.perf_counter()
        with urlopen(request, timeout=15) as response:
            response.read(1)
        elapsed = time.perf_counter() - started
        if elapsed <= 0:
            raise RuntimeError("Invalid upload sample")
        return (len(payload) * 8) / elapsed / 1_000_000
