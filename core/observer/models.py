# core/observer/models.py
"""Data models and enumerations for the proactive observer subsystem."""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional, Tuple
import uuid


class ActivityType(str, Enum):
    """Types of observable desktop activity events."""
    APPLICATION_OPENED = "APPLICATION_OPENED"
    APPLICATION_CLOSED = "APPLICATION_CLOSED"
    WINDOW_CHANGED = "WINDOW_CHANGED"
    WEBSITE_OPENED = "WEBSITE_OPENED"
    PAGE_CHANGED = "PAGE_CHANGED"
    VIDEO_VISIBLE = "VIDEO_VISIBLE"
    VIDEO_PLAYED = "VIDEO_PLAYED"
    VIDEO_PAUSED = "VIDEO_PAUSED"
    VIDEO_STOPPED = "VIDEO_STOPPED"
    VOLUME_CHANGED = "VOLUME_CHANGED"
    FILE_OPENED = "FILE_OPENED"
    DOCUMENT_EDITED = "DOCUMENT_EDITED"
    USER_IDLE = "USER_IDLE"
    USER_ACTIVE = "USER_ACTIVE"


class ActivityImportance(str, Enum):
    """Importance weighting for activity events to control memory storage and processing."""
    LOW = "LOW"        # Minor cursor/focus changes, periodic idle checks
    MEDIUM = "MEDIUM"  # App changes, website changes, tab changes, volume changes
    HIGH = "HIGH"      # Media playback, file opened, workflow actions, user confirmations


@dataclass(frozen=True)
class DesktopSnapshot:
    """Point-in-time snapshot of the desktop environment."""
    hwnd: int
    title: str
    process_name: str
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    is_idle: bool = False
    idle_seconds: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        """Returns True if the snapshot contains an identifiable active window."""
        return bool(self.hwnd and self.title.strip())


@dataclass
class ActivityEvent:
    """Structured record of a meaningful desktop activity event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: ActivityType = ActivityType.WINDOW_CHANGED
    importance: ActivityImportance = ActivityImportance.MEDIUM
    application: str = ""
    window_title: str = ""
    content_title: Optional[str] = None
    website: Optional[str] = None
    url: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    source: str = "window_observer"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the event into a clean dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else str(self.event_type),
            "importance": self.importance.value if isinstance(self.importance, Enum) else str(self.importance),
            "application": self.application,
            "window_title": self.window_title,
            "content_title": self.content_title,
            "website": self.website,
            "url": self.url,
            "timestamp": self.timestamp,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "metadata": dict(self.metadata)
        }
