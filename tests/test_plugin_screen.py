# tests/test_plugin_screen.py
"""Automated unit and verification tests for upgraded Screen plugin."""

import os
import pytest
from plugins.screen.plugin import ScreenPlugin


@pytest.fixture
def screen_plugin(tmp_path):
    plugin = ScreenPlugin()
    plugin._screenshots_dir = str(tmp_path / "screenshots")
    os.makedirs(plugin._screenshots_dir, exist_ok=True)
    return plugin


def test_screen_manifest_and_health(screen_plugin):
    manifest = screen_plugin.get_manifest()
    assert manifest.name == "screen"
    assert len(manifest.actions) == 16  # 14 + brightness_up/down (relative controls)
    assert {a.name for a in manifest.actions} >= {"brightness_up", "brightness_down"}

    health = screen_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 16


def test_take_screenshot_and_verify(screen_plugin):
    res = screen_plugin.execute("take_screenshot", {"filename": "test_snap.png"})
    assert res.success is True
    assert os.path.exists(res.data["path"])
    assert os.path.getsize(res.data["path"]) > 0

    # Verify state hook
    v = screen_plugin.verify_state("take_screenshot", {}, res.data)
    assert v is not None
    assert v.verified is True


def test_capture_region_and_window(screen_plugin):
    res_reg = screen_plugin.execute("capture_region_screenshot", {
        "x": 100, "y": 100, "width": 200, "height": 150
    })
    assert res_reg.success is True
    assert os.path.exists(res_reg.data["path"])

    res_win = screen_plugin.execute("capture_active_window")
    assert res_win.success is True
    assert os.path.exists(res_win.data["path"])


def test_display_diagnostics(screen_plugin):
    res_res = screen_plugin.execute("get_screen_resolution")
    assert res_res.success is True
    assert res_res.data["width"] > 0
    assert res_res.data["height"] > 0

    res_mon = screen_plugin.execute("list_monitors")
    assert res_mon.success is True
    assert res_mon.data["count"] >= 1

    res_pix = screen_plugin.execute("get_pixel_color", {"x": 50, "y": 50})
    assert res_pix.success is True
    assert "rgb" in res_pix.data


def test_recording_and_file_management(screen_plugin):
    res_start = screen_plugin.execute("start_recording")
    assert res_start.success is True
    assert res_start.data["recording"] is True

    res_stop = screen_plugin.execute("stop_recording")
    assert res_stop.success is True
    assert res_stop.data["recording"] is False

    # List saved screenshots
    screen_plugin.execute("take_screenshot", {"filename": "to_delete.png"})
    res_list = screen_plugin.execute("list_saved_screenshots")
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Delete
    res_del = screen_plugin.execute("delete_screenshot", {"filename": "to_delete.png"})
    assert res_del.success is True


def test_relative_brightness_controls(screen_plugin):
    # Relative controls never raise (WMI absence degrades to dispatched notice)
    res_up = screen_plugin.execute("brightness_up", {"step": 15})
    assert res_up.success is True
    assert 0 <= res_up.data["brightness"] <= 100

    res_down = screen_plugin.execute("brightness_down", {"step": 15})
    assert res_down.success is True
    assert 0 <= res_down.data["brightness"] <= 100
