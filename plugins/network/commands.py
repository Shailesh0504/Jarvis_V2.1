# plugins/network/commands.py
"""Command actions supported by Network Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="list_saved_wifi_passwords",
        description="Lists all saved Wi-Fi profile names and passwords through the secure GUI display channel",
        keywords=["all wifi passwords", "sabhi wifi password", "saved wifi passwords", "past connected wifi"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="copy_wifi_password",
        description="Securely copies the current or named saved Wi-Fi password to the clipboard",
        keywords=[
            "wifi password", "wifi ka password batao", "wi-fi password",
            "wireless password", "network password"
        ],
        parameters=[
            PluginParameter(
                name="ssid",
                type="string",
                description="Saved Wi-Fi profile name; current connection is used when omitted",
                required=False,
                default="",
            )
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="measure_speed",
        description="Measures current internet download speed, upload speed, and latency",
        keywords=[
            "internet speed", "internet ki speed kitni hai", "wifi speed",
            "network speed", "speed test", "download speed", "upload speed"
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="check_connection",
        description="Checks internet connectivity status and latency",
        keywords=["check internet", "internet chal raha hai kya", "network status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="get_ip_address",
        description="Gets the local and public IP addresses of the system",
        keywords=["ip address", "mera ip kya hai", "local ip"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="ping_host",
        description="Pings a specific host or domain to measure response time",
        keywords=["ping", "ping google", "latency check"],
        parameters=[
            PluginParameter(name="host", type="string", description="Host domain or IP address", required=False, default="8.8.8.8")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="dns_lookup",
        description="Resolves domain names to IP addresses and host info",
        keywords=["dns lookup", "resolve domain", "domain ip"],
        parameters=[
            PluginParameter(name="domain", type="string", description="Domain to resolve", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="get_bandwidth_stats",
        description="Retrieves network bandwidth I/O stats (bytes sent/received, packets, errors)",
        keywords=["bandwidth stats", "data usage", "network traffic", "internet data"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="scan_local_network",
        description="Discovers active IP and MAC addresses in the local network ARP table",
        keywords=["scan network", "local devices", "arp scan", "who is on wifi"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="check_port_open",
        description="Checks if a specific TCP port is open and responding on a remote host",
        keywords=["check port", "test port", "port scanner", "is port open"],
        parameters=[
            PluginParameter(name="host", type="string", description="Target host or IP", required=True),
            PluginParameter(name="port", type="integer", description="Port number", required=True),
            PluginParameter(name="timeout", type="float", description="Connection timeout in seconds", required=False, default=3.0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="flush_dns_cache",
        description="Flushes the Windows DNS resolver cache",
        keywords=["flush dns", "clear dns", "reset dns cache"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_active_connections",
        description="Lists active TCP and UDP network connections with process IDs and remote addresses",
        keywords=["active connections", "open ports", "netstat", "listening ports"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum connections to return", required=False, default=25)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="get_network_adapter_details",
        description="Returns detailed hardware and IP configuration for all network adapters",
        keywords=["network adapters", "mac address", "ethernet status", "wifi adapter info"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="get_public_ip_details",
        description="Fetches public IP address and ISP/geo details",
        keywords=["public ip", "external ip", "what is my public ip"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="traceroute",
        description="Traces network route hops to a destination host",
        keywords=["traceroute", "trace route", "tracert"],
        parameters=[
            PluginParameter(name="host", type="string", description="Destination host", required=True),
            PluginParameter(name="max_hops", type="integer", description="Maximum hops to trace", required=False, default=15)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="get_wifi_network_list",
        description="Scans and lists nearby available Wi-Fi networks with signal strength",
        keywords=["nearby wifi", "scan wifi", "available wifi networks", "wifi list"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    )
]
