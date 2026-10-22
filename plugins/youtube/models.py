# plugins/youtube/models.py
"""Typed state and search models for the YouTube subsystem."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PlaybackState(str, Enum):
    IDLE = "idle"
    OPENED = "opened"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"
    FAILED = "failed"


@dataclass(frozen=True)
class YouTubeResult:
    video_id: str
    title: str
    channel: str = ""
    duration: str = ""
    view_count: str = ""
    published: str = ""
    score: float = 0.0
    unavailable: bool = False

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class QueueItem:
    query: str
    video_id: str = ""
    title: str = ""
    url: str = ""


@dataclass
class YouTubeSession:
    current_video: Optional[YouTubeResult] = None
    current_url: str = ""
    browser_name: str = ""
    browser_executable: str = ""
    playback_state: PlaybackState = PlaybackState.IDLE
    queue: List[QueueItem] = field(default_factory=list)
    history: List[QueueItem] = field(default_factory=list)
    last_search_query: str = ""
    last_position_seconds: int = 0

    def reset_playback(self) -> None:
        self.current_video = None
        self.current_url = ""
        self.playback_state = PlaybackState.STOPPED
        self.last_position_seconds = 0
