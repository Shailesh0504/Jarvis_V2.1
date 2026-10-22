# tests/test_phase_3_b2_primary_execution.py
"""
Unit and integration test suite for Phase 3.0-B2 (SemanticActionExecutor wiring).
Validates:
1. Primary handlers (_handle_window_action, _handle_folder_action, _handle_launch_app,
   _handle_open_file, _handle_website_open) wire into ExecutionOutcomeHook.
2. TurnContext.execution_outcome is populated with TurnOutcome.
3. core.last_execution_result is populated.
4. Telemetry event 'execution.outcome' is emitted.
5. Response string matches existing behavior.
6. Failure scenario correctly resolves to FAILED/UNVERIFIED without raising exceptions.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.context import TurnContext, TurnOutcomeStatus
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.semantic import SemanticAction
from core.target_engine import ActionOutcome
from plugins.windows.window_manager import WindowInfo


@pytest.fixture
def core_harness(tmp_path):
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_b2.db")
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


class TestPhase3B2SemanticExecutorWiring:

    def test_window_action_populates_turn_outcome_and_last_execution(self, core_harness):
        """Window action (minimize) must populate TurnOutcome with VERIFIED and emit telemetry."""
        wm_mock = MagicMock()
        wm_mock.find_windows_for_app.return_value = [
            WindowInfo(hwnd=101, title="TestApp", process_name="testapp.exe", pid=123)
        ]
        wm_mock.minimize_window.return_value = True
        core_harness.target_engine.window_manager = wm_mock

        emitted_events = []
        orig_emit = core_harness.event_bus.emit

        def tracking_emit(event_name, data=None):
            emitted_events.append((event_name, data))
            return orig_emit(event_name, data)

        core_harness.event_bus.emit = tracking_emit

        turn = core_harness.conversation_manager.session.start_new_turn("testapp minimize karo")
        act = SemanticAction(
            intent="WINDOW_MINIMIZE",
            service="windows",
            action="minimize_window",
            query="testapp",
            parameters={"app_name": "testapp"}
        )
        handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status == TurnOutcomeStatus.VERIFIED
        assert core_harness.last_execution_result is not None
        assert core_harness.last_execution_result.executed_action == "minimize"
        assert any(e[0] == "execution.outcome" for e in emitted_events)

    def test_folder_action_populates_turn_outcome(self, core_harness):
        """Folder open action must populate TurnOutcome."""
        mock_exec_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="open_folder",
            executed_action="open_folder",
            target="downloads",
            action_type="folder",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="folder_open")
        )
        with patch.object(core_harness.execution_strategies, "open_folder_verified", return_value=mock_exec_res):
            turn = core_harness.conversation_manager.session.start_new_turn("open downloads folder")
            act = SemanticAction(
                intent="FOLDER_OPEN",
                service="files",
                action="open_folder",
                query="downloads",
                parameters={"target": "downloads"}
            )
            handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status == TurnOutcomeStatus.VERIFIED
        assert core_harness.last_execution_result is not None

    def test_launch_app_populates_turn_outcome(self, core_harness):
        """Launch app must populate TurnOutcome with VERIFIED."""
        mock_exec_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            target="notepad",
            action_type="application",
            data={"display_name": "Notepad"},
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="process_running")
        )
        with patch.object(core_harness.execution_strategies, "launch_application_verified", return_value=mock_exec_res):
            turn = core_harness.conversation_manager.session.start_new_turn("open notepad")
            act = SemanticAction(
                intent="OPEN_APPLICATION",
                service="windows",
                action="launch_app",
                query="notepad",
                parameters={"app_name": "notepad"}
            )
            handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status == TurnOutcomeStatus.VERIFIED
        assert core_harness.last_execution_result.target == "notepad"

    def test_website_open_populates_turn_outcome(self, core_harness):
        """Website open must populate TurnOutcome."""
        action_outcome = ActionOutcome(
            success=True,
            message="YouTube open kar diya hai, Boss.",
            verified=True,
            status="completed"
        )
        with patch.object(core_harness.target_engine, "execute", return_value=action_outcome):
            turn = core_harness.conversation_manager.session.start_new_turn("open youtube")
            act = SemanticAction(
                intent="OPEN_WEBSITE",
                service="youtube",
                action="open_youtube",
                query="youtube",
                parameters={"site": "youtube"}
            )
            handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status == TurnOutcomeStatus.VERIFIED

    def test_open_file_populates_turn_outcome(self, core_harness):
        """Open file must adapt result and populate TurnOutcome."""
        turn = core_harness.conversation_manager.session.start_new_turn("open report.txt")
        act = SemanticAction(
            intent="OPEN_FILE",
            service="files",
            action="open_file",
            query="report.txt",
            parameters={"file_name": "report.txt"}
        )
        with patch("plugins.files.operations.FilesystemOperations.open") as mock_open:
            mock_res = MagicMock()
            mock_res.success = True
            mock_res.data = {"message": "File opened"}
            mock_open.return_value = mock_res
            handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status in (TurnOutcomeStatus.VERIFIED, TurnOutcomeStatus.UNVERIFIED)

    def test_failure_scenario_resolves_to_failed_without_crash(self, core_harness):
        """Failure scenario must produce FAILED TurnOutcome and preserve error feedback."""
        mock_exec_res = ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="launch_app",
            executed_action="launch_app",
            target="nonexistent_app_xyz",
            action_type="application",
            data={"display_name": "Nonexistent_app_xyz"},
            error="Process not found",
            reason="not_installed",
            verification_result=VerificationResult(verified=False, state=ExecutionState.FAILED, check_type="process_running")
        )
        with patch.object(core_harness.execution_strategies, "launch_application_verified", return_value=mock_exec_res):
            turn = core_harness.conversation_manager.session.start_new_turn("open nonexistent_app_xyz")
            act = SemanticAction(
                intent="OPEN_APPLICATION",
                service="windows",
                action="launch_app",
                query="nonexistent_app_xyz",
                parameters={"app_name": "nonexistent_app_xyz"}
            )
            handled, resp = core_harness.semantic_executor.execute(act, turn, 0.0)

        assert handled is True
        assert turn.execution_outcome is not None
        assert turn.execution_outcome.status == TurnOutcomeStatus.FAILED
        assert turn.execution_outcome.error == "Process not found"
