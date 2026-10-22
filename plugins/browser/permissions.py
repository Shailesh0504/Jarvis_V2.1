# plugins/browser/permissions.py
"""Permissions declaration for Browser Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
    PluginCapability.PROCESS.value
]
