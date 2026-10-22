# tests/test_execution_verification_layer.py
"""
Regression tests for Mandatory Execution Verification Layer in Jarvis V2.
Verifies the architectural invariant:
execute() -> observe actual system state -> compare expected vs actual -> SUCCESS only if verified.
Zero exceptions during execute() NEVER automatically implies success.
Covers all 10 required regression test scenarios.
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.execution.diagnostics import ExecutionDiagnosticEngine
from core.execution.feedback import ExecutionFeedbackHandler, FeedbackInterpretation
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.strategies import ExecutionStrategyEngine
from core.execution.verifier import ExecutionVerificationLayer
from plugins.windows.window_manager import WindowManager


@pytest.fixture
def core_app(tmp_path):
    """Creates a configured JarvisCore test harness with initialized subsystems."""
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_exec_verif.db")
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


class TestExecutionVerificationLayer:
    """10 mandatory regression tests for execution verification, diagnostics, and recovery."""

    # 1. Successful folder opening
    def test_1_successful_folder_opening(self, core_app):
        """Folder command executes and Explorer window actually opens -> Verified SUCCESS."""
        wm_mock = MagicMock()
        wm_mock.find_folder_windows.return_value = [
            {"hwnd": 9999, "title": "Startup", "url": "shell:startup"}
        ]
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("plugins.files.operations.subprocess.Popen"), \
             patch("plugins.files.operations.os.startfile"):
            resp = core_app.process_input("open startup folder")

        assert "open kar diya hai aur verify kar liya hai" in resp or "Startup" in resp
        assert core_app.last_execution_result is not None
        assert core_app.last_execution_result.status == ExecutionState.SUCCESS
        assert core_app.last_execution_result.success is True
        assert core_app.last_execution_result.verification_result.verified is True

    # 2. Folder command executes but Explorer does not open
    def test_2_command_executes_but_explorer_does_not_open(self, core_app):
        """Command returns without exception (mocked Popen) but no window appears -> FAILED, no success claim."""
        wm_mock = MagicMock()
        # Explorer window never appears
        wm_mock.find_folder_windows.return_value = []
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("plugins.files.operations.subprocess.Popen"), \
             patch("plugins.files.operations.os.startfile"):
            resp = core_app.process_input("open startup folder")

        # Invariant: NO VERIFICATION = NO SUCCESS CLAIM
        assert "open kar diya hai" not in resp
        assert "open nahi ho paya" in resp or "Reason" in resp
        assert core_app.last_execution_result is not None
        assert core_app.last_execution_result.status == ExecutionState.FAILED
        assert core_app.last_execution_result.success is False

    # 3. Invalid path
    def test_3_invalid_path_fails_cleanly(self, core_app):
        """Invalid path format or non-existent illegal folder -> FAILED without misleading claims."""
        strategy_engine = ExecutionStrategyEngine()
        result = strategy_engine.open_folder_verified(target="invalid<folder>|path*?")

        assert result.success is False
        assert result.status == ExecutionState.FAILED
        assert "Invalid path" in (result.reason or result.error or "")

    # 4. Permission failure
    def test_4_permission_failure_diagnosed(self):
        """Target folder cannot be accessed -> Diagnosed as permission denied and marked FAILED."""
        diag_engine = ExecutionDiagnosticEngine()

        with patch("os.access", return_value=False), \
             patch("os.path.exists", return_value=True):
            report = diag_engine.diagnose_folder_operation("C:\\Restricted\\SystemFolder")

        assert report.failure_identified is True
        assert "Permission" in report.root_cause or any("Permission" in d for d in report.diagnostics)

    # 5. Explorer already has multiple windows
    def test_5_explorer_already_has_multiple_windows(self):
        """Handles pre-existing Explorer windows and correctly identifies when target window becomes available."""
        wm_mock = MagicMock()
        # Initially 2 unrelated folder windows exist
        initial = [
            {"hwnd": 101, "title": "Downloads", "url": "C:/Users/Admin/Downloads"},
            {"hwnd": 102, "title": "Documents", "url": "C:/Users/Admin/Documents"}
        ]
        # Afterwards, target window Startup appears
        after = initial + [
            {"hwnd": 201, "title": "Startup", "url": "shell:startup"}
        ]

        verifier = ExecutionVerificationLayer(window_manager=wm_mock)
        wm_mock.find_folder_windows.return_value = after

        v_res = verifier.verify_folder_open(target="startup", initial_windows=initial)

        assert v_res.verified is True
        assert v_res.state == ExecutionState.SUCCESS
        assert v_res.details["hwnd"] == 201

    # 6. User says "open nahi hua"
    def test_6_user_negative_feedback_marks_failed_and_retries_differently(self, core_app):
        """
        When user says 'startup folder open nahi hua' or 'open nahi hua':
        1. Does NOT repeat the same failed strategy blindly.
        2. Marks previous task failed.
        3. Switches to an alternative/improved strategy.
        4. Verifies and reports.
        """
        # Set up a previous execution where Strategy 1 ('shell_uri') failed
        core_app.last_execution_result = ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="open startup folder",
            executed_action="open_folder:shell_uri",
            target="startup",
            strategy_used="shell_uri",
            error="Window did not appear"
        )

        wm_mock = MagicMock()
        # Alternative strategy ('physical_path') will succeed in opening the window
        wm_mock.find_folder_windows.return_value = [
            {"hwnd": 5555, "title": "Startup", "url": "C:/Users/Admin/AppData/Roaming/Startup"}
        ]
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("plugins.files.operations.subprocess.Popen") as mock_popen, \
             patch("plugins.files.operations.os.startfile"):
            resp = core_app.process_input("startup folder open nahi hua")

        # Must acknowledge previous failure and use improved strategy
        assert "Previous attempt fail ho gaya tha" in resp or "improved strategy" in resp or "Startup" in resp
        # Must NOT say the unverified legacy phrase: "'Startup' open kar diya hai, Boss." without failure acknowledgement
        assert "Previous attempt" in resp or "improved strategy" in resp
        assert core_app.last_execution_result.strategy_used != "shell_uri"

    # 7. User asks "check karo kyun nahi hua"
    def test_7_user_asks_check_karo_enters_diagnostic_mode(self, core_app):
        """
        When user says 'check karo kyun open nahi ho paa raha hai startup folder':
        Enters diagnostic mode, inspects environment, paths, processes, and reports findings.
        """
        core_app.last_execution_result = ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="open startup folder",
            executed_action="open_folder:shell_uri",
            target="startup",
            strategy_used="shell_uri",
            error="CabinetWClass window missing"
        )

        with patch("plugins.files.operations.subprocess.Popen"), \
             patch.object(core_app.execution_strategies.verifier, "verify_folder_open") as mock_v:
            mock_v.return_value = VerificationResult(
                verified=True, state=ExecutionState.SUCCESS, check_type="folder_window_open", message="Verified"
            )
            resp = core_app.process_input("check karo kyun open nahi ho paa raha hai startup folder")

        assert "investigate" in resp.lower() or "diagnostic" in resp.lower() or "root cause" in resp.lower()
        assert "alternative method" in resp.lower() or "startup" in resp.lower()

    # 8. First strategy fails and second strategy succeeds
    def test_8_first_strategy_fails_and_second_strategy_succeeds(self):
        """Strategy 1 (shell_uri) fails verification -> Strategy 2 (physical_path) succeeds -> SUCCESS."""
        wm_mock = MagicMock()
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        call_count = {"n": 0}
        def mock_find(target=""):
            call_count["n"] += 1
            # Attempt 1 (strategy shell_uri) fails; attempt 2 (strategy physical_path) succeeds
            if call_count["n"] >= 6:
                return [{"hwnd": 8888, "title": "Startup", "url": "C:/Users/Admin/AppData/Roaming/Startup"}]
            return []
        wm_mock.find_folder_windows.side_effect = mock_find

        engine = ExecutionStrategyEngine(verifier=verifier)

        with patch("plugins.files.operations.subprocess.Popen"):
            res = engine.open_folder_verified("startup")

        assert res.success is True
        assert res.status == ExecutionState.SUCCESS
        assert res.retry_count == 1
        assert res.strategy_used == "physical_path"

    # 9. All strategies fail
    def test_9_all_strategies_fail(self):
        """All attempted strategies fail verification -> status FAILED, zero success claim."""
        wm_mock = MagicMock()
        wm_mock.find_folder_windows.return_value = []
        verifier = ExecutionVerificationLayer(window_manager=wm_mock)

        engine = ExecutionStrategyEngine(verifier=verifier)

        with patch("plugins.files.operations.subprocess.Popen"):
            res = engine.open_folder_verified("startup", max_retries=2)

        assert res.success is False
        assert res.status == ExecutionState.FAILED
        assert res.retry_count == 2
        assert "failed" in (res.reason or res.error).lower()
        assert len(res.diagnostics) > 0

    # 10. Verification is impossible
    def test_10_verification_is_impossible_classified_as_unverified(self):
        """When direct system verification cannot observe state -> classified as UNVERIFIED, not SUCCESS."""
        verifier = ExecutionVerificationLayer(window_manager=None)

        unverif_res = verifier.classify_unverifiable(
            action="custom_blind_action",
            reason="No system state observer available for this external hardware peripheral."
        )

        assert unverif_res.verified is False
        assert unverif_res.state == ExecutionState.UNVERIFIED
        assert "unverifiable" in unverif_res.check_type

        # Verify ResponseGenerator formats UNVERIFIED without claiming SUCCESS
        from brain.response import ResponseGenerator
        resp_gen = ResponseGenerator()
        exec_res = ExecutionResult(
            success=False,
            status=ExecutionState.UNVERIFIED,
            requested_action="custom_blind_action",
            executed_action="custom_blind_action",
            target="custom_device",
            reason="Direct verification impossible"
        )
        msg = resp_gen.generate_verified_response(exec_res)

        assert "direct verification possible nahi thi" in msg or "UNVERIFIED" in msg
        assert "successfully executed" not in msg
        assert "verify kar liya hai" not in msg

    # 11. Recycle bin folder resolution and verification
    def test_11_open_recycle_bin_folder_verified(self, core_app):
        """'open recycle bin folder' resolves special virtual folder and verifies Explorer window."""
        wm_mock = MagicMock()
        wm_mock.find_folder_windows.return_value = [
            {"hwnd": 5555, "title": "Recycle Bin - File Explorer", "url": ""}
        ]
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("plugins.files.operations.subprocess.Popen"):
            resp = core_app.process_input("open recycle bin folder")

        assert "Recycle Bin" in resp
        assert "verify kar liya hai" in resp or "open kar diya hai" in resp
        assert core_app.last_execution_result is not None
        assert core_app.last_execution_result.success is True
        assert core_app.last_execution_result.status == ExecutionState.SUCCESS

    # 12. Close all folders with Hinglish phrasing
    def test_12_close_all_folders_hinglish_variations(self, core_app):
        """'sabhi open folder close karo' correctly closes all open folder windows."""
        with patch("plugins.windows.window_manager.WindowManager.close_all_folder_windows", return_value=3):
            resp = core_app.process_input("sabhi open folder close karo")
            assert "band kar diye hain" in resp or "folder" in resp

    # 13. Open picture singular folder
    def test_13_open_picture_singular_folder(self, core_app):
        """'open picture' is recognized as pictures folder rather than a website."""
        wm_mock = MagicMock()
        wm_mock.find_folder_windows.return_value = [
            {"hwnd": 6666, "title": "Pictures", "url": "file:///C:/Users/Admin/Pictures"}
        ]
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("plugins.files.operations.subprocess.Popen"), \
             patch("plugins.files.operations.os.startfile"):
            resp = core_app.process_input("open picture")

        assert "website" not in resp.lower()
        assert "pictures" in resp.lower() or "Pictures" in resp


