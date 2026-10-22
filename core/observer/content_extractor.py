# core/observer/content_extractor.py
"""
Multi-tier semantic content extractor for desktop applications, browsers, and media players.
Extracts website identities, video titles, search queries, repositories, and document titles
from window titles and process context with zero hallucination.
"""

import logging
import re
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("jarvis.core.observer.content")

# Suffix regexes to strip browser branding from window titles
BROWSER_SUFFIX_RE = re.compile(
    r"\s*[-—|]\s*(?:Google\s*Chrome|Brave(?:\s*Browser)?|Microsoft\s*Edge|Mozilla\s*Firefox|Firefox|Opera|Vivaldi)$",
    re.IGNORECASE
)

# Unread notification counters like "(3) ", "(99+) "
NOTIFICATION_COUNTER_RE = re.compile(r"^\(\d+\+?\)\s*")

# Known non-video YouTube sections
NON_VIDEO_YOUTUBE_PAGES: Set[str] = {
    "youtube", "subscriptions", "history", "trending", "library",
    "home", "watch later", "explore", "music", "shorts", "your videos",
    "your clips", "downloads"
}

# Known browser process names
BROWSER_PROCESSES: Set[str] = {"chrome", "brave", "edge", "firefox", "opera", "vivaldi"}


class ContentExtractor:
    """
    Analyzes window titles and process names to extract meaningful
    semantic content (websites, videos, documents, queries).
    """

    def __init__(self):
        # YouTube pattern: "<title> - YouTube"
        self.yt_pattern = re.compile(r"^(?P<title>.+?)\s*[-—|]\s*YouTube$", re.IGNORECASE)
        # Google Search: "<query> - Google Search" or "<query> - Google"
        self.google_search_pattern = re.compile(r"^(?P<query>.+?)\s*[-—|]\s*Google(?:\s+Search)?$", re.IGNORECASE)
        # GitHub: "<repo/issue> · GitHub" or "<repo> - GitHub"
        self.github_pattern = re.compile(r"^(?P<title>.+?)\s*[-—·|]\s*GitHub$", re.IGNORECASE)
        # ChatGPT / Claude: "<topic> - ChatGPT"
        self.chatgpt_pattern = re.compile(r"^(?P<topic>.+?)\s*[-—|]\s*ChatGPT$", re.IGNORECASE)
        self.claude_pattern = re.compile(r"^(?P<topic>.+?)\s*[-—|]\s*Claude$", re.IGNORECASE)
        # Wikipedia: "<article> - Wikipedia"
        self.wikipedia_pattern = re.compile(r"^(?P<article>.+?)\s*[-—|]\s*Wikipedia.*$", re.IGNORECASE)
        # Reddit: "<post> : r/<subreddit>" or "<subreddit> - Reddit"
        self.reddit_pattern = re.compile(r"^(?P<title>.+?)\s*[-—|:]\s*Reddit.*$", re.IGNORECASE)

    def clean_title(self, raw_title: str) -> str:
        """Strips notification counters and trims whitespace."""
        if not raw_title:
            return ""
        clean = NOTIFICATION_COUNTER_RE.sub("", raw_title.strip())
        return clean.strip()

    def strip_browser_suffix(self, title: str) -> str:
        """Removes trailing browser application name from the title."""
        return BROWSER_SUFFIX_RE.sub("", title).strip()

    def extract(self, raw_title: str, process_name: str = "") -> Dict[str, Any]:
        """
        Main extraction entrypoint. Returns structured metadata dictionary:
        {
            "website": Optional[str],
            "content_title": Optional[str],
            "is_video": bool,
            "is_media": bool,
            "is_document": bool,
            "category": str,  # 'media', 'web', 'document', 'system'
            "confidence": float
        }
        """
        cleaned = self.clean_title(raw_title)
        proc_clean = (process_name or "").lower().replace(".exe", "").strip()

        # 1. Media Players
        if proc_clean == "vlc":
            return self._extract_vlc(cleaned)
        elif proc_clean == "spotify":
            return self._extract_spotify(cleaned)

        # 2. Document & Office Applications
        if proc_clean in ("excel", "winword", "word", "powerpnt", "powerpoint", "vscode", "code", "notepad"):
            return self._extract_document(cleaned, proc_clean)

        # 3. Web Browsers
        if proc_clean in BROWSER_PROCESSES:
            return self._extract_browser(cleaned)

        # 4. Fallback: Generic desktop window
        return {
            "website": None,
            "content_title": cleaned or None,
            "is_video": False,
            "is_media": False,
            "is_document": False,
            "category": "app",
            "confidence": 0.5
        }

    def _extract_vlc(self, title: str) -> Dict[str, Any]:
        """Extracts media title from VLC media player."""
        # VLC title format: "<filename> - VLC media player"
        clean = re.sub(r"\s*[-—|]\s*VLC\s*media\s*player$", "", title, flags=re.IGNORECASE).strip()
        is_playing = bool(clean and clean.lower() != "vlc media player")
        return {
            "website": None,
            "content_title": clean if is_playing else None,
            "is_video": is_playing,
            "is_media": is_playing,
            "is_document": False,
            "category": "media",
            "confidence": 0.95 if is_playing else 0.5
        }

    def _extract_spotify(self, title: str) -> Dict[str, Any]:
        """Extracts track/artist from Spotify desktop."""
        # Spotify title format: "<artist> - <track>" or "Spotify Free" / "Spotify Premium"
        is_generic = bool(re.match(r"^Spotify(?:\s+(?:Free|Premium))?$", title, re.IGNORECASE))
        has_track = bool(title and not is_generic and " - " in title)
        return {
            "website": "spotify",
            "content_title": title if has_track else None,
            "is_video": False,
            "is_media": has_track,
            "is_document": False,
            "category": "media",
            "confidence": 0.90 if has_track else 0.5
        }

    def _extract_document(self, title: str, process_name: str) -> Dict[str, Any]:
        """Extracts active file or workbook from productivity apps."""
        # Excel: "<filename> - Excel"
        # Word: "<filename> - Word"
        # VS Code: "<filename> - <workspace> - Visual Studio Code"
        # Notepad: "<filename> - Notepad"
        clean = title
        if process_name in ("excel", "word", "winword", "notepad"):
            clean = re.sub(r"\s*[-—|]\s*(?:Excel|Word|Notepad)$", "", title, flags=re.IGNORECASE).strip()
        elif process_name in ("vscode", "code"):
            clean = re.sub(r"\s*[-—|]\s*Visual\s*Studio\s*Code$", "", title, flags=re.IGNORECASE).strip()

        has_file = bool(clean and clean.lower() not in (process_name, "untitled", "document1", "book1"))
        return {
            "website": None,
            "content_title": clean or title,
            "is_video": False,
            "is_media": False,
            "is_document": True,
            "category": "document",
            "confidence": 0.90 if has_file else 0.70
        }

    def _extract_browser(self, title: str) -> Dict[str, Any]:
        """Dissects browser window titles into websites and content titles."""
        inner_title = self.strip_browser_suffix(title)

        # A. YouTube
        m_yt = self.yt_pattern.match(inner_title)
        if m_yt or inner_title.lower() == "youtube" or " - youtube" in inner_title.lower():
            raw_vid = m_yt.group("title").strip() if m_yt else re.sub(r"\s*[-—|]\s*YouTube$", "", inner_title, flags=re.IGNORECASE).strip()
            if raw_vid.lower() in NON_VIDEO_YOUTUBE_PAGES or not raw_vid or raw_vid.lower() == "youtube":
                return {
                    "website": "youtube",
                    "content_title": None,
                    "is_video": False,
                    "is_media": False,
                    "is_document": False,
                    "category": "web",
                    "confidence": 0.85
                }
            return {
                "website": "youtube",
                "content_title": raw_vid,
                "is_video": True,
                "is_media": True,
                "is_document": False,
                "category": "media",
                "confidence": 0.95
            }

        # B. Google Search
        m_search = self.google_search_pattern.match(inner_title)
        if m_search:
            return {
                "website": "google",
                "content_title": m_search.group("query").strip(),
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "search",
                "confidence": 0.95
            }

        # C. GitHub
        m_gh = self.github_pattern.match(inner_title)
        if m_gh or inner_title.lower() == "github":
            gh_title = m_gh.group("title").strip() if m_gh else None
            return {
                "website": "github",
                "content_title": gh_title,
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "development",
                "confidence": 0.90
            }

        # D. ChatGPT & Claude
        m_gpt = self.chatgpt_pattern.match(inner_title)
        if m_gpt or inner_title.lower() == "chatgpt":
            return {
                "website": "chatgpt",
                "content_title": m_gpt.group("topic").strip() if m_gpt else None,
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "ai",
                "confidence": 0.90
            }
        m_claude = self.claude_pattern.match(inner_title)
        if m_claude or inner_title.lower() == "claude":
            return {
                "website": "claude",
                "content_title": m_claude.group("topic").strip() if m_claude else None,
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "ai",
                "confidence": 0.90
            }

        # E. Wikipedia
        m_wiki = self.wikipedia_pattern.match(inner_title)
        if m_wiki or "wikipedia" in inner_title.lower():
            wiki_topic = m_wiki.group("article").strip() if m_wiki else None
            return {
                "website": "wikipedia",
                "content_title": wiki_topic,
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "knowledge",
                "confidence": 0.90
            }

        # F. Reddit
        m_reddit = self.reddit_pattern.match(inner_title)
        if m_reddit or "reddit" in inner_title.lower():
            reddit_topic = m_reddit.group("title").strip() if m_reddit else None
            return {
                "website": "reddit",
                "content_title": reddit_topic,
                "is_video": False,
                "is_media": False,
                "is_document": False,
                "category": "social",
                "confidence": 0.85
            }

        # G. Other recognized web domains
        low_title = inner_title.lower()
        for site_name in ("netflix", "primevideo", "prime video", "twitter", "x.com", "linkedin", "stackoverflow", "stack overflow"):
            if site_name in low_title:
                clean_site = site_name.replace(" ", "").replace(".com", "")
                is_stream = clean_site in ("netflix", "primevideo")
                return {
                    "website": clean_site,
                    "content_title": inner_title,
                    "is_video": is_stream,
                    "is_media": is_stream,
                    "is_document": False,
                    "category": "media" if is_stream else "web",
                    "confidence": 0.85
                }

        # Generic web page
        return {
            "website": "web",
            "content_title": inner_title or None,
            "is_video": False,
            "is_media": False,
            "is_document": False,
            "category": "web",
            "confidence": 0.70
        }
