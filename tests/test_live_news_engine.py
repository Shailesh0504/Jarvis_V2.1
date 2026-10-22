"""
Automated unit and integration tests for LiveNewsEngine and News Subsystem.

Tests cover:
1. Data models (NewsItem, clean_title(), NewsQueryResult)
2. GoogleNewsFeedClient (URL mapping, RSS XML parsing, caching, network error resilience)
3. NewsResponseFormatter (Hindi/Hinglish and English conversational & display output)
4. LiveNewsEngine (Candidate check, category classification, query execution)
5. AnswerVerificationEngine (News grounding and confidence boost)
6. FastPathEngine (Direct news interception)
7. NewsPlugin (Plugin command discovery and execution via PluginManager)
"""

import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import time

from core.knowledge.news.models import NewsCategory, NewsItem, NewsQueryResult
from core.knowledge.news.client import GoogleNewsFeedClient
from core.knowledge.news.formatter import NewsResponseFormatter
from core.knowledge.news.engine import LiveNewsEngine, get_live_news_engine
from core.intelligence.answer_verification import AnswerVerificationEngine, AnswerSource, GroundingStatus
from core.execution.fast_path import FastPathEngine
from plugins.manager import PluginManager


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <link>https://news.google.com</link>
    <description>Top Stories</description>
    <item>
      <title>ISRO Launches Advanced Navigation Satellite - The Hindu</title>
      <link>https://news.google.com/articles/sample1</link>
      <pubDate>Sun, 13 Sep 2026 10:00:00 GMT</pubDate>
      <source url="https://www.thehindu.com">The Hindu</source>
    </item>
    <item>
      <title>Sensex Surges 500 Points on Global Cues - Economic Times</title>
      <link>https://news.google.com/articles/sample2</link>
      <pubDate>Sun, 13 Sep 2026 11:30:00 GMT</pubDate>
      <source url="https://economictimes.indiatimes.com">Economic Times</source>
    </item>
    <item>
      <title>India Clinches Thrilling Victory in World Cup Final - NDTV Sports</title>
      <link>https://news.google.com/articles/sample3</link>
      <pubDate>Sun, 13 Sep 2026 12:45:00 GMT</pubDate>
      <source url="https://sports.ndtv.com">NDTV Sports</source>
    </item>
  </channel>
</rss>
"""


class TestNewsModels(unittest.TestCase):
    def test_clean_title_method(self):
        item = NewsItem(
            title="Tech Giant Unveils New AI Chip - Reuters",
            source="Reuters",
            published_at="Sun, 13 Sep 2026 10:00:00 GMT",
            link="https://example.com/1",
        )
        self.assertEqual(item.clean_title(), "Tech Giant Unveils New AI Chip")

    def test_clean_title_no_source_suffix(self):
        item = NewsItem(
            title="Major Discovery in Quantum Computing",
            source="",
            published_at="",
            link="",
        )
        self.assertEqual(item.clean_title(), "Major Discovery in Quantum Computing")


class TestGoogleNewsFeedClient(unittest.TestCase):
    def setUp(self):
        self.client = GoogleNewsFeedClient(ttl_seconds=60, timeout=2.0)
        self.client.clear_cache()

    def test_build_feed_url_categories(self):
        url_top = self.client.get_feed_url(NewsCategory.TOP)
        self.assertIn("news.google.com/rss", url_top)
        self.assertNotIn("/topic/", url_top)

        url_tech = self.client.get_feed_url(NewsCategory.TECHNOLOGY)
        self.assertIn("/topic/TECHNOLOGY", url_tech)

        url_search = self.client.get_feed_url(NewsCategory.TOP, search_query="chandrayaan 4")
        self.assertIn("/rss/search?q=", url_search)
        self.assertIn("chandrayaan+4", url_search)

    @patch("urllib.request.urlopen")
    def test_fetch_headlines_success_and_parsing(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_RSS_XML.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        items, is_cached = self.client.fetch_headlines(NewsCategory.TOP, limit=5)
        self.assertEqual(len(items), 3)
        self.assertFalse(is_cached)
        self.assertEqual(items[0].clean_title(), "ISRO Launches Advanced Navigation Satellite")
        self.assertEqual(items[0].source, "The Hindu")
        self.assertEqual(items[1].clean_title(), "Sensex Surges 500 Points on Global Cues")
        self.assertEqual(items[2].clean_title(), "India Clinches Thrilling Victory in World Cup Final")

    @patch("urllib.request.urlopen")
    def test_caching_behavior(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_RSS_XML.encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # 1st call: network fetch
        items1, is_cached1 = self.client.fetch_headlines(NewsCategory.TOP, limit=3)
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertFalse(is_cached1)

        # 2nd call: cached
        items2, is_cached2 = self.client.fetch_headlines(NewsCategory.TOP, limit=3)
        self.assertEqual(mock_urlopen.call_count, 1)  # No extra call
        self.assertTrue(is_cached2)
        self.assertEqual(len(items2), 3)

        # Cache clear
        self.client.clear_cache()
        items3, is_cached3 = self.client.fetch_headlines(NewsCategory.TOP, limit=3)
        self.assertEqual(mock_urlopen.call_count, 2)  # Fetched again
        self.assertFalse(is_cached3)

    @patch("urllib.request.urlopen")
    def test_network_error_resilience(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        items, is_cached = self.client.fetch_headlines(NewsCategory.TOP)
        self.assertEqual(items, [])
        self.assertFalse(is_cached)


class TestNewsResponseFormatter(unittest.TestCase):
    def setUp(self):
        self.items = [
            NewsItem(title="ISRO Launches Advanced Satellite - The Hindu", source="The Hindu", published_at="2026-09-13", link=""),
            NewsItem(title="Sensex Rallies 500 Points - Mint", source="Mint", published_at="2026-09-13", link=""),
        ]

    def test_format_hindi(self):
        display, spoken = NewsResponseFormatter.format_news(
            self.items,
            category=NewsCategory.TOP,
            is_hindi=True,
        )
        self.assertIn("Boss, abhi ki mukhya live news headlines", display)
        self.assertIn("1. ISRO Launches Advanced Satellite", display)
        self.assertIn("2. Sensex Rallies 500 Points", display)
        self.assertTrue(spoken.startswith("Boss, abhi ki mukhya headlines ye hain."))
        self.assertIn("Pehli, ISRO Launches Advanced Satellite", spoken)

    def test_format_english(self):
        display, spoken = NewsResponseFormatter.format_news(
            self.items,
            category=NewsCategory.TECHNOLOGY,
            is_hindi=False,
        )
        self.assertIn("Here are the latest technology news headlines, Boss:", display)
        self.assertTrue(spoken.startswith("Here are the top technology headlines, Boss."))
        self.assertIn("First, ISRO Launches Advanced Satellite", spoken)

    def test_format_empty(self):
        display, spoken = NewsResponseFormatter.format_news([], category=NewsCategory.TOP, is_hindi=True)
        self.assertIn("abhi koi live news nahi mili", spoken)


class TestLiveNewsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = LiveNewsEngine()

    def test_candidate_detection(self):
        self.assertTrue(self.engine.is_news_candidate("abhi ki news kya hai?"))
        self.assertTrue(self.engine.is_news_candidate("aaj ke taja samachar"))
        self.assertTrue(self.engine.is_news_candidate("latest breaking news batao"))
        self.assertTrue(self.engine.is_news_candidate("cricket news"))
        self.assertTrue(self.engine.is_news_candidate("kya news chal rahi hai"))

        # Non-news queries
        self.assertFalse(self.engine.is_news_candidate("what is python?"))
        self.assertFalse(self.engine.is_news_candidate("open chrome"))
        self.assertFalse(self.engine.is_news_candidate("time kya hua hai"))
        self.assertFalse(self.engine.is_news_candidate("what is the definition of news"))

    def test_category_classification(self):
        cat, topic, is_hindi = self.engine.classify_news_query("tech news batao")
        self.assertEqual(cat, NewsCategory.TECHNOLOGY)
        self.assertTrue(is_hindi)

        cat, topic, is_hindi = self.engine.classify_news_query("business news headlines")
        self.assertEqual(cat, NewsCategory.BUSINESS)

        cat, topic, is_hindi = self.engine.classify_news_query("sports news dikhao")
        self.assertEqual(cat, NewsCategory.SPORTS)
        self.assertTrue(is_hindi)

        cat, topic, is_hindi = self.engine.classify_news_query("world news update")
        self.assertEqual(cat, NewsCategory.WORLD)

        cat, topic, is_hindi = self.engine.classify_news_query("abhi ki news kya hai?")
        self.assertEqual(cat, NewsCategory.TOP)
        self.assertTrue(is_hindi)

    @patch.object(GoogleNewsFeedClient, "fetch_headlines")
    def test_query_success(self, mock_fetch):
        mock_fetch.return_value = (
            [NewsItem(title="AI Model Sets New Benchmark - TechRadar", source="TechRadar", published_at="", link="")],
            False
        )
        res = self.engine.query("technology news batao", limit=3)
        self.assertTrue(res.found)
        self.assertEqual(len(res.headlines), 1)
        self.assertIn("AI Model Sets New Benchmark", res.formatted_text)


class TestSubsystemIntegration(unittest.TestCase):
    def test_answer_verification_grounding_for_live_news(self):
        verifier = AnswerVerificationEngine()
        news_answer = "Taza samachar aur breaking headlines:\n1. Global summit concludes."

        verified = verifier.verify_answer(
            query="abhi ki news kya hai?",
            proposed_answer=news_answer,
            source=AnswerSource.LIVE_SEARCH,
        )
        self.assertEqual(verified.grounding_status, GroundingStatus.GROUNDED)
        self.assertGreaterEqual(verified.confidence, 0.90)

    @patch.object(LiveNewsEngine, "query")
    def test_fast_path_news_interception(self, mock_query):
        mock_res = NewsQueryResult(
            found=True,
            headlines=[],
            formatted_text="Test Display News",
            spoken_text="Test Spoken News",
            category=NewsCategory.TOP,
            is_hindi=True,
            cached=False
        )
        mock_query.return_value = mock_res

        fast_path = FastPathEngine()
        turn = MagicMock()
        turn.metadata = {}
        result = fast_path.try_handle(
            raw_text="abhi ki news kya hai?",
            normalized_input="abhi ki news kya hai?",
            turn=turn,
            start_time=time.time(),
            tracker=None,
            source="text"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result, "Test Display News")
        self.assertEqual(turn.spoken_response, "Test Spoken News")

    def test_plugin_manager_news_execution(self):
        pm = PluginManager()
        pm.discover_and_load()
        news_plugin = pm.get_plugin("news")
        self.assertIsNotNone(news_plugin)
        res = news_plugin.execute("get_top_news", parameters={"limit": 1})
        self.assertTrue(res.success)
        self.assertIn("message", res.data)


if __name__ == "__main__":
    unittest.main()
