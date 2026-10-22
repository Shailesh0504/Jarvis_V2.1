# tests/test_desktop_executor_refactor.py
"""
Regression and architectural decoupling tests for the refactored Desktop Task Executor.
Verifies that:
1. Core orchestration has zero direct filesystem execution dependencies (dispatches via Plugin Router).
2. Future non-filesystem plugins (e.g. browser, media, excel) consume the same execution interface.
3. Core refuses to declare success when plugin verification fails.
4. Core natural language commands continue to work seamlessly:
   - "desktop pe test naam ka folder banao"
   - "test folder ke under ek text file banao aur usme Jarvis type karo"
   - "desktop pe kitne folder hain"
   - chained multi-turn follow-up commands using pronouns ('usme', 'that file')
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from core.desktop_task.action_registry import FilesystemActionRegistry, TaskActionResult
from core.desktop_task.context import DesktopExecutionContext, TaskExecutionContext
from core.desktop_task.executor import DesktopExecutionReport, DesktopTaskExecutor
from core.desktop_task.planner import AtomicTaskStep, DesktopTaskPlan, DesktopTaskPlanner
from core.desktop_workflow import DesktopWorkflowCoordinator
from plugins.files.operations import FilesystemOperations
from plugins.files.plugin import FilesPlugin
from plugins.manifest import PluginResult


# =========================================================================
# 1. Architectural Decoupling Tests: Zero Direct Filesystem in Core
# =========================================================================

def test_core_has_no_direct_filesystem_dependency():
    """
    Proves that DesktopTaskExecutor relies strictly on the Plugin Router / Manager
    and performs zero direct filesystem/disk operations in Core.
    """
    mock_pm = MagicMock()
    # Mock plugin manager returning verified results for each action
    mock_pm.execute_action.side_effect = lambda plugin, action, params: PluginResult(
        success=True,
        data={
            "path": f"/virtual/{params.get('name', 'item')}",
            "verified": True,
            "target": f"/virtual/{params.get('name', 'item')}"
        }
    )

    context = TaskExecutionContext()
    executor = DesktopTaskExecutor(plugin_manager=mock_pm, context=context)

    plan = DesktopTaskPlan(
        raw_query="desktop pe test naam ka folder banao",
        steps=[
            AtomicTaskStep(
                step_id="step_1",
                action="RESOLVE_PATH",
                capability="files",
                parameters={"target": "desktop"}
            ),
            AtomicTaskStep(
                step_id="step_2",
                action="CREATE_FOLDER",
                capability="files",
                parameters={"parent": "$step_1.path", "name": "test"},
                depends_on=["step_1"]
            ),
            AtomicTaskStep(
                step_id="step_3",
                action="VERIFY",
                capability="files",
                parameters={"verify_type": "folder_exists", "target": "$step_2.path"},
                depends_on=["step_2"]
            ),
        ],
        intent_type="CREATE_FOLDER"
    )

    report = executor.execute(plan)

    assert report.success is True
    assert len(report.step_results) == 3
    # Verify mock_pm was invoked for each action
    assert mock_pm.execute_action.call_count == 3
    calls = [c[0] for c in mock_pm.execute_action.call_args_list]
    assert calls[0] == ("files", "RESOLVE_PATH", {"target": "desktop"})
    assert calls[1] == ("files", "CREATE_FOLDER", {"parent": "/virtual/item", "name": "test"})
    assert calls[2] == ("files", "VERIFY", {"verify_type": "folder_exists", "target": "/virtual/test"})

    # Context updated from plugin result without any real disk I/O
    assert context.active_folder == os.path.abspath("/virtual/test")


def test_future_plugin_consumes_same_task_execution_interface():
    """
    Demonstrates that a future capability (e.g. Browser or Media) can consume
    the same Task Planner -> Step Decomposition -> Router -> Executor pipeline.
    """
    mock_pm = MagicMock()

    # Browser capability plugin actions: NAVIGATE, EXTRACT_DATA, VERIFY
    def browser_dispatch(plugin, action, params):
        assert plugin == "browser"
        if action == "NAVIGATE":
            return PluginResult(success=True, data={"url": params.get("url"), "verified": True, "target": "page"})
        elif action == "EXTRACT_DATA":
            return PluginResult(success=True, data={"extracted": "Product Price: $99", "verified": True, "target": "price"})
        elif action == "VERIFY":
            return PluginResult(success=True, data={"verified": True, "target": "page"})
        return PluginResult(success=False, error="Unknown action")

    mock_pm.execute_action.side_effect = browser_dispatch

    context = TaskExecutionContext()
    executor = DesktopTaskExecutor(plugin_manager=mock_pm, context=context)

    # Multi-step plan targeting the 'browser' capability
    browser_plan = DesktopTaskPlan(
        raw_query="open store and check price",
        steps=[
            AtomicTaskStep(
                step_id="step_1",
                action="NAVIGATE",
                capability="browser",
                parameters={"url": "https://store.example.com"}
            ),
            AtomicTaskStep(
                step_id="step_2",
                action="EXTRACT_DATA",
                capability="browser",
                parameters={"selector": ".price"},
                depends_on=["step_1"]
            ),
            AtomicTaskStep(
                step_id="step_3",
                action="VERIFY",
                capability="browser",
                parameters={"verify_type": "page_loaded", "target": "page"},
                depends_on=["step_2"]
            )
        ],
        intent_type="BROWSER_TASK"
    )

    report = executor.execute(browser_plan)

    assert report.success is True
    assert len(report.step_results) == 3
    assert mock_pm.execute_action.call_count == 3
    # Verify context stored the non-filesystem entity
    assert context.get_entity("extract_data") == "price"


def test_verification_failure_refuses_success_claim():
    """
    Core must NEVER report success based solely on planning.
    If the plugin executes but verification fails, Core must halt and report failure.
    """
    mock_pm = MagicMock()
    # Simulate an action that succeeds in execution but fails verification on disk
    mock_pm.execute_action.side_effect = [
        PluginResult(success=True, data={"path": "/desk", "verified": True}),
        PluginResult(success=True, data={"path": "/desk/test", "verified": False}, error="Disk verification failed"),
    ]

    context = TaskExecutionContext()
    executor = DesktopTaskExecutor(plugin_manager=mock_pm, context=context)

    plan = DesktopTaskPlan(
        raw_query="desktop pe test folder banao",
        steps=[
            AtomicTaskStep(step_id="step_1", action="RESOLVE_PATH", capability="files", parameters={"target": "desktop"}),
            AtomicTaskStep(step_id="step_2", action="CREATE_FOLDER", capability="files", parameters={"parent": "$step_1.path", "name": "test"})
        ],
        intent_type="CREATE_FOLDER"
    )

    report = executor.execute(plan)

    assert report.success is False
    assert "fail" in report.response_message.lower() or "error" in report.response_message.lower()
    assert report.error == "Disk verification failed"


# =========================================================================
# 2. Regression Tests with Real Filesystem Plugin
# =========================================================================

@pytest.fixture
def refactor_env(tmp_path):
    """Fixture providing a mock desktop environment with real FilesPlugin."""
    mock_desktop = tmp_path / "Desktop"
    mock_desktop.mkdir()

    def mock_get_special(name: str) -> str:
        clean = name.strip().lower()
        if clean in ("desktop", "desktop pe", "desktop par", "desktop per", "on desktop"):
            return str(mock_desktop)
        return ""

    with patch.object(FilesystemActionRegistry, "get_special_path", side_effect=mock_get_special):
        files_plugin = FilesPlugin()
        # Mock plugin manager that routes 'files' capability to real FilesPlugin
        pm = MagicMock()
        pm.execute_action.side_effect = lambda plugin, action, params: files_plugin.execute(action, params)

        context = DesktopExecutionContext(default_base=str(mock_desktop))
        coordinator = DesktopWorkflowCoordinator(plugin_manager=pm, task_context=context)

        yield {
            "desktop": mock_desktop,
            "context": context,
            "coordinator": coordinator,
            "files_plugin": files_plugin,
        }


def test_regression_desktop_pe_test_naam_ka_folder_banao(refactor_env):
    """Regression test: 'desktop pe test naam ka folder banao'."""
    coordinator = refactor_env["coordinator"]
    desktop = refactor_env["desktop"]

    handled, response, report = coordinator.try_handle("desktop pe test naam ka folder banao")

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "test" in response.lower()

    # Verify folder exists on disk
    expected_folder = desktop / "test"
    assert expected_folder.is_dir()
    assert coordinator.task_context.active_folder == str(expected_folder)


def test_regression_test_folder_ke_under_text_file_aur_usme_jarvis_type_karo(refactor_env):
    """Regression test: 'test folder ke under ek text file banao aur usme Jarvis type karo'."""
    coordinator = refactor_env["coordinator"]
    desktop = refactor_env["desktop"]

    # Pre-create test folder
    (desktop / "test").mkdir()

    query = "test folder ke under ek text file banao aur usme Jarvis type karo"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "jarvis" in response.lower()

    # Verify created file on disk
    files = list((desktop / "test").glob("*.txt"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Jarvis" in content


def test_regression_desktop_pe_kitne_folder_hain(refactor_env):
    """Regression test: 'desktop pe kitne folder hain'."""
    coordinator = refactor_env["coordinator"]
    desktop = refactor_env["desktop"]

    (desktop / "dir1").mkdir()
    (desktop / "dir2").mkdir()
    (desktop / "dir3").mkdir()
    (desktop / "file.txt").write_text("hello")

    handled, response, report = coordinator.try_handle("desktop pe kitne folder hain")

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "3 folders" in response or "3 folder" in response


def test_regression_chained_followup_commands(refactor_env):
    """
    Regression test for chained follow-up commands using pronouns ('usme'):
    Turn 1: "desktop pe project_alpha naam ka folder banao"
    Turn 2: "usme ek aur file banao"
    Turn 3: "usme Hello World type karo"
    """
    coordinator = refactor_env["coordinator"]
    desktop = refactor_env["desktop"]

    # Turn 1
    h1, r1, rep1 = coordinator.try_handle("desktop pe project_alpha naam ka folder banao")
    assert h1 is True and rep1.success is True
    alpha_dir = desktop / "project_alpha"
    assert alpha_dir.is_dir()

    # Turn 2
    h2, r2, rep2 = coordinator.try_handle("usme ek aur file banao")
    assert h2 is True and rep2.success is True
    created_file = alpha_dir / "file.txt"
    assert created_file.is_file()

    # Turn 3
    h3, r3, rep3 = coordinator.try_handle("usme Hello World type karo")
    assert h3 is True and rep3.success is True
    assert "Hello World" in created_file.read_text(encoding="utf-8")
