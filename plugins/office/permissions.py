# plugins/office/permissions.py
"""Permissions declaration for Office Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.OFFICE.value,
    PluginCapability.FILESYSTEM.value,
    PluginCapability.PROCESS.value
]
