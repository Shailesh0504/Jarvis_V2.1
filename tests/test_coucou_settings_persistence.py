# tests/test_coucou_settings_persistence.py
"""Tests verifying Coucou Dynamic Island settings persistence on Done button click."""

import os
import yaml
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from gui.island.views import CoucouSettingsCard
from gui.island.island import CoucouIslandWidget

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


@pytest.fixture
def tmp_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    initial_cfg = {
        "system": {
            "name": "JARVIS",
            "wake_words": ["jarvis", "hey jarvis"],
        },
        "sound": {
            "enabled": True,
            "volume": 12,
        },
        "voice": {
            "enabled": True,
            "speed": 100,
        },
        "island": {
            "auto_close_sec": 15,
            "hide_delay_sec": 60,
            "accessory": "none",
            "animation": "normal",
            "theme": "dark",
            "greeting_enabled": True,
        },
    }
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(initial_cfg, f)
    return str(cfg_file)


def test_autoclose_exclusive_selection():
    """Verify clicking auto-close delay pills behaves exclusively."""
    card = CoucouSettingsCard()
    try:
        assert card.get_autoclose() == 15
        card._on_autoclose_clicked(10)
        assert card.get_autoclose() == 10
        # Check only 10s is checked
        checked = [btn.text() for btn in card._autoclose_btns if btn.isChecked()]
        assert checked == ["10s"]

        card._on_autoclose_clicked(30)
        assert card.get_autoclose() == 30
        checked = [btn.text() for btn in card._autoclose_btns if btn.isChecked()]
        assert checked == ["30s"]
    finally:
        card.close()


def test_hide_delay_exclusive_selection():
    """Verify clicking hide delay pills behaves exclusively."""
    card = CoucouSettingsCard()
    try:
        assert card.get_hide_delay() == 60
        card._on_hide_delay_clicked(30)
        assert card.get_hide_delay() == 30
        checked = [btn.text() for btn in card._hide_delay_btns if btn.isChecked()]
        assert checked == ["30s"]
    finally:
        card.close()


def test_settings_card_get_and_set():
    """Verify get_settings and set_settings bidirectional synchronization."""
    card = CoucouSettingsCard()
    try:
        test_data = {
            "sound_enabled": False,
            "sound_volume": 42,
            "auto_close_sec": 10,
            "hide_delay_sec": 120,
            "mic_enabled": False,
            "wake_word": "friday",
            "speech_speed": 130,
            "accessory": "crown",
            "animation": "lively",
            "theme": "darker",
            "greeting_enabled": False,
        }
        card.set_settings(test_data)
        result = card.get_settings()

        assert result["sound_enabled"] is False
        assert result["sound_volume"] == 42
        assert result["auto_close_sec"] == 10
        assert result["hide_delay_sec"] == 120
        assert result["mic_enabled"] is False
        assert result["wake_word"] == "friday"
        assert result["speech_speed"] == 130
        assert result["accessory"] == "crown"
        assert result["animation"] == "lively"
        assert result["theme"] == "darker"
        assert result["greeting_enabled"] is False
    finally:
        card.close()


def test_settings_save_to_yaml_and_done_button(tmp_config):
    """Verify that clicking Done button writes settings to config.yaml and emits signals."""
    card = CoucouSettingsCard()
    card.config_path = tmp_config

    saved_emitted = []
    done_emitted = []
    card.settings_saved.connect(saved_emitted.append)
    card.done_clicked.connect(lambda: done_emitted.append(True))

    try:
        # User changes settings
        card.set_settings({
            "sound_enabled": True,
            "sound_volume": 85,
            "auto_close_sec": 10,
            "hide_delay_sec": 30,
            "mic_enabled": True,
            "wake_word": "jarvis",
            "speech_speed": 115,
            "accessory": "sunglasses",
            "animation": "calm",
            "theme": "darker",
            "greeting_enabled": True,
        })

        # User clicks Done
        card._on_done_clicked()

        # Immediate verification: settings_saved emitted and Done button text morphed
        assert len(saved_emitted) == 1
        assert saved_emitted[0]["sound_volume"] == 85
        assert saved_emitted[0]["auto_close_sec"] == 10
        assert card.done_btn.text() == "✓ Saved!"

        # Synchronous verification: done_emitted emitted immediately
        assert len(done_emitted) == 1

        # Verify config.yaml was written correctly
        with open(tmp_config, "r", encoding="utf-8") as f:
            persisted = yaml.safe_load(f)

        assert persisted["sound"]["volume"] == 85
        assert persisted["voice"]["speed"] == 115
        assert persisted["island"]["auto_close_sec"] == 10
        assert persisted["island"]["hide_delay_sec"] == 30
        assert persisted["island"]["accessory"] == "sunglasses"
        assert persisted["island"]["animation"] == "calm"
        assert persisted["island"]["theme"] == "darker"
    finally:
        card.close()


def test_island_load_settings_from_config(tmp_config):
    """Verify CoucouIslandWidget loads settings from configuration accurately."""
    with open(tmp_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["sound"]["volume"] = 72
    cfg["island"]["auto_close_sec"] = 30
    cfg["island"]["hide_delay_sec"] = 120
    cfg["island"]["accessory"] = "party_hat"
    with open(tmp_config, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)

    island = CoucouIslandWidget()
    island.view_settings.config_path = tmp_config
    try:
        island.load_settings_from_config()
        current = island.view_settings.get_settings()
        assert current["sound_volume"] == 72
        assert current["auto_close_sec"] == 30
        assert current["hide_delay_sec"] == 120
        assert current["accessory"] == "party_hat"
    finally:
        island.close()
