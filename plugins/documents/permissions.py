# plugins/documents/permissions.py
"""Permissions declaration for Documents Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value
]
