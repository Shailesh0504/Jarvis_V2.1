# plugins/software_update/commands.py
"""Command definitions for Software Update Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="check_updates",
        description="Checks available application, Windows, and Store updates without installing",
        keywords=[
            "check updates",
            "software update check",
            "check software update",
            "koi update hai kya",
            "updates check karo",
            "check karo koi software update hai",
            "updates available hain kya",
            "check for updates",
        ],
        parameters=[
            PluginParameter(name="scope", type="string", description="Scope of updates to check", required=False, default="ALL_SUPPORTED"),
            PluginParameter(name="include_unknown", type="bool", description="Include packages with unknown versions", required=False, default=False),
            PluginParameter(name="include_pinned", type="bool", description="Include pinned packages", required=False, default=False),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="install_updates",
        description="Installs available application and system updates according to policy",
        keywords=[
            "saare software update kar do",
            "software update karo",
            "software update kar do",
            "mere applications update kar do",
            "jo updates available hain sab install kar do",
            "sab kuch latest kar do",
            "apps update kar do",
            "all apps update karo",
            "mere installed programs latest kar do",
            "update all software",
            "install updates",
        ],
        parameters=[
            PluginParameter(name="scope", type="string", description="Scope: APPLICATIONS, OS, or ALL_SUPPORTED", required=False, default="ALL_SUPPORTED"),
            PluginParameter(name="allow_reboot", type="bool", description="Allow automatic reboot if needed", required=False, default=False),
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="windows_update",
        description="Checks or installs Windows OS updates specifically",
        keywords=[
            "windows update kar do",
            "windows bhi update kar do",
            "windows update karo",
            "windows update check karo",
            "update windows",
            "os update",
        ],
        parameters=[
            PluginParameter(name="action_mode", type="string", description="check or install", required=False, default="check"),
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="get_status",
        description="Returns current update manager status, active plan, or history",
        keywords=[
            "update status",
            "software update status",
            "update manager status",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
    PluginAction(
        name="cancel_update",
        description="Cancels any ongoing update checks or operations safely",
        keywords=[
            "update band kar do",
            "cancel update",
            "stop update",
            "update roko",
        ],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value,
    ),
]
