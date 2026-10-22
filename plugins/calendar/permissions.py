# plugins/calendar/permissions.py
"""Permissions declaration for Calendar Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.OFFICE.value,
    PluginCapability.FILESYSTEM.value
]
