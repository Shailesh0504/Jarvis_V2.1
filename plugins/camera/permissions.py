# plugins/camera/permissions.py
"""Permissions declaration for Camera Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.CAMERA.value,
    PluginCapability.FILESYSTEM.value
]
