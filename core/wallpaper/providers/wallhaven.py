# core/wallpaper/providers/wallhaven.py
"""
Wallhaven public wallpaper search provider (Zero API keys required).
Directly queries Wallhaven's public search endpoint for high-resolution desktop wallpapers.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from core.wallpaper.models import AspectRatioTier, CandidateImage, DisplayMetrics
from core.wallpaper.providers.base import WallpaperSearchProvider

logger = logging.getLogger("jarvis.wallpaper.providers.wallhaven")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


class WallhavenProvider(WallpaperSearchProvider):
    """Searches Wallhaven for desktop wallpapers with resolution and SFW purity filtering."""

    def __init__(self, timeout: float = 3.5):
        self.timeout = timeout
        self.base_url = "https://wallhaven.cc/api/v1/search"

    def get_provider_name(self) -> str:
        return "Wallhaven"

    def search_images(
        self,
        query: str,
        display_metrics: Optional[DisplayMetrics] = None,
        max_results: int = 8,
    ) -> List[CandidateImage]:
        candidates: List[CandidateImage] = []
        try:
            clean_query = query.strip()
            # Normalize common compound names
            for comp, exp in [("ironman", "iron man"), ("spiderman", "spider man"), ("antman", "ant man")]:
                clean_query = re.sub(rf"\b{comp}\b", exp, clean_query, flags=re.IGNORECASE)

            # Determine suitable aspect ratio parameter
            ratios = "16x9,16x10"
            if display_metrics:
                if display_metrics.tier == AspectRatioTier.ULTRAWIDE:
                    ratios = "21x9,16x9"
                elif display_metrics.tier == AspectRatioTier.SUPER_ULTRAWIDE:
                    ratios = "32x9,21x9"

            params = {
                "q": clean_query,
                "categories": "110",  # General + Anime, SFW
                "purity": "100",      # 100 = SFW strictly
                "sorting": "relevance",
                "ratios": ratios,
            }
            encoded_url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(encoded_url, headers=DEFAULT_HEADERS)

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    logger.warning(f"Wallhaven returned status {resp.status}")
                    return []
                raw_data = resp.read().decode("utf-8", errors="ignore")
                payload = json.loads(raw_data)

            items = payload.get("data", [])
            for item in items[:max_results]:
                full_path = item.get("path")
                if not full_path:
                    continue

                res_str = item.get("resolution", "")
                w, h = None, None
                if "x" in res_str:
                    try:
                        parts = res_str.split("x")
                        w, h = int(parts[0]), int(parts[1])
                    except (ValueError, IndexError):
                        pass

                aspect = (float(w) / float(h)) if (w and h and h > 0) else None
                candidates.append(CandidateImage(
                    image_url=full_path,
                    source_name="Wallhaven",
                    source_url=item.get("url") or full_path,
                    title=f"Wallhaven {item.get('id', '')} - {query}",
                    width=w,
                    height=h,
                    format=item.get("file_type", "image/jpeg").split("/")[-1],
                    size_bytes=item.get("file_size"),
                    aspect_ratio=aspect,
                    licensing="Wallhaven Community (Personal Desktop Use)",
                    relevance_score=1.0,
                ))

            logger.info(f"Wallhaven found {len(candidates)} candidate wallpapers for query '{query}'")
        except Exception as e:
            logger.warning(f"Wallhaven search failed for '{query}': {e}")

        return candidates
