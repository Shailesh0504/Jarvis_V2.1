# tests/test_games_chess_plugin.py
"""Tests for Chess game opening and Games plugin functionality."""

import os
from unittest.mock import MagicMock, patch
import pytest

from brain.semantic_parser import HinglishNLUParser
from plugins.games.plugin import GamesPlugin
from plugins.manager import PluginManager


@pytest.mark.parametrize(
    "utterance",
    [
        "open chess",
        "chess open karo",
        "chess kholo",
        "play chess",
        "chess game open karo",
        "chess game kholo",
    ]
)
def test_chess_semantic_parsing(utterance):
    """Verifies that various natural phrases for Chess are parsed as open_app."""
    action = HinglishNLUParser.parse(utterance)
    assert action is not None
    assert action.intent == "OPEN_APP"
    assert "chess" in action.parameters.get("app_name", "").lower()


def test_games_plugin_open_chess_execution():
    """Verifies that GamesPlugin executes open_chess and calls Popen on the chess executable."""
    plugin = GamesPlugin()
    with patch("subprocess.Popen") as mock_popen:
        res = plugin.execute("open_chess", {})
        assert res.success is True
        assert "chess" in res.data.get("message", "").lower()
        mock_popen.assert_called_once()
        called_args = mock_popen.call_args[0][0]
        assert any("chess.exe" in str(arg).lower() for arg in (called_args if isinstance(called_args, list) else [called_args]))


def test_windows_plugin_launch_app_chess():
    """Verifies that WindowsPlugin launch_app with app_name='chess' launches the chess executable."""
    from plugins.windows.plugin import WindowsPlugin

    plugin = WindowsPlugin()
    with patch("subprocess.Popen") as mock_popen:
        res = plugin.execute("launch_app", {"app_name": "chess"})
        assert res.success is True
        mock_popen.assert_called_once()
        called_args = mock_popen.call_args[0][0]
        arg_str = " ".join(called_args) if isinstance(called_args, list) else str(called_args)
        assert "chess.exe" in arg_str.lower()


def test_plugin_manager_catalogs_games_cleanly():
    """Verifies that PluginManager catalogs games without error."""
    pm = PluginManager(plugin_dir="plugins")
    pm.discover_and_load()
    manifests = pm.get_all_manifests()
    assert "games" in manifests
    assert manifests["games"].name == "games"
    assert "games" not in pm._plugin_errors
    assert "sounds" not in pm._plugin_errors
