# plugins/vlc/permissions.py
"""Permissions declaration for VLC Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value,
    PluginCapability.PROCESS.value
]
