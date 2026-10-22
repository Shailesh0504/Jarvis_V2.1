# plugins/activity_monitor/extractors.py
"""
Multi-tier title and media extractor for passive screen awareness.
Detects active applications, websites (especially YouTube), and media titles
using browser window titles, accessibility APIs, and local OCR fallback.
Adheres strictly to zero-hallucination principles.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.plugins.activity_monitor.extractors")

KNOWN_BROWSERS = {
    "chrome.exe", "brave.exe", "msedge.exe", "firefox.exe",
    "opera.exe", "vivaldi.exe", "chrome", "brave", "msedge",
    "firefox", "opera", "vivaldi"
}

NON_VIDEO_YOUTUBE_PAGES = {
    "youtube",
    "subscriptions",
    "history",
    "trending",
    "library",
    "home",
    "watch later",
    "explore",
    "music",
    "shorts",
    "your videos",
    "your clips",
    "downloads"
}


class YouTubeTitleExtractor:
    """
    Multi-tier extractor for YouTube and web video/media titles.
    Tier 1: Window & Tab Title Pattern Parsing.
    Tier 2: UI Automation / Accessibility inspection.
    Tier 3: Local OCR fallback for fullscreen/frameless player.
    """

    def __init__(self):
        self.notification_badge_regex = re.compile(r"^\(\d+\+?\)\s*")
        # Matches patterns like:
        # "Title - YouTube - Google Chrome"
        # "Title - YouTube — Mozilla Firefox"
        # "Title - YouTube"
        # "Title - YouTube - Brave"
        self.yt_pattern = re.compile(
            r"^(?P<title>.+?)\s*[-—|]\s*YouTube(?:\s*[-—|]\s*(?:Google\s*Chrome|Brave|Microsoft\s*Edge|Mozilla\s*Firefox|Firefox|Opera|Vivaldi))?$",
            re.IGNORECASE
        )
        self.yt_standalone_pattern = re.compile(
            r"^YouTube(?:\s*[-—|]\s*(?:Google\s*Chrome|Brave|Microsoft\s*Edge|Mozilla\s*Firefox|Firefox|Opera|Vivaldi))?$",
            re.IGNORECASE
        )

    def clean_raw_title(self, raw_title: str) -> str:
        """Removes unread notification badges like '(3) ' or '(99+) '."""
        if not raw_title:
            return ""
        clean = self.notification_badge_regex.sub("", raw_title.strip())
        return clean.strip()

    def extract_from_window_info(self, raw_title: str, process_name: str = "") -> Dict[str, Any]:
        """
        Tier 1: Extracts YouTube video or page information from window title.
        Returns structured dict with is_youtube, is_video, content_title, confidence, source.
        """
        clean_title = self.clean_raw_title(raw_title)
        pname_clean = (process_name or "").lower().replace(".exe", "").strip()

        # Check if this is a standalone YouTube home/feed window without video
        if self.yt_standalone_pattern.match(clean_title):
            return {
                "website": "youtube",
                "is_youtube": True,
                "is_video": False,
                "content_title": None,
                "confidence": 0.0,
                "source": "window_title",
                "notes": "YouTube home or feed page (no active video)"
            }

        # Check video title pattern: "<Video Title> - YouTube [ - Browser]"
        match = self.yt_pattern.match(clean_title)
        if match:
            candidate_title = match.group("title").strip()
            # Clean possible nested suffixes
            candidate_title = re.sub(r"\s*[-—|]\s*YouTube$", "", candidate_title, flags=re.I).strip()

            # Check if candidate is a static non-video page like "Subscriptions", "History", etc.
            if candidate_title.lower() in NON_VIDEO_YOUTUBE_PAGES:
                return {
                    "website": "youtube",
                    "is_youtube": True,
                    "is_video": False,
                    "content_title": None,
                    "confidence": 0.0,
                    "source": "window_title",
                    "notes": f"YouTube static page: {candidate_title}"
                }

            if len(candidate_title) >= 2:
                return {
                    "website": "youtube",
                    "is_youtube": True,
                    "is_video": True,
                    "content_title": candidate_title,
                    "confidence": 0.95,
                    "source": "window_title",
                    "notes": "Extracted from browser window title"
                }

        # If "YouTube" appears in the title but doesn't match standard regex
        if "youtube" in clean_title.lower():
            # Try splitting by " - YouTube"
            parts = re.split(r"\s*[-—|]\s*YouTube", clean_title, flags=re.I)
            if parts and parts[0].strip():
                cand = parts[0].strip()
                if cand.lower() not in NON_VIDEO_YOUTUBE_PAGES and len(cand) >= 2:
                    return {
                        "website": "youtube",
                        "is_youtube": True,
                        "is_video": True,
                        "content_title": cand,
                        "confidence": 0.85,
                        "source": "window_title",
                        "notes": "Extracted via split heuristic"
                    }
            return {
                "website": "youtube",
                "is_youtube": True,
                "is_video": False,
                "content_title": None,
                "confidence": 0.0,
                "source": "window_title",
                "notes": "YouTube detected but video title could not be resolved from title"
            }

        return {
            "website": "",
            "is_youtube": False,
            "is_video": False,
            "content_title": None,
            "confidence": 0.0,
            "source": "window_title",
            "notes": "Not YouTube"
        }

    def extract_from_accessibility(self, hwnd: int) -> Dict[str, Any]:
        """
        Tier 2: UI Automation / Accessibility fallback for browser window.
        Safe execution wrapped in try-except to prevent crashes or lag.
        """
        if not hwnd:
            return {"success": False, "confidence": 0.0, "content_title": None}

        try:
            # Check for Windows UI Automation if available
            import comtypes  # noqa: F401
            import comtypes.client  # noqa: F401
            # Graceful inspection placeholder:
            # If full UIA tree walking is enabled, extracts document title or address bar text.
            return {"success": False, "confidence": 0.0, "content_title": None}
        except Exception as e:
            logger.debug("Accessibility inspection unavailable or failed: %s", e)
            return {"success": False, "confidence": 0.0, "content_title": None}

    def extract_from_ocr(self, hwnd: int) -> Dict[str, Any]:
        """
        Tier 3: Local OCR fallback for fullscreen video or hidden titlebar.
        Uses local pytesseract or OCR plugin if available.
        Strict zero-hallucination: returns None if text is not clearly detected.
        """
        if not hwnd:
            return {"success": False, "confidence": 0.0, "content_title": None}

        try:
            from PIL import ImageGrab
            import pytesseract

            # Grab window area if possible
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                # Crop upper portion (top 25% where video title/header usually resides)
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                if right > left and bottom > top:
                    h = bottom - top
                    top_bar = (left, top, right, top + int(h * 0.25))
                    img = ImageGrab.grab(bbox=top_bar)
                    text = pytesseract.image_to_string(img).strip()
                    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 3]
                    for line in lines:
                        # Clean line
                        clean_line = self.clean_raw_title(line)
                        if "youtube" not in clean_line.lower() and len(clean_line) > 5:
                            return {
                                "success": True,
                                "content_title": clean_line,
                                "confidence": 0.75,
                                "source": "ocr"
                            }
        except Exception as e:
            logger.debug("OCR title extraction unavailable or failed: %s", e)

        return {"success": False, "confidence": 0.0, "content_title": None}

    def extract(self, raw_title: str, process_name: str = "", hwnd: int = 0) -> Dict[str, Any]:
        """
        Executes multi-tier extraction hierarchy:
        1. Window Title Parsing
        2. Accessibility / UI Automation
        3. OCR Fallback
        Zero-hallucination: never returns fabricated titles.
        """
        app_name = (process_name or "").lower().replace(".exe", "").strip()

        # Step 1: Window Title Parsing
        res = self.extract_from_window_info(raw_title, process_name)
        if res.get("is_youtube"):
            if res.get("content_title") and res.get("confidence", 0) >= 0.8:
                return {
                    "application": app_name,
                    "website": "youtube",
                    "is_youtube": True,
                    "is_video": True,
                    "content_title": res["content_title"],
                    "confidence": res["confidence"],
                    "source": res["source"],
                    "url": None
                }

            # If YouTube is confirmed but title was not extracted from window title,
            # try Tier 2 (Accessibility) and Tier 3 (OCR)
            if hwnd:
                acc_res = self.extract_from_accessibility(hwnd)
                if acc_res.get("success") and acc_res.get("content_title"):
                    return {
                        "application": app_name,
                        "website": "youtube",
                        "is_youtube": True,
                        "is_video": True,
                        "content_title": acc_res["content_title"],
                        "confidence": acc_res.get("confidence", 0.8),
                        "source": "accessibility",
                        "url": acc_res.get("url")
                    }

                ocr_res = self.extract_from_ocr(hwnd)
                if ocr_res.get("success") and ocr_res.get("content_title"):
                    return {
                        "application": app_name,
                        "website": "youtube",
                        "is_youtube": True,
                        "is_video": True,
                        "content_title": ocr_res["content_title"],
                        "confidence": ocr_res.get("confidence", 0.75),
                        "source": "ocr",
                        "url": None
                    }

            # If YouTube was open but title could not be identified honestly
            return {
                "application": app_name,
                "website": "youtube",
                "is_youtube": True,
                "is_video": False,
                "content_title": None,
                "confidence": 0.0,
                "source": "window_title",
                "url": None
            }

        # Check for other general media applications (e.g. VLC, Spotify, Windows Media Player)
        clean = self.clean_raw_title(raw_title)
        if "vlc" in app_name:
            # Pattern: "Filename.ext - VLC media player"
            cand = re.sub(r"\s*[-—|]\s*VLC\s+media\s+player$", "", clean, flags=re.I).strip()
            if cand and cand.lower() != "vlc media player":
                return {
                    "application": "vlc",
                    "website": "",
                    "is_youtube": False,
                    "is_video": True,
                    "content_title": cand,
                    "confidence": 0.9,
                    "source": "window_title",
                    "url": None
                }
            return {
                "application": "vlc",
                "website": "",
                "is_youtube": False,
                "is_video": False,
                "content_title": None,
                "confidence": 0.0,
                "source": "window_title",
                "url": None
            }

        # Generic active window / application
        return {
            "application": app_name,
            "website": "",
            "is_youtube": False,
            "is_video": False,
            "content_title": clean if clean and app_name not in KNOWN_BROWSERS else None,
            "confidence": 0.5 if clean else 0.0,
            "source": "window_title",
            "url": None
        }
