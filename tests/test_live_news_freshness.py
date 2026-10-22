# tests/test_live_news_freshness.py
"""
Comprehensive automated tests for Live News Freshness, Revalidation,
Article Fingerprinting, and Adaptive Caching Policies in Jarvis V2.1.
"""

import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from core.knowledge.news.client import FetchHeadlinesResult, GoogleNewsFeedClient
from core.knowledge.news.engine import LiveNewsEngine
from core.knowledge.news.formatter import NewsResponseFormatter
from core.knowledge.news.models import (
    CacheStatus,
    NewsCategory,
    NewsFreshnessTier,
    NewsItem,
    NewsQueryResult,
)
from core.execution.fast_path import FastPathEngine
from core.knowledge.router import KnowledgeRouter


SAMPLE_RSS_XML_1 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>ISRO Launches Advanced Navigation Satellite - The Hindu</title>
      <link>https://news.google.com/articles/sample1?utm_source=rss</link>
      <pubDate>Wed, 16 Sep 2026 12:50:00 GMT</pubDate>
      <source url="https://www.thehindu.com">The Hindu</source>
    </item>
    <item>
      <title>Sensex Surges 500 Points on Global Cues - Economic Times</title>
      <link>https://news.google.com/articles/sample2</link>
      <pubDate>Wed, 16 Sep 2026 12:55:00 GMT</pubDate>
      <source url="https://economictimes.indiatimes.com">Economic Times</source>
    </item>
  </channel>
</rss>
"""

SAMPLE_RSS_XML_2_NEW_STORIES = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Breaking: Major Economic Policy Announced - Reuters</title>
      <link>https://news.google.com/articles/sample3</link>
      <pubDate>Wed, 16 Sep 2026 13:00:00 GMT</pubDate>
      <source url="https://reuters.com">Reuters</source>
    </item>
    <item>
      <title>ISRO Launches Advanced Navigation Satellite - The Hindu</title>
      <link>https://news.google.com/articles/sample1</link>
      <pubDate>Wed, 16 Sep 2026 12:50:00 GMT</pubDate>
      <source url="https://www.thehindu.com">The Hindu</source>
    </item>
  </channel>
</rss>
"""


class ControllableClock:
    """Deterministic controllable clock for instant time simulations."""
    def __init__(self, start_time: float = 1726000000.0):
        self._current_time = start_time

    def time(self) -> float:
        return self._current_time

    def advance(self, seconds: float):
        self._current_time += seconds


class TestNewsFreshnessClassification(unittest.TestCase):
    def setUp(self):
        self.engine = LiveNewsEngine()

    def test_freshness_critical_queries(self):
        critical_examples = [
            "abhi ki news kya hai",
            "latest news batao",
            "today's news",
            "fresh news batao",
            "abhi kya chal raha hai",
            "breaking news",
            "latest India news",
            "aaj ki news",
            "current news headlines",
            "taza samachar",
            "taaza khabar",
        ]
        for q in critical_examples:
            tier = self.engine.classify_freshness_intent(q)
            self.assertEqual(
                tier,
                NewsFreshnessTier.FRESHNESS_CRITICAL,
                f"Query '{q}' should be classified as FRESHNESS_CRITICAL"
            )

    def test_normal_cacheable_queries(self):
        normal_examples = [
            "technology news",
            "business news",
            "sports news",
            "India news summary",
            "cricket news",
            "science news",
        ]
        for q in normal_examples:
            tier = self.engine.classify_freshness_intent(q)
            self.assertEqual(
                tier,
                NewsFreshnessTier.NORMAL_CACHEABLE,
                f"Query '{q}' should be classified as NORMAL_CACHEABLE"
            )

    def test_historical_queries(self):
        historical_examples = [
            "kal ki news kya thi",
            "yesterday's news",
            "last week's news",
            "2025 ki news",
            "purani news dikhao",
        ]
        for q in historical_examples:
            tier = self.engine.classify_freshness_intent(q)
            self.assertEqual(
                tier,
                NewsFreshnessTier.HISTORICAL,
                f"Query '{q}' should be classified as HISTORICAL"
            )


class TestLiveNewsFreshnessAndCaching(unittest.TestCase):
    def setUp(self):
        self.clock = ControllableClock(start_time=1000.0)
        self.client = GoogleNewsFeedClient(
            critical_ttl_seconds=30.0,
            normal_ttl_seconds=600.0,
            historical_ttl_seconds=3600.0,
            time_provider=self.clock.time,
        )
        self.engine = LiveNewsEngine(client=self.client)

    @patch("urllib.request.urlopen")
    def test_identical_query_twice_revalidates_and_detects_unchanged(self, mock_urlopen):
        """Scenario: User asks 'abhi ki news' at 12:59 and 13:00. Upstream returns same XML."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_RSS_XML_1.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # 12:59: Initial query at T = 1000
        res1 = self.engine.query("abhi ki news kya hai")
        self.assertTrue(res1.found)
        self.assertFalse(res1.cached)
        self.assertEqual(res1.cache_status, CacheStatus.UPSTREAM_REFRESHED)
        self.assertEqual(mock_urlopen.call_count, 1)

        # 13:00: Advance time by 60 seconds (exceeding 30s critical TTL)
        self.clock.advance(60.0)

        # Same query asked again at 13:00
        res2 = self.engine.query("abhi ki news kya hai")
        self.assertTrue(res2.found)
        # Must revalidate with upstream because it is FRESHNESS_CRITICAL
        self.assertEqual(mock_urlopen.call_count, 2)
        # Because XML was unchanged, status is UPSTREAM_UNCHANGED
        self.assertEqual(res2.cache_status, CacheStatus.UPSTREAM_UNCHANGED)
        self.assertEqual(res2.fingerprint, res1.fingerprint)

    @patch("urllib.request.urlopen")
    def test_identical_query_twice_revalidates_and_delivers_new_stories(self, mock_urlopen):
        """Scenario: User asks 'abhi ki news' at 12:59 and 13:00. Upstream has breaking new stories."""
        mock_resp1 = MagicMock()
        mock_resp1.read.return_value = SAMPLE_RSS_XML_1.encode("utf-8")
        mock_resp2 = MagicMock()
        mock_resp2.read.return_value = SAMPLE_RSS_XML_2_NEW_STORIES.encode("utf-8")

        mock_urlopen.return_value.__enter__.side_effect = [mock_resp1, mock_resp2]

        # 12:59: Initial query
        res1 = self.engine.query("abhi ki news kya hai")
        self.assertIn("ISRO Launches", res1.headlines[0].title)

        # 13:00: Advance time by 60s
        self.clock.advance(60.0)

        # 13:00 query
        res2 = self.engine.query("abhi ki news kya hai")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(res2.cache_status, CacheStatus.UPSTREAM_REFRESHED)
        self.assertNotEqual(res2.fingerprint, res1.fingerprint)
        self.assertIn("Breaking: Major Economic Policy", res2.headlines[0].title)

    @patch("urllib.request.urlopen")
    def test_freshness_critical_cache_hit_within_30s(self, mock_urlopen):
        """Within 30 seconds, even critical query reuses fresh in-memory cache to prevent spamming."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_RSS_XML_1.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # First request at T = 1000
        res1 = self.engine.query("latest news")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Second request 10 seconds later (T = 1010 < 1030)
        self.clock.advance(10.0)
        res2 = self.engine.query("latest news")
        self.assertEqual(mock_urlopen.call_count, 1)  # Reused fresh cache
        self.assertTrue(res2.cached)
        self.assertEqual(res2.cache_status, CacheStatus.CACHE_HIT_FRESH)

    @patch("urllib.request.urlopen")
    def test_normal_topic_query_cache_retention_600s(self, mock_urlopen):
        """Topical non-critical queries ('technology news') retain 600s cache for performance."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_RSS_XML_1.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Request at T = 1000
        res1 = self.engine.query("technology news")
        self.assertEqual(mock_urlopen.call_count, 1)

        # Request at T = 1200 (200s later, < 600s)
        self.clock.advance(200.0)
        res2 = self.engine.query("technology news")
        self.assertEqual(mock_urlopen.call_count, 1)  # Cache reused
        self.assertTrue(res2.cached)
        self.assertEqual(res2.cache_status, CacheStatus.CACHE_HIT_FRESH)

    @patch("urllib.request.urlopen")
    def test_network_failure_transparent_stale_fallback(self, mock_urlopen):
        """Network error when cache exists serves transparent stale fallback with honest notice."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_RSS_XML_1.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Successful initial fetch at T = 1000
        res1 = self.engine.query("breaking news batao")
        self.assertFalse(res1.is_stale_fallback)

        # At T = 1100, network goes down
        self.clock.advance(100.0)
        mock_urlopen.side_effect = urllib.error.URLError("DNS resolution failed")

        res2 = self.engine.query("breaking news batao")
        self.assertTrue(res2.found)
        self.assertTrue(res2.is_stale_fallback)
        self.assertEqual(res2.cache_status, CacheStatus.CACHE_HIT_STALE)
        # Formatter should honestly inform user
        self.assertIn("pichhli saved headlines", res2.formatted_text)
        self.assertIn("live feed", res2.spoken_text)

    @patch("urllib.request.urlopen")
    def test_network_failure_with_no_cache_returns_error(self, mock_urlopen):
        """Network failure with empty cache fails gracefully with offline error."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        res = self.engine.query("breaking news batao")
        self.assertFalse(res.found)
        self.assertEqual(res.error, "feed_unreachable")
        self.assertIn("Internet connection uplabdh nahi hai", res.formatted_text)

    def test_stable_article_fingerprinting(self):
        """Verifies article ID and feed fingerprint stability."""
        item1 = NewsItem(
            title="AI Breakthrough in Healthcare - BBC",
            source="BBC",
            published_at="Wed, 16 Sep 2026 12:00:00 GMT",
            link="https://bbc.com/news/1?utm_medium=rss&utm_source=feed"
        )
        item2 = NewsItem(
            title="AI Breakthrough in Healthcare - BBC",
            source="BBC",
            published_at="Wed, 16 Sep 2026 12:00:00 GMT",
            link="https://bbc.com/news/1"  # Strip UTM params
        )
        self.assertEqual(item1.compute_article_id(), item2.compute_article_id())

    def test_targeted_cache_invalidation(self):
        """Targeted invalidation clears only specified categories or queries."""
        self.client._cache[("TOP", True, "")] = MagicMock()
        self.client._cache[("TECHNOLOGY", False, "")] = MagicMock()
        self.client._cache[("BUSINESS", False, "")] = MagicMock()

        # Invalidate only TECHNOLOGY
        removed = self.client.invalidate_cache(category=NewsCategory.TECHNOLOGY)
        self.assertEqual(removed, 1)
        self.assertNotIn(("TECHNOLOGY", False, ""), self.client._cache)
        self.assertIn(("TOP", True, ""), self.client._cache)


class TestNewsPipelineIntegration(unittest.TestCase):
    @patch.object(LiveNewsEngine, "query")
    def test_fast_path_propagates_freshness_metadata(self, mock_query):
        mock_res = NewsQueryResult(
            found=True,
            headlines=[NewsItem(title="Headline 1", source="News")],
            formatted_text="📰 Headlines",
            spoken_text="Spoken Headlines",
            category=NewsCategory.TOP,
            is_hindi=True,
            cached=False,
            freshness_tier=NewsFreshnessTier.FRESHNESS_CRITICAL,
            cache_status=CacheStatus.UPSTREAM_REFRESHED,
            is_stale_fallback=False
        )
        mock_query.return_value = mock_res

        fast_path = FastPathEngine()
        turn = MagicMock()
        turn.metadata = {}

        resp = fast_path.try_handle(
            raw_text="abhi ki news kya hai",
            normalized_input="abhi ki news kya hai",
            turn=turn,
            start_time=time.time(),
            tracker=None,
            source="text"
        )
        self.assertEqual(resp, "📰 Headlines")
        self.assertEqual(turn.spoken_response, "Spoken Headlines")
        self.assertTrue(turn.metadata.get("live_news"))


if __name__ == "__main__":
    unittest.main()
