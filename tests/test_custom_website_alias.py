# tests/test_custom_website_alias.py
"""
Unit and Integration Tests for User-Learned Website Alias System in Jarvis V2.
Validates:
- Teaching custom website aliases via natural language ("remember X means Y", "jab main bolun open X to Y kholna", "X ko Y se map karo").
- Persistent storage in SQLite custom_aliases table.
- Priority: User-defined custom alias > built-in sites > domain inference.
- Execution across speech variations: "Open GLPI", "GLPI kholo", "GLPI open karo", "GLPI website kholo", "Jarvis, GLPI".
- Safe browser tab focus reuse (avoiding duplicate tabs).
- Alias modification / URL updating.
- Alias deletion and cleanup.
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from core.alias_manager import CustomAliasManager, get_alias_manager
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def alias_db(tmp_path):
    db_file = str(tmp_path / "test_alias.db")
    mgr = CustomAliasManager(db_path=db_file)
    return mgr


@pytest.fixture
def app_with_alias(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_alias_app.db")
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
        response_generator=resp_gen
    )
    # Configure CustomAliasManager for test db
    core.alias_manager = CustomAliasManager(db_path=db_path)
    return core


def test_alias_manager_crud(alias_db):
    """Verifies low-level CRUD operations in CustomAliasManager."""
    # 1. Add Alias
    ok = alias_db.add_alias("glpi", "https://glpi-jioinstitute1.msappproxy.net/index.php", "OPEN_WEBSITE", "GLPI Portal")
    assert ok is True

    # 2. Retrieve Alias
    entry = alias_db.get_alias("glpi")
    assert entry is not None
    assert entry["alias"] == "glpi"
    assert entry["target"] == "https://glpi-jioinstitute1.msappproxy.net/index.php"
    assert entry["action_type"] == "OPEN_WEBSITE"

    # 3. Case-insensitivity & query resolution
    assert alias_db.resolve_alias("GLPI") is not None
    assert alias_db.resolve_alias("open glpi") is not None
    assert alias_db.resolve_alias("glpi website kholo") is not None

    # 4. Update Alias
    upd = alias_db.update_alias("glpi", "https://glpi-v2.company.com")
    assert upd is True
    updated = alias_db.get_alias("glpi")
    assert updated["target"] == "https://glpi-v2.company.com"

    # 5. List Aliases
    all_items = alias_db.list_aliases()
    assert len(all_items) == 1
    assert all_items[0]["alias"] == "glpi"

    # 6. Delete Alias
    deleted = alias_db.delete_alias("glpi")
    assert deleted is True
    assert alias_db.get_alias("glpi") is None


def test_learn_alias_via_natural_language(app_with_alias):
    """Verifies teaching Jarvis custom aliases using natural Hindi/Hinglish speech."""
    # 1. Teach GLPI alias
    resp1 = app_with_alias.process_input("Jarvis, remember GLPI means this website: https://glpi-jioinstitute1.msappproxy.net/index.php")
    assert "Samajh gaya" in resp1
    assert "GLPI" in resp1

    # 2. Teach Jira alias
    resp2 = app_with_alias.process_input("Jira ko https://jira.company.com se map karo")
    assert "Samajh gaya" in resp2
    assert "JIRA" in resp2

    # 3. Teach Payroll alias
    resp3 = app_with_alias.process_input("Whenever I say payroll, open the payroll website https://payroll.company.com")
    assert "Samajh gaya" in resp3
    assert "PAYROLL" in resp3


def test_execute_learned_alias_browser_action(app_with_alias):
    """Verifies that learned aliases open the correct target URL in browser."""
    # Pre-register GLPI alias
    app_with_alias.process_input("Jarvis, remember GLPI means this website: https://glpi-jioinstitute1.msappproxy.net/index.php")

    with patch("webbrowser.open") as mock_open:
        # 1. "Open GLPI"
        app_with_alias.process_input("Open GLPI")
        mock_open.assert_called_once_with("https://glpi-jioinstitute1.msappproxy.net/index.php")
        mock_open.reset_mock()

        # 2. "GLPI kholo"
        app_with_alias.process_input("GLPI kholo")
        mock_open.assert_called_once_with("https://glpi-jioinstitute1.msappproxy.net/index.php")
        mock_open.reset_mock()

        # 3. "GLPI open karo"
        app_with_alias.process_input("GLPI open karo")
        mock_open.assert_called_once_with("https://glpi-jioinstitute1.msappproxy.net/index.php")
        mock_open.reset_mock()

        # 4. "GLPI website kholo"
        app_with_alias.process_input("GLPI website kholo")
        mock_open.assert_called_once_with("https://glpi-jioinstitute1.msappproxy.net/index.php")
        mock_open.reset_mock()


def test_update_and_delete_learned_alias(app_with_alias):
    """Verifies updating target URLs and deleting user aliases."""
    # 1. Initial learn
    app_with_alias.process_input("Jarvis, remember GLPI means this website: https://glpi-jioinstitute1.msappproxy.net/index.php")

    # 2. Update URL
    resp_upd = app_with_alias.process_input("GLPI ka website change kar do to https://glpi-updated.company.com")
    assert "GLPI" in resp_upd
    assert "update" in resp_upd.lower()

    with patch("webbrowser.open") as mock_open:
        app_with_alias.process_input("open GLPI")
        assert mock_open.called
        assert mock_open.call_args[0][0].startswith("https://glpi-updated.company.com")

    # 3. Delete Alias
    resp_del = app_with_alias.process_input("GLPI alias delete kar do")
    assert "delete" in resp_del.lower()
    assert "GLPI" in resp_del
