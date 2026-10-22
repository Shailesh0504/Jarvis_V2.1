# tests/test_multi_entity_commands.py
"""
Comprehensive regression test suite for Natural Multi-Entity Commands in Jarvis V2.1.
Validates:
- Multi-Entity / Multi-Action parsing
- Global action inheritance (open, close, minimize, maximize)
- Entity boundary and adjacent known entity discovery
- Independent context & preference resolution per entity
- Sequential verified execution with honest response synthesis
- Strict backward compatibility for single-entity commands
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.multi_executor import MultiActionExecutor
from core.semantic.multi_entity import ActionItem, MultiActionPlan, MultiEntityCommandParser, get_multi_entity_parser
from plugins.windows.window_manager import WindowInfo


@pytest.fixture
def core_app(tmp_path):
    """Creates a configured JarvisCore test harness."""
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    db_path = str(tmp_path / "test_multi_entity.db")
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


class TestMultiEntityParser:
    """Unit tests for MultiEntityCommandParser."""

    @pytest.fixture
    def parser(self):
        return get_multi_entity_parser()

    def test_1_adjacent_entities_without_conjunctions(self, parser):
        """User: 'open excel chrome brave word' -> 4 actions."""
        plan = parser.parse("open excel chrome brave word")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 4
        targets = [a.target for a in plan.actions]
        assert targets == ["excel", "chrome", "brave", "word"]
        for a in plan.actions:
            assert a.action == "open"
            assert a.container == ""

    def test_2_hinglish_conjunction_aur(self, parser):
        """User: 'chrome brave aur excel kholo' -> 3 actions."""
        plan = parser.parse("chrome brave aur excel kholo")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["chrome", "brave", "excel"]

    def test_3_two_apps_aur_open_karo(self, parser):
        """User: 'excel aur word open karo' -> 2 actions."""
        plan = parser.parse("excel aur word open karo")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 2
        targets = [a.target for a in plan.actions]
        assert targets == ["excel", "word"]

    def test_4_commas_and_conjunction(self, parser):
        """User: 'chrome, brave aur firefox kholo' -> 3 actions."""
        plan = parser.parse("chrome, brave aur firefox kholo")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["chrome", "brave", "firefox"]

    def test_5_per_entity_container_specification(self, parser):
        """User: 'youtube brave mein aur gmail chrome mein kholo' -> 2 website actions with respective browsers."""
        plan = parser.parse("youtube brave mein aur gmail chrome mein kholo")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 2

        yt = plan.actions[0]
        assert yt.target == "youtube"
        assert yt.container == "brave"

        gm = plan.actions[1]
        assert gm.target == "gmail"
        assert gm.container == "chrome"

    def test_6_temporal_ordering_clauses(self, parser):
        """User: 'pehle chrome kholo phir excel aur word' -> 3 actions."""
        plan = parser.parse("pehle chrome kholo phir excel aur word")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["chrome", "excel", "word"]

    def test_7_three_adjacent_office_apps(self, parser):
        """User: 'excel word powerpoint open karo' -> 3 actions."""
        plan = parser.parse("excel word powerpoint open karo")
        assert plan is not None
        assert plan.global_action == "open"
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["excel", "word", "powerpoint"]

    def test_8_global_close_inheritance(self, parser):
        """User: 'close chrome brave word' -> 3 close actions."""
        plan = parser.parse("close chrome brave word")
        assert plan is not None
        assert plan.global_action == "close"
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["chrome", "brave", "word"]
        for a in plan.actions:
            assert a.action == "close"

    def test_9_global_minimize_inheritance(self, parser):
        """User: 'minimize chrome brave' -> 2 minimize actions."""
        plan = parser.parse("minimize chrome brave")
        assert plan is not None
        assert plan.global_action == "minimize"
        assert len(plan.actions) == 2
        for a in plan.actions:
            assert a.action == "minimize"

    def test_10_independent_preference_resolution(self, parser):
        """YouTube inherits remembered preference (Brave), Gmail uses default."""
        mock_prefs = MagicMock()
        mock_prefs.get_execution_preference.side_effect = lambda t: "brave" if t == "youtube" else None

        plan = parser.parse("open youtube gmail", preference_manager=mock_prefs)
        assert plan is not None
        assert len(plan.actions) == 2

        yt = plan.actions[0]
        assert yt.target == "youtube"
        assert yt.container == "brave"  # Inherited from preference memory!

        gm = plan.actions[1]
        assert gm.target == "gmail"
        assert gm.container == ""  # Default browser

    def test_11_explicit_container_overrides_stored_preference(self, parser):
        """Explicit container in utterance overrides stored preference."""
        mock_prefs = MagicMock()
        mock_prefs.get_execution_preference.return_value = "brave"  # Remembered preference is brave

        # User explicitly says Chrome for youtube
        plan = parser.parse("open youtube in chrome and gmail in brave", preference_manager=mock_prefs)
        assert plan is not None
        assert len(plan.actions) == 2

        yt = plan.actions[0]
        assert yt.target == "youtube"
        assert yt.container == "chrome"  # Explicit wins!

        gm = plan.actions[1]
        assert gm.target == "gmail"
        assert gm.container == "brave"

    def test_12_single_entity_returns_none(self, parser):
        """Single entity command returns None so it passes through to single-action pipeline."""
        plan = parser.parse("open camera")
        assert plan is None

        plan_excel = parser.parse("open excel")
        assert plan_excel is None


class TestMultiActionExecutor:
    """Unit tests for MultiActionExecutor."""

    def test_executor_synthesizes_all_success_response(self):
        """When all targets succeed, response acknowledges all targets."""
        mock_strat = MagicMock()
        mock_strat.launch_application_verified.return_value = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="app_running"),
            target="test"
        )

        executor = MultiActionExecutor(strategy_engine=mock_strat)
        plan = MultiActionPlan(
            global_action="open",
            actions=[
                ActionItem(action="open", target="excel", display_name="Excel", entity_type="application"),
                ActionItem(action="open", target="chrome", display_name="Chrome", entity_type="browser"),
                ActionItem(action="open", target="brave", display_name="Brave", entity_type="browser"),
                ActionItem(action="open", target="word", display_name="Word", entity_type="application"),
            ]
        )

        all_succ, msg, results = executor.execute_plan(plan)
        assert all_succ is True
        assert "Excel, Chrome, Brave aur Word sab open ho gaye, Boss." in msg
        assert len(results) == 4

    def test_executor_synthesizes_partial_failure_response(self):
        """When some succeed and one fails, honest response specifies both."""
        def mock_launch(app_name, is_new=False):
            succ = (app_name != "brave")
            return ExecutionResult(
                success=succ,
                status=ExecutionState.SUCCESS if succ else ExecutionState.FAILED,
                requested_action="launch_app",
                executed_action="launch_app",
                verification_result=VerificationResult(verified=succ, state=ExecutionState.SUCCESS if succ else ExecutionState.FAILED, check_type="app_running"),
                target=app_name
            )

        mock_strat = MagicMock()
        mock_strat.launch_application_verified.side_effect = mock_launch

        executor = MultiActionExecutor(strategy_engine=mock_strat)
        plan = MultiActionPlan(
            global_action="open",
            actions=[
                ActionItem(action="open", target="excel", display_name="Excel", entity_type="application"),
                ActionItem(action="open", target="chrome", display_name="Chrome", entity_type="browser"),
                ActionItem(action="open", target="brave", display_name="Brave", entity_type="browser"),
                ActionItem(action="open", target="word", display_name="Word", entity_type="application"),
            ]
        )

        all_succ, msg, results = executor.execute_plan(plan)
        assert all_succ is False
        assert "Excel, Chrome aur Word open ho gaye" in msg
        assert "Brave open nahi ho paaya" in msg


class TestEndToEndMultiEntityCommands:
    """End-to-end integration tests via JarvisCore.process_input()."""

    def test_e2e_open_excel_chrome_brave_word(self, core_app):
        """End-to-end: 'open excel chrome brave word' opens all 4 and reports success."""
        mock_launch = MagicMock(return_value=ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="app_running"),
            target="app"
        ))
        core_app.execution_strategies.launch_application_verified = mock_launch

        resp = core_app.process_input("open excel chrome brave word")

        assert "Excel, Chrome, Brave aur Word sab open ho gaye" in resp
        assert mock_launch.call_count == 4

    def test_e2e_chrome_brave_aur_excel_kholo(self, core_app):
        """End-to-end: 'chrome brave aur excel kholo'."""
        mock_launch = MagicMock(return_value=ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="app_running"),
            target="app"
        ))
        core_app.execution_strategies.launch_application_verified = mock_launch

        resp = core_app.process_input("chrome brave aur excel kholo")

        assert "Chrome, Brave aur Excel sab open ho gaye" in resp
        assert mock_launch.call_count == 3

    def test_e2e_close_chrome_brave_word(self, core_app):
        """End-to-end: 'close chrome brave word' closes all 3."""
        mock_close = MagicMock(return_value=ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="close",
            executed_action="close",
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="app_not_running"),
            target="app"
        ))
        core_app.execution_strategies.close_target_verified = mock_close

        resp = core_app.process_input("close chrome brave word")

        assert "Chrome, Brave aur Word sab band ho gaye" in resp
        assert mock_close.call_count == 3

    def test_e2e_single_action_backward_compatibility(self, core_app):
        """Single-entity command 'open camera' continues working exactly as before."""
        wm_mock = MagicMock()
        wm_mock.find_windows_for_app.return_value = [
            WindowInfo(hwnd=777, title="Camera", process_name="WindowsCamera.exe", pid=123)
        ]
        wm_mock.is_process_running.return_value = (True, [123])
        core_app.execution_strategies.verifier.window_manager = wm_mock

        with patch("subprocess.Popen"):
            resp = core_app.process_input("open camera")

        assert "Camera open ho gaya, Boss." in resp or "open ho gaya" in resp
