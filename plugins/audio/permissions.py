# plugins/audio/permissions.py
"""Permissions declaration for Audio Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.SYSTEM_CONTROL.value
]
