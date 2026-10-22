# tests/test_runtime_context.py
"""Tests for the Single Authoritative RuntimeContext architecture in Jarvis V2.1."""

import os
import pytest
from core.context import (
    ActiveTargetContext,
    DesktopContext,
    RuntimeContext,
    SessionContext,
    TaskContext,
    UserContext,
)
from core.desktop_task.context import TaskExecutionContext


def test_runtime_context_structure_and_defaults():
    """Verify RuntimeContext unifies Session, Desktop, Task, and User context."""
    rc = RuntimeContext()
    assert isinstance(rc.session, SessionContext)
    assert isinstance(rc.desktop, ActiveTargetContext)
    assert isinstance(rc.task, TaskContext)
    assert isinstance(rc.user, UserContext)

    # DesktopContext is an alias/specialization of ActiveTargetContext
    assert DesktopContext is ActiveTargetContext
    assert rc.active_context is rc.desktop


def test_runtime_context_backward_compatible_properties():
    """Verify delegated properties match desktop and task states."""
    rc = RuntimeContext()
    rc.desktop.set_application("vscode", title="main.py - Visual Studio Code")
    assert rc.application == "vscode"
    assert rc.window == "main.py - Visual Studio Code"

    rc.desktop.set_website("github", url="https://github.com")
    assert rc.website == "github"
    assert rc.application == "browser"

    rc.task.workflow = "EXCEL_OPEN"
    assert rc.current_workflow == "EXCEL_OPEN"


def test_task_context_slots_and_lifecycle():
    """Verify TaskContext slot tracking and reset."""
    tc = TaskContext()
    tc.active_intent = "OPEN_FILE"
    tc.set_slot("file_name", "report.xlsx")
    tc.set_slot("target_folder", "C:/Work")

    assert tc.get_slot("file_name") == "report.xlsx"
    assert tc.get_slot("target_folder") == "C:/Work"
    assert tc.get_slot("missing", "default_val") == "default_val"

    tc.clear()
    assert tc.active_intent is None
    assert tc.get_slot("file_name") is None


def test_desktop_task_context_runtime_context_bridge(tmp_path):
    """Verify TaskExecutionContext synchronizes file updates with RuntimeContext."""
    rc = RuntimeContext()
    task_ctx = TaskExecutionContext(default_base=str(tmp_path), runtime_context=rc)

    test_file = tmp_path / "summary.csv"
    test_file.write_text("a,b,c")

    # Update active file in task_ctx
    task_ctx.update_active_file(str(test_file))

    # Must be immediately visible on rc.desktop
    assert rc.desktop.last_file == "summary.csv"
    assert os.path.normpath(rc.desktop.last_file_path) == os.path.normpath(str(test_file))
    assert rc.desktop.target_type == "file"

    # Must resolve pronoun through task_ctx
    resolved = task_ctx.resolve_reference("us file me")
    assert resolved == str(test_file)

    # If task_ctx is cleared, it should still fallback to rc.desktop
    task_ctx.active_file = None
    resolved_fallback = task_ctx.resolve_reference("that file")
    assert resolved_fallback == str(test_file)


def test_jarvis_core_has_authoritative_runtime_context():
    """Verify JarvisCore initializes and exposes runtime_context."""
    from core.app import JarvisCore
    core = JarvisCore()
    assert hasattr(core, "runtime_context")
    assert isinstance(core.runtime_context, RuntimeContext)
    # active_context must refer to the exact same desktop context instance
    assert core.active_context is core.runtime_context.desktop
