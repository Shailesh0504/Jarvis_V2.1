# core/observer/__init__.py
"""
Proactive Desktop Activity Observer Package for Jarvis V2.
Provides passive, event-driven observation of foreground windows, user idle states,
content extraction, dual-tier activity memory, and structured activity event streaming.
"""

from .models import (
    ActivityEvent,
    ActivityImportance,
    ActivityType,
    DesktopSnapshot,
)
from .screen_observer import ScreenObserver
from .window_observer import WindowObserver
from .content_extractor import ContentExtractor
from .volume_observer import VolumeObserver
from .activity_memory import ActivityMemory
from .activity_observer import ProactiveActivityObserver

__all__ = [
    "ActivityEvent",
    "ActivityImportance",
    "ActivityType",
    "DesktopSnapshot",
    "ScreenObserver",
    "WindowObserver",
    "ContentExtractor",
    "VolumeObserver",
    "ActivityMemory",
    "ProactiveActivityObserver",
]
