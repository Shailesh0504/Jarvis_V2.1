# plugins/ocr/permissions.py
"""Permissions declaration for OCR Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.FILESYSTEM.value,
    PluginCapability.SYSTEM_CONTROL.value
]
