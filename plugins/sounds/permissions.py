# plugins/sounds/permissions.py
"""Permissions for Sounds Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.FILESYSTEM.value
]
