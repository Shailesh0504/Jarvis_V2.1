# plugins/code_assistant/permissions.py
"""Permissions declaration for Developer Code Assistant Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value,
    PluginCapability.PROCESS.value,
]
