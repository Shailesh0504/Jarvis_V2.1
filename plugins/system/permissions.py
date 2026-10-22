# plugins/system/permissions.py
"""Permissions declaration for System Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.PROCESS.value
]
