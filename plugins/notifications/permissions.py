# plugins/notifications/permissions.py
"""Permissions declaration for Notifications Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.FILESYSTEM.value
]
