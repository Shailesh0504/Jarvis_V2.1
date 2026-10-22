# tests/test_universal_verification_layer.py
"""
Universal Action Verification Layer regression tests for Jarvis V2.1.
Enforces the mandatory rule:
Jarvis must NEVER claim that an action succeeded only because a command/process returned successfully.
'Command executed' and 'Action completed' are different states.
Verification must observe actual system state before reporting success.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.strategies import ExecutionStrategyEngine
from core.execution.verifier import ExecutionVerificationLayer
from core.target_engine import ActionOutcome, TargetRequest, UniversalTargetDiscoveryEngine
from plugins.windows.window_manager import WindowInfo


@pytest.fixture
def core_app(tmp_path):
    """Creates a configured JarvisCore test harness."""
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_univ_verif.db")
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
        response_generator=resp_gen,
    )
    return core


class TestUniversalActionVerificationLayer:
    """Comprehensive test suite for Universal Action Verification Layer."""

    # -------------------------------------------------------------------------
    # 1. Browser Opened Verification Unit Tests
    # -------------------------------------------------------------------------

    def test_verify_browser_opened_success_on_window_title_match(self):
        """Browser window with site in title confirms browser opened successfully."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=101, title="YouTube - Google Chrome", process_name="chrome.exe", pid=1234)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(site="youtube", browser="chrome", retries=1)

        assert result.verified is True
        assert result.state == ExecutionState.SUCCESS
        assert result.check_type == "browser_opened"
        assert result.details.get("hwnd") == 101

    def test_verify_browser_opened_fails_when_window_does_not_appear(self):
        """If browser process or window does not appear, verification returns False."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=202, title="Untitled - Notepad", process_name="notepad.exe", pid=5678)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        result = verifier.verify_browser_opened(site="youtube", browser="chrome", retries=1)

        assert result.verified is False
        assert result.state == ExecutionState.FAILED
        assert result.check_type == "browser_opened"

    def test_verify_browser_opened_success_on_new_window_count(self):
        """Even if title is not yet updated, increased browser window count confirms launch."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=301, title="New Tab - Brave", process_name="brave.exe", pid=9991),
            WindowInfo(hwnd=302, title="Brave", process_name="brave.exe", pid=9992),
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        # initial_window_count was 1, now 2 -> confirmed new window
        result = verifier.verify_browser_opened(
            site="flipkart", browser="brave", initial_window_count=1, retries=1
        )

        assert result.verified is True
        assert result.state == ExecutionState.SUCCESS

    # -------------------------------------------------------------------------
    # 2. Strategy Engine Verified Operations
    # -------------------------------------------------------------------------

    def test_open_website_verified_success(self):
        """open_website_verified succeeds and verifies when browser window opens."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=401, title="GitHub - Brave", process_name="brave.exe", pid=4444)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        engine = ExecutionStrategyEngine(verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"message": "Opened github in Brave"}
        mock_plugin_mgr.execute_action.return_value = mock_result

        exec_res = engine.open_website_verified(
            site="github", browser="brave", plugin_manager=mock_plugin_mgr, max_retries=1
        )

        assert exec_res.success is True
        assert exec_res.status == ExecutionState.SUCCESS
        assert exec_res.verification_result.verified is True

    def test_open_website_verified_is_unverified_when_window_cannot_be_observed(self):
        """A browser acknowledgement is successful even when observation is unavailable."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = []
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        engine = ExecutionStrategyEngine(verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True  # Plugin claimed success!
        mock_plugin_mgr.execute_action.return_value = mock_result

        exec_res = engine.open_website_verified(
            site="netflix", browser="chrome", plugin_manager=mock_plugin_mgr, max_retries=2
        )

        assert exec_res.success is True
        assert exec_res.status == ExecutionState.UNVERIFIED
        assert exec_res.verification_result.verified is False
        assert exec_res.data["status"] == "opened"
        assert exec_res.data["verification"] == "unknown"

    def test_close_target_verified_success(self):
        """close_target_verified confirms app is not running after close."""
        wm_mock = MagicMock()
        wm_mock.find_windows_for_app.return_value = []
        wm_mock.is_process_running.return_value = (False, [])
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        engine = ExecutionStrategyEngine(verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True
        mock_plugin_mgr.execute_action.return_value = mock_res

        exec_res = engine.close_target_verified(
            target="notepad", action="close", plugin_manager=mock_plugin_mgr
        )

        assert exec_res.success is True
        assert exec_res.verification_result.verified is True

    def test_close_target_verified_fails_if_still_running(self):
        """close_target_verified fails if window/process still exists post-close."""
        wm_mock = MagicMock()
        # Still running!
        wm_mock.find_windows_for_app.return_value = [
            WindowInfo(hwnd=501, title="Document - Notepad", process_name="notepad.exe", pid=777)
        ]
        wm_mock.is_process_running.return_value = (True, [777])
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        engine = ExecutionStrategyEngine(verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True  # Close command claimed success
        mock_plugin_mgr.execute_action.return_value = mock_res

        exec_res = engine.close_target_verified(
            target="notepad", action="close", plugin_manager=mock_plugin_mgr, max_retries=1
        )

        assert exec_res.success is False
        assert exec_res.status == ExecutionState.FAILED
        assert exec_res.verification_result.verified is False

    # -------------------------------------------------------------------------
    # 3. Target Engine Verification Integration
    # -------------------------------------------------------------------------

    def test_target_engine_rejects_unverified_browser_open(self):
        """Target engine execute refuses to claim success if verifier rejects browser window."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = []  # No browser window
        wm_mock.is_process_running.return_value = (False, [])
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        engine = UniversalTargetDiscoveryEngine(window_manager=wm_mock, verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True  # Plugin said success
        mock_plugin_mgr.execute_action.return_value = mock_res
        engine.executor.plugin_manager = mock_plugin_mgr

        outcome = engine.execute(TargetRequest(target="spotify", action="open"))

        # Invariant: Command succeeded, but action NOT completed -> verified=False, success=False
        assert outcome.success is False
        assert outcome.verified is False
        assert "browser mein khul nahi paya" in outcome.message

    def test_target_engine_accepts_verified_browser_open(self):
        """Target engine execute claims success only when verifier confirms browser window."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = [
            WindowInfo(hwnd=601, title="Spotify - Web Player", process_name="chrome.exe", pid=888)
        ]
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        engine = UniversalTargetDiscoveryEngine(window_manager=wm_mock, verifier=verifier)

        mock_plugin_mgr = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True
        mock_res.data = {"message": "Spotify open kar diya."}
        mock_plugin_mgr.execute_action.return_value = mock_res
        engine.executor.plugin_manager = mock_plugin_mgr

        outcome = engine.execute(TargetRequest(target="spotify", action="open"))

        assert outcome.success is True
        assert outcome.verified is True
        assert "spotify" in outcome.message.lower()

    # -------------------------------------------------------------------------
    # 4. End-to-End Core Verification & Natural Responses
    # -------------------------------------------------------------------------

    def test_app_launch_natural_hinglish_success_response(self, core_app):
        """App launch generates natural Hinglish response instead of 'Launched X successfully'."""
        wm_mock = MagicMock()
        wm_mock.find_windows_for_app.return_value = [
            WindowInfo(hwnd=701, title="Camera", process_name="WindowsCamera.exe", pid=333)
        ]
        wm_mock.is_process_running.return_value = (True, [333])
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("subprocess.Popen"):
            resp = core_app.process_input("open camera")

        assert "Camera open ho gaya, Boss." in resp or "open ho gaya" in resp
        assert "Launched 'camera' successfully" not in resp

    def test_browser_open_command_unverified_does_not_report_a_false_failure(self, core_app):
        """A missing browser observation is not evidence that navigation failed."""
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = []  # No browser window
        wm_mock.is_process_running.return_value = (False, [])
        core_app.target_engine.window_manager = wm_mock
        core_app.target_engine.verifier.window_manager = wm_mock

        with patch("webbrowser.open", return_value=True):
            resp = core_app.process_input("open youtube")

        assert "khul nahi paya" not in resp
        assert core_app.last_execution_result is not None
        assert core_app.last_execution_result.success is True

    def test_close_calc_verified_success_and_natural_response(self, core_app):
        """Closing Calculator ('close calc') correctly verifies closed window and avoids false failure."""
        wm_mock = MagicMock()
        # No matching windows remain (window is closed)
        wm_mock.find_windows_for_app.return_value = []
        # UWP background broker or suspended process might still be running
        wm_mock.is_process_running.return_value = (True, [9999])
        core_app.target_engine.window_manager = wm_mock
        core_app.target_engine.verifier.window_manager = wm_mock
        core_app.execution_strategies.verifier.window_manager = wm_mock

        v_res = core_app.execution_strategies.verifier.verify_window_operation("calc", "close", hwnd=12345)
        assert v_res.verified is True
        assert "Calculator" in v_res.message
        assert "band ho gaya" in v_res.message
        assert "band nahi ho paya" not in v_res.message

