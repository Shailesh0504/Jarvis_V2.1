# tests/test_nlu_youtube_architecture.py
"""
Unit and Integration Tests for Core Brain Natural-Language Understanding (NLU),
Semantic Entity Extraction, and Decoupled YouTube Plugin Direct Playback Architecture.
"""

import pytest
from unittest.mock import patch, MagicMock
from brain.semantic_parser import HinglishNLUParser, SemanticAction
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from plugins.youtube.plugin import YouTubePlugin


@pytest.fixture
def jarvis_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_nlu.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_nlu_parser_flexible_word_order():
    """Verify semantic parser extracts structured actions regardless of Hinglish word order."""
    # 1. "tera surur youtube pe play karo"
    act1 = HinglishNLUParser.parse("tera surur youtube pe play karo")
    assert act1 is not None
    assert act1.intent == "PLAY_MEDIA"
    assert act1.service == "youtube"
    assert act1.action == "search_and_play"
    assert "Surroor" in act1.query or "Tera" in act1.query

    # 2. "Tera Surroor YouTube pe chalao"
    act2 = HinglishNLUParser.parse("Tera Surroor YouTube pe chalao")
    assert act2 is not None
    assert act2.service == "youtube"
    assert "Tera" in act2.query and "Surroor" in act2.query

    # 3. "YouTube pe Tera Surroor laga do"
    act3 = HinglishNLUParser.parse("YouTube pe Tera Surroor laga do")
    assert act3 is not None
    assert act3.service == "youtube"
    assert "Tera" in act3.query and "Surroor" in act3.query

    # 4. "Tera Surroor wala gaana bajao"
    act4 = HinglishNLUParser.parse("Tera Surroor wala gaana bajao")
    assert act4 is not None
    assert act4.service == "youtube"
    assert "Tera" in act4.query and "Surroor" in act4.query

    # 5. "YouTube par Tera Surroor search karke play karo"
    act5 = HinglishNLUParser.parse("YouTube par Tera Surroor search karke play karo")
    assert act5 is not None
    assert act5.service == "youtube"
    assert act5.action == "search_and_play"
    assert "Tera" in act5.query and "Surroor" in act5.query

    # 6. "bhai youtube pe tera surroor chala na"
    act6 = HinglishNLUParser.parse("bhai youtube pe tera surroor chala na")
    assert act6 is not None
    assert act6.service == "youtube"
    assert "Tera" in act6.query and "Surroor" in act6.query

    # 7. "VLC mein Tera Surroor chalao"
    act7 = HinglishNLUParser.parse("VLC mein Tera Surroor chalao")
    assert act7 is not None
    assert act7.service == "vlc"
    assert "Tera" in act7.query and "Surroor" in act7.query

    # 8. Missing query -> Needs clarification
    act8 = HinglishNLUParser.parse("YouTube pe gaana play karo")
    assert act8 is not None
    assert act8.needs_clarification is True
    assert "Kaunsa gaana" in act8.clarification_prompt

    # 9. Open YouTube
    act9 = HinglishNLUParser.parse("youtube kholo")
    assert act9 is not None
    assert act9.intent == "OPEN_APP"
    assert act9.action == "open_youtube"

    # 10. Conversation is ignored by NLU parser
    act10 = HinglishNLUParser.parse("kya haal hai")
    assert act10 is None


def test_nlu_parser_arbitrary_media_and_search_distinction():
    """Verify arbitrary song queries and SEARCH vs PLAY distinction."""
    # Arbitrary songs
    act_arijit = HinglishNLUParser.parse("Arijit Singh Tum Hi Ho chalao")
    assert act_arijit is not None
    assert act_arijit.intent == "PLAY_MEDIA"
    assert act_arijit.service == "youtube"
    assert "Arijit" in act_arijit.query and "Tum Hi Ho" in act_arijit.query

    act_kgf = HinglishNLUParser.parse("KGF trailer YouTube pe play karo")
    assert act_kgf is not None
    assert act_kgf.intent == "PLAY_MEDIA"
    assert "Kgf Trailer" in act_kgf.query or "KGF" in act_kgf.query

    act_carry = HinglishNLUParser.parse("CarryMinati ka latest video chalao")
    assert act_carry is not None
    assert act_carry.intent == "PLAY_MEDIA"
    assert "Carryminati" in act_carry.query

    # Search queries (SEARCH_MEDIA intent, action='search')
    act_search1 = HinglishNLUParser.parse("YouTube pe Tera Surroor search karo")
    assert act_search1 is not None
    assert act_search1.intent == "SEARCH_MEDIA"
    assert act_search1.action == "search"
    assert "Surroor" in act_search1.query

    act_search2 = HinglishNLUParser.parse("YouTube par Python tutorial dhoondo")
    assert act_search2 is not None
    assert act_search2.intent == "SEARCH_MEDIA"
    assert act_search2.action == "search"
    assert "Python Tutorial" in act_search2.query or "Python" in act_search2.query


def test_youtube_plugin_direct_play_workflow():
    """Regression test proving PLAY requests navigate to /watch?v=... and NOT /results?search_query=."""
    plugin = YouTubePlugin()

    # Mock _find_top_video to simulate successful search result extraction
    with patch.object(plugin, "_find_top_video", return_value=("idNyQkZU2VA", "Tera Suroor - Himesh Reshammiya")), \
         patch.object(plugin, "get_brave_executable", return_value=None), \
         patch("webbrowser.open") as mock_browser_open:

        res = plugin.safe_execute("search_and_play", {"query": "Tera Surroor"})

        assert res.success is True
        assert res.data["video_id"] == "idNyQkZU2VA"
        assert res.data["url"] == "https://www.youtube.com/watch?v=idNyQkZU2VA"
        assert "watch?v=" in res.data["url"]
        assert "results?search_query=" not in res.data["url"]

        # Verify browser was commanded to open the direct watch URL
        mock_browser_open.assert_called_once_with("https://www.youtube.com/watch?v=idNyQkZU2VA")


def test_youtube_plugin_brave_preference_when_installed():
    """Verify that when Brave Browser is installed, YouTube videos launch directly in Brave."""
    plugin = YouTubePlugin()
    brave_fake_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

    with patch.object(plugin, "_find_top_video", return_value=("idNyQkZU2VA", "Tera Surroor")), \
         patch.object(plugin, "get_brave_executable", return_value=brave_fake_path), \
         patch("subprocess.Popen") as mock_popen, \
         patch("webbrowser.open") as mock_webbrowser:

        res = plugin.safe_execute("search_and_play", {"query": "Tera Surroor"})

        assert res.success is True
        assert res.data["in_brave"] is True
        assert res.data["browser"] == "Brave"
        assert res.data["url"] == "https://www.youtube.com/watch?v=idNyQkZU2VA"

        mock_popen.assert_called_once_with([brave_fake_path, "https://www.youtube.com/watch?v=idNyQkZU2VA"])
        mock_webbrowser.assert_not_called()


def test_youtube_plugin_brave_fallback_when_not_installed():
    """Verify that when Brave is not installed, it gracefully falls back to default browser."""
    plugin = YouTubePlugin()

    with patch.object(plugin, "_find_top_video", return_value=("idNyQkZU2VA", "Tera Surroor")), \
         patch.object(plugin, "get_brave_executable", return_value=None), \
         patch("webbrowser.open") as mock_webbrowser:

        res = plugin.safe_execute("search_and_play", {"query": "Tera Surroor"})

        assert res.success is True
        assert res.data["in_brave"] is False
        assert res.data["url"] == "https://www.youtube.com/watch?v=idNyQkZU2VA"
        mock_webbrowser.assert_called_once_with("https://www.youtube.com/watch?v=idNyQkZU2VA")


def test_youtube_plugin_brave_fallback_on_launch_error():
    """Verify that if launching Brave throws an error, fallback to default browser happens without failing."""
    plugin = YouTubePlugin()
    brave_fake_path = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

    with patch.object(plugin, "_find_top_video", return_value=("idNyQkZU2VA", "Tera Surroor")), \
         patch.object(plugin, "get_brave_executable", return_value=brave_fake_path), \
         patch("subprocess.Popen", side_effect=OSError("Brave binary corrupted")), \
         patch("webbrowser.open") as mock_webbrowser:

        res = plugin.safe_execute("search_and_play", {"query": "Tera Surroor"})

        assert res.success is True
        assert res.data["url"] == "https://www.youtube.com/watch?v=idNyQkZU2VA"
        mock_webbrowser.assert_called_once_with("https://www.youtube.com/watch?v=idNyQkZU2VA")


def test_youtube_plugin_search_action_opens_search_results():
    """Verify that SEARCH requests open the /results?search_query= page."""
    plugin = YouTubePlugin()

    with patch.object(plugin, "get_brave_executable", return_value=None), \
         patch("webbrowser.open") as mock_browser_open:
        res = plugin.safe_execute("search", {"query": "Tera Surroor"})

        assert res.success is True
        assert "results?search_query=" in res.data["url"]
        assert "Tera+Surroor" in res.data["url"] or "Tera%20Surroor" in res.data["url"]
        mock_browser_open.assert_called_once()


def test_youtube_plugin_not_found_handling():
    """Verify that when no video result is found, Jarvis informs the user without opening an empty page."""
    plugin = YouTubePlugin()

    with patch.object(plugin, "_find_top_video", return_value=None), \
         patch("webbrowser.open") as mock_browser_open:

        res = plugin.safe_execute("search_and_play", {"query": "NonexistentRandomGibberishVideoXYZ999"})

        assert res.success is False
        assert "koi video nahi mili" in res.error
        # Browser must NOT be opened
        mock_browser_open.assert_not_called()


def test_end_to_end_media_and_conversation_routing(jarvis_app):
    """End-to-end testing of Core routing and decoupled execution with direct play."""
    with patch("plugins.youtube.plugin.YouTubePlugin._find_top_video", return_value=("Umqb9KENgmk", "Tum Hi Ho")):
        # 1. Play YouTube with speech variance
        resp1 = jarvis_app.process_input("tera surur youtube pe play karo")
        assert "YouTube par play kar raha hoon" in resp1 or "Tum Hi Ho" in resp1 or "Tera Surroor" in resp1 or "YouTube video" in resp1 or "direct YouTube" in resp1

    # 2. Open YouTube
    resp2 = jarvis_app.process_input("youtube kholo")
    assert "YouTube open" in resp2 or "open" in resp2.lower() or "active kar diya" in resp2.lower()

    # 3. Missing song name triggers clarification
    resp3 = jarvis_app.process_input("YouTube pe gaana play karo")
    assert "Kaunsa gaana play karun" in resp3

    # 4. Pure conversation routes to Conversation Core
    resp4 = jarvis_app.process_input("kya haal hai")
    assert "Main bilkul theek hoon" in resp4
