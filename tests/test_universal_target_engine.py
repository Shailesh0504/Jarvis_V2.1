# tests/test_universal_target_engine.py
"""Regression coverage for generic target discovery, matching, planning and verification."""

import pytest

from brain.semantic_parser import HinglishNLUParser
from core.target_engine import (
    ActionOutcome, TargetAction, TargetCandidate, TargetKind, TargetMatcher,
    TargetRequest, UniversalTargetDiscoveryEngine,
)


class FakeResolver:
    def __init__(self, candidates):
        self.candidates = list(candidates)

    def resolve(self, _request):
        return list(self.candidates)


class FakeExecutor:
    def __init__(self, resolver):
        self.resolver = resolver
        self.executed = []
        self.plugin_manager = None

    def execute(self, action, target):
        self.executed.append((action, target))
        self.resolver.candidates.remove(target)
        return True


def tab(title, url, browser="brave", hwnd=10, index=0, backend="devtools"):
    from urllib.parse import urlsplit
    return TargetCandidate(
        TargetKind.BROWSER_TAB, url, title=title, url=url,
        domain=urlsplit(url).hostname or "", browser=browser, hwnd=hwnd,
        tab_index=index, tab_id=f"{browser}-{hwnd}-{index}", backend=backend,
        confidence=1.0,
    )


def engine_with(candidates):
    engine = UniversalTargetDiscoveryEngine()
    resolver = FakeResolver(candidates)
    engine.resolver = resolver
    engine.executor = FakeExecutor(resolver)
    return engine


@pytest.mark.parametrize(
    ("utterance", "target", "action", "container"),
    [
        ("YouTube band karo", "youtube", "close", ""),
        ("Flipkart wala tab band karo", "flipkart", "close", ""),
        ("GitHub ko activate karo", "github", "activate", ""),
        ("Chrome mein YouTube wala tab kholo", "youtube", "open", "chrome"),
        ("youtube ko brave me open karo", "youtube", "open", "brave"),
        ("open youtube on brave", "youtube", "open", "brave"),
        ("brave me youtube kholo", "youtube", "open", "brave"),
        ("open youtube in chrome", "youtube", "open", "chrome"),
        ("youtube ko brave me band karo", "youtube", "close", "brave"),
        ("close youtube in brave", "youtube", "close", "brave"),
    ],
)
def test_examples_use_one_universal_structured_pipeline(utterance, target, action, container):
    parsed = HinglishNLUParser.parse(utterance)
    assert parsed is not None
    assert parsed.intent == "UNIVERSAL_TARGET_ACTION"
    assert parsed.service == "target"
    assert parsed.action == "execute"
    assert parsed.parameters == {"target": target, "action": action, "container": container, "scope": "auto"}


def test_background_tab_is_found_closed_and_verified():
    youtube = tab("Video - YouTube", "https://www.youtube.com/watch?v=1", index=3)
    engine = engine_with([youtube])
    result = engine.execute(TargetRequest("youtube", "close"))
    assert result.success and result.verified
    assert engine.executor.executed[0][0] == "close_tab"


def test_duplicate_targets_across_windows_and_browsers_ask_instead_of_acting():
    matches = [
        tab("YouTube", "https://youtube.com/", "brave", 10),
        tab("YouTube Music", "https://music.youtube.com/", "chrome", 20),
    ]
    engine = engine_with(matches)
    result = engine.execute(TargetRequest("youtube", "close"))
    assert result.needs_clarification is True
    assert engine.executor.executed == []


def test_explicit_all_scope_closes_duplicate_targets_in_multiple_browsers():
    matches = [
        tab("YouTube", "https://youtube.com/", "brave", 10),
        tab("YouTube Music", "https://music.youtube.com/", "chrome", 20),
    ]
    engine = engine_with(matches)
    result = engine.execute(TargetRequest("youtube", "close", scope="all"))
    assert result.success and result.verified
    assert len(engine.executor.executed) == 2


def test_minimized_or_non_foreground_tab_uses_discovered_identity_not_active_state():
    target = tab("GitHub", "https://github.com/openai", "edge", 44, 5)
    target.metadata["window_state"] = "minimized"
    engine = engine_with([target])
    result = engine.execute(TargetRequest("github", "activate"))
    assert result.success
    assert engine.executor.executed[0][0] == "activate_tab"


def test_target_matcher_uses_domain_title_process_alias_and_container_without_unrelated_matches():
    matcher = TargetMatcher()
    candidates = [
        tab("Inbox - Gmail", "https://mail.google.com/mail/u/0/", "chrome"),
        tab("News", "https://example.com/youtube-review", "brave"),
        TargetCandidate(TargetKind.WINDOW, "spotify.exe", title="Spotify", process_name="Spotify.exe"),
    ]
    gmail = matcher.rank("gmail", candidates, "chrome")
    assert gmail[0].domain == "mail.google.com"
    spotify = matcher.rank("spotify", candidates)
    assert spotify[0].process_name == "Spotify.exe"
    assert not matcher.rank("youtube", [candidates[1]]) or matcher.rank("youtube", [candidates[1]])[0].confidence < 0.9


def test_open_in_specific_browser_forwards_container():
    engine = UniversalTargetDiscoveryEngine()
    engine.resolver = FakeResolver([])
    calls = []
    class FakePM:
        def execute_action(self, plugin, action, params):
            calls.append((plugin, action, params))
            return type("Res", (), {"success": True, "data": {"message": f"'{params.get('site')}' {params.get('browser', '').capitalize()} mein open kar diya."}})()
    engine.executor.plugin_manager = FakePM()
    result = engine.execute(TargetRequest("youtube", "open", container="brave"))
    assert result.success is True
    assert "Brave" in result.message
    assert calls[0] == ("browser", "open_website", {"site": "youtube", "browser": "brave", "container": "brave"})


def test_browser_plugin_direct_browser_launch(monkeypatch):
    import time
    from unittest.mock import MagicMock
    from plugins.browser.plugin import BrowserPlugin
    plugin = BrowserPlugin()
    plugin.connectivity._cached_status = True
    plugin.connectivity._last_checked = time.time()
    mock_popen = MagicMock()
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    res = plugin.execute("open_website", {"site": "youtube", "browser": "brave"})
    assert res.success is True
    assert "Brave" in res.data.get("message", "")
    assert mock_popen.called
    called_args = mock_popen.call_args[0][0]
    assert any("brave.exe" in arg.lower() for arg in called_args)
    assert "https://www.youtube.com/" in called_args

