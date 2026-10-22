# plugins/network/permissions.py
"""Permissions declaration for Network Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
    PluginCapability.SYSTEM_CONTROL.value
]
