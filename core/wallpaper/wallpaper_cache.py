# core/wallpaper/wallpaper_cache.py
"""
Dedicated application wallpaper cache manager.
Safely stores current wallpaper, metadata, and performs automatic LRU pruning.
"""

import json
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from core.wallpaper.models import CandidateImage

logger = logging.getLogger("jarvis.wallpaper.cache")

DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "wallpaper_cache")
MAX_CACHED_WALLPAPERS = 5
MAX_CACHE_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB


class WallpaperCacheManager:
    """Manages dedicated application storage for desktop wallpapers."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.temp_dir = os.path.join(self.cache_dir, "temp")
        self.metadata_file = os.path.join(self.cache_dir, "metadata.json")
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def get_temp_target_path(self, ext: str = "jpg") -> str:
        """Generates a temporary file path for in-flight downloads."""
        timestamp = int(time.time() * 1000)
        clean_ext = ext.lstrip(".").lower() or "jpg"
        return os.path.join(self.temp_dir, f"dl_{timestamp}.{clean_ext}")

    def promote_to_current(
        self,
        validated_file_path: str,
        candidate: CandidateImage,
        query: str,
        visual_query: str,
    ) -> str:
        """
        Promotes a validated temporary image to current.jpg in the cache,
        updates metadata.json, and prunes obsolete images.
        """
        self._ensure_directories()
        timestamp = int(time.time())
        archive_name = f"wallpaper_{timestamp}.jpg"
        archive_path = os.path.join(self.cache_dir, archive_name)
        current_path = os.path.join(self.cache_dir, "current.jpg")

        # Convert and save as high-quality RGB JPEG for guaranteed Windows OS compatibility
        try:
            from PIL import Image
            with Image.open(validated_file_path) as img:
                rgb_img = img.convert("RGB")
                rgb_img.save(current_path, "JPEG", quality=95)
                rgb_img.save(archive_path, "JPEG", quality=95)
        except Exception as e:
            logger.warning(f"Failed to convert image via Pillow, falling back to copy: {e}")
            shutil.copy2(validated_file_path, archive_path)
            shutil.copy2(validated_file_path, current_path)

        # Write metadata
        metadata: Dict[str, Any] = {
            "query": query,
            "visual_query": visual_query,
            "source_name": candidate.source_name,
            "source_url": candidate.source_url,
            "image_url": candidate.image_url,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
            "width": candidate.width,
            "height": candidate.height,
            "format": "JPG",
            "size_bytes": os.path.getsize(current_path),
            "licensing": candidate.licensing,
            "current_file": current_path,
        }
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write wallpaper metadata.json: {e}")

        # Prune old cache files
        self.prune_cache()

        return os.path.abspath(current_path)

    def get_current_metadata(self) -> Optional[Dict[str, Any]]:
        """Reads current wallpaper metadata if available."""
        if os.path.isfile(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def prune_cache(self) -> None:
        """Removes temporary files and enforces LRU limits on archived wallpapers."""
        try:
            # 1. Clean temp folder
            now = time.time()
            if os.path.isdir(self.temp_dir):
                for f in os.listdir(self.temp_dir):
                    fp = os.path.join(self.temp_dir, f)
                    if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > 600:
                        try:
                            os.remove(fp)
                        except OSError:
                            pass

            # 2. Collect historical wallpaper files
            history_files = []
            for f in os.listdir(self.cache_dir):
                if f.startswith("wallpaper_") and any(f.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".bmp")):
                    fp = os.path.join(self.cache_dir, f)
                    history_files.append((fp, os.path.getmtime(fp), os.path.getsize(fp)))

            # Sort newest first
            history_files.sort(key=lambda x: x[1], reverse=True)

            # Keep only MAX_CACHED_WALLPAPERS
            for fp, _, _ in history_files[MAX_CACHED_WALLPAPERS:]:
                try:
                    os.remove(fp)
                except OSError:
                    pass

        except Exception as e:
            logger.warning(f"Error during wallpaper cache pruning: {e}")
