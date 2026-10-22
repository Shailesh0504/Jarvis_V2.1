# plugins/equity_research/permissions.py
"""Permissions declaration for Equity Research Plugin."""

from core.permissions import PluginCapability

PERMISSIONS_REQUIRED = [
    PluginCapability.NETWORK.value,
]
