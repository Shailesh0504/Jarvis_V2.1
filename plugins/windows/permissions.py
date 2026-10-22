# plugins/windows/permissions.py
"""Permissions declaration for Windows Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.PROCESS.value,
    PluginCapability.SYSTEM_CONTROL.value
]
