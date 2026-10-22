# plugins/location/permissions.py
"""
Permission definitions for the Location & Geography Plugin.
"""

from core.permissions import PermissionLevel, PluginCapability


class LocationPermissions:
    READ_GEO = PermissionLevel.READ
    OPEN_MAP = PermissionLevel.EXECUTE


PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
]
