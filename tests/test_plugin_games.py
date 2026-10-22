# tests/test_plugin_games.py
"""Tests for GamesPlugin covering original and newly added actions."""

import os
import pytest
from unittest.mock import patch, MagicMock
from plugins.games.plugin import GamesPlugin


@pytest.fixture
def plugin(tmp_path):
    p = GamesPlugin()
    p._data_dir = str(tmp_path / "data")
    p._sessions_file = str(tmp_path / "data" / "game_sessions.json")
    p._screenshots_dir = str(tmp_path / "data" / "screenshots" / "games")
    p.initialize()
    return p


def test_games_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "games"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "open_chess",
        "launch_game",
        "scan_installed_games",
        "detect_running_games",
        "enable_game_mode",
        "disable_game_mode",
        "set_game_priority",
        "log_game_session",
        "get_game_session_stats",
        "take_game_screenshot",
        "list_steam_games",
        "kill_game_process"
    }
    assert expected.issubset(action_names)


def test_games_session_logging_and_stats(plugin):
    # Log session 1
    res1 = plugin.execute("log_game_session", {
        "game_name": "Portal 2",
        "duration_minutes": 45.5,
        "notes": "Completed chapter 3"
    })
    assert res1.success is True
    assert res1.data["session"]["game_name"] == "Portal 2"
    assert res1.data["session"]["duration_minutes"] == 45.5

    # Log session 2
    res2 = plugin.execute("log_game_session", {
        "game_name": "Portal 2",
        "duration_minutes": 30.0
    })
    assert res2.success is True

    # Stats
    res_stats = plugin.execute("get_game_session_stats", {})
    assert res_stats.success is True
    assert res_stats.data["total_sessions"] == 2
    assert res_stats.data["total_playtime_minutes"] == 75.5
    assert res_stats.data["breakdown"]["Portal 2"] == 75.5


def test_games_screenshot(plugin):
    res = plugin.execute("take_game_screenshot", {"game_name": "TestGame"})
    assert res.success is True
    assert "screenshot_path" in res.data
    assert os.path.exists(res.data["screenshot_path"])
    assert res.data["size_bytes"] > 0


def test_games_detection_and_scans(plugin):
    # Running games detection
    res_detect = plugin.execute("detect_running_games", {})
    assert res_detect.success is True
    assert "running_games" in res_detect.data

    # Installed games scan
    res_scan = plugin.execute("scan_installed_games", {})
    assert res_scan.success is True
    assert "games" in res_scan.data

    # Steam games scan
    res_steam = plugin.execute("list_steam_games", {})
    assert res_steam.success is True
    assert "steam_games" in res_steam.data


def test_games_game_mode_and_priority(plugin):
    # Enable game mode
    res_enable = plugin.execute("enable_game_mode", {})
    assert res_enable.success is True
    assert res_enable.data["game_mode_active"] is True

    # Disable game mode
    res_disable = plugin.execute("disable_game_mode", {})
    assert res_disable.success is True
    assert res_disable.data["game_mode_active"] is False

    # Set priority on non-existent process safely
    res_prio = plugin.execute("set_game_priority", {
        "process_name": "non_existent_game_xyz",
        "priority": "high"
    })
    assert res_prio.success is True
    assert res_prio.data["modified_processes"] == 0


def test_games_open_chess_missing_or_launch(plugin):
    # With nonexistent path
    res = plugin.execute("launch_game", {"game_name": "unsupported_game_12345"})
    assert res.success is False
