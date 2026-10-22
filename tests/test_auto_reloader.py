# tests/test_auto_reloader.py
"""Regression coverage for live auto-update, file watching, and hot-reload supervisor."""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from brain.semantic_parser import HinglishNLUParser
from core.reloader import (
    ENV_RELOAD_SESSION,
    ENV_RELOADER_CHILD,
    RELOAD_EXIT_CODE,
    FileWatcher,
    ReloaderSupervisor,
    is_reload_session,
    is_reloader_child,
    trigger_reload,
)
from main import create_jarvis


@pytest.fixture
def jarvis():
    return create_jarvis()


def test_file_watcher_detects_modification_and_addition(tmp_path):
    """Verify that FileWatcher detects modifications, additions, and deletions."""
    src_dir = tmp_path / "core"
    src_dir.mkdir()
    sample_file = src_dir / "sample.py"
    sample_file.write_text("print('v1')", encoding="utf-8")

    watcher = FileWatcher(project_root=str(tmp_path), watch_dirs=["core"], root_files=[])
    assert watcher.check_for_changes() is None

    # 1. Modify existing file
    time.sleep(0.05)
    sample_file.write_text("print('v2')", encoding="utf-8")
    # Update mtime explicitly in case filesystem resolution is coarse
    os.utime(str(sample_file), (time.time() + 2, time.time() + 2))

    changed = watcher.check_for_changes()
    assert changed is not None
    assert "sample.py" in changed

    # 2. Add new file
    new_file = src_dir / "new_module.py"
    new_file.write_text("x = 1", encoding="utf-8")
    added = watcher.check_for_changes()
    assert added is not None
    assert "new_module.py" in added

    # 3. Delete file
    os.remove(str(new_file))
    deleted = watcher.check_for_changes()
    assert deleted is not None
    assert "new_module.py" in deleted


def test_file_watcher_ignores_ignored_directories_and_extensions(tmp_path):
    """Verify that logs, cache, and database files are completely ignored."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "app.log"
    log_file.write_text("log line 1", encoding="utf-8")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "test.db"
    db_file.write_text("db binary", encoding="utf-8")

    src_dir = tmp_path / "core"
    src_dir.mkdir()
    pyc_file = src_dir / "module.pyc"
    pyc_file.write_text("compiled", encoding="utf-8")

    watcher = FileWatcher(project_root=str(tmp_path), watch_dirs=["core", "logs", "data"], root_files=[])

    # Modify ignored items
    log_file.write_text("log line 2", encoding="utf-8")
    db_file.write_text("db modified", encoding="utf-8")
    pyc_file.write_text("compiled 2", encoding="utf-8")

    assert watcher.check_for_changes() is None


def test_reloader_environment_flags(monkeypatch):
    """Verify environment detection helpers."""
    monkeypatch.delenv(ENV_RELOADER_CHILD, raising=False)
    monkeypatch.delenv(ENV_RELOAD_SESSION, raising=False)
    assert is_reloader_child() is False
    assert is_reload_session() is False

    monkeypatch.setenv(ENV_RELOADER_CHILD, "1")
    monkeypatch.setenv(ENV_RELOAD_SESSION, "1")
    assert is_reloader_child() is True
    assert is_reload_session() is True


def test_trigger_reload_exits_with_code_when_under_supervisor(monkeypatch):
    """When running as a child of the supervisor, trigger_reload exits with RELOAD_EXIT_CODE."""
    monkeypatch.setenv(ENV_RELOADER_CHILD, "1")
    with pytest.raises(SystemExit) as exc_info:
        trigger_reload()
    assert exc_info.value.code == RELOAD_EXIT_CODE


def test_reloader_supervisor_clean_exit_and_reload(tmp_path):
    """Verify ReloaderSupervisor lifecycle: clean exit terminates, RELOAD_EXIT_CODE restarts."""
    supervisor = ReloaderSupervisor(project_root=str(tmp_path), args=["--cli"], poll_interval=0.01)

    mock_proc_1 = MagicMock()
    mock_proc_1.poll.return_value = RELOAD_EXIT_CODE

    mock_proc_2 = MagicMock()
    mock_proc_2.poll.return_value = 0

    with patch.object(supervisor, "_spawn_child", side_effect=[mock_proc_1, mock_proc_2]) as mock_spawn:
        exit_code = supervisor.run()
        assert exit_code == 0
        assert mock_spawn.call_count == 2
        # Second spawn was marked as reload session
        assert mock_spawn.call_args_list[1].kwargs.get("is_reload") is True


@pytest.mark.parametrize(
    "utterance",
    [
        "jarvis restart",
        "jarvis reload",
        "restart jarvis",
        "reload jarvis",
        "jarvis ko restart karo",
        "jarvis ko reload karo",
        "live auto update karo",
    ],
)
def test_jarvis_restart_semantic_parsing(utterance):
    """Verify that Jarvis application restart is parsed as JARVIS_RESTART, distinct from PC restart."""
    action = HinglishNLUParser.parse(utterance)
    assert action is not None
    assert action.intent == "JARVIS_RESTART"
    assert action.service == "system"
    assert action.action == "restart_jarvis"


def test_pc_restart_preserved_and_not_hijacked():
    """Verify that PC/computer restart commands remain mapped to SYSTEM_RESTART."""
    action = HinglishNLUParser.parse("system restart karo")
    assert action is not None
    assert action.intent == "SYSTEM_RESTART"

    action2 = HinglishNLUParser.parse("computer restart karo")
    assert action2 is not None
    assert action2.intent == "SYSTEM_RESTART"


def test_jarvis_core_handles_restart_intent(jarvis):
    """Verify that JarvisCore responds to restart intent and schedules trigger_reload."""
    with patch("threading.Timer") as mock_timer:
        mock_timer_instance = MagicMock()
        mock_timer.return_value = mock_timer_instance

        resp = jarvis.process_input("jarvis restart karo")
        assert "restart" in resp.lower()
        assert mock_timer.called
        assert mock_timer_instance.start.called
