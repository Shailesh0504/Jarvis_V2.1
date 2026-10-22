# plugins/bluetooth/permissions.py
"""Permissions declaration for Bluetooth Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.NETWORK.value
]
