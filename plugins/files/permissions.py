# plugins/files/permissions.py
"""Permissions declaration for Files Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value
]
