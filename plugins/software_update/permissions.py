# plugins/software_update/permissions.py
"""Permissions declaration for Software Update Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.PROCESS.value,
    PluginCapability.NETWORK.value,
]
