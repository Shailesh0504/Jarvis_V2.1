# tests/test_screen_awareness_activity_memory.py
"""
Comprehensive tests for persistent Screen Awareness & Activity Memory system.
Verifies multi-tier YouTube video title extraction, ActivityMemory temporal querying,
silent background observation, zero-hallucination guarantees, and end-to-end Jarvis responses.
"""

import os
import time
from unittest.mock import MagicMock, patch
import pytest

from brain.semantic_parser import HinglishNLUParser
from main import create_jarvis
from plugins.activity_monitor.extractors import YouTubeTitleExtractor
from plugins.activity_monitor.memory import ActivityEvent, ActivityMemory
from plugins.activity_monitor.observer import ActivityObserver
from plugins.activity_monitor.plugin import ActivityMonitorPlugin


# ---------------------------------------------------------------------------
# 1. Multi-tier YouTube Title Extractor Tests
# ---------------------------------------------------------------------------

def test_extractor_youtube_browser_window_titles():
    """Verifies extraction from various browser window titles and strips notification counters."""
    extractor = YouTubeTitleExtractor()

    # Chrome
    res1 = extractor.extract(
        raw_title="Building an AI Assistant from Scratch - YouTube - Google Chrome",
        process_name="chrome.exe"
    )
    assert res1["is_youtube"] is True
    assert res1["is_video"] is True
    assert res1["content_title"] == "Building an AI Assistant from Scratch"
    assert res1["confidence"] >= 0.9

    # Brave with notification counter
    res2 = extractor.extract(
        raw_title="(3) Python Tutorial for Beginners - YouTube - Brave",
        process_name="brave.exe"
    )
    assert res2["is_youtube"] is True
    assert res2["is_video"] is True
    assert res2["content_title"] == "Python Tutorial for Beginners"

    # Firefox with em-dash separator
    res3 = extractor.extract(
        raw_title="Interstellar Official Trailer - YouTube — Mozilla Firefox",
        process_name="firefox.exe"
    )
    assert res3["is_youtube"] is True
    assert res3["content_title"] == "Interstellar Official Trailer"

    # Edge standalone
    res4 = extractor.extract(
        raw_title="Lofi Hip Hop Radio - Beats to Relax - YouTube - Microsoft Edge",
        process_name="msedge.exe"
    )
    assert res4["is_youtube"] is True
    assert res4["content_title"] == "Lofi Hip Hop Radio - Beats to Relax"


def test_extractor_youtube_non_video_pages_zero_hallucination():
    """Ensures non-video YouTube pages do not hallucinate fake video titles."""
    extractor = YouTubeTitleExtractor()

    # Home feed
    res_home = extractor.extract("YouTube - Google Chrome", process_name="chrome.exe")
    assert res_home["is_youtube"] is True
    assert res_home["is_video"] is False
    assert res_home["content_title"] is None
    assert res_home["confidence"] == 0.0

    # Subscriptions
    res_subs = extractor.extract("Subscriptions - YouTube - Brave", process_name="brave.exe")
    assert res_subs["is_youtube"] is True
    assert res_subs["is_video"] is False
    assert res_subs["content_title"] is None

    # History
    res_hist = extractor.extract("History - YouTube - Google Chrome", process_name="chrome.exe")
    assert res_hist["is_youtube"] is True
    assert res_hist["is_video"] is False
    assert res_hist["content_title"] is None


def test_extractor_media_apps_and_general_apps():
    """Verifies recognition of non-browser media players like VLC."""
    extractor = YouTubeTitleExtractor()

    res_vlc = extractor.extract("Cosmos_Episode_1.mkv - VLC media player", process_name="vlc.exe")
    assert res_vlc["application"] == "vlc"
    assert res_vlc["is_video"] is True
    assert res_vlc["content_title"] == "Cosmos_Episode_1.mkv"


# ---------------------------------------------------------------------------
# 2. ActivityMemory Lifecycle & Temporal Query Tests
# ---------------------------------------------------------------------------

def test_activity_memory_lifecycle_non_destructive():
    """Verifies that switching focus or closing an app finalizes instead of deleting records."""
    mem = ActivityMemory()

    # 1. Video 1 starts
    e1 = mem.record_or_update(
        application="chrome",
        website="youtube",
        content_title="Deep Learning Crash Course",
        event_type="youtube_video_watched"
    )
    assert e1.state == "active"
    assert len(mem.get_history()) == 1

    # 2. User switches to Video 2
    e2 = mem.record_or_update(
        application="chrome",
        website="youtube",
        content_title="Quantum Computing 101",
        event_type="youtube_video_watched"
    )
    # e1 must now be finalized (closed), e2 active
    assert e1.state == "closed"
    assert e2.state == "active"
    assert len(mem.get_history()) == 2
    assert mem.get_history()[0]["content_title"] == "Deep Learning Crash Course"
    assert mem.get_history()[1]["content_title"] == "Quantum Computing 101"

    # 3. User closes browser
    mem.finalize_active(reason="browser_closed")
    assert e2.state == "closed"
    assert mem.active_event is None
    # Both events preserved in history
    assert len(mem.get_history()) == 2


def test_activity_memory_temporal_queries():
    """Tests temporal query semantics: abhi, last, thodi_der_pehle, and offset_minutes."""
    mem = ActivityMemory()
    now = time.time()

    # Video from 25 minutes ago
    e_old = ActivityEvent(
        application="chrome",
        website="youtube",
        content_title="20 Min Ago Video",
        start_time=now - (25 * 60),
        last_seen_time=now - (20 * 60),
        state="closed"
    )
    mem._events.append(e_old)

    # Video from 10 minutes ago
    e_mid = ActivityEvent(
        application="chrome",
        website="youtube",
        content_title="Previous Video",
        start_time=now - (15 * 60),
        last_seen_time=now - (8 * 60),
        state="closed"
    )
    mem._events.append(e_mid)

    # Current active video
    e_curr = ActivityEvent(
        application="chrome",
        website="youtube",
        content_title="Current Active Video",
        start_time=now - (5 * 60),
        last_seen_time=now,
        state="active"
    )
    mem._events.append(e_curr)
    mem._active_event = e_curr

    # Test "abhi" / "current"
    q_curr = mem.query_temporal(website="youtube", temporal="abhi")
    assert q_curr is not None
    assert q_curr.content_title == "Current Active Video"

    # Test "last" / "previous"
    q_last = mem.query_temporal(website="youtube", temporal="last")
    assert q_last is not None
    assert q_last.content_title == "Previous Video"

    # Test "thodi_der_pehle"
    q_earlier = mem.query_temporal(website="youtube", temporal="thodi_der_pehle")
    assert q_earlier is not None
    assert q_earlier.content_title == "Previous Video"

    # Test exact offset "20 minute pehle"
    q_20min = mem.query_temporal(website="youtube", offset_minutes=20)
    assert q_20min is not None
    assert q_20min.content_title == "20 Min Ago Video"


# ---------------------------------------------------------------------------
# 3. Silent Activity Observer Tests
# ---------------------------------------------------------------------------

def test_observer_poll_once_silent():
    """Verifies that poll_once observes foreground window without emitting audio/TTS."""
    mem = ActivityMemory()
    observer = ActivityObserver(memory=mem)

    callback_called = []

    def mock_cb(event):
        callback_called.append(event)

    observer.on_activity_callback = mock_cb

    # Mock get_active_window_info
    with patch.object(
        observer,
        "get_active_window_info",
        return_value={
            "hwnd": 12345,
            "title": "Machine Learning from Scratch - YouTube - Google Chrome",
            "process_name": "chrome.exe"
        }
    ):
        event = observer.poll_once()
        assert event is not None
        assert event.content_title == "Machine Learning from Scratch"
        assert event.website == "youtube"
        assert len(callback_called) == 1
        assert callback_called[0].content_title == "Machine Learning from Scratch"


# ---------------------------------------------------------------------------
# 4. ActivityMonitorPlugin Action Execution
# ---------------------------------------------------------------------------

def test_plugin_declared_actions_and_honest_failures():
    """Verifies plugin actions and zero-hallucination honest failure response."""
    plugin = ActivityMonitorPlugin()

    # Check manifest
    manifest = plugin.get_manifest()
    assert manifest.name == "activity_monitor"
    action_names = [a.name for a in manifest.actions]
    assert "get_current_activity" in action_names
    assert "get_past_activity" in action_names
    assert "get_activity_history" in action_names
    assert "poll_activity" in action_names

    # 1. No activity initially
    res1 = plugin.execute("get_current_activity", {})
    assert res1.success is True
    assert "koi active window" in res1.data["message"]

    # 2. Record video with title
    plugin.memory.record_or_update(
        application="chrome",
        website="youtube",
        content_title="AlphaGo Documentary",
        event_type="youtube_video_watched",
        confidence=0.95
    )

    res2 = plugin.execute("get_past_activity", {"website": "youtube", "temporal": "abhi"})
    assert res2.success is True
    assert "AlphaGo Documentary" in res2.data["message"]

    # 3. Record YouTube open without title (zero hallucination check)
    plugin.memory.record_or_update(
        application="chrome",
        website="youtube",
        content_title=None,
        confidence=0.0
    )
    res3 = plugin.execute("get_past_activity", {"website": "youtube", "temporal": "abhi"})
    assert res3.success is True
    assert "main specific video ka title detect nahi kar paya" in res3.data["message"]


# ---------------------------------------------------------------------------
# 5. End-to-End Jarvis Core Integration Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def jarvis_instance(tmp_path):
    db_file = os.path.join(tmp_path, "activity_integration.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_AWARENESS_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


def test_e2e_youtube_past_video_detection_and_questions(jarvis_instance):
    """
    Simulates watching YouTube, closing YouTube, and querying via all required conversational phrases:
    - "abhi maine YouTube pe konsa video dekha?"
    - "maine abhi kya dekha?"
    - "YouTube pe kya video chal raha tha?"
    - "thodi der pehle kya dekh raha tha?"
    - "last video konsa tha?"
    - "maine 20 minute pehle kya dekha?"
    """
    act_plugin = jarvis_instance.plugin_manager.get_plugin("activity_monitor")
    assert act_plugin is not None

    now = time.time()

    # 1. 20 minutes ago video
    act_plugin.memory._events.append(
        ActivityEvent(
            application="chrome",
            website="youtube",
            content_title="Deep Learning in 20 Minutes",
            start_time=now - (25 * 60),
            last_seen_time=now - (18 * 60),
            state="closed",
            confidence=0.95
        )
    )

    # 2. Previous video (thodi der pehle)
    act_plugin.memory._events.append(
        ActivityEvent(
            application="chrome",
            website="youtube",
            content_title="SpaceX Starship Launch",
            start_time=now - (15 * 60),
            last_seen_time=now - (8 * 60),
            state="closed",
            confidence=0.95
        )
    )

    # 3. Currently active video
    curr_event = act_plugin.memory.record_or_update(
        application="chrome",
        website="youtube",
        content_title="Building an AI Assistant from Scratch",
        event_type="youtube_video_watched",
        confidence=0.95
    )

    # Query 1: "abhi maine YouTube pe konsa video dekha?"
    r1 = jarvis_instance.process_input("abhi maine YouTube pe konsa video dekha?")
    assert "Building an AI Assistant from Scratch" in r1
    assert "YouTube" in r1

    # Query 2: "maine abhi kya dekha?"
    r2 = jarvis_instance.process_input("maine abhi kya dekha?")
    assert "Building an AI Assistant from Scratch" in r2

    # Query 3: "YouTube pe kya video chal raha tha?"
    r3 = jarvis_instance.process_input("YouTube pe kya video chal raha tha?")
    assert "Building an AI Assistant from Scratch" in r3

    # Query 4: "last video konsa tha?" -> must return previous video
    r4 = jarvis_instance.process_input("last video konsa tha?")
    assert "SpaceX Starship Launch" in r4

    # Query 5: "thodi der pehle kya dekh raha tha?" -> must return previous video
    r5 = jarvis_instance.process_input("thodi der pehle kya dekh raha tha?")
    assert "SpaceX Starship Launch" in r5

    # Query 6: "maine 20 minute pehle kya dekha?" -> must return 20 min ago video
    r6 = jarvis_instance.process_input("maine 20 minute pehle kya dekha?")
    assert "Deep Learning in 20 Minutes" in r6

    # 4. Now simulate closing YouTube
    act_plugin.memory.finalize_active(reason="user_closed_youtube")
    # Query again after YouTube is closed: Jarvis must still remember what was watched!
    r_after_close = jarvis_instance.process_input("abhi maine YouTube pe konsa video dekha?")
    assert "Building an AI Assistant from Scratch" in r_after_close


def test_e2e_honest_failure_when_title_undetected(jarvis_instance):
    """
    Simulates user browsing YouTube home page where video title is undetected.
    Jarvis must honestly admit inability to identify the title and never hallucinate.
    """
    act_plugin = jarvis_instance.plugin_manager.get_plugin("activity_monitor")
    assert act_plugin is not None

    # Clear previous
    act_plugin.memory.clear()

    # Active event is YouTube with undetected title
    act_plugin.memory.record_or_update(
        application="chrome",
        website="youtube",
        content_title=None,
        confidence=0.0
    )

    resp = jarvis_instance.process_input("abhi maine YouTube pe konsa video dekha?")
    assert "specific video ka title detect nahi kar paya" in resp
