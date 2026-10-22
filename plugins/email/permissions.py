# plugins/email/permissions.py
"""Permissions declaration for Email Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
    PluginCapability.OFFICE.value,
    PluginCapability.FILESYSTEM.value,
    PluginCapability.PROCESS.value
]
