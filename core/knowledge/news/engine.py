# core/knowledge/news/engine.py
"""Live News Engine for Jarvis - Real-time RSS news feed aggregation (Live Update Active v2.5).
Fetches, categorizes, formats, and serves real-time news headlines across English and Hinglish.
"""

import logging
import re
import threading
from typing import Optional, Tuple

from .client import GoogleNewsFeedClient
from .formatter import NewsResponseFormatter
from .models import CacheStatus, NewsCategory, NewsFreshnessTier, NewsQueryResult

logger = logging.getLogger("jarvis.knowledge.news.engine")


class LiveNewsEngine:
    """
    Authoritative coordinator for real-time internet news discovery and delivery.
    """

    _instance: Optional["LiveNewsEngine"] = None
    _lock = threading.Lock()

    # Core news triggers
    NEWS_TRIGGERS = [
        "news", "headlines", "headline", "samachar", "khabar", "khabarein",
        "taza khabar", "taaza khabar", "breaking news", "latest news", "aaj ki news",
        "abhi ki news", "current news", "top stories", "daily news"
    ]

    # Freshness classification patterns
    FRESHNESS_CRITICAL_PATTERNS = [
        r"\b(?:abhi|latest|taza|taaza|breaking|current|fresh|live|right\s+now|just\s+in)\b",
        r"\b(?:today|today's|aaj|aaj\s+ki|aaj\s+ke)\b",
        r"\b(?:kya\s+chal\s+raha\s+hai|kya\s+hua\s+hai|abhi\s+kya)\b"
    ]

    HISTORICAL_PATTERNS = [
        r"\b(?:kal|kal\s+ki|yesterday|yesterday's)\b",
        r"\b(?:last\s+week|pichle\s+hafte|past\s+week)\b",
        r"\b(?:last\s+month|pichle\s+mahine)\b",
        r"\b(?:purani|purane|historical|archive|archived)\b",
        r"\b(?:202[0-5]|201\d)\b"
    ]

    # Category cues
    CATEGORY_PATTERNS = {
        NewsCategory.TECHNOLOGY: [
            "tech", "technology", "ai", "artificial intelligence", "gadgets", "mobile",
            "software", "computer", "internet", "tech news", "technology news"
        ],
        NewsCategory.SPORTS: [
            "sports", "sport", "cricket", "football", "ipl", "khel", "match",
            "sports news", "cricket news", "khel samachar"
        ],
        NewsCategory.BUSINESS: [
            "business", "finance", "market", "stock market", "sensex", "nifty",
            "economy", "arthik", "vyapar", "business news"
        ],
        NewsCategory.WORLD: [
            "world", "international", "global", "duniya", "videsh", "foreign",
            "world news", "international news"
        ],
        NewsCategory.ENTERTAINMENT: [
            "entertainment", "bollywood", "hollywood", "cinema", "movies", "film",
            "manoranjan", "entertainment news"
        ],
        NewsCategory.SCIENCE: [
            "science", "space", "isro", "nasa", "astronomy", "vigyan", "scientific",
            "science news"
        ],
        NewsCategory.INDIA: [
            "india", "national", "desh", "bharat", "indian news", "national news", "desh ki news"
        ]
    }

    HINDI_INDICATORS = [
        "kya hai", "kya chal raha", "batao", "sunao", "dikhao", "dikhayein",
        "aaj", "abhi", "taza", "taaza", "samachar", "khabar", "khabarein",
        "ki news", "ke news", "kaunsi", "desh", "duniya", "khel"
    ]

    def __init__(self, client: Optional[GoogleNewsFeedClient] = None):
        self.client = client or GoogleNewsFeedClient(critical_ttl_seconds=30.0, normal_ttl_seconds=600.0, timeout=5.0)
        logger.info("[LIVE_NEWS_ENGINE] Initialized Live News Engine with Google News RSS feed client.")

    @classmethod
    def get_instance(cls) -> "LiveNewsEngine":
        """Thread-safe singleton getter."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_news_candidate(self, query: str) -> bool:
        """
        Determines whether the utterance asks for live news headlines.
        Guards against app/website launching directives (e.g. 'open google news').
        """
        if not query:
            return False

        q_low = query.lower().strip()

        # Guard: Website / Application launching requests belong to App/Target/Browser resolver
        app_launch_cues = [
            "kholo", "open", "launch", "chalao", "start", "website", "app", "application"
        ]
        if any(w in q_low for w in ["google news", "aaj tak app", "bbc app", "news website", "news app"]):
            if any(c in q_low for c in app_launch_cues):
                return False

        # Guard: General Knowledge definitions like 'what is the definition of news'
        if "definition of news" in q_low or "meaning of news" in q_low:
            return False

        # Check explicit news triggers
        has_news_trigger = any(re.search(r"\b" + re.escape(trig) + r"\b", q_low) for trig in self.NEWS_TRIGGERS)
        if has_news_trigger:
            return True

        # Check for category-specific headline inquiries (e.g. "aaj ke mukhya samachar", "cricket update")
        if any(w in q_low for w in ["samachar", "khabar", "headlines", "top stories"]):
            return True

        return False

    def classify_freshness_intent(self, query: str) -> NewsFreshnessTier:
        """Classifies the freshness sensitivity of a news inquiry."""
        if not query:
            return NewsFreshnessTier.NORMAL_CACHEABLE

        q_low = query.lower().strip()

        # Check historical first
        for pat in self.HISTORICAL_PATTERNS:
            if re.search(pat, q_low):
                return NewsFreshnessTier.HISTORICAL

        # Check freshness critical
        for pat in self.FRESHNESS_CRITICAL_PATTERNS:
            if re.search(pat, q_low):
                return NewsFreshnessTier.FRESHNESS_CRITICAL

        # Default to normal cacheable for topical inquiries (e.g. "technology news")
        return NewsFreshnessTier.NORMAL_CACHEABLE

    def classify_news_query(self, query: str) -> Tuple[NewsCategory, str, bool]:
        """
        Extracts Category, specific search topic keyword (if applicable), and Hindi flag.
        Returns: (category, search_topic, is_hindi)
        """
        q_low = query.lower().strip()

        # Detect language
        is_hindi = any(ind in q_low for ind in self.HINDI_INDICATORS)

        # Detect category
        matched_cat = NewsCategory.TOP
        for cat, keywords in self.CATEGORY_PATTERNS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", q_low):
                    matched_cat = cat
                    break
            if matched_cat != NewsCategory.TOP:
                break

        # Check if user mentioned a specific custom search keyword (e.g. "ISRO news", "Tesla news")
        search_topic = ""
        # Strip common boilerplates to isolate custom topic
        cleaned = re.sub(
            r"\b(news|samachar|khabar|khabarein|headlines|latest|abhi|ki|ke|ka|ko|se|batao|sunao|kya|hai|what|is|the|tell|me|give|show|read|get|today|today's|update|breaking|dikhao|dikhayein|kuch|some|any|aur)\b",
            " ",
            q_low
        )
        # Strip category keywords if matched to allow clean category RSS topic feeds
        if matched_cat != NewsCategory.TOP:
            for kw in self.CATEGORY_PATTERNS.get(matched_cat, []):
                cleaned = re.sub(r"\b" + re.escape(kw) + r"\b", " ", cleaned)

        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?.,!")

        stopwords = {"top", "live", "fresh", "taza", "taaza", "main", "major", "important"}
        if cleaned and len(cleaned) >= 2 and cleaned.lower() not in stopwords:
            search_topic = cleaned

        return matched_cat, search_topic, is_hindi

    def query(
        self,
        query: str,
        limit: int = 5,
        force_refresh: bool = False
    ) -> NewsQueryResult:
        """
        Queries live news and returns structured NewsQueryResult with freshness metadata.
        """
        category, search_topic, is_hindi = self.classify_news_query(query)
        freshness_tier = self.classify_freshness_intent(query)

        res = self.client.fetch_headlines(
            category=category,
            is_hindi=is_hindi,
            search_query=search_topic,
            limit=limit,
            force_refresh=force_refresh,
            freshness_tier=freshness_tier
        )

        headlines = res[0]
        is_cached = res[1]
        cache_status = getattr(res, "status", CacheStatus.UPSTREAM_REFRESHED)
        cache_entry = getattr(res, "entry", None)
        is_stale_fallback = (cache_status == CacheStatus.CACHE_HIT_STALE)

        if not headlines:
            fmt_text, spoken_text = NewsResponseFormatter.format_offline_error(is_hindi=is_hindi)
            return NewsQueryResult(
                found=False,
                headlines=[],
                formatted_text=fmt_text,
                spoken_text=spoken_text,
                category=category,
                is_hindi=is_hindi,
                cached=False,
                error="feed_unreachable",
                freshness_tier=freshness_tier,
                cache_status=cache_status,
                is_stale_fallback=False
            )

        fmt_text, spoken_text = NewsResponseFormatter.format_news(
            headlines=headlines,
            category=category,
            is_hindi=is_hindi,
            search_topic=search_topic,
            is_stale_fallback=is_stale_fallback
        )

        feed_fetched_at = cache_entry.feed_fetched_at if cache_entry else 0.0
        fingerprint = cache_entry.fingerprint if cache_entry else ""

        return NewsQueryResult(
            found=True,
            headlines=headlines,
            formatted_text=fmt_text,
            spoken_text=spoken_text,
            category=category,
            is_hindi=is_hindi,
            cached=is_cached,
            freshness_tier=freshness_tier,
            cache_status=cache_status,
            feed_fetched_at=feed_fetched_at,
            is_stale_fallback=is_stale_fallback,
            fingerprint=fingerprint
        )


def get_live_news_engine() -> LiveNewsEngine:
    """Authoritative singleton accessor for LiveNewsEngine."""
    return LiveNewsEngine.get_instance()
