# tests/test_plugin_vlc.py
"""Automated unit and verification tests for upgraded VLC plugin."""

import pytest
from plugins.vlc.plugin import VLCPlugin


def test_vlc_manifest_and_health():
    plugin = VLCPlugin()
    manifest = plugin.get_manifest()
    assert manifest.name == "vlc"
    assert len(manifest.actions) == 12

    health = plugin.get_health_status()
    assert "status" in health
    assert health["actions_count"] == 12


def test_vlc_executable_discovery():
    plugin = VLCPlugin()
    res = plugin.execute("find_vlc_executable", {})
    assert "vlc_path" in res.data


def test_vlc_running_status_and_stop():
    plugin = VLCPlugin()
    res = plugin.execute("is_vlc_running", {})
    assert res.success is True
    assert "running" in res.data
    assert isinstance(res.data["pids"], list)

    # Stop playback when not running should gracefully succeed with 0 stopped
    res_stop = plugin.execute("stop_playback", {})
    assert res_stop.success is True


def test_vlc_controls_when_not_running():
    plugin = VLCPlugin()
    # When VLC is not running, hotkey actions should gracefully report error instead of hanging or crashing
    actions = [
        "pause_resume_vlc",
        "vlc_fullscreen_toggle",
        "vlc_volume_up",
        "vlc_volume_down",
        "vlc_mute_toggle",
        "vlc_seek_forward",
        "vlc_seek_backward",
        "vlc_next_track"
    ]
    for action in actions:
        res = plugin.execute(action, {})
        if not plugin._get_vlc_pids():
            assert res.success is False
            assert "not currently running" in res.error
