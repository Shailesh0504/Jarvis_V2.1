# plugins/archify/commands.py
"""PluginAction definitions for the Archify Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="show_architecture",
        description="Opens and displays the complete interactive Archify architecture map of Jarvis V2.1",
        keywords=[
            "archify dikhao",
            "archify open karo",
            "show archify",
            "open archify",
            "complete archify dikhao",
            "jarvis architecture dikhao",
            "jarvis ka architecture dikhao",
            "show jarvis architecture",
            "archify display karo",
            "archify viewer kholo",
        ],
        parameters=[
            PluginParameter(name="target", type="string", description="Optional view or section", required=False, default=None),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
]
