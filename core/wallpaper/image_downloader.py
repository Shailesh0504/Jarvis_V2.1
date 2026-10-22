# core/wallpaper/image_downloader.py
"""
Safe image downloader with streaming limits, timeout control, and untrusted data isolation.
"""

import logging
import os
import urllib.parse
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.wallpaper.downloader")

DEFAULT_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB max stream cap
CHUNK_SIZE = 64 * 1024                 # 64 KB chunk size


class ImageDownloader:
    """Safely downloads candidate wallpaper images to local temporary cache."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def download_image(self, url: str, destination_path: str) -> Tuple[bool, Optional[str]]:
        """
        Streams image data from public URL to destination file.
        Returns: (success, error_message)
        """
        # Validate URL scheme
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Invalid URL scheme: {parsed.scheme}"

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)

        tmp_path = destination_path + ".tmp"
        try:
            req = urllib.request.Request(url, headers=DEFAULT_DOWNLOAD_HEADERS)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    return False, f"HTTP download returned status {resp.status}"

                content_type = resp.headers.get("Content-Type", "").lower()
                if content_type and any(bad in content_type for bad in ("text/html", "application/json", "text/plain")):
                    return False, f"Refused download: Content-Type '{content_type}' is not an image"

                downloaded_bytes = 0
                with open(tmp_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > MAX_DOWNLOAD_BYTES:
                            return False, f"Exceeded maximum download limit of {MAX_DOWNLOAD_BYTES} bytes"
                        out_f.write(chunk)

            # Atomic replace
            if os.path.exists(destination_path):
                os.remove(destination_path)
            os.rename(tmp_path, destination_path)
            logger.info(f"Successfully downloaded {downloaded_bytes} bytes to {destination_path}")
            return True, None

        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.warning(f"Download failed from '{url}': {e}")
            return False, str(e)
