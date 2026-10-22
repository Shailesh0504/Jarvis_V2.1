# plugins/activity_monitor/permissions.py
"""Permissions declaration for Activity Monitor plugin."""

from core.permissions import PermissionLevel, PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.FILESYSTEM.value
]
