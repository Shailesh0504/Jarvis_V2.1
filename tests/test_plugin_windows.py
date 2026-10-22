# tests/test_plugin_windows.py
"""Automated unit and verification tests for upgraded Windows plugin."""

import pytest
from plugins.windows.plugin import WindowsPlugin


@pytest.fixture
def win_plugin():
    return WindowsPlugin()


def test_windows_manifest_and_health(win_plugin):
    manifest = win_plugin.get_manifest()
    assert manifest.name == "windows"
    assert len(manifest.actions) == 28

    health = win_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 28


def test_get_windows_and_active_info(win_plugin):
    res_wins = win_plugin.execute("get_windows")
    assert res_wins.success is True
    assert "windows" in res_wins.data

    # Active window info
    res_act = win_plugin.execute("get_active_window_info")
    assert res_act.success is True
    assert "hwnd" in res_act.data
    assert "rect" in res_act.data

    # Verify state hook
    v = win_plugin.verify_state("get_active_window_info", {}, res_act.data)
    assert v is not None
    assert v.verified is True


def test_cascade_and_tile_windows(win_plugin):
    res_cas = win_plugin.execute("cascade_windows")
    assert res_cas.success is True

    res_tile_h = win_plugin.execute("tile_windows_horizontally")
    assert res_tile_h.success is True

    res_tile_v = win_plugin.execute("tile_windows_vertically")
    assert res_tile_v.success is True


def test_minimize_and_restore_all(win_plugin):
    res_min = win_plugin.execute("minimize_all_windows")
    assert res_min.success is True

    res_res = win_plugin.execute("restore_all_windows")
    assert res_res.success is True


def test_open_path_validation(win_plugin):
    res = win_plugin.execute("open_path", {"path": ""})
    assert res.success is False
    assert "Path is required" in res.error
