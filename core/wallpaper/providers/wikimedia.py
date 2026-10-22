# core/wallpaper/providers/wikimedia.py
"""
Wikimedia Commons public media provider (Zero API keys required).
Queries the MediaWiki API for high-resolution public domain and Creative Commons imagery.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional

from core.wallpaper.models import CandidateImage, DisplayMetrics
from core.wallpaper.providers.base import WallpaperSearchProvider

logger = logging.getLogger("jarvis.wallpaper.providers.wikimedia")

DEFAULT_HEADERS = {
    "User-Agent": "JarvisAssistant/2.1 (https://github.com/jarvis; jarvis@local.offline) Python/3.13",
    "Accept": "application/json",
}


class WikimediaCommonsProvider(WallpaperSearchProvider):
    """Fallback provider querying Wikimedia Commons for open-license high-resolution desktop wallpapers."""

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.base_url = "https://commons.wikimedia.org/w/api.php"

    def get_provider_name(self) -> str:
        return "Wikimedia Commons"

    def search_images(
        self,
        query: str,
        display_metrics: Optional[DisplayMetrics] = None,
        max_results: int = 8,
    ) -> List[CandidateImage]:
        candidates: List[CandidateImage] = []
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{query} wallpaper filetype:bitmap",
                "gsrnamespace": "6",  # File: namespace
                "gsrlimit": str(max_results),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "format": "json",
            }
            encoded_url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(encoded_url, headers=DEFAULT_HEADERS)

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return []
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            pages = data.get("query", {}).get("pages", {})
            for _, page_info in pages.items():
                image_infos = page_info.get("imageinfo", [])
                if not image_infos:
                    continue
                info = image_infos[0]
                img_url = info.get("url")
                if not img_url or not img_url.startswith("http"):
                    continue

                w = info.get("width")
                h = info.get("height")
                # Filter out portrait orientation for desktop wallpaper
                if w and h and w < h:
                    continue

                aspect = (float(w) / float(h)) if (w and h and h > 0) else None
                ext_meta = info.get("extmetadata", {})
                license_short = ext_meta.get("LicenseShortName", {}).get("value", "Public Domain / CC")

                candidates.append(CandidateImage(
                    image_url=img_url,
                    source_name="Wikimedia Commons",
                    source_url=info.get("descriptionurl") or img_url,
                    title=page_info.get("title", query).replace("File:", ""),
                    width=w,
                    height=h,
                    format=info.get("mime", "image/jpeg").split("/")[-1],
                    size_bytes=info.get("size"),
                    aspect_ratio=aspect,
                    licensing=f"Wikimedia Commons ({license_short})",
                    relevance_score=0.85,
                ))

            logger.info(f"Wikimedia Commons found {len(candidates)} candidate wallpapers for query '{query}'")
        except Exception as e:
            logger.warning(f"Wikimedia Commons search failed for '{query}': {e}")

        return candidates
