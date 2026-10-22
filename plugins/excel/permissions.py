# plugins/excel/permissions.py
"""Permissions declaration for Excel Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value,
    PluginCapability.OFFICE.value
]
