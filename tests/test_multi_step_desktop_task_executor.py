# tests/test_multi_step_desktop_task_executor.py
"""Comprehensive automated tests for multi-step desktop task planning, execution, and verification."""

import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from core.desktop_task.action_registry import FilesystemActionRegistry, TaskActionResult
from core.desktop_task.context import DesktopExecutionContext
from core.desktop_task.executor import DesktopExecutionReport, DesktopTaskExecutor
from core.desktop_task.planner import AtomicTaskStep, DesktopTaskPlan, DesktopTaskPlanner
from core.desktop_workflow import DesktopWorkflowCoordinator


@pytest.fixture
def test_env(tmp_path):
    """Fixture providing a mock desktop environment in a temp folder."""
    mock_desktop = tmp_path / "Desktop"
    mock_desktop.mkdir()

    def mock_get_special(name: str) -> str:
        clean = name.strip().lower()
        if clean in ("desktop", "desktop pe", "desktop par", "desktop per", "on desktop"):
            return str(mock_desktop)
        return ""

    with patch.object(FilesystemActionRegistry, "get_special_path", side_effect=mock_get_special):
        context = DesktopExecutionContext(default_base=str(mock_desktop))
        registry = FilesystemActionRegistry()
        executor = DesktopTaskExecutor(registry=registry, context=context)
        planner = DesktopTaskPlanner()
        coordinator = DesktopWorkflowCoordinator(task_context=context)
        yield {
            "desktop": mock_desktop,
            "context": context,
            "registry": registry,
            "executor": executor,
            "planner": planner,
            "coordinator": coordinator,
        }


# =========================================================================
# 1. Single-Step Tasks Tests
# =========================================================================

def test_single_step_create_folder(test_env):
    """Test 'desktop pe test naam ka folder banao' single-step folder creation."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    query = "desktop pe test naam ka folder banao"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert "test" in response.lower()
    assert report is not None
    assert report.success is True

    # Verify folder physically exists on disk
    expected_path = desktop / "test"
    assert expected_path.is_dir()

    # Verify context updated
    assert coordinator.task_context.active_folder == str(expected_path)


def test_single_step_create_file(test_env):
    """Test single-step text file creation."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    query = "desktop pe notes.txt file banao"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True

    expected_file = desktop / "notes.txt"
    assert expected_file.is_file()
    assert coordinator.task_context.active_file == str(expected_file)


def test_single_step_read_file(test_env):
    """Test reading a file with verified content."""
    registry = test_env["registry"]
    desktop = test_env["desktop"]

    sample_file = desktop / "sample.txt"
    sample_file.write_text("Hello from Jarvis", encoding="utf-8")

    result = registry.read_file(str(sample_file))
    assert result.success is True
    assert result.verified is True
    assert result.data["content"] == "Hello from Jarvis"


# =========================================================================
# 2. Multi-Step Chained Tasks Tests
# =========================================================================

def test_multi_step_folder_and_file_creation_with_write(test_env):
    """Test 'test folder ke under ek text file banao aur usme Jarvis type karo'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    # First ensure test folder exists
    (desktop / "test").mkdir(exist_ok=True)
    coordinator.task_context.resolved_paths["test folder"] = str(desktop / "test")

    query = "test folder ke under ek text file banao aur usme Jarvis type karo"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "Jarvis" in response or "file.txt" in response

    # Verify physical file existence and content
    target_file = desktop / "test" / "file.txt"
    assert target_file.is_file()
    content = target_file.read_text(encoding="utf-8")
    assert "Jarvis" in content

    # Verify all steps succeeded and were verified
    assert all(r.verified for r in report.step_results)


def test_multi_step_with_or_conjunction(test_env):
    """Test Hinglish 'or' used as conjunction 'aur'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    (desktop / "work").mkdir(exist_ok=True)
    coordinator.task_context.resolved_paths["work folder"] = str(desktop / "work")

    query = "work folder ke under ek text file banao or usme Jarvis type karo"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True

    target_file = desktop / "work" / "file.txt"
    assert target_file.is_file()
    assert "Jarvis" in target_file.read_text(encoding="utf-8")


# =========================================================================
# 3. Directory Counting Tasks Tests
# =========================================================================

def test_count_folders_on_desktop(test_env):
    """Test 'desktop pe kitne folder hain?'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    # Create 3 subdirectories and 2 files
    (desktop / "dir1").mkdir()
    (desktop / "dir2").mkdir()
    (desktop / "dir3").mkdir()
    (desktop / "file1.txt").write_text("a")
    (desktop / "file2.txt").write_text("b")

    query = "desktop pe kitne folder hain?"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "3 folders" in response or "3 folder" in response


def test_count_folders_variation_kitane(test_env):
    """Test Hinglish spelling variation 'kitane folder hain'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    (desktop / "alpha").mkdir()
    (desktop / "beta").mkdir()

    query = "desktop pe kitane folder hain?"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "2 folders" in response or "2 folder" in response


def test_count_files_on_desktop(test_env):
    """Test 'desktop par kitni files hain'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    (desktop / "f1.txt").write_text("1")
    (desktop / "f2.txt").write_text("2")
    (desktop / "f3.txt").write_text("3")

    query = "desktop par kitni files hain"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "3 files" in response or "3 file" in response


# =========================================================================
# 4. Multi-Turn Pronoun & Context Resolution Tests
# =========================================================================

def test_multi_turn_pronoun_resolution_sequence(test_env):
    """Test full multi-turn conversational task sequence using pronouns."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    # Turn 1: Create folder
    h1, r1, rep1 = coordinator.try_handle("desktop pe my_project naam ka folder banao")
    assert h1 is True and rep1.success is True
    project_dir = desktop / "my_project"
    assert project_dir.is_dir()
    assert coordinator.task_context.active_folder == str(project_dir)

    # Turn 2: Follow-up using 'usme': "usme ek aur file banao"
    h2, r2, rep2 = coordinator.try_handle("usme ek aur file banao")
    assert h2 is True and rep2.success is True
    created_file = project_dir / "file.txt"
    assert created_file.is_file()
    assert coordinator.task_context.active_file == str(created_file)

    # Turn 3: Follow-up using 'usme': "usme Jarvis likho"
    h3, r3, rep3 = coordinator.try_handle("usme Jarvis likho")
    assert h3 is True and rep3.success is True
    content = created_file.read_text(encoding="utf-8")
    assert "Jarvis" in content

    # Turn 4: Follow-up using 'iske andar folder bana do'
    h4, r4, rep4 = coordinator.try_handle("iske andar subfolder bana do")
    assert h4 is True and rep4.success is True
    sub_dir = project_dir / "subfolder"
    assert sub_dir.is_dir()


def test_pronoun_that_file_open(test_env):
    """Test 'us file ko open karo' referencing previously active file."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    test_file = desktop / "readme.txt"
    test_file.write_text("Important readme", encoding="utf-8")
    coordinator.task_context.update_active_file(str(test_file))

    with patch("os.startfile", create=True) as mock_startfile:
        handled, response, report = coordinator.try_handle("us file ko open karo")
        assert handled is True
        assert report is not None
        assert report.success is True
        assert "readme.txt" in response


# =========================================================================
# 5. Nonexistent Paths & Negative Cases
# =========================================================================

def test_nonexistent_parent_path_fails_gracefully(test_env):
    """Test creating a file inside a nonexistent directory fails honestly."""
    coordinator = test_env["coordinator"]

    query = "ghost_folder_xyz ke under ek text file banao"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is False
    assert "exist nahi karta" in response or "error" in response.lower()
    # Must NOT claim completion
    assert "bana diya" not in response


def test_clarification_on_genuinely_missing_parameter(test_env):
    """Test asking clarification when user says 'folder banao' with no name or context."""
    planner = test_env["planner"]
    plan = planner.parse("folder banao")

    assert plan is not None
    assert plan.missing_slots == ["folder_name"]
    assert "naam kya rakhna hai" in plan.clarification_prompt


# =========================================================================
# 6. Duplicate Files & Folders
# =========================================================================

def test_duplicate_folder_creation_is_safe(test_env):
    """Test creating a folder that already exists succeeds safely with exist_ok."""
    registry = test_env["registry"]
    desktop = test_env["desktop"]

    (desktop / "existing_folder").mkdir()
    result = registry.create_folder(str(desktop), "existing_folder")

    assert result.success is True
    assert result.verified is True
    assert result.data["already_existed"] is True


# =========================================================================
# 7. Permission & OS Error Handling
# =========================================================================

def test_permission_error_handling(test_env):
    """Test handling PermissionError without crashing or claiming success."""
    registry = test_env["registry"]
    desktop = test_env["desktop"]

    with patch("os.makedirs", side_effect=PermissionError("Access Denied")):
        result = registry.create_folder(str(desktop), "forbidden_dir")
        assert result.success is False
        assert result.verified is False
        assert "Access Denied" in result.error

    executor = test_env["executor"]
    plan = DesktopTaskPlan(
        raw_query="test",
        steps=[
            AtomicTaskStep(step_id="s1", action="CREATE_FOLDER", parameters={"parent": str(desktop), "name": "forbidden"})
        ],
        intent_type="CREATE_FOLDER"
    )
    with patch.object(registry, "create_folder", return_value=TaskActionResult(success=False, action="CREATE_FOLDER", error="Access Denied")):
        report = executor.execute(plan)
        assert report.success is False
        assert "Access Denied" in report.error or "Permission" in report.response_message


# =========================================================================
# 8. Verification Failure Handling
# =========================================================================

def test_verification_failure_refuses_success(test_env):
    """Test that if written content does not match on disk, verification fails."""
    registry = test_env["registry"]
    desktop = test_env["desktop"]
    target_file = desktop / "corrupt.txt"
    target_file.write_text("Old Content", encoding="utf-8")

    # Simulate write failure where disk content does not update
    with patch("builtins.open", side_effect=[MagicMock(), MagicMock(__enter__=lambda s: MagicMock(read=lambda: "Old Content"))]):
        result = registry.write_file(str(target_file), "Expected Content")
        assert result.success is False
        assert result.verified is False
        assert "Verification failed" in result.error


# =========================================================================
# 9. Destructive Safety Confirmation Flow
# =========================================================================

def test_destructive_delete_requires_and_handles_confirmation(test_env):
    """Test destructive delete workflow: stages prompt, cancellation, and confirmed execution."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    target_file = desktop / "to_delete.txt"
    target_file.write_text("Delete me", encoding="utf-8")
    assert target_file.is_file()

    # Step 1: User requests delete -> stages confirmation
    h1, r1, rep1 = coordinator.try_handle("to_delete.txt delete karo")
    assert h1 is True
    assert rep1.needs_confirmation is True
    assert "delete karna chahte hain" in r1
    # File must still exist
    assert target_file.is_file()

    # Step 2: User says "nahi" -> cancels safely
    h2, r2, rep2 = coordinator.try_handle("nahi rehne do")
    assert h2 is True
    assert "cancel kar diya" in r2
    assert target_file.is_file()

    # Step 3: User requests delete again, then confirms with "haan"
    coordinator.try_handle("to_delete.txt delete karo")
    h3, r3, rep3 = coordinator.try_handle("haan delete kardo")
    assert h3 is True
    assert rep3.success is True
    # File must now be permanently deleted
    assert not target_file.exists()


# =========================================================================
# 10. End-to-End Integration through JarvisCore
# =========================================================================

def test_jarvis_core_end_to_end_does_not_fall_to_generic_chat(test_env):
    """Verify that desktop commands processed via JarvisCore execute and don't fall back to chat."""
    from core.app import JarvisCore
    desktop = test_env["desktop"]

    app = JarvisCore(config_path="nonexistent_cfg.yaml")
    # Initialize with mock desktop coordinator
    app.initialize_subsystems()
    app.desktop_workflows.task_context = test_env["context"]
    app.desktop_workflows.task_executor.registry = test_env["registry"]

    response = app.process_input("desktop pe test naam ka folder banao", source="test")

    assert response != ""
    assert "test" in response.lower()
    # Must NOT be generic fallback
    assert "Main samajh gaya" not in response
    assert "Main aapki kya madad kar sakta hoon" not in response

    # Verify folder was created
    assert (desktop / "test").is_dir()


def test_create_file_and_write_jarvis_content(test_env):
    """Test 'desktop pe ek test.txt file banao or usme Jarvis type karo' writes 'Jarvis' and not 'usme'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    query = "desktop pe ek test.txt file banao or usme Jarvis type karo"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "Jarvis" in response
    assert "usme 'usme'" not in response

    # Verify physical file content
    created_file = desktop / "test.txt"
    assert created_file.is_file()
    content = created_file.read_text(encoding="utf-8")
    assert content == "Jarvis"


def test_create_file_and_write_with_verb_first(test_env):
    """Test 'desktop pe ek test.txt file banao or usme likho Jarvis' writes 'Jarvis'."""
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    query = "desktop pe ek notes.txt file banao or usme likho Jarvis"
    handled, response, report = coordinator.try_handle(query)

    assert handled is True
    assert report is not None
    assert report.success is True
    assert "Jarvis" in response

    created_file = desktop / "notes.txt"
    assert created_file.is_file()
    assert created_file.read_text(encoding="utf-8") == "Jarvis"


def test_multi_turn_clarification_when_write_content_omitted(test_env):
    """
    Test human-like clarification flow when content is omitted:
    User: 'desktop pe ek prompt.txt file banao or usme type karo'
    Jarvis: 'File me kya text type karna hai, Boss?'
    User: 'Jarvis'
    Jarvis completes file and writes 'Jarvis'.
    """
    coordinator = test_env["coordinator"]
    desktop = test_env["desktop"]

    # Turn 1: User requests write but omits content
    h1, r1, rep1 = coordinator.try_handle("desktop pe ek prompt.txt file banao or usme type karo")
    assert h1 is True
    assert rep1 is None
    assert "File me kya text type karna hai" in r1
    assert coordinator.pending_task_plan is not None

    # Turn 2: User provides content "Jarvis"
    h2, r2, rep2 = coordinator.try_handle("Jarvis")
    assert h2 is True
    assert rep2 is not None
    assert rep2.success is True
    assert "Jarvis" in r2
    assert coordinator.pending_task_plan is None

    # Verify physical file content
    created_file = desktop / "prompt.txt"
    assert created_file.is_file()
    assert created_file.read_text(encoding="utf-8") == "Jarvis"

