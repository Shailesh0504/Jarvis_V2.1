# tests/test_plugins_advanced.py
"""Comprehensive tests for the advanced plugin subsystem, isolation, and lifecycle."""

import json
import os
import shutil
import pytest
from main import create_jarvis
from plugins.manager import PluginManager
from plugins.manifest import PluginStatus


@pytest.fixture
def clean_jarvis(tmp_path):
    # Copy plugins folder into temp directory
    temp_plugins = tmp_path / "plugins"
    shutil.copytree("plugins", temp_plugins)

    cfg_content = f"""
system:
  name: "JARVIS_TEST"
memory:
  db_path: "{os.path.join(tmp_path, 'test.db').replace('\\', '/')}"
learning:
  enabled: true
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(cfg_content)
    return create_jarvis(str(cfg_file)), temp_plugins


def test_all_standard_plugins_discovered(clean_jarvis):
    jarvis, _ = clean_jarvis
    mgr = jarvis.plugin_manager
    expected = ["bluetooth", "browser", "excel", "files", "pdf", "system", "vlc", "windows", "youtube"]
    available = mgr.get_available_plugins()

    for exp in expected:
        assert exp in available, f"Expected plugin '{exp}' to be loaded."


def test_plugin_json_manifest_attributes(clean_jarvis):
    jarvis, _ = clean_jarvis
    excel = jarvis.plugin_manager.get_plugin("excel")
    assert excel is not None
    assert excel.manifest.name == "excel"
    assert "filesystem" in excel.manifest.permissions
    assert "office" in excel.manifest.permissions
    assert len(excel.manifest.actions) >= 2


def test_crash_isolation_on_broken_plugin(clean_jarvis):
    jarvis, temp_plugins = clean_jarvis

    # Create a corrupted/broken plugin directory
    broken_dir = temp_plugins / "broken_tool"
    broken_dir.mkdir()
    (broken_dir / "plugin.json").write_text('{"name": "broken_tool", "enabled": true}')
    (broken_dir / "plugin.py").write_text('SYNTAX ERROR IN PYTHON CODE !!! {{{')

    # Re-discover plugins
    mgr = jarvis.plugin_manager
    mgr.discover_and_load()

    # Verify Jarvis did not crash and marked broken_tool as error
    assert "broken_tool" in mgr._plugin_errors
    # Verify other plugins still work normally
    status_table = mgr.get_plugin_status_table()
    assert "Broken_tool" in status_table
    assert "Excel" in status_table

    resp = jarvis.process_input("what time is it")
    assert "time" in resp.lower()


def test_crash_isolation_during_execution(clean_jarvis):
    jarvis, _ = clean_jarvis
    excel = jarvis.plugin_manager.get_plugin("excel")

    # Simulate an unexpected exception inside plugin execute
    def crashing_execute(action_name, params):
        raise RuntimeError("Fatal hardware simulation error")

    excel.execute = crashing_execute

    # Safe execute should catch it and return error result without raising unhandled exception
    res = jarvis.plugin_manager.execute_action("excel", "read_sheet", {})
    assert res.success is False
    assert "Crash in plugin 'excel'" in res.error


def test_dynamic_enable_disable_lifecycle(clean_jarvis):
    jarvis, _ = clean_jarvis
    mgr = jarvis.plugin_manager

    # Disable excel
    success, msg = mgr.disable_plugin("excel")
    assert success is True
    assert "excel" not in mgr.get_available_plugins()
    assert mgr.get_plugin("excel").status == PluginStatus.DISABLED

    # Execute should be rejected
    res = mgr.execute_action("excel", "read_sheet", {})
    assert res.success is False
    assert "DISABLED" in res.error

    # Enable excel
    success, msg = mgr.enable_plugin("excel")
    assert success is True
    assert "excel" in mgr.get_available_plugins()
    assert mgr.get_plugin("excel").status == PluginStatus.ENABLED


def test_cli_plugin_manager_commands(clean_jarvis):
    jarvis, _ = clean_jarvis

    # 1. Plugin list command
    resp = jarvis.process_input("plugin list")
    assert "PLUGIN MANAGER" in resp
    assert "Excel" in resp
    assert "● Enabled" in resp

    # 2. Plugin disable command
    resp = jarvis.process_input("plugin disable excel")
    assert "now disabled" in resp.lower()

    # 3. Verify status changed in list
    resp = jarvis.process_input("plugins")
    assert "○ Disabled" in resp

    # 4. Plugin enable command
    resp = jarvis.process_input("plugin enable excel")
    assert "now enabled" in resp.lower()
