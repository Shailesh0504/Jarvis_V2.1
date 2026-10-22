# tests/test_system_maintenance.py
"""System-maintenance routing and non-empty response invariants."""

import pytest
from unittest.mock import MagicMock

from brain.semantic_parser import HinglishNLUParser
from main import create_jarvis
from plugins.manifest import PluginResult


@pytest.mark.parametrize(
    ("utterance", "action"),
    [
        ("clear recycle bin", "empty_recycle_bin"),
        ("empty the recycle bin", "empty_recycle_bin"),
        ("recycle bin saaf karo", "empty_recycle_bin"),
        ("recycle bin clean kar do", "empty_recycle_bin"),
        ("recycle bin clear karo", "empty_recycle_bin"),
        ("clear temp file", "clear_temp_files"),
        ("clear temporary files", "clear_temp_files"),
        ("temp files saaf karo", "clear_temp_files"),
    ],
)
def test_maintenance_commands_have_structured_system_intents(utterance, action):
    parsed = HinglishNLUParser.parse(utterance)

    assert parsed is not None
    assert parsed.intent == "SYSTEM_MAINTENANCE"
    assert parsed.service == "system"
    assert parsed.action == action
    assert parsed.confidence == 1.0


@pytest.fixture
def maintenance_core(tmp_path):
    db_path = str(tmp_path / "maintenance.db").replace("\\", "/")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'''system:\n  name: JARVIS_MAINTENANCE_TEST\nmemory:\n  db_path: "{db_path}"\nbrain:\n  llm_provider: mock\nplugins:\n  plugin_dir: plugins\n  auto_load: true\n''',
        encoding="utf-8",
    )
    return create_jarvis(str(config_path))


def test_maintenance_command_routes_to_system_plugin_and_replies(maintenance_core, monkeypatch):
    calls = []

    def fake_execute(plugin, action, parameters):
        calls.append((plugin, action, parameters))
        return PluginResult(success=True, data={"message": "Cleanup complete, Boss."})

    monkeypatch.setattr(maintenance_core.plugin_manager, "execute_action", fake_execute)

    response = maintenance_core.process_input("clear temp file")
    assert response == "Cleanup complete."
    assert "Boss" not in response
    assert calls == [("system", "clear_temp_files", {})]


def test_core_never_returns_blank_for_an_accepted_command(maintenance_core, monkeypatch):
    monkeypatch.setattr(
        maintenance_core.conversation_engine,
        "process_conversation_turn",
        lambda *_args, **_kwargs: (False, "", None),
    )
    monkeypatch.setattr(maintenance_core.dual_brain, "route_and_execute", lambda *_args: ("NONE", "", {}))
    monkeypatch.setattr(maintenance_core.brain, "chat", lambda **_kwargs: "   ")

    response = maintenance_core.process_input("completely unknown request xyz")

    assert response == "Command process nahi ho paya. Please dobara try kijiye."


@pytest.mark.parametrize("utterance", ["time file clean kar do", "time file click karo"])
def test_ambiguous_temp_cleanup_is_suggested_not_executed(maintenance_core, monkeypatch, utterance):
    original_execute = maintenance_core.plugin_manager.execute_action
    execute = MagicMock(wraps=original_execute)
    monkeypatch.setattr(maintenance_core.plugin_manager, "execute_action", execute)

    response = maintenance_core.process_input(utterance)

    assert "temp files clean" in response.lower()
    assert "kya aap" in response.lower()
    execute.assert_not_called()


def test_recycle_bin_already_clear(maintenance_core, monkeypatch):
    """When Recycle Bin has 0 items, notify user that it's already clear."""
    from plugins.system.plugin import SystemPlugin

    plugin = SystemPlugin()
    plugin.manifest = MagicMock()

    class FakeSHQUERYRBINFO:
        cbSize = 0
        i64Size = 0
        i64NumItems = 0

    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
        def fake_query(_root, byref_obj):
            byref_obj._obj.i64NumItems = 0
            byref_obj._obj.i64Size = 0
            return 0
        monkeypatch.setattr(ctypes.windll.shell32, "SHQueryRecycleBinW", fake_query)

    res = plugin.execute("empty_recycle_bin", {})
    assert res.success is True
    assert "pehle se clear" in res.data.get("message", "").lower() or "already" in res.data.get("message", "").lower()


def test_recycle_bin_cleared_when_has_items(maintenance_core, monkeypatch):
    """When Recycle Bin has >0 items, empty it and return success message."""
    from plugins.system.plugin import SystemPlugin

    plugin = SystemPlugin()
    plugin.manifest = MagicMock()

    import ctypes
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
        def fake_query(_root, byref_obj):
            byref_obj._obj.i64NumItems = 5
            byref_obj._obj.i64Size = 10240
            return 0
        def fake_empty(_hwnd, _root, _flags):
            return 0
        monkeypatch.setattr(ctypes.windll.shell32, "SHQueryRecycleBinW", fake_query)
        monkeypatch.setattr(ctypes.windll.shell32, "SHEmptyRecycleBinW", fake_empty)

    res = plugin.execute("empty_recycle_bin", {})
    assert res.success is True
    assert "clear kar diya hai" in res.data.get("message", "")
