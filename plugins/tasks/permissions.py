# plugins/tasks/permissions.py
"""Permissions declaration for Tasks Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.OFFICE.value,
    PluginCapability.FILESYSTEM.value
]
