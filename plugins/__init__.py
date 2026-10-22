# plugins/__init__.py
"""Plugins subsystem for modular tool integration in Jarvis V2."""

from .manifest import PluginManifest, PluginAction, PluginParameter, PluginResult
from .base import BasePlugin
from .manager import PluginManager

__all__ = [
    "PluginManifest",
    "PluginAction",
    "PluginParameter",
    "PluginResult",
    "BasePlugin",
    "PluginManager",
]
