# plugins/games/permissions.py
"""Permissions configuration for Games Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.PROCESS.value,
    PluginCapability.SYSTEM_CONTROL.value,
]
