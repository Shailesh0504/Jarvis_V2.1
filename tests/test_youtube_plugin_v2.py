# tests/test_youtube_plugin_v2.py
"""Regression coverage for the no-API YouTube v2 subsystem."""

import logging

import pytest

from brain.semantic_parser import HinglishNLUParser
from plugins.youtube.browser_controller import BrowserOpenResult
from plugins.youtube.models import PlaybackState, YouTubeResult
from plugins.youtube.plugin import YouTubePlugin
from plugins.youtube.search import YouTubeSearchResolver
from plugins.manifest import PluginResult


def result(video_id, title, channel=""):
    return YouTubeResult(video_id=video_id, title=title, channel=channel)


@pytest.mark.parametrize(
    "utterance",
    [
        "Arijit Singh ka Tum Hi Ho chalao",
        "KGF trailer chalao",
        "CarryMinati ka latest video chalao",
        "random future song title baja do",
    ],
)
def test_arbitrary_play_requests_are_structured_not_hardcoded(utterance):
    action = HinglishNLUParser.parse(utterance)

    assert action is not None
    assert action.intent == "PLAY_MEDIA"
    assert action.service == "youtube"
    assert action.action == "search_and_play"
    assert action.parameters["query"]


@pytest.mark.parametrize(
    ("utterance", "action", "parameters"),
    [
        ("pause karo", "pause", {}),
        ("phir se chalao", "resume", {}),
        ("next video", "next", {}),
        ("pichhla video", "previous", {}),
        ("10 minute aage karo", "seek", {"seconds": 600}),
        ("30 seconds piche karo", "seek", {"seconds": -30}),
        ("yahi video dobara chalao", "replay", {}),
        ("youtube volume 20 karo", "set_volume", {"level": 20}),
        ("youtube pe kuch nahi chal raha", "get_current_video", {}),
    ],
)
def test_followups_route_to_youtube_session_actions(utterance, action, parameters):
    parsed = HinglishNLUParser.parse(utterance)

    assert parsed is not None
    assert parsed.service == "youtube"
    assert parsed.action == action
    assert parsed.parameters == parameters


@pytest.mark.parametrize("utterance", ["YouTube band karo", "close YouTube"])
def test_close_youtube_is_tab_close_not_playback_stop(utterance):
    parsed = HinglishNLUParser.parse(utterance)
    assert parsed is not None
    assert parsed.service == "target"
    assert parsed.action == "execute"
    assert parsed.parameters["target"] == "youtube"
    assert parsed.parameters["action"] == "close"


def test_deterministic_ranking_prefers_title_and_channel_match():
    resolver = YouTubeSearchResolver()
    ranked = resolver.rank("Arijit Singh Tum Hi Ho", [
        result("aaaaaaaaaaa", "Tum Hi Ho Karaoke", "Karaoke Hub"),
        result("bbbbbbbbbbb", "Tum Hi Ho Official Song", "Arijit Singh"),
        result("ccccccccccc", "Arijit Singh Interview", "News"),
    ])

    assert ranked[0].video_id == "bbbbbbbbbbb"


def test_ambiguous_results_request_clarification_without_opening_browser(monkeypatch):
    plugin = YouTubePlugin()
    candidates = [
        YouTubeResult("aaaaaaaaaaa", "Live version alpha", score=0.6),
        YouTubeResult("bbbbbbbbbbb", "Live version beta", score=0.59),
    ]
    monkeypatch.setattr(plugin.search_resolver, "search", lambda _query: candidates)
    monkeypatch.setattr(plugin.search_resolver, "select_best", lambda *_args: (None, "ambiguous"))
    opened = []
    monkeypatch.setattr(plugin, "_open_url", lambda url: opened.append(url))

    response = plugin.safe_execute("PLAY_VIDEO", {"query": "live version"})

    assert response.success is False
    assert "Kaunsi play karun" in response.error
    assert opened == []


def test_ambiguous_youtube_result_keeps_followup_workflow_active(monkeypatch, tmp_path):
    from main import create_jarvis

    config = tmp_path / "config.yaml"
    config.write_text(
        "brain:\n  llm_provider: mock\nplugins:\n  plugin_dir: plugins\n  auto_load: true\n",
        encoding="utf-8",
    )
    core = create_jarvis(str(config))
    ambiguous = PluginResult(success=False, error="Multiple matching videos mili. Kaunsi play karun?")
    monkeypatch.setattr(core.plugin_manager, "execute_action", lambda *_args, **_kwargs: ambiguous)

    response = core.process_input("koi romantic gana sunao")

    assert "Kaunsi play karun" in response
    assert core.dialog_manager.has_active_lock() is True
    assert core.dialog_manager.active_lock.workflow_type == "YOUTUBE_PLAY"


def test_play_resolves_watch_url_updates_session_and_emits_lifecycle_logs(monkeypatch, caplog):
    plugin = YouTubePlugin()
    selected = result("idNyQkZU2VA", "Tera Surroor Official", "T-Series")
    monkeypatch.setattr(plugin.search_resolver, "search", lambda _query: [selected])
    monkeypatch.setattr(plugin.search_resolver, "select_best", lambda *_args: (selected, "selected"))
    urls = []
    monkeypatch.setattr(plugin, "_open_url", lambda url: urls.append(url) or BrowserOpenResult(True, "Brave", "brave.exe", True))

    with caplog.at_level(logging.INFO):
        response = plugin.safe_execute("PLAY_SONG", {"query": "Tera Surroor"})

    assert response.success is True
    assert urls == ["https://www.youtube.com/watch?v=idNyQkZU2VA"]
    assert "results?search_query=" not in urls[0]
    assert plugin.session.current_video.video_id == "idNyQkZU2VA"
    assert plugin.session.playback_state == PlaybackState.OPENED
    assert "playing" not in response.data["playback_state"]
    for event in ("QUERY_PARSED", "SEARCH_RESULT_SELECTED", "VIDEO_ID_RESOLVED", "SESSION_UPDATED"):
        assert event in caplog.text


def test_browser_failure_is_reported_and_never_claims_playing(monkeypatch):
    plugin = YouTubePlugin()
    selected = result("idNyQkZU2VA", "Resolved Video")
    monkeypatch.setattr(plugin.search_resolver, "search", lambda _query: [selected])
    monkeypatch.setattr(plugin.search_resolver, "select_best", lambda *_args: (selected, "selected"))
    monkeypatch.setattr(plugin, "_open_url", lambda _url: BrowserOpenResult(False, "Default Browser", error="launch failed"))

    response = plugin.safe_execute("PLAY_VIDEO", {"query": "Resolved Video"})

    assert response.success is False
    assert "browser open nahi hua" in response.error
    assert plugin.session.playback_state == PlaybackState.FAILED


def test_pause_resume_seek_replay_queue_and_previous_use_active_session(monkeypatch):
    plugin = YouTubePlugin()
    current = result("aaaaaaaaaaa", "Current Song")
    plugin.session.current_video = current
    plugin.session.current_url = current.watch_url
    plugin.session.playback_state = PlaybackState.OPENED
    keys = []
    monkeypatch.setattr(plugin.browser, "send_media_key", lambda key, presses=1: keys.append((key, presses)) or True)
    monkeypatch.setattr(plugin.browser, "seek", lambda seconds: keys.append(("seek", seconds)) or True)
    monkeypatch.setattr(plugin, "_open_url", lambda _url: BrowserOpenResult(True, "Brave"))

    assert plugin.safe_execute("PAUSE", {}).success
    assert plugin.session.playback_state == PlaybackState.PAUSED
    assert plugin.safe_execute("RESUME", {}).success
    assert plugin.session.playback_state == PlaybackState.PLAYING
    assert plugin.safe_execute("SEEK", {"seconds": 600}).success
    assert plugin.safe_execute("REPLAY", {}).success
    assert plugin.safe_execute("ADD_TO_QUEUE", {"query": "Next arbitrary song"}).success
    assert plugin.session.queue[0].query == "Next arbitrary song"
    assert ("k", 1) in keys and ("seek", 600) in keys


def test_unavailable_video_is_reported(monkeypatch):
    plugin = YouTubePlugin()
    selected = YouTubeResult("aaaaaaaaaaa", "Private Video", unavailable=True, score=1.0)
    monkeypatch.setattr(plugin.search_resolver, "search", lambda _query: [selected])
    monkeypatch.setattr(plugin.search_resolver, "select_best", lambda *_args: (selected, "selected"))

    response = plugin.safe_execute("PLAY_VIDEO", {"query": "Private Video"})

    assert response.success is False
    assert "unavailable ya restricted" in response.error
