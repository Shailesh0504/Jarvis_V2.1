# tests/test_conversation_slot_filling.py
"""Comprehensive unit tests for Workflow Lock & Dynamic Slot Filling in Conversation Engine."""

import os
import shutil
import pytest
from main import create_jarvis


@pytest.fixture
def jarvis_conv(tmp_path):
    orig_plugins = os.path.abspath("plugins")
    temp_plugins = tmp_path / "plugins"
    shutil.copytree(orig_plugins, temp_plugins)

    db_path = os.path.join(tmp_path, "conv_test.db").replace("\\", "/")
    cfg_content = f"""
system:
  name: "JARVIS_CONV_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_multi_turn_excel_open_slot_filling(jarvis_conv):
    """
    Turn 1: User says 'Jarvis Excel file kholo' -> Jarvis asks clarification or proactive candidate.
    Turn 2: User says 'Sales wali' -> Jarvis continues active EXCEL_OPEN workflow and opens sales file.
    """
    # Turn 1
    resp1 = jarvis_conv.process_input("Jarvis Excel file kholo")
    assert jarvis_conv.dialog_manager.awaits_user_followup() is True

    # Turn 2: User responds with slot value
    resp2 = jarvis_conv.process_input("Sales wali")
    assert jarvis_conv.dialog_manager.has_active_lock() is False
    assert jarvis_conv.dialog_manager.has_pending_suggestion() is False
    assert "sales" in resp2.lower() or "opened" in resp2.lower() or "khol di" in resp2.lower()


def test_new_excel_request_gets_natural_reply_without_internal_path(jarvis_conv, monkeypatch):
    from plugins.manifest import PluginResult

    monkeypatch.setattr(
        jarvis_conv.plugin_manager,
        "execute_action",
        lambda *_args, **_kwargs: PluginResult(success=True, data={}),
    )
    resp1 = jarvis_conv.process_input("excel file open karo")
    assert jarvis_conv.dialog_manager.awaits_user_followup() is True

    resp2 = jarvis_conv.process_input("new excel file open karo please")

    assert "nayi blank Excel workbook" in resp2
    assert "C:\\" not in resp2
    assert "monthly_sales" not in resp2
    assert "new excel open karo" not in resp2.lower()


def test_multi_turn_media_play_slot_filling(jarvis_conv):
    """
    Turn 1: User says 'Movie chalao' -> Jarvis asks 'Kaunsi movie?'
    Turn 2: User says 'Inception' -> Jarvis plays Inception in VLC.
    """
    # Turn 1
    resp1 = jarvis_conv.process_input("Movie chalao")
    assert "Kaunsi movie" in resp1
    assert jarvis_conv.dialog_manager.has_active_lock() is True

    # Turn 2
    resp2 = jarvis_conv.process_input("Inception")
    assert jarvis_conv.dialog_manager.has_active_lock() is False
    assert "inception" in resp2.lower() or "vlc" in resp2.lower()


def test_workflow_lock_cancellation(jarvis_conv):
    """
    Turn 1: User says 'Excel file kholo' -> Jarvis asks for input.
    Turn 2: User says 'Nahi rehne do' -> Jarvis cancels active lock or suggestion cleanly.
    """
    # Turn 1
    resp1 = jarvis_conv.process_input("Excel file kholo")
    assert jarvis_conv.dialog_manager.awaits_user_followup() is True

    # Turn 2: Cancellation
    resp2 = jarvis_conv.process_input("Nahi rehne do")
    assert jarvis_conv.dialog_manager.has_active_lock() is False
    assert jarvis_conv.dialog_manager.has_pending_suggestion() is False
    assert "cancel" in resp2.lower() or "rehne do" in resp2.lower() or "theek hai" in resp2.lower()


def test_excel_open_zero_matches_does_not_open_random_file(jarvis_conv, tmp_path, monkeypatch):
    """
    When user requests 'test file' and no test file exists,
    Jarvis should NOT open monthly_sales.csv or random file.
    """
    # Set search dirs to an empty folder
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    from core.dialog_manager import DialogManager
    res = DialogManager.resolve_file("test file", search_dirs=[str(empty_dir)])
    assert len(res["exact_matches"]) == 0

    # Test full conversation flow
    jarvis_conv.process_input("open Excel file")
    resp = jarvis_conv.process_input("nonexistent_random_xyz_file")
    assert "monthly_sales" not in resp
    assert "koi" in resp.lower() or "nahi mili" in resp.lower()


def test_excel_open_multiple_matches_clarification(jarvis_conv, tmp_path, monkeypatch):
    """
    When user requests 'test' and multiple test files exist,
    Jarvis should ask for clarification instead of picking arbitrarily.
    """
    test_dir = tmp_path / "test_docs"
    test_dir.mkdir()
    (test_dir / "test_january.xlsx").write_text("a,b,c")
    (test_dir / "test_february.xlsx").write_text("d,e,f")

    from core.dialog_manager import DialogManager
    res = DialogManager.resolve_file("test", search_dirs=[str(test_dir)])
    assert len(res["exact_matches"]) >= 2

    monkeypatch.setattr(
        DialogManager,
        "resolve_file",
        lambda *args, **kwargs: {
            "exact_matches": [
                {"name": "test_january.xlsx", "path": str(test_dir / "test_january.xlsx"), "mtime": 100},
                {"name": "test_february.xlsx", "path": str(test_dir / "test_february.xlsx"), "mtime": 101},
            ],
            "close_suggestions": [],
            "all_discovered": [],
        }
    )

    jarvis_conv.process_input("open Excel file")
    resp = jarvis_conv.process_input("test file")
    assert "matches mile" in resp
    assert "test_january.xlsx" in resp
    assert "test_february.xlsx" in resp
    assert "Kaunsi file open karni hai" in resp


def test_excel_open_single_match_opens_file(jarvis_conv, tmp_path, monkeypatch):
    """
    When user requests 'test file' and exactly 1 test file exists,
    Jarvis should open that file directly.
    """
    test_dir = tmp_path / "single_doc"
    test_dir.mkdir()
    target_file = test_dir / "test.xlsx"
    target_file.write_text("x,y,z")

    monkeypatch.setattr(
        "core.dialog_manager.DialogManager.resolve_file",
        lambda *args, **kwargs: {
            "exact_matches": [
                {"name": "test.xlsx", "path": str(target_file), "mtime": 200},
            ],
            "close_suggestions": [],
            "all_discovered": [],
        }
    )

    jarvis_conv.process_input("open Excel file")
    resp = jarvis_conv.process_input("test file")
    assert "'test.xlsx' Excel mein khol di hai" in resp
