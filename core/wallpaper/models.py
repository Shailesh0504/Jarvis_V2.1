# core/wallpaper/models.py
"""
Data models and contracts for Jarvis API-Free Desktop Wallpaper Engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class AspectRatioTier(str, Enum):
    STANDARD_WIDE = "16:9"
    WIDE_WORK = "16:10"
    ULTRAWIDE = "21:9"
    SUPER_ULTRAWIDE = "32:9"
    PORTRAIT = "portrait"
    SQUARE = "square"
    OTHER = "other"


@dataclass
class DisplayMetrics:
    """Detected desktop screen metrics."""
    width: int = 1920
    height: int = 1080
    aspect_ratio: float = 1.7777777777777777
    tier: AspectRatioTier = AspectRatioTier.STANDARD_WIDE


@dataclass
class CandidateImage:
    """Metadata for a candidate wallpaper found via public search."""
    image_url: str
    source_name: str
    source_url: str
    title: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    format: str = "jpg"
    size_bytes: Optional[int] = None
    aspect_ratio: Optional[float] = None
    licensing: str = "Public Web / Wallhaven / Wikimedia"
    relevance_score: float = 1.0


@dataclass
class WallpaperRequest:
    """Parsed wallpaper request parameters."""
    raw_query: str
    visual_query: str
    modifiers: List[str] = field(default_factory=list)
    is_random: bool = False
    is_ambiguous: bool = False
    preferred_category: Optional[str] = None
    context_refinement: bool = False


@dataclass
class WallpaperResult:
    """Outcome of a wallpaper operation."""
    success: bool
    formatted_response: str
    image_path: Optional[str] = None
    candidate: Optional[CandidateImage] = None
    execution_time_ms: float = 0.0
    verified: bool = False
    is_offline: bool = False
    error_message: Optional[str] = None
