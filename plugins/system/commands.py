# plugins/system/commands.py
"""Command actions supported by System plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="get_time",
        description="Returns current system time and date",
        keywords=["what time", "current time", "time now", "date today", "time", "clock"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_system_info",
        description="Get CPU, RAM and OS specs",
        keywords=["system info", "cpu usage", "ram usage", "memory status", "system status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_battery",
        description="Checks system battery percentage and charging state",
        keywords=["battery", "battery percentage", "battery check", "battery kitni hai", "charging status", "battery status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="take_screenshot",
        description="Captures a desktop screenshot and saves snapshot",
        keywords=["screenshot lo", "take screenshot", "capture screen", "screenshot"],
        parameters=[
            PluginParameter(name="filename", type="string", description="Optional filename", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_volume",
        description="Sets system audio volume level (0-100)",
        keywords=["volume karo", "set volume", "volume", "volume 50", "sound level", "awaz badhao", "awaz kam karo"],
        parameters=[
            PluginParameter(name="level", type="int", description="Volume percentage 0 to 100", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="shutdown_pc",
        description="Shutdown or restart computer",
        keywords=["computer shutdown karo", "shutdown computer", "pc band karo", "turn off pc", "shutdown pc", "restart computer", "restart pc", "reboot"],
        parameters=[
            PluginParameter(name="restart", type="bool", description="If True, restarts instead of powering off", required=False, default=False)
        ],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="lock_pc",
        description="Locks the Windows workstation screen",
        keywords=["lock pc", "system lock", "lock screen", "lock computer", "pc lock karo", "screen lock karo", "lock"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="empty_recycle_bin",
        description="Permanently empties the current user's Windows Recycle Bin",
        keywords=["clear recycle bin", "empty recycle bin", "recycle bin saaf karo"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_temp_files",
        description="Removes removable files from the current user's temporary directory",
        keywords=["clear temp files", "clear temp file", "delete temp files", "temp files saaf karo"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="get_disk_space",
        description="Queries disk drives and partitions for total, used, and free space",
        keywords=["disk space", "hard drive space", "storage info", "drive storage", "kitni storage bachi hai"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_system_uptime",
        description="Returns system uptime and boot timestamp",
        keywords=["system uptime", "pc kab se on hai", "boot time", "how long pc running"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_cpu_per_core_usage",
        description="Returns utilization percentage for each logical CPU core and clock frequencies",
        keywords=["cpu core usage", "per core cpu", "core load", "processor frequency"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_active_network_interfaces",
        description="Lists network interfaces, IP addresses, MAC addresses, and connection statuses",
        keywords=["network interfaces", "ip address", "mac address", "adapter details"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_os_environment_variable",
        description="Retrieves the value of a system or user environment variable",
        keywords=["env variable", "environment variable", "get env", "system path variable"],
        parameters=[
            PluginParameter(name="variable_name", type="string", description="Environment variable name (e.g. PATH, USERNAME, TEMP)", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="sleep_pc",
        description="Puts the Windows system into sleep/standby mode",
        keywords=["sleep pc", "system sleep", "standby karo", "sleep mode"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="hibernate_pc",
        description="Puts the Windows computer into hibernation",
        keywords=["hibernate pc", "hibernate", "hibernation mode"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="schedule_shutdown",
        description="Schedules a delayed shutdown or restart after specified seconds",
        keywords=["schedule shutdown", "shutdown timer", "pc band hone ka time set karo"],
        parameters=[
            PluginParameter(name="seconds", type="integer", description="Delay in seconds before shutdown", required=True),
            PluginParameter(name="restart", type="boolean", description="If True, restart instead of shutdown", required=False, default=False)
        ],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="abort_shutdown",
        description="Cancels any currently pending or scheduled Windows shutdown timer",
        keywords=["cancel shutdown", "abort shutdown", "shutdown roko"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_system_health_report",
        description="Generates an all-in-one system health and resource diagnostic overview",
        keywords=["system health report", "full system check", "diagnostic summary", "pc health"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
