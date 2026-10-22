# core/wallpaper/preference_tracker.py
"""
Tracks user style preferences, conversational continuity, and query history for wallpapers.
"""

from collections import Counter
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("jarvis.wallpaper.preferences")


class WallpaperPreferenceTracker:
    """Manages active conversation context and user wallpaper style preferences."""

    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self.last_query: str = ""
        self.last_visual_query: str = ""
        self.last_modifiers: List[str] = []
        self.last_applied_at = time.time()
        self.style_counts: Counter = Counter()
        self.pending_clarification: bool = False
        self.pending_clarification_at: float = 0.0

    def set_pending_clarification(self) -> None:
        self.pending_clarification = True
        self.pending_clarification_at = time.time()

    def clear_pending_clarification(self) -> None:
        self.pending_clarification = False
        self.pending_clarification_at = 0.0

    def is_awaiting_clarification(self, timeout: float = 120.0) -> bool:
        if not self.pending_clarification:
            return False
        if (time.time() - self.pending_clarification_at) > timeout:
            self.clear_pending_clarification()
            return False
        return True

    def record_success(self, query: str, visual_query: str, modifiers: List[str]) -> None:
        """Records successful wallpaper application and updates style frequency."""
        self.last_query = query
        self.last_visual_query = visual_query
        self.last_modifiers = list(modifiers)
        self.last_applied_at = time.time()

        if visual_query:
            self.style_counts[visual_query.lower()] += 1
        for mod in modifiers:
            self.style_counts[mod.lower()] += 1

    def is_context_active(self) -> bool:
        """Returns True if previous wallpaper interaction occurred within TTL."""
        if not self.last_visual_query:
            return False
        return (time.time() - self.last_applied_at) <= self.ttl_seconds

    def get_context_topic(self) -> Optional[str]:
        return self.last_visual_query if self.is_context_active() else None

    def get_context_modifiers(self) -> List[str]:
        return self.last_modifiers if self.is_context_active() else []

    def get_top_preferred_styles(self, top_n: int = 3) -> List[str]:
        """Returns most frequently requested styles for smart random suggestions."""
        return [item[0] for item in self.style_counts.most_common(top_n)]
