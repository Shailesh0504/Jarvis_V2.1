# core/wallpaper/__init__.py
"""
Jarvis API-Free Desktop Wallpaper Subsystem.
"""

from core.wallpaper.models import (
    AspectRatioTier,
    CandidateImage,
    DisplayMetrics,
    WallpaperRequest,
    WallpaperResult,
)
from core.wallpaper.wallpaper_engine import WallpaperEngine, get_wallpaper_engine

__all__ = [
    "AspectRatioTier",
    "CandidateImage",
    "DisplayMetrics",
    "WallpaperEngine",
    "WallpaperRequest",
    "WallpaperResult",
    "get_wallpaper_engine",
]
