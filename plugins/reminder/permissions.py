# plugins/reminder/permissions.py
"""Permissions declaration for Reminder Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.FILESYSTEM.value
]
