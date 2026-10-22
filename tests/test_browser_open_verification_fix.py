"""
Test Suite: Browser Open Verification Fix
Verifies that opening websites in specific browsers (Brave, Chrome, Edge, etc.)
does not report false failure ("browser mein khul nahi paya") when the browser
launches from 0 windows or opens with loading/transitional titles.
"""

import pytest
from unittest.mock import MagicMock, patch
from core.execution.verifier import ExecutionVerificationLayer
from core.execution.models import ExecutionState
from core.target_engine import UniversalTargetDiscoveryEngine, TargetRequest
from plugins.windows.window_manager import WindowInfo


class TestBrowserOpenVerificationFix:
    def test_verify_browser_opened_when_initial_window_count_is_zero(self):
        """
        When browser had 0 windows before launch (initial_window_count=0),
        and 1 new window appears with transitional title ('Untitled' or 'New Tab'),
        verification should succeed via Check 2 (new window count > 0).
        """
        wm_mock = MagicMock()
        # Brave launches and has 1 window with 'Untitled' title
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=1001, title="Untitled", process_name="brave.exe", pid=5001)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(
            site="youtube",
            browser="brave",
            initial_window_count=0,
            retries=1
        )

        assert result.verified is True
        assert result.state == ExecutionState.SUCCESS
        assert result.check_type == "browser_opened"
        assert result.details.get("browser") == "brave.exe"
        assert "open ho gaya" in result.message

    def test_verify_browser_opened_full_url_keyword_extraction(self):
        """
        When site is passed as a full URL ('https://www.youtube.com/'),
        the verifier extracts the keyword 'youtube' and matches window title 'YouTube - Brave'.
        """
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=1002, title="YouTube - Brave", process_name="brave.exe", pid=5002)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(
            site="https://www.youtube.com/",
            browser="brave",
            retries=1
        )

        assert result.verified is True
        assert result.state == ExecutionState.SUCCESS
        assert "YouTube - Brave" in result.actual

    def test_verify_browser_opened_delayed_title_update_detected(self):
        """
        When title is initially 'New Tab' and updates to 'YouTube' on attempt 2,
        the retry loop detects the updated title.
        """
        wm_mock = MagicMock()
        # Attempt 1: 'New Tab', Attempt 2: 'YouTube - Brave'
        wm_mock.list_all_windows.side_effect = [
            [WindowInfo(hwnd=1003, title="New Tab", process_name="brave.exe", pid=5003)],
            [WindowInfo(hwnd=1003, title="YouTube - Brave", process_name="brave.exe", pid=5003)]
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(
            site="youtube",
            browser="brave",
            initial_window_count=1,  # count didn't increase
            retries=3,
            delay_seconds=0.01
        )

        assert result.verified is True
        assert result.state == ExecutionState.SUCCESS
        assert "YouTube - Brave" in result.actual

    def test_verify_browser_opened_fails_when_no_browser_window_exists(self):
        """
        When no browser window is present (only Notepad open),
        verification must return False.
        """
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=2001, title="document.txt - Notepad", process_name="notepad.exe", pid=8001)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(
            site="youtube",
            browser="brave",
            initial_window_count=0,
            retries=1
        )

        assert result.verified is False
        assert result.state == ExecutionState.FAILED

    def test_target_engine_execute_open_youtube_in_brave_success(self):
        """
        Target engine execute('open youtube in brave') snapshots window count,
        invokes plugin, verifies the opened Brave window, and returns positive feedback.
        """
        wm_mock = MagicMock()
        current_windows = []
        wm_mock.list_all_windows.side_effect = lambda: list(current_windows)

        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        engine = UniversalTargetDiscoveryEngine(window_manager=wm_mock, verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"message": "'youtube' Brave mein open kar diya."}

        def simulate_browser_launch(plugin_name, action_name, params):
            current_windows.append(
                WindowInfo(hwnd=3001, title="Untitled", process_name="brave.exe", pid=9001)
            )
            return mock_result

        mock_plugin_mgr.execute_action.side_effect = simulate_browser_launch
        engine.executor.plugin_manager = mock_plugin_mgr

        request = TargetRequest(target="youtube", action="open", container="brave")
        outcome = engine.execute(request)

        assert outcome.success is True
        assert outcome.verified is True
        assert "khul nahi paya" not in outcome.message
        assert "open kar diya" in outcome.message
