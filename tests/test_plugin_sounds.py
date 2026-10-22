# tests/test_plugin_sounds.py
"""Automated unit and verification tests for upgraded Sounds plugin."""

import pytest
from plugins.sounds.plugin import SoundsPlugin


def test_sounds_manifest_and_health():
    plugin = SoundsPlugin()
    manifest = plugin.get_manifest()
    assert manifest.name == "sounds"
    assert len(manifest.actions) == 11

    health = plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 11


def test_list_and_verify_sounds():
    plugin = SoundsPlugin()
    res_list = plugin.execute("list_available_sounds", {})
    assert res_list.success is True
    assert res_list.data["count"] >= 4
    assert "jarvis" in res_list.data["sounds"]
    assert "alarm" in res_list.data["sounds"]

    res_verify = plugin.execute("verify_sound_file", {"sound_name_or_path": "jarvis"})
    assert res_verify.success is True
    assert res_verify.data["valid"] is True

    res_bad = plugin.execute("verify_sound_file", {"sound_name_or_path": "nonexistent_sound"})
    assert res_bad.success is False


def test_playback_and_volume():
    plugin = SoundsPlugin()
    # Play built-in sound
    res_play = plugin.execute("play_sound", {"sound_name": "jarvis"})
    assert res_play.success is True
    assert "path" in res_play.data

    # Set volume
    res_vol = plugin.execute("set_sound_volume", {"volume_percent": 50})
    assert res_vol.success is True
    assert res_vol.data["volume_percent"] == 50

    # Stop all sounds
    res_stop = plugin.execute("stop_all_sounds", {})
    assert res_stop.success is True


def test_beep_and_tone():
    plugin = SoundsPlugin()
    res_beep = plugin.execute("play_system_beep", {"beep_type": "ok"})
    assert res_beep.success is True

    res_tone = plugin.execute("generate_frequency_tone", {"frequency": 1200, "duration_ms": 100})
    assert res_tone.success is True
