# tests/test_plugin_automation.py
"""Automated unit and verification tests for upgraded Automation plugin."""

import os
import pytest
from plugins.automation.plugin import AutomationPlugin


@pytest.fixture
def auto_plugin(tmp_path):
    plugin = AutomationPlugin()
    plugin.macros_file = str(tmp_path / "test_macros.json")
    plugin._macros = {}
    plugin._save_macros()
    return plugin


def test_automation_manifest_and_health(auto_plugin):
    manifest = auto_plugin.get_manifest()
    assert manifest.name == "automation"
    assert len(manifest.actions) == 15

    health = auto_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 15


def test_cursor_position_and_move(auto_plugin):
    res_pos = auto_plugin.execute("get_cursor_position")
    assert res_pos.success is True
    assert "x" in res_pos.data
    assert "y" in res_pos.data
    assert res_pos.data["screen_width"] > 0

    # Move cursor
    res_move = auto_plugin.execute("move_cursor", {"x": 200, "y": 200, "duration": 0.01})
    assert res_move.success is True

    # Verify state hook
    v = auto_plugin.verify_state("move_cursor", {"x": 200, "y": 200}, res_move.data)
    assert v is not None
    assert v.verified is True


def test_custom_macro_lifecycle(auto_plugin):
    steps = [
        {"action": "move_cursor", "x": 100, "y": 100},
        {"action": "delay", "seconds": 0.01}
    ]
    # Register
    res_reg = auto_plugin.execute("register_custom_macro", {
        "macro_name": "test_workflow",
        "steps": steps,
        "description": "Quick test sequence"
    })
    assert res_reg.success is True

    # Verify state hook
    v = auto_plugin.verify_state("register_custom_macro", {"macro_name": "test_workflow"}, {})
    assert v is not None
    assert v.verified is True

    # List
    res_list = auto_plugin.execute("list_macros")
    assert res_list.success is True
    assert any(m["name"] == "test_workflow" for m in res_list.data["macros"])

    # Run
    res_run = auto_plugin.execute("run_macro", {"macro_name": "test_workflow"})
    assert res_run.success is True
    assert res_run.data["steps_executed"] == 2

    # Delete
    res_del = auto_plugin.execute("delete_macro", {"macro_name": "test_workflow"})
    assert res_del.success is True

    # Check deleted
    res_list2 = auto_plugin.execute("list_macros")
    assert not any(m["name"] == "test_workflow" for m in res_list2.data["macros"])


def test_mouse_actions(auto_plugin):
    res_click = auto_plugin.execute("click", {"x": 150, "y": 150})
    assert res_click.success is True

    res_dbl = auto_plugin.execute("double_click", {"x": 150, "y": 150})
    assert res_dbl.success is True

    res_right = auto_plugin.execute("right_click", {"x": 150, "y": 150})
    assert res_right.success is True

    res_scroll = auto_plugin.execute("mouse_scroll", {"clicks": 2})
    assert res_scroll.success is True


def test_press_hotkey(auto_plugin):
    res = auto_plugin.execute("press_hotkey", {"hotkey": "ctrl"})
    assert res.success is True
    assert "ctrl" in res.data["hotkey"]
