# plugins/whatsapp/permissions.py
"""
Permission definitions for the WhatsApp Plugin.
"""

from core.permissions import PermissionLevel, PluginCapability


class WhatsAppPermissions:
    READ_CHAT = PermissionLevel.READ
    SEND_MESSAGE = PermissionLevel.WRITE
    CALL = PermissionLevel.WRITE


PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
]
