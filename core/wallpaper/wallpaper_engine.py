# core/wallpaper/wallpaper_engine.py
"""
Central Wallpaper Engine for Jarvis V2.1.
Orchestrates API-free image discovery, validation, caching, Windows setting, and verification.
"""

import logging
import random
import time
from typing import Optional

from core.connectivity import ConnectivityManager
from core.wallpaper.image_downloader import ImageDownloader
from core.wallpaper.image_validator import ImageValidator
from core.wallpaper.models import CandidateImage, WallpaperRequest, WallpaperResult
from core.wallpaper.preference_tracker import WallpaperPreferenceTracker
from core.wallpaper.query_enhancer import CURATED_RANDOM_THEMES, WallpaperQueryEnhancer
from core.wallpaper.search_manager import WallpaperSearchManager
from core.wallpaper.wallpaper_cache import WallpaperCacheManager
from core.wallpaper.wallpaper_service import WindowsWallpaperService

logger = logging.getLogger("jarvis.wallpaper.engine")


class WallpaperEngine:
    """Authoritative coordinator for automated desktop wallpaper management."""

    _instance: Optional["WallpaperEngine"] = None

    def __init__(
        self,
        search_manager: Optional[WallpaperSearchManager] = None,
        cache_manager: Optional[WallpaperCacheManager] = None,
        downloader: Optional[ImageDownloader] = None,
        connectivity_manager: Optional[ConnectivityManager] = None,
    ):
        self.search_manager = search_manager or WallpaperSearchManager()
        self.cache_manager = cache_manager or WallpaperCacheManager()
        self.downloader = downloader or ImageDownloader(timeout=8.0)
        self.connectivity_manager = connectivity_manager or ConnectivityManager()
        self.preferences = WallpaperPreferenceTracker()

    @classmethod
    def get_instance(cls) -> "WallpaperEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def process_wallpaper_request(self, raw_text: str) -> WallpaperResult:
        """End-to-end handler for natural language wallpaper requests."""
        start_t = time.perf_counter()

        # 1. Truthful Offline Safety Check
        if self.connectivity_manager and not self.connectivity_manager.is_online:
            logger.info("Offline mode active: refusing wallpaper search truthfully")
            return WallpaperResult(
                success=False,
                formatted_response="Abhi internet connection nahi hai, isliye wallpaper search nahi kar sakta.",
                is_offline=True,
                execution_time_ms=(time.perf_counter() - start_t) * 1000,
            )

        # 2. Context-Aware Query Enhancement
        ctx_topic = self.preferences.get_context_topic()
        was_awaiting = self.preferences.is_awaiting_clarification()
        ctx_mods = self.preferences.get_context_modifiers()
        request = WallpaperQueryEnhancer.enhance_request(
            raw_text=raw_text,
            context_topic=ctx_topic,
            context_modifiers=ctx_mods,
        )

        # 3. Ambiguous Intent Handling ("wallpaper change karo")
        if request.is_ambiguous:
            self.preferences.set_pending_clarification()
            return WallpaperResult(
                success=False,
                formatted_response="Kaunsa wallpaper lagana hai, Boss?",
                execution_time_ms=(time.perf_counter() - start_t) * 1000,
            )

        # Clear pending clarification since a topic was specified
        if was_awaiting:
            self.preferences.clear_pending_clarification()


        # 4. Random / Automatic Selection Handling
        search_query = request.visual_query
        if request.is_random:
            preferred = self.preferences.get_top_preferred_styles()
            if preferred and random.random() < 0.5:
                search_query = f"{preferred[0]} 4k desktop wallpaper"
            else:
                search_query = random.choice(CURATED_RANDOM_THEMES)

        # 5. Retrieve Monitor Display Metrics
        display_metrics = WindowsWallpaperService.get_display_metrics()

        # 6. Execute Provider Search
        candidates = self.search_manager.search(
            query=search_query,
            display_metrics=display_metrics,
            max_results=8,
        )
        if not candidates:
            msg = f"{request.visual_query.title()} wallpaper nahi mil pa raha, isliye abhi wallpaper change nahi kar saka."
            return WallpaperResult(
                success=False,
                formatted_response=msg,
                execution_time_ms=(time.perf_counter() - start_t) * 1000,
            )

        # 7. Candidate Download, Validation & Application Loop
        applied_path, winning_cand = self._apply_best_candidate(candidates, request, search_query)
        exec_ms = (time.perf_counter() - start_t) * 1000

        if not applied_path or not winning_cand:
            return WallpaperResult(
                success=False,
                formatted_response="Wallpaper download ya validate karne mein dikkat aayi, Boss.",
                execution_time_ms=exec_ms,
            )

        # 8. Record Preference and Construct Spoken Feedback
        self.preferences.record_success(
            query=search_query,
            visual_query=request.visual_query or search_query,
            modifiers=request.modifiers,
        )

        subject_label = request.visual_query.title() if request.visual_query else "Desktop"
        if request.is_random:
            spoken_feedback = f"Ek {request.visual_query or 'naya'} wallpaper laga diya, Boss."
        else:
            spoken_feedback = f"{subject_label} wallpaper laga diya, Boss."

        return WallpaperResult(
            success=True,
            formatted_response=spoken_feedback,
            image_path=applied_path,
            candidate=winning_cand,
            execution_time_ms=exec_ms,
            verified=True,
        )

    def _apply_best_candidate(
        self,
        candidates: list,
        request: WallpaperRequest,
        search_query: str,
    ) -> tuple:
        """Attempts download, validation, and OS application across candidate list."""
        for cand in candidates:
            temp_path = self.cache_manager.get_temp_target_path(cand.format)
            dl_ok, dl_err = self.downloader.download_image(cand.image_url, temp_path)
            if not dl_ok:
                continue

            valid, val_reason, val_meta = ImageValidator.validate_file(temp_path)
            if not valid:
                logger.info(f"Candidate validation rejected: {val_reason}")
                continue

            # Update candidate metadata with validated values
            if val_meta:
                cand.width = val_meta.get("width")
                cand.height = val_meta.get("height")
                cand.format = val_meta.get("format", "JPEG").lower()

            # Promote to dedicated cache
            current_path = self.cache_manager.promote_to_current(
                validated_file_path=temp_path,
                candidate=cand,
                query=search_query,
                visual_query=request.visual_query,
            )

            # Apply to Windows Desktop
            apply_ok, apply_err = WindowsWallpaperService.apply_wallpaper(current_path)
            if apply_ok:
                return current_path, cand

        return None, None


def get_wallpaper_engine() -> WallpaperEngine:
    """Returns the singleton WallpaperEngine instance."""
    return WallpaperEngine.get_instance()
