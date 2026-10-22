# core/wallpaper/providers/__init__.py
"""
Wallpaper Search Providers package.
"""

from core.wallpaper.providers.base import WallpaperSearchProvider
from core.wallpaper.providers.wallhaven import WallhavenProvider
from core.wallpaper.providers.bing_images import BingImageProvider
from core.wallpaper.providers.wikimedia import WikimediaCommonsProvider

__all__ = [
    "WallpaperSearchProvider",
    "WallhavenProvider",
    "BingImageProvider",
    "WikimediaCommonsProvider",
]
