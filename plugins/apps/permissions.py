# plugins/apps/permissions.py
"""Permissions declaration for Apps Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.PROCESS.value,
    PluginCapability.SYSTEM_CONTROL.value
]
