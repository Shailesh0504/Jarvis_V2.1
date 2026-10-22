# plugins/archive/permissions.py
"""Permissions declaration for Archive Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value
]
