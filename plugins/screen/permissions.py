# plugins/screen/permissions.py
"""Permissions declaration for Screen Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.FILESYSTEM.value
]
