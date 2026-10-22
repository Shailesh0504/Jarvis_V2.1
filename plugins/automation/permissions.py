# plugins/automation/permissions.py
"""Permissions declaration for Automation Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value,
    PluginCapability.PROCESS.value,
    PluginCapability.FILESYSTEM.value
]
