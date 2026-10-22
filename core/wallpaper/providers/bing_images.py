# core/wallpaper/providers/bing_images.py
"""
Bing Images public web search provider (Zero API keys required).
Parses public Bing image search HTML with wide aspect and high-resolution filters.
"""

import html
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from core.wallpaper.models import CandidateImage, DisplayMetrics
from core.wallpaper.providers.base import WallpaperSearchProvider

logger = logging.getLogger("jarvis.wallpaper.providers.bing")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BingImageProvider(WallpaperSearchProvider):
    """Fallback provider querying Bing Images public search for wide desktop wallpapers."""

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout
        self.base_url = "https://www.bing.com/images/search"

    def get_provider_name(self) -> str:
        return "Bing Images"

    def _fetch_candidates_for_term(self, term: str, max_results: int) -> List[CandidateImage]:
        candidates: List[CandidateImage] = []
        try:
            encoded_url = f"{self.base_url}?{urllib.parse.urlencode({'q': term})}"
            req = urllib.request.Request(encoded_url, headers=DEFAULT_HEADERS)

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return []
                content = resp.read().decode("utf-8", errors="ignore")

            matches = re.findall(r'm=&quot;(\{.*?\})&quot;', content) or re.findall(r'm="(\{.*?\})"', content)
            for raw_m in matches[: max_results * 3]:
                try:
                    meta = json.loads(html.unescape(raw_m))
                    murl = meta.get("murl")
                    if not murl or not murl.startswith("http"):
                        continue

                    # Filter out obvious non-image or tracking URLs
                    if any(bad in murl.lower() for bad in ("base64", "favicon", ".svg", "/icon", "logo")):
                        continue

                    raw_title = meta.get("t") or term
                    clean_title = re.sub(r"[\ue000-\uf8ff]", "", raw_title).strip()

                    w_raw = meta.get("width")
                    h_raw = meta.get("height")
                    w, h = None, None
                    if w_raw is not None and h_raw is not None:
                        try:
                            w, h = int(w_raw), int(h_raw)
                        except (ValueError, TypeError):
                            pass

                    aspect = (float(w) / float(h)) if (w and h and h > 0) else None

                    # If resolution is specified and it's portrait, skip for desktop wallpaper
                    if w is not None and h is not None and w < h:
                        continue

                    candidates.append(CandidateImage(
                        image_url=murl,
                        source_name="Bing Images",
                        source_url=meta.get("purl") or murl,
                        title=clean_title,
                        width=w,
                        height=h,
                        format="jpg",
                        aspect_ratio=aspect,
                        licensing="Public Web Indexing",
                        relevance_score=0.95,
                    ))
                    if len(candidates) >= max_results:
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Bing Images fetch failed for term '{term}': {e}")

        return candidates

    def search_images(
        self,
        query: str,
        display_metrics: Optional[DisplayMetrics] = None,
        max_results: int = 8,
    ) -> List[CandidateImage]:
        clean_q = query.strip()
        # Normalize compound superhero/character names
        for comp, exp in [("ironman", "iron man"), ("spiderman", "spider man"), ("antman", "ant man")]:
            clean_q = re.sub(rf"\b{comp}\b", exp, clean_q, flags=re.IGNORECASE)

        # Primary high-res search term
        if "wallpaper" not in clean_q.lower():
            primary_term = f"{clean_q} wallpaper 4k"
        else:
            primary_term = f"{clean_q} 4k"

        candidates = self._fetch_candidates_for_term(primary_term, max_results)

        # Fallback if primary yielded very few results
        if len(candidates) < 4:
            fallback_term = f"{clean_q} hd wallpaper" if "wallpaper" not in clean_q.lower() else f"{clean_q} hd"
            if fallback_term != primary_term:
                fb_candidates = self._fetch_candidates_for_term(fallback_term, max_results)
                seen_urls = {c.image_url for c in candidates}
                for fb_c in fb_candidates:
                    if fb_c.image_url not in seen_urls:
                        candidates.append(fb_c)
                        seen_urls.add(fb_c.image_url)
                    if len(candidates) >= max_results:
                        break

        logger.info(f"Bing Images found {len(candidates)} candidate wallpapers for query '{query}'")
        return candidates
