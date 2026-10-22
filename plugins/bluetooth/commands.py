# plugins/bluetooth/commands.py
"""Command actions supported by Bluetooth plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="list_devices",
        description="Lists paired and nearby discoverable Bluetooth devices",
        keywords=["bluetooth devices", "show bluetooth", "paired devices", "bluetooth devices dikhao"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="toggle_bluetooth",
        description="Enables or disables Bluetooth radio adapter",
        keywords=["toggle bluetooth", "bluetooth on", "bluetooth off", "bluetooth band karo", "bluetooth chalu karo"],
        parameters=[
            PluginParameter(name="enable", type="bool", description="True to enable, False to disable", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="status",
        description="Checks Bluetooth adapter status and operational state",
        keywords=["bluetooth status", "bluetooth state", "bluetooth check", "bluetooth ka status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="get_bluetooth_adapter_status",
        description="Queries detailed operational state and driver status of the host Bluetooth adapter",
        keywords=["bluetooth adapter status", "adapter health", "radio status", "bluetooth hardware"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="enable_bluetooth",
        description="Enables the host Bluetooth adapter radio",
        keywords=["enable bluetooth", "turn on bluetooth", "bluetooth chalu karo", "bluetooth on karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="disable_bluetooth",
        description="Disables the host Bluetooth adapter radio",
        keywords=["disable bluetooth", "turn off bluetooth", "bluetooth band karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_paired_devices",
        description="Lists all paired Bluetooth devices with connection state and device IDs",
        keywords=["paired bluetooth devices", "list paired devices", "paired devices dikhao"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_connected_audio_devices",
        description="Lists connected Bluetooth headphones, earbuds, speakers, and audio endpoints",
        keywords=["bluetooth audio devices", "bluetooth headphones", "connected speakers", "audio devices dikhao"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_device_details",
        description="Retrieves hardware details, manufacturer, and driver info for a Bluetooth device",
        keywords=["bluetooth device details", "device info bluetooth", "device details batao"],
        parameters=[
            PluginParameter(name="device_name", type="string", description="Name or partial name of device", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="disconnect_device",
        description="Disconnects or disables a specific Bluetooth device",
        keywords=["disconnect bluetooth", "disconnect device", "device disconnect karo"],
        parameters=[
            PluginParameter(name="device_name", type="string", description="Name or partial name of device", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="connect_paired_device",
        description="Enables or triggers connection to a known paired Bluetooth device",
        keywords=["connect bluetooth", "connect device", "device connect karo", "headphone jodo"],
        parameters=[
            PluginParameter(name="device_name", type="string", description="Name or partial name of device", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="restart_bluetooth_service",
        description="Restarts the Windows Bluetooth Support Service (bthserv) to resolve connectivity glitches",
        keywords=["restart bluetooth service", "reset bluetooth service", "bluetooth service restart"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="bluetooth_troubleshooter",
        description="Runs automated diagnostics on Bluetooth adapter, radio, services, and paired devices",
        keywords=["bluetooth troubleshooter", "diagnose bluetooth", "fix bluetooth", "bluetooth checkup"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
