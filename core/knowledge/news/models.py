# core/knowledge/news/models.py
"""
Data models for the Live News Engine subsystem.
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NewsCategory(str, Enum):
    """Supported news categories and topic feeds."""
    TOP = "TOP"
    WORLD = "WORLD"
    INDIA = "INDIA"
    TECHNOLOGY = "TECHNOLOGY"
    BUSINESS = "BUSINESS"
    SPORTS = "SPORTS"
    ENTERTAINMENT = "ENTERTAINMENT"
    SCIENCE = "SCIENCE"


class NewsFreshnessTier(str, Enum):
    """Classification of freshness sensitivity for news inquiries."""
    FRESHNESS_CRITICAL = "FRESHNESS_CRITICAL"  # Immediate ("abhi", "latest", "breaking", "today")
    NORMAL_CACHEABLE = "NORMAL_CACHEABLE"      # Topical/category ("technology news", "sports news")
    HISTORICAL = "HISTORICAL"                  # Past/archive ("kal ki news", "last week")


class CacheStatus(str, Enum):
    """Cache lookup and feed lifecycle status."""
    CACHE_HIT_FRESH = "CACHE_HIT_FRESH"
    CACHE_HIT_STALE = "CACHE_HIT_STALE"
    UPSTREAM_UNCHANGED = "UPSTREAM_UNCHANGED"
    UPSTREAM_REFRESHED = "UPSTREAM_REFRESHED"
    NETWORK_ERROR = "NETWORK_ERROR"


@dataclass
class NewsItem:
    """Individual parsed news item from live feed."""
    title: str
    source: str
    published_at: str = ""
    link: str = ""
    category: NewsCategory = NewsCategory.TOP

    def clean_title(self) -> str:
        """Returns clean headline without source suffix if present."""
        t = self.title.strip()
        if " - " in t:
            parts = t.rsplit(" - ", 1)
            if len(parts[0].strip()) > 10:
                return parts[0].strip()
        return t

    def compute_article_id(self) -> str:
        """Derives a stable, position-independent article fingerprint."""
        norm_url = re.sub(r"[?&]utm_[^&]+", "", self.link.strip().lower())
        norm_title = re.sub(r"[^\w\s]", "", self.clean_title().lower()).strip()
        norm_source = self.source.strip().lower()
        norm_pub = self.published_at.strip()
        raw = f"{norm_source}|{norm_url}|{norm_title}|{norm_pub}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_briefing_dict(self) -> Dict[str, Any]:
        """Serializes this item for the GUI News Briefing view.

        Uses ONLY real feed-supplied fields. RSS provides no summary or
        image, so ``summary`` is always ``""`` and ``image_url`` is always
        ``None`` — the GUI must omit those affordances rather than invent
        content.
        """
        cat = self.category.value if isinstance(self.category, NewsCategory) else str(self.category)
        return {
            "headline": self.clean_title(),
            "summary": "",
            "source": self.source or "News",
            "published_at": self.published_at or "",
            "url": self.link or "",
            "category": cat,
            "image_url": None,
        }


@dataclass
class NewsCacheEntry:
    """Structured cache entry tracking timestamps, metadata, and feed fingerprints."""
    items: List[NewsItem]
    cache_created_at: float
    feed_fetched_at: float
    oldest_article_time: str = ""
    newest_article_time: str = ""
    query: str = ""
    category: NewsCategory = NewsCategory.TOP
    locale: str = "en"
    source: str = "google_news"
    fingerprint: str = ""
    status: CacheStatus = CacheStatus.UPSTREAM_REFRESHED

    @classmethod
    def compute_fingerprint(cls, items: List[NewsItem]) -> str:
        """Computes a stable hash across all articles in a result set."""
        ids = [it.compute_article_id() for it in items]
        return hashlib.sha256(",".join(ids).encode("utf-8")).hexdigest()[:16]


@dataclass
class NewsQueryResult:
    """Structured result of evaluating a news query."""
    found: bool
    headlines: List[NewsItem] = field(default_factory=list)
    formatted_text: str = ""
    spoken_text: str = ""
    category: NewsCategory = NewsCategory.TOP
    is_hindi: bool = False
    cached: bool = False
    error: Optional[str] = None
    freshness_tier: NewsFreshnessTier = NewsFreshnessTier.NORMAL_CACHEABLE
    cache_status: CacheStatus = CacheStatus.UPSTREAM_REFRESHED
    feed_fetched_at: float = 0.0
    is_stale_fallback: bool = False
    fingerprint: str = ""

    def to_briefing_dict(self) -> Dict[str, Any]:
        """Builds the minimal structured news-briefing contract for the GUI.

        The formatted/spoken text paths remain authoritative for chat/TTS;
        this dict is visual-presentation only and contains no invented
        summaries, timestamps, sources, or images.
        """
        fetched = self.feed_fetched_at or time.time()
        try:
            date_str = time.strftime("%d %B %Y", time.localtime(fetched))
        except Exception:
            date_str = ""
        cat = self.category.value if isinstance(self.category, NewsCategory) else str(self.category)
        return {
            "type": "news",
            "title": "Today's News",
            "date": date_str,
            "category": cat,
            "is_hindi": self.is_hindi,
            "is_stale_fallback": self.is_stale_fallback,
            "fetched_at": fetched,
            "count": len(self.headlines),
            "spoken_text": self.spoken_text,
            "articles": [h.to_briefing_dict() for h in self.headlines],
        }
