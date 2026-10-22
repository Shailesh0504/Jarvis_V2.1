# core/knowledge/news/client.py
"""
Live Google News RSS Feed Client.
Fetches, parses, and in-memory caches real-time news headlines using standard Python libraries.
"""

import html
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .models import CacheStatus, NewsCategory, NewsCacheEntry, NewsFreshnessTier, NewsItem

logger = logging.getLogger("jarvis.knowledge.news.client")


class FetchHeadlinesResult(tuple):
    """
    Two-tuple (items, is_cached) subclass supporting transparent 2-tuple unpacking
    while carrying rich freshness metadata (status, entry).
    """
    items: List[NewsItem]
    is_cached: bool
    status: CacheStatus
    entry: Optional[NewsCacheEntry]

    def __new__(
        cls,
        items: List[NewsItem],
        is_cached: bool,
        status: CacheStatus = CacheStatus.UPSTREAM_REFRESHED,
        entry: Optional[NewsCacheEntry] = None
    ):
        instance = super().__new__(cls, (items, is_cached))
        instance.items = items
        instance.is_cached = is_cached
        instance.status = status
        instance.entry = entry
        return instance


class GoogleNewsFeedClient:
    """
    Fetches real-time headlines from Google News RSS feeds with zero external dependencies.
    Includes thread-safe in-memory caching with adaptive freshness policies and fingerprinting.
    """

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    TOPIC_MAP = {
        NewsCategory.TOP: "",
        NewsCategory.WORLD: "WORLD",
        NewsCategory.INDIA: "NATION",
        NewsCategory.TECHNOLOGY: "TECHNOLOGY",
        NewsCategory.BUSINESS: "BUSINESS",
        NewsCategory.SPORTS: "SPORTS",
        NewsCategory.ENTERTAINMENT: "ENTERTAINMENT",
        NewsCategory.SCIENCE: "SCIENCE",
    }

    def __init__(
        self,
        critical_ttl_seconds: float = 30.0,
        normal_ttl_seconds: float = 600.0,
        historical_ttl_seconds: float = 3600.0,
        timeout: float = 5.0,
        time_provider: Optional[Callable[[], float]] = None,
        ttl_seconds: Optional[float] = None,
    ):
        self.critical_ttl_seconds = critical_ttl_seconds
        self.normal_ttl_seconds = ttl_seconds if ttl_seconds is not None else normal_ttl_seconds
        self.historical_ttl_seconds = historical_ttl_seconds
        self.ttl_seconds = self.normal_ttl_seconds
        self.timeout = timeout
        self.time_provider = time_provider or time.time
        self._cache: Dict[Tuple[str, bool, str], NewsCacheEntry] = {}
        self._lock = threading.Lock()

    def get_ttl_for_tier(self, tier: NewsFreshnessTier) -> float:
        """Returns the appropriate TTL according to query freshness sensitivity."""
        if tier == NewsFreshnessTier.FRESHNESS_CRITICAL:
            return self.critical_ttl_seconds
        elif tier == NewsFreshnessTier.HISTORICAL:
            return self.historical_ttl_seconds
        return self.normal_ttl_seconds

    def get_feed_url(
        self,
        category: NewsCategory = NewsCategory.TOP,
        is_hindi: bool = False,
        search_query: str = ""
    ) -> str:
        """Constructs canonical Google News RSS feed URL."""
        hl = "hi" if is_hindi else "en-IN"
        gl = "IN"
        ceid = "IN:hi" if is_hindi else "IN:en"

        if search_query:
            encoded = urllib.parse.quote_plus(search_query)
            return f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid={ceid}"

        topic_code = self.TOPIC_MAP.get(category, "")
        if topic_code:
            return f"https://news.google.com/rss/headlines/section/topic/{topic_code}?hl={hl}&gl={gl}&ceid={ceid}"

        return f"https://news.google.com/rss?hl={hl}&gl={gl}&ceid={ceid}"

    def fetch_headlines(
        self,
        category: NewsCategory = NewsCategory.TOP,
        is_hindi: bool = False,
        search_query: str = "",
        limit: int = 5,
        force_refresh: bool = False,
        freshness_tier: NewsFreshnessTier = NewsFreshnessTier.NORMAL_CACHEABLE
    ) -> FetchHeadlinesResult:
        """
        Fetches headlines from Google News RSS or memory cache with freshness awareness.
        Returns: FetchHeadlinesResult(items, is_cached) with .status and .entry attributes.
        """
        cache_key = (category.value, is_hindi, search_query.strip().lower())
        now = self.time_provider()
        effective_ttl = self.get_ttl_for_tier(freshness_tier)

        existing_entry: Optional[NewsCacheEntry] = None
        with self._lock:
            if cache_key in self._cache:
                existing_entry = self._cache[cache_key]

        # 1. Fast freshness check: return cached if within effective freshness window
        if not force_refresh and existing_entry and existing_entry.items:
            age = now - existing_entry.feed_fetched_at
            if age < effective_ttl:
                logger.debug(
                    "[NEWS_CLIENT] Cache hit (%s) for %s (age=%.1fs, ttl=%.1fs)",
                    freshness_tier.value, cache_key, age, effective_ttl
                )
                return FetchHeadlinesResult(
                    existing_entry.items[:limit],
                    True,
                    CacheStatus.CACHE_HIT_FRESH,
                    existing_entry
                )

        # 2. Upstream fetch / revalidation required
        url = self.get_feed_url(category=category, is_hindi=is_hindi, search_query=search_query)
        logger.info("[NEWS_CLIENT] Fetching live feed (%s): %s", freshness_tier.value, url)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.DEFAULT_USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_data = resp.read()

            items = self._parse_rss_xml(xml_data, category=category)
            if items:
                new_fingerprint = NewsCacheEntry.compute_fingerprint(items)

                # Differentiate upstream unchanged vs refreshed
                status = CacheStatus.UPSTREAM_REFRESHED
                cache_created = now
                if existing_entry and existing_entry.fingerprint == new_fingerprint:
                    status = CacheStatus.UPSTREAM_UNCHANGED
                    cache_created = existing_entry.cache_created_at
                    logger.info("[NEWS_CLIENT] Upstream feed verified UNCHANGED for %s (fp=%s)", cache_key, new_fingerprint)
                else:
                    logger.info("[NEWS_CLIENT] Upstream feed REFRESHED for %s (new_fp=%s)", cache_key, new_fingerprint)

                pub_dates = [it.published_at for it in items if it.published_at]
                newest_pub = pub_dates[0] if pub_dates else ""
                oldest_pub = pub_dates[-1] if pub_dates else ""

                entry = NewsCacheEntry(
                    items=items,
                    cache_created_at=cache_created,
                    feed_fetched_at=now,
                    oldest_article_time=oldest_pub,
                    newest_article_time=newest_pub,
                    query=search_query,
                    category=category,
                    locale="hi" if is_hindi else "en",
                    source="google_news",
                    fingerprint=new_fingerprint,
                    status=status
                )

                with self._lock:
                    self._cache[cache_key] = entry

                return FetchHeadlinesResult(
                    items[:limit],
                    False,
                    status,
                    entry
                )

            logger.warning("[NEWS_CLIENT] No news items parsed from feed: %s", url)
            return FetchHeadlinesResult([], False, CacheStatus.NETWORK_ERROR, None)

        except Exception as exc:
            logger.warning("[NEWS_CLIENT] Failed to fetch news feed (%s): %s", url, exc)
            # If network error occurs, serve stale cache if present as explicit fallback
            with self._lock:
                if existing_entry and existing_entry.items:
                    logger.info("[NEWS_CLIENT] Serving stale cache fallback due to network failure")
                    stale_entry = NewsCacheEntry(
                        items=existing_entry.items,
                        cache_created_at=existing_entry.cache_created_at,
                        feed_fetched_at=existing_entry.feed_fetched_at,
                        oldest_article_time=existing_entry.oldest_article_time,
                        newest_article_time=existing_entry.newest_article_time,
                        query=existing_entry.query,
                        category=existing_entry.category,
                        locale=existing_entry.locale,
                        source=existing_entry.source,
                        fingerprint=existing_entry.fingerprint,
                        status=CacheStatus.CACHE_HIT_STALE
                    )
                    return FetchHeadlinesResult(
                        existing_entry.items[:limit],
                        True,
                        CacheStatus.CACHE_HIT_STALE,
                        stale_entry
                    )
            return FetchHeadlinesResult([], False, CacheStatus.NETWORK_ERROR, None)

    def _parse_rss_xml(self, xml_bytes: bytes, category: NewsCategory) -> List[NewsItem]:
        """Parses RSS XML into clean NewsItem objects."""
        results: List[NewsItem] = []
        try:
            root = ET.fromstring(xml_bytes)
            items = root.findall("./channel/item")
            for it in items:
                title_elem = it.find("title")
                link_elem = it.find("link")
                pub_date_elem = it.find("pubDate")
                source_elem = it.find("source")

                raw_title = title_elem.text if title_elem is not None and title_elem.text else ""
                link = link_elem.text if link_elem is not None and link_elem.text else ""
                pub_date = pub_date_elem.text if pub_date_elem is not None and pub_date_elem.text else ""

                source_name = ""
                if source_elem is not None and source_elem.text:
                    source_name = source_elem.text.strip()
                elif " - " in raw_title:
                    source_name = raw_title.rsplit(" - ", 1)[-1].strip()

                clean_t = html.unescape(raw_title).strip()
                if clean_t:
                    results.append(
                        NewsItem(
                            title=clean_t,
                            source=source_name or "News",
                            published_at=pub_date.strip(),
                            link=link.strip(),
                            category=category
                        )
                    )
        except Exception as e:
            logger.error("[NEWS_CLIENT] Error parsing RSS XML: %s", e)

        return results

    def clear_cache(self) -> None:
        """Clears in-memory news cache."""
        with self._lock:
            self._cache.clear()
            logger.debug("[NEWS_CLIENT] News cache cleared.")

    def invalidate_cache(
        self,
        category: Optional[NewsCategory] = None,
        is_hindi: Optional[bool] = None,
        search_query: Optional[str] = None
    ) -> int:
        """Invalidates targeted news cache entries."""
        with self._lock:
            if category is None and is_hindi is None and search_query is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            keys_to_remove = []
            for k in self._cache.keys():
                k_cat, k_hi, k_query = k
                if category is not None and k_cat != category.value:
                    continue
                if is_hindi is not None and k_hi != is_hindi:
                    continue
                if search_query is not None and k_query != search_query.strip().lower():
                    continue
                keys_to_remove.append(k)

            for k in keys_to_remove:
                del self._cache[k]
            return len(keys_to_remove)
