# plugins/trading_signals/manifest.py
"""Plugin Manifest wrapper for Trading Signals Plugin."""

from plugins.manifest import PluginManifest
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

MANIFEST = PluginManifest(
    name="trading_signals",
    version="1.0.0",
    description="Screen-Only Live Options Buy/Exit Signal Engine for NIFTY Index and Option confluence (Signal-Only Decision Support).",
    author="Jarvis Team",
    enabled=True,
    permissions=PERMISSIONS_REQUIRED,
    actions=ACTIONS
)
