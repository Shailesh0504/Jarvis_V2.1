# plugins/pdf/permissions.py
"""Permissions declaration for PDF Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value,
    PluginCapability.OFFICE.value
]
