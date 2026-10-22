# plugins/math/permissions.py
"""
Permission definitions for the Math Plugin.
Calculations are read-only mathematical operations.
"""

from core.permissions import PermissionLevel


class MathPermissions:
    CALCULATE = PermissionLevel.READ
    SOLVE = PermissionLevel.READ
    STATISTICS = PermissionLevel.READ


PERMISSIONS_REQUIRED = []
