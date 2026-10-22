# tests/test_browser_container_activities.py
"""
Tests for Feature 55: Browser-Contained Activities and Targeted Tab Resolution.
Verifies that phrases targeting activities/tabs within a browser container
(e.g., 'chrome wala youtube band kar do', 'brave me netflix band karo')
correctly bind the container browser, close only the target tab without
terminating the browser application process, and return natural feedback.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.semantic.parsers.windows import parse_universal_target_action, parse_app_close
from core.semantic.multi_entity import get_multi_entity_parser
from core.target_engine import (
    ActionOutcome,
    TargetCandidate,
    TargetKind,
    TargetRequest,
    UniversalTargetDiscoveryEngine,
)


class TestBrowserContainedParsing:
    """Test NLU parsing and container binding for browser activities."""

    @pytest.mark.parametrize("query,expected_target,expected_container,expected_action", [
        ("chrome wala youtube band kar do", "youtube", "chrome", "close"),
        ("chrome ka youtube band kar do", "youtube", "chrome", "close"),
        ("chrome me youtube band kar do", "youtube", "chrome", "close"),
        ("chrome mein youtube band karo", "youtube", "chrome", "close"),
        ("brave wala youtube band karo", "youtube", "brave", "close"),
        ("brave me chatgpt band kar do", "chatgpt", "brave", "close"),
        ("close youtube in chrome", "youtube", "chrome", "close"),
        ("close chatgpt on brave", "chatgpt", "brave", "close"),
        ("youtube chrome wala band karo", "youtube", "chrome", "close"),
        ("chrome wala youtube kholo", "youtube", "chrome", "open"),
        ("brave me flipkart open karo", "flipkart", "brave", "open"),
    ])
    def test_universal_target_action_container_binding(self, query, expected_target, expected_container, expected_action):
        action = parse_universal_target_action(query, query.lower())
        assert action is not None, f"Failed to parse query: {query}"
        assert action.intent == "UNIVERSAL_TARGET_ACTION"
        assert action.parameters.get("target") == expected_target
        assert action.parameters.get("container") == expected_container
        assert action.parameters.get("action") == expected_action

    def test_app_close_guard_prevents_closing_browser_for_contained_activity(self):
        """Phrases like 'chrome wala youtube band kar do' must never trigger WINDOW_CLOSE on Chrome."""
        assert parse_app_close("chrome wala youtube band kar do", "chrome wala youtube band kar do") is None
        assert parse_app_close("chrome me youtube band karo", "chrome me youtube band karo") is None
        assert parse_app_close("close youtube in chrome", "close youtube in chrome") is None
        assert parse_app_close("brave wala tab band karo", "brave wala tab band karo") is None

    def test_app_close_still_closes_standalone_browser_app(self):
        """Preserve existing behavior: 'chrome band karo' or 'close chrome' MUST close the Chrome application."""
        action = parse_app_close("chrome band karo", "chrome band karo")
        assert action is not None
        assert action.intent == "WINDOW_CLOSE"
        assert action.parameters.get("app_name") == "chrome"

        action_close = parse_app_close("close chrome", "close chrome")
        assert action_close is not None
        assert action_close.intent == "WINDOW_CLOSE"

    def test_multi_entity_parser_container_binding(self):
        """Single-container phrase returns None from multi_entity_parser (falls to single-action pipeline)."""
        parser = get_multi_entity_parser()
        plan = parser.parse("chrome wala youtube band kar do")
        # Since 'chrome' is bound as container for 'youtube', there is only 1 independent target, so plan is None
        assert plan is None

    def test_multi_entity_parser_with_multiple_containers(self):
        """Multiple containerized targets are parsed as independent actions without standalone browser items."""
        parser = get_multi_entity_parser()
        plan = parser.parse("chrome wala youtube aur brave wala netflix band kar do")
        assert plan is not None
        assert len(plan.actions) == 2
        assert plan.actions[0].target == "youtube"
        assert plan.actions[0].container == "chrome"
        assert plan.actions[0].action == "close"
        assert plan.actions[1].target == "netflix"
        assert plan.actions[1].container == "brave"
        assert plan.actions[1].action == "close"


class TestTargetEngineContainerExecution:
    """Test TargetEngine tab closing, non-destruction of browser process, and natural feedback."""

    def test_target_engine_closes_tab_and_reports_container(self):
        engine = UniversalTargetDiscoveryEngine()
        yt_tab = TargetCandidate(
            TargetKind.BROWSER_TAB,
            "YouTube - Google Chrome",
            "youtube",
            hwnd=12345,
            process_name="chrome.exe",
            browser="chrome",
            tab_index=1,
        )

        with patch.object(engine.resolver, "resolve", return_value=[yt_tab]), \
             patch.object(engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
             patch.object(engine.window_manager, "execute_operation") as mock_win_op:

            req = TargetRequest(target="youtube", action="close", container="chrome")
            outcome = engine.execute(req)

            assert outcome.success is True
            assert mock_tab_action.called
            # Window manager close must NOT be called to kill the browser process
            mock_win_op.assert_not_called()
            assert "Chrome mein YouTube band kar diya, Boss." in outcome.message

    def test_target_engine_container_not_found_does_not_kill_browser(self):
        engine = UniversalTargetDiscoveryEngine()

        with patch.object(engine.resolver, "resolve", return_value=[]), \
             patch.object(engine.window_manager, "execute_operation") as mock_win_op:

            req = TargetRequest(target="youtube", action="close", container="chrome")
            outcome = engine.execute(req)

            assert outcome.success is False
            mock_win_op.assert_not_called()
            assert "Chrome mein 'youtube' open nahi mila, Boss." in outcome.message


@pytest.fixture
def core_app(tmp_path):
    from core.app import JarvisCore
    from memory.memory_manager import MemoryManager
    from brain.response import ResponseGenerator
    from brain.llm import MockLLMProvider
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_container_app.db")
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


class TestEndToEndBrowserContainerActivities:
    """End-to-end pipeline tests verifying user's exact query and natural feedback."""

    def test_e2e_chrome_wala_youtube_band_kar_do_closes_tab_not_browser(self, core_app):
        """User command 'chrome wala youtube band kar do' closes only YouTube tab and gives targeted confirmation."""
        yt_tab = TargetCandidate(
            TargetKind.BROWSER_TAB,
            "YouTube - Google Chrome",
            "youtube",
            hwnd=12345,
            process_name="chrome.exe",
            browser="chrome",
            tab_index=1,
        )

        with patch.object(core_app.target_engine.resolver, "resolve", return_value=[yt_tab]), \
             patch.object(core_app.target_engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
             patch.object(core_app.target_engine.window_manager, "execute_operation") as mock_win_op:

            resp = core_app.process_input("chrome wala youtube band kar do")
            assert mock_tab_action.called
            mock_win_op.assert_not_called()
            assert "Chrome mein YouTube band kar diya" in resp
            # Must never say Chrome aur YouTube band ho gaye
            assert "Chrome aur YouTube band ho gaye" not in resp

    def test_e2e_chrome_wala_youtube_band_kar_do_not_found(self, core_app):
        """When YouTube tab is not open in Chrome, informs user without closing Chrome."""
        with patch.object(core_app.target_engine.resolver, "resolve", return_value=[]), \
             patch.object(core_app.target_engine.window_manager, "execute_operation") as mock_win_op:

            resp = core_app.process_input("chrome wala youtube band kar do")
            mock_win_op.assert_not_called()
            assert "Chrome mein 'youtube' open nahi mila" in resp
            assert "Chrome aur YouTube band ho gaye" not in resp

