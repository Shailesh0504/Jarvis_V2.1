# plugins/activity_monitor/__init__.py
"""Activity monitor package for persistent screen awareness and activity memory."""

from .plugin import ActivityMonitorPlugin
from .memory import ActivityEvent, ActivityMemory
from .observer import ActivityObserver

__all__ = ["ActivityMonitorPlugin", "ActivityEvent", "ActivityMemory", "ActivityObserver"]
