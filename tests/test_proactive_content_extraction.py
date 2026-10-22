# tests/test_proactive_content_extraction.py
"""
Comprehensive tests for Phase 2: Meaningful Activity Events & Multi-Tier Content Extraction.
Verifies website dissection, YouTube video detection, media players, document editors,
volume change tracking, event classification, and content-level deduplication.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.observer.content_extractor import ContentExtractor
from core.observer.volume_observer import VolumeObserver
from core.observer.models import ActivityEvent, ActivityImportance, ActivityType, DesktopSnapshot
from core.observer.activity_observer import ProactiveActivityObserver


# ---------------------------------------------------------------------------
# 1. Web & Video Extraction Tests
# ---------------------------------------------------------------------------

def test_youtube_video_title_extraction():
    """Verifies that YouTube video titles are extracted cleanly while stripping browser branding."""
    extractor = ContentExtractor()

    # Chrome
    res1 = extractor.extract(
        raw_title="Kesariya Song - Brahmāstra - YouTube - Google Chrome",
        process_name="chrome"
    )
    assert res1["website"] == "youtube"
    assert res1["content_title"] == "Kesariya Song - Brahmāstra"
    assert res1["is_video"] is True
    assert res1["category"] == "media"
    assert res1["confidence"] >= 0.9

    # Brave with notification badge
    res2 = extractor.extract(
        raw_title="(2) Python Tutorial for Beginners - YouTube - Brave",
        process_name="brave"
    )
    assert res2["website"] == "youtube"
    assert res2["content_title"] == "Python Tutorial for Beginners"
    assert res2["is_video"] is True

    # Firefox with em-dash
    res3 = extractor.extract(
        raw_title="Interstellar Official Trailer - YouTube — Mozilla Firefox",
        process_name="firefox"
    )
    assert res3["website"] == "youtube"
    assert res3["content_title"] == "Interstellar Official Trailer"
    assert res3["is_video"] is True


def test_youtube_feeds_and_home_zero_hallucination():
    """Verifies that non-video YouTube pages do not hallucinate video playback."""
    extractor = ContentExtractor()

    # Home feed
    res_home = extractor.extract("YouTube - Google Chrome", process_name="chrome")
    assert res_home["website"] == "youtube"
    assert res_home["is_video"] is False
    assert res_home["content_title"] is None

    # Subscriptions
    res_subs = extractor.extract("Subscriptions - YouTube - Brave", process_name="brave")
    assert res_subs["website"] == "youtube"
    assert res_subs["is_video"] is False
    assert res_subs["content_title"] is None

    # History
    res_hist = extractor.extract("History - YouTube - Microsoft Edge", process_name="edge")
    assert res_hist["website"] == "youtube"
    assert res_hist["is_video"] is False
    assert res_hist["content_title"] is None


def test_search_engine_query_extraction():
    """Verifies extraction of Google search queries from browser titles."""
    extractor = ContentExtractor()

    res = extractor.extract(
        raw_title="python asyncio tutorial - Google Search - Google Chrome",
        process_name="chrome"
    )
    assert res["website"] == "google"
    assert res["content_title"] == "python asyncio tutorial"
    assert res["category"] == "search"
    assert res["is_video"] is False


def test_github_and_ai_websites():
    """Verifies extraction for GitHub, ChatGPT, and Claude."""
    extractor = ContentExtractor()

    # GitHub
    res_gh = extractor.extract("microsoft/vscode · GitHub - Brave", process_name="brave")
    assert res_gh["website"] == "github"
    assert res_gh["content_title"] == "microsoft/vscode"
    assert res_gh["category"] == "development"

    # ChatGPT
    res_gpt = extractor.extract("FastAPI Best Practices - ChatGPT - Google Chrome", process_name="chrome")
    assert res_gpt["website"] == "chatgpt"
    assert res_gpt["content_title"] == "FastAPI Best Practices"
    assert res_gpt["category"] == "ai"


# ---------------------------------------------------------------------------
# 2. Media Players & Documents Tests
# ---------------------------------------------------------------------------

def test_vlc_and_spotify_media_extraction():
    """Verifies media title extraction from desktop players."""
    extractor = ContentExtractor()

    # VLC Media Player
    res_vlc = extractor.extract("Dune_Part_Two.mkv - VLC media player", process_name="vlc")
    assert res_vlc["content_title"] == "Dune_Part_Two.mkv"
    assert res_vlc["is_video"] is True
    assert res_vlc["is_media"] is True
    assert res_vlc["category"] == "media"

    # Spotify Desktop
    res_spot = extractor.extract("Arijit Singh - Tum Hi Ho", process_name="spotify")
    assert res_spot["website"] == "spotify"
    assert res_spot["content_title"] == "Arijit Singh - Tum Hi Ho"
    assert res_spot["is_media"] is True


def test_document_and_productivity_extraction():
    """Verifies document title extraction from Excel, Word, VSCode, and Notepad."""
    extractor = ContentExtractor()

    # Excel
    res_excel = extractor.extract("Annual_Financials.xlsx - Excel", process_name="excel")
    assert res_excel["content_title"] == "Annual_Financials.xlsx"
    assert res_excel["is_document"] is True
    assert res_excel["category"] == "document"

    # VS Code
    res_code = extractor.extract("app.py - Jarvis - Visual Studio Code", process_name="vscode")
    assert "app.py" in res_code["content_title"]
    assert res_code["is_document"] is True


# ---------------------------------------------------------------------------
# 3. VolumeObserver Tests
# ---------------------------------------------------------------------------

def test_volume_observer_thresholding_and_jitter():
    """Verifies that VolumeObserver suppresses small volume jitter (< 2%) and emits significant changes."""
    obs = VolumeObserver(change_threshold=2)

    with patch("plugins.audio.volume_controller.get_system_volume") as mock_vol:
        # 1. Baseline initialization: 40%
        mock_vol.return_value = {"success": True, "volume": 40, "muted": False}
        changed, old_v, new_v, muted = obs.check_volume_change()
        assert changed is False
        assert new_v == 40

        # 2. Small jitter: 41% (difference is 1% < 2%) -> Suppressed
        mock_vol.return_value = {"success": True, "volume": 41, "muted": False}
        changed, old_v, new_v, muted = obs.check_volume_change()
        assert changed is False

        # 3. Significant change: 30% (difference is 10% >= 2%) -> Emits change
        mock_vol.return_value = {"success": True, "volume": 30, "muted": False}
        changed, old_v, new_v, muted = obs.check_volume_change()
        assert changed is True
        assert old_v == 40
        assert new_v == 30
        assert muted is False

        # 4. Mute toggle -> Emits change even if percentage unchanged
        mock_vol.return_value = {"success": True, "volume": 30, "muted": True}
        changed, old_v, new_v, muted = obs.check_volume_change()
        assert changed is True
        assert muted is True


# ---------------------------------------------------------------------------
# 4. End-to-End ActivityObserver Refined Events & Content Deduplication
# ---------------------------------------------------------------------------

def test_activity_observer_video_event_and_deduplication():
    """Verifies that video playback produces VIDEO_PLAYED (HIGH) and continuous watching is deduplicated."""
    obs = ProactiveActivityObserver(poll_interval=1.0)
    snap_yt = DesktopSnapshot(
        hwnd=501,
        title="Kesariya Song - Brahmāstra - YouTube - Google Chrome",
        process_name="chrome"
    )

    with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap_yt), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, 40, 40, False)):

        # Poll 1: Video started -> Emits VIDEO_PLAYED with HIGH importance
        ev1 = obs.poll_once()
        assert ev1 is not None
        assert ev1.event_type == ActivityType.VIDEO_PLAYED
        assert ev1.importance == ActivityImportance.HIGH
        assert ev1.website == "youtube"
        assert ev1.content_title == "Kesariya Song - Brahmāstra"

        # Poll 2: Still watching same video -> Suppressed (deduplication)
        ev2 = obs.poll_once()
        assert ev2 is None

        # Poll 3: Still watching same video -> Suppressed
        ev3 = obs.poll_once()
        assert ev3 is None


def test_activity_observer_volume_change_event():
    """Verifies that master volume changes generate VOLUME_CHANGED events."""
    obs = ProactiveActivityObserver(poll_interval=1.0)

    with patch.object(obs.volume_observer, "check_volume_change", return_value=(True, 40, 25, False)), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)):

        ev = obs.poll_once()
        assert ev is not None
        assert ev.event_type == ActivityType.VOLUME_CHANGED
        assert ev.importance == ActivityImportance.MEDIUM
        assert ev.metadata["old_volume"] == 40
        assert ev.metadata["new_volume"] == 25


def test_activity_observer_document_switch():
    """Verifies that switching to a document emits DOCUMENT_EDITED."""
    obs = ProactiveActivityObserver(poll_interval=1.0)
    snap_excel = DesktopSnapshot(
        hwnd=601,
        title="Sales_Q3.xlsx - Excel",
        process_name="excel"
    )

    with patch.object(obs.window_observer, "get_foreground_snapshot", return_value=snap_excel), \
         patch.object(obs.screen_observer, "check_attention_state", return_value=(0.5, False, None)), \
         patch.object(obs.volume_observer, "check_volume_change", return_value=(False, 40, 40, False)):

        ev = obs.poll_once()
        assert ev is not None
        assert ev.event_type == ActivityType.DOCUMENT_EDITED
        assert ev.importance == ActivityImportance.MEDIUM
        assert ev.content_title == "Sales_Q3.xlsx"
        assert ev.application == "excel"
