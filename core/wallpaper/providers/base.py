# core/wallpaper/providers/base.py
"""
Abstract base class for API-free wallpaper search providers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from core.wallpaper.models import CandidateImage, DisplayMetrics


class WallpaperSearchProvider(ABC):
    """Base interface for public web and wallpaper search providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the unique human-readable name of the provider."""
        pass

    @abstractmethod
    def search_images(
        self,
        query: str,
        display_metrics: Optional[DisplayMetrics] = None,
        max_results: int = 8,
    ) -> List[CandidateImage]:
        """
        Executes an API-free public search for wallpaper images.
        Must handle network failures locally and return empty list on failure.
        """
        pass

    def is_available(self) -> bool:
        """Optional healthcheck or availability indicator."""
        return True
