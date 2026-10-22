# tests/test_plugin_audio.py
"""Automated unit and verification tests for upgraded Audio plugin."""

import pytest
from plugins.audio.plugin import AudioPlugin


@pytest.fixture
def audio_plugin():
    return AudioPlugin()


def test_audio_manifest_and_health(audio_plugin):
    manifest = audio_plugin.get_manifest()
    assert manifest.name == "audio"
    assert len(manifest.actions) == 15

    health = audio_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 15


def test_get_and_set_volume(audio_plugin):
    res_get = audio_plugin.execute("get_volume")
    assert res_get.success is True
    assert "volume" in res_get.data

    # Set volume
    orig = res_get.data["volume"]
    res_set = audio_plugin.execute("set_volume", {"level": orig})
    assert res_set.success is True

    # Verify state hook
    v = audio_plugin.verify_state("set_volume", {"level": orig}, res_set.data)
    assert v is not None
    assert v.verified is True


def test_volume_up_and_down(audio_plugin):
    res_up = audio_plugin.execute("volume_up", {"step": 2})
    assert res_up.success is True

    res_down = audio_plugin.execute("volume_down", {"step": 2})
    assert res_down.success is True


def test_list_audio_devices_and_sessions(audio_plugin):
    res_devs = audio_plugin.execute("list_audio_devices")
    assert res_devs.success is True
    assert res_devs.data["count"] >= 1

    res_sess = audio_plugin.execute("list_app_audio_sessions")
    assert res_sess.success is True
    assert isinstance(res_sess.data["sessions"], list)

    res_def = audio_plugin.execute("get_default_audio_device")
    assert res_def.success is True
    assert "device" in res_def.data


def test_check_audio_engine_and_frequency(audio_plugin):
    res_eng = audio_plugin.execute("check_audio_engine_status")
    assert res_eng.success is True
    assert "audio_engine_active" in res_eng.data
