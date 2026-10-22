# tests/test_outcome_verification_feature.py
"""
Comprehensive test suite for Feature #62: Outcome Verification (execution.verification).
Enforces the mandatory intelligence invariant:
User request -> Jarvis interpretation -> Action -> Actual system state -> Did it really succeed?

Decouples command completion from task success; observes real system state before claiming success.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.verifier import ExecutionVerificationLayer, get_execution_verifier
from plugins.windows.window_manager import WindowInfo, WindowState


@pytest.fixture
def mock_wm():
    """Mock WindowManager for controlling observed OS system state."""
    wm = MagicMock()
    wm.list_all_windows.return_value = []
    wm.find_windows_for_app.return_value = []
    wm.is_process_running.return_value = (False, [])
    wm.find_folder_windows.return_value = []
    return wm


@pytest.fixture
def verifier(mock_wm):
    """Configured ExecutionVerificationLayer instance with mock WindowManager."""
    return ExecutionVerificationLayer(window_manager=mock_wm)


class TestAuthoritativeOutcomeVerification:
    """Validates unified Outcome Verification (execution.verification) across all system targets."""

    # -------------------------------------------------------------------------
    # 1. Application Launch & Closure Verification
    # -------------------------------------------------------------------------
    def test_verify_outcome_application_launch_success(self, verifier, mock_wm):
        """Action 'launch_app' succeeds when process and window appear."""
        mock_wm.is_process_running.side_effect = lambda t: (True, [1234]) if "chrome" in t else (False, [])
        mock_wm.find_windows_for_app.side_effect = lambda t: [
            WindowInfo(hwnd=101, title="New Tab - Google Chrome", process_name="chrome.exe", pid=1234)
        ] if "chrome" in t else []

        res = verifier.verify_outcome(action="launch_app", target="chrome")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "app_running"
        assert res.expected is True
        assert res.actual is True

    def test_verify_outcome_application_launch_failure_when_not_running(self, verifier, mock_wm):
        """Action 'open_app' fails if process or window never appeared on OS."""
        mock_wm.is_process_running.return_value = (False, [])
        mock_wm.find_windows_for_app.return_value = []

        res = verifier.verify_outcome(action="open_app", target="calculator")
        assert res.verified is False
        assert res.state == ExecutionState.FAILED
        assert res.actual is False

    def test_verify_outcome_application_close_success(self, verifier, mock_wm):
        """Action 'close_app' succeeds when matching windows and processes are gone."""
        mock_wm.find_windows_for_app.return_value = []
        mock_wm.is_process_running.return_value = (False, [])

        res = verifier.verify_outcome(action="close_app", target="notepad")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "window_close"
        assert res.actual == "closed"

    def test_verify_outcome_application_close_failure_when_process_remains(self, verifier, mock_wm):
        """Action 'close_app' fails if process continues running in background."""
        mock_wm.find_windows_for_app.return_value = []
        mock_wm.is_process_running.return_value = (True, [9999])

        res = verifier.verify_outcome(action="close_app", target="notepad")
        assert res.verified is False
        assert res.state == ExecutionState.FAILED
        assert res.actual == "still_running"

    # -------------------------------------------------------------------------
    # 2. Browser & Website Operations Verification
    # -------------------------------------------------------------------------
    def test_verify_outcome_browser_website_open_title_match(self, verifier, mock_wm):
        """Action 'open_website' succeeds when browser window title contains target site."""
        mock_wm.list_all_windows.return_value = [
            WindowInfo(hwnd=202, title="YouTube - Google Chrome", process_name="chrome.exe", pid=4567)
        ]

        res = verifier.verify_outcome(action="open_website", target="youtube")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "browser_opened"
        assert "YouTube" in res.actual

    def test_verify_outcome_browser_website_open_new_window_count(self, verifier, mock_wm):
        """Action 'open_website' succeeds if open browser window count increased."""
        mock_wm.list_all_windows.return_value = [
            WindowInfo(hwnd=201, title="Brave", process_name="brave.exe", pid=1001),
            WindowInfo(hwnd=202, title="Brave (2)", process_name="brave.exe", pid=1002),
        ]

        # initial_window_count was 1, now 2 -> new window appeared
        res = verifier.verify_outcome(action="open_website", target="reddit", initial_window_count=1)
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS

    def test_verify_outcome_browser_website_open_fails_when_no_window_appears(self, verifier, mock_wm):
        """Action 'open_website' fails if browser window never appears."""
        mock_wm.list_all_windows.return_value = []

        res = verifier.verify_outcome(action="open_website", target="github", retries=1)
        assert res.verified is False
        assert res.state == ExecutionState.FAILED
        assert res.check_type == "browser_opened"

    # -------------------------------------------------------------------------
    # 3. Window State Changes Verification (Maximize / Minimize / Restore)
    # -------------------------------------------------------------------------
    def test_verify_outcome_window_state_maximize_with_hwnd(self, verifier, mock_wm):
        """Action 'maximize' verifies HWND state via WindowManager."""
        st = WindowState(hwnd=555, is_minimized=False, is_maximized=True, is_restored=False)
        mock_wm.capture_window_state.return_value = st

        res = verifier.verify_outcome(action="maximize", target="brave", hwnd=555)
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "window_maximized"
        assert res.actual == "maximized"

    def test_verify_outcome_window_state_minimize_with_hwnd(self, verifier, mock_wm):
        """Action 'minimize' verifies HWND minimized state."""
        st = WindowState(hwnd=555, is_minimized=True, is_maximized=False, is_restored=False)
        mock_wm.capture_window_state.return_value = st

        res = verifier.verify_outcome(action="minimize", target="brave", hwnd=555)
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "window_minimized"

    def test_verify_outcome_window_state_fails_when_state_mismatch(self, verifier, mock_wm):
        """Action 'maximize' fails if window is not maximized."""
        st = WindowState(hwnd=555, is_minimized=False, is_maximized=False, is_restored=True)
        mock_wm.capture_window_state.return_value = st

        res = verifier.verify_outcome(action="maximize", target="brave", hwnd=555, retries=1)
        assert res.verified is False
        assert res.state == ExecutionState.FAILED

    # -------------------------------------------------------------------------
    # 4. Folder & Explorer Operations Verification
    # -------------------------------------------------------------------------
    def test_verify_outcome_folder_open_success(self, verifier, mock_wm):
        """Action 'open_folder' succeeds when Explorer window for folder is found."""
        mock_wm.find_folder_windows.return_value = [
            {"hwnd": 777, "title": "Downloads", "url": "C:\\Users\\Admin\\Downloads"}
        ]

        res = verifier.verify_outcome(action="open_folder", target="Downloads")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "folder_window_open"
        assert "Downloads" in res.actual

    def test_verify_outcome_folder_close_success(self, verifier, mock_wm):
        """Action 'close_folder' succeeds when folder window is no longer present."""
        mock_wm.find_folder_windows.return_value = []

        res = verifier.verify_outcome(action="close_folder", target="Downloads")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.check_type == "folder_window_closed"

    # -------------------------------------------------------------------------
    # 5. Filesystem Operations Verification
    # -------------------------------------------------------------------------
    def test_verify_outcome_file_existence_and_content(self, verifier, tmp_path):
        """Action 'file_exists' and 'file_content' verify physical disk state."""
        test_file = tmp_path / "test_report.txt"
        test_file.write_text("Jarvis System Status: All Systems Operational", encoding="utf-8")

        # 1. File exists check
        res_exists = verifier.verify_outcome(action="file_exists", target=str(test_file))
        assert res_exists.verified is True
        assert res_exists.state == ExecutionState.SUCCESS

        # 2. File content check
        res_content = verifier.verify_outcome(
            action="file_content",
            target=str(test_file),
            expected_content="All Systems Operational"
        )
        assert res_content.verified is True
        assert res_content.state == ExecutionState.SUCCESS

        # 3. File content mismatch check
        res_mismatch = verifier.verify_outcome(
            action="file_content",
            target=str(test_file),
            expected_content="CRITICAL SYSTEM ERROR"
        )
        assert res_mismatch.verified is False
        assert res_mismatch.state == ExecutionState.FAILED

    # -------------------------------------------------------------------------
    # 6. System Settings & Hardware State Verification
    # -------------------------------------------------------------------------
    def test_verify_outcome_system_setting(self, verifier):
        """Action 'system_setting' verifies observable hardware/setting state."""
        fetcher_mock = MagicMock(return_value=75)

        res = verifier.verify_outcome(
            action="system_setting",
            target="master_volume",
            expected_value=75,
            actual_fetcher=fetcher_mock
        )
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
        assert res.actual == 75

        # Value mismatch
        fetcher_mock.return_value = 50
        res_mismatch = verifier.verify_outcome(
            action="system_setting",
            target="master_volume",
            expected_value=75,
            actual_fetcher=fetcher_mock
        )
        assert res_mismatch.verified is False
        assert res_mismatch.state == ExecutionState.FAILED

    # -------------------------------------------------------------------------
    # 7. Unverifiable Action Handling
    # -------------------------------------------------------------------------
    def test_verify_outcome_unverifiable_action_refuses_false_success(self, verifier):
        """Unverifiable action is honestly classified as UNVERIFIED, never false SUCCESS."""
        res = verifier.verify_outcome(action="arbitrary_unknown_hardware_signal", target="remote_device")
        assert res.verified is False
        assert res.state == ExecutionState.UNVERIFIED
        assert res.check_type == "unverifiable"

    # -------------------------------------------------------------------------
    # 8. Custom Verifier Hook
    # -------------------------------------------------------------------------
    def test_verify_outcome_custom_verifier_hook(self, verifier):
        """Custom verifiers registered at runtime are cleanly dispatched."""
        def custom_network_check(**kwargs):
            return VerificationResult(
                verified=True,
                state=ExecutionState.SUCCESS,
                check_type="custom_network",
                actual="connected",
                message="VPN tunnel is established."
            )

        verifier.register_custom_verifier("vpn_connect", custom_network_check)
        res = verifier.verify_outcome(action="vpn_connect", target="work_vpn")
        assert res.verified is True
        assert res.check_type == "custom_network"
        assert res.actual == "connected"


class TestAuthoritativeSingletonAccessor:
    """Validates that get_execution_verifier returns the authoritative runtime singleton."""

    def test_get_execution_verifier_singleton(self):
        v1 = get_execution_verifier()
        v2 = get_execution_verifier()
        assert v1 is v2
        assert isinstance(v1, ExecutionVerificationLayer)
