# core/wallpaper/search_manager.py
"""
Search Manager orchestrating the provider fallback chain and ranking candidates.
"""

import logging
from typing import List, Optional

from core.wallpaper.models import CandidateImage, DisplayMetrics
from core.wallpaper.providers.base import WallpaperSearchProvider
from core.wallpaper.providers.bing_images import BingImageProvider
from core.wallpaper.providers.wallhaven import WallhavenProvider
from core.wallpaper.providers.wikimedia import WikimediaCommonsProvider

logger = logging.getLogger("jarvis.wallpaper.search_manager")


class WallpaperSearchManager:
    """Coordinates search providers with resilient fallback chaining."""

    def __init__(self, providers: Optional[List[WallpaperSearchProvider]] = None):
        self.providers = providers if providers is not None else [
            WallhavenProvider(),
            BingImageProvider(),
            WikimediaCommonsProvider(),
        ]

    def search(
        self,
        query: str,
        display_metrics: Optional[DisplayMetrics] = None,
        max_results: int = 8,
    ) -> List[CandidateImage]:
        """
        Executes search across providers using fallback chain.
        Returns ranked candidate images.
        """
        all_candidates: List[CandidateImage] = []
        for provider in self.providers:
            try:
                candidates = provider.search_images(
                    query=query,
                    display_metrics=display_metrics,
                    max_results=max_results,
                )
                if candidates:
                    logger.info(f"Provider '{provider.get_provider_name()}' succeeded with {len(candidates)} candidates")
                    all_candidates.extend(candidates)
                    if len(all_candidates) >= max_results:
                        break
            except Exception as e:
                logger.warning(f"Provider '{provider.get_provider_name()}' encountered error: {e}")
                continue

        if all_candidates:
            return self._rank_candidates(all_candidates, display_metrics)[:max_results]

        logger.warning(f"All wallpaper providers failed or returned no results for '{query}'")
        return []

    def _rank_candidates(
        self,
        candidates: List[CandidateImage],
        display_metrics: Optional[DisplayMetrics],
    ) -> List[CandidateImage]:
        """Ranks candidates prioritizing resolution and aspect ratio suitability."""
        if not display_metrics:
            return candidates

        target_aspect = display_metrics.aspect_ratio
        target_w = display_metrics.width
        target_h = display_metrics.height

        def score_candidate(cand: CandidateImage) -> float:
            score = cand.relevance_score

            # Resolution bonus
            if cand.width and cand.height:
                if cand.width >= target_w and cand.height >= target_h:
                    score += 0.5
                if cand.width >= 1920:
                    score += 0.3

            # Aspect ratio delta penalty
            if cand.aspect_ratio:
                diff = abs(cand.aspect_ratio - target_aspect)
                score -= min(diff * 0.4, 0.6)

            return score

        return sorted(candidates, key=score_candidate, reverse=True)
