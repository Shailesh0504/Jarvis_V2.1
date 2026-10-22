# plugins/youtube/permissions.py
"""Permissions declaration for YouTube Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
    PluginCapability.PROCESS.value
]
