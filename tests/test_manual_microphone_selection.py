# tests/test_manual_microphone_selection.py
"""
Unit and Integration Tests for Manual Microphone Selection in GUI Settings & AudioDeviceManager.
Tests:
- Manual device preference configuration and persistence
- Routing override: selected mic overrides automatic Bluetooth earbud prioritization
- Deduplication across Windows host APIs (WASAPI/DirectSound/MME)
- Fallback to auto-detection when preferred device is disconnected
- Hot-switch callback notifications
- SettingsView UI controls: combo box, refresh button, test mic diagnostic
"""

import os
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from voice.device_manager import AudioDeviceManager, AudioDeviceInfo
from gui.views.settings_view import SettingsView, MicTestWorker


@pytest.fixture(autouse=True)
def reset_audio_device_manager():
    """Reset singleton state between tests."""
    adm = AudioDeviceManager()
    adm.set_manual_device(None)
    adm._device_change_callbacks.clear()
    yield
    adm.set_manual_device(None)
    adm._device_change_callbacks.clear()


def test_set_and_get_manual_device():
    adm = AudioDeviceManager()
    
    adm.set_manual_device("Blue Yeti USB Microphone")
    assert adm.get_manual_device() == "Blue Yeti USB Microphone"

    # Reset to auto via various representations
    adm.set_manual_device("auto")
    assert adm.get_manual_device() is None

    adm.set_manual_device("Auto")
    assert adm.get_manual_device() is None

    adm.set_manual_device(None)
    assert adm.get_manual_device() is None

    adm.set_manual_device("")
    assert adm.get_manual_device() is None


def test_manual_selection_overrides_bluetooth_earbuds():
    """Verify that user's manual selection takes precedence over Bluetooth earbuds priority."""
    adm = AudioDeviceManager()

    dev_internal = AudioDeviceInfo(
        index=1,
        name="Microphone Array (Realtek High Definition Audio)",
        clean_name="Microphone Array (Realtek)",
        is_bluetooth=False,
        is_earbuds=False,
        is_usb=False,
        is_default=True,
        score=30,
        hostapi_name="Windows DirectSound",
        max_input_channels=2,
        default_samplerate=44100.0,
    )
    dev_earbuds = AudioDeviceInfo(
        index=2,
        name="CMF Buds 2 (Bluetooth)",
        clean_name="CMF Buds 2 (Bluetooth)",
        is_bluetooth=True,
        is_earbuds=True,
        is_usb=False,
        is_default=False,
        score=100,
        hostapi_name="Windows WASAPI",
        max_input_channels=1,
        default_samplerate=16000.0,
    )
    dev_usb = AudioDeviceInfo(
        index=3,
        name="Blue Yeti USB Microphone",
        clean_name="Blue Yeti USB Microphone",
        is_bluetooth=False,
        is_earbuds=False,
        is_usb=True,
        is_default=False,
        score=70,
        hostapi_name="Windows WASAPI",
        max_input_channels=2,
        default_samplerate=48000.0,
    )

    all_devices = [dev_internal, dev_earbuds, dev_usb]

    with patch.object(adm, "list_input_devices", return_value=all_devices):
        # 1. Without manual preference, auto prioritizes earbuds
        adm.set_manual_device(None)
        best = adm.get_best_input_device()
        assert best is not None
        assert best.clean_name == "CMF Buds 2 (Bluetooth)"

        # 2. With manual preference set to "Blue Yeti", Yeti wins over earbuds
        adm.set_manual_device("Blue Yeti")
        best = adm.get_best_input_device()
        assert best is not None
        assert best.clean_name == "Blue Yeti USB Microphone"

        # 3. With manual preference set by exact index "1"
        adm.set_manual_device("1")
        best = adm.get_best_input_device()
        assert best is not None
        assert best.index == 1

        # 4. If preferred device is disconnected, fallback to auto earbuds
        adm.set_manual_device("Elgato Wave 3")
        best = adm.get_best_input_device()
        assert best is not None
        assert best.clean_name == "CMF Buds 2 (Bluetooth)"


def test_unique_input_devices_deduplication():
    """Verify deduplication across host APIs (WASAPI/DirectSound/MME) and filtering of score 0."""
    adm = AudioDeviceManager()

    dev_ds = AudioDeviceInfo(
        index=1,
        name="Microphone Array",
        clean_name="Microphone Array",
        is_bluetooth=False,
        is_earbuds=False,
        is_usb=False,
        is_default=False,
        score=30,
        hostapi_name="Windows DirectSound",
        max_input_channels=2,
        default_samplerate=44100.0,
    )
    dev_wasapi = AudioDeviceInfo(
        index=2,
        name="Microphone Array",
        clean_name="Microphone Array",
        is_bluetooth=False,
        is_earbuds=False,
        is_usb=False,
        is_default=False,
        score=30,
        hostapi_name="Windows WASAPI",
        max_input_channels=2,
        default_samplerate=48000.0,
    )
    dev_stereo_mix = AudioDeviceInfo(
        index=3,
        name="Stereo Mix (Realtek)",
        clean_name="Stereo Mix",
        is_bluetooth=False,
        is_earbuds=False,
        is_usb=False,
        is_default=False,
        score=0,  # Excluded
        hostapi_name="MME",
        max_input_channels=2,
        default_samplerate=44100.0,
    )

    with patch.object(adm, "list_input_devices", return_value=[dev_ds, dev_wasapi, dev_stereo_mix]):
        unique = adm.get_unique_input_devices()
        # Should deduplicate Microphone Array to 1 entry and exclude Stereo Mix
        assert len(unique) == 1
        # WASAPI should be preferred over DirectSound
        assert unique[0].hostapi_name == "Windows WASAPI"
        assert unique[0].clean_name == "Microphone Array"


def test_device_change_listener_notified_on_manual_switch():
    adm = AudioDeviceManager()
    callback_calls = []

    def on_change(dev):
        callback_calls.append(dev)

    adm.register_device_change_listener(on_change)

    dev1 = AudioDeviceInfo(
        index=1, name="Mic 1", clean_name="Mic 1", is_bluetooth=False,
        is_earbuds=False, is_usb=False, is_default=True, score=30,
        hostapi_name="MME", max_input_channels=1, default_samplerate=16000.0
    )
    dev2 = AudioDeviceInfo(
        index=2, name="Mic 2", clean_name="Mic 2", is_bluetooth=False,
        is_earbuds=False, is_usb=True, is_default=False, score=70,
        hostapi_name="MME", max_input_channels=1, default_samplerate=16000.0
    )

    with patch.object(adm, "list_input_devices", return_value=[dev1, dev2]):
        adm.set_manual_device("Mic 1")
        assert len(callback_calls) >= 1
        assert callback_calls[-1].clean_name == "Mic 1"

        adm.set_manual_device("Mic 2")
        assert callback_calls[-1].clean_name == "Mic 2"


def test_test_device_audio():
    adm = AudioDeviceManager()

    sample_rate = 16000
    mock_audio = np.ones((int(1.0 * sample_rate), 1), dtype=np.float32) * 0.05

    with patch("sounddevice.rec", return_value=mock_audio) as mock_rec, \
         patch("sounddevice.wait"):
        result = adm.test_device_audio(device_index=1, duration=1.0)
        assert result["success"] is True
        assert result["rms"] > 0
        assert result["peak"] > 0
        assert "Audio captured successfully" in result["message"]


def test_speech_recognition_device_index_manual():
    adm = AudioDeviceManager()
    mic_list = ["Microsoft Sound Mapper - Input", "Microphone Array (Realtek)", "Blue Yeti USB Microphone"]

    mock_sr = MagicMock()
    mock_sr.Microphone.list_microphone_names.return_value = mic_list

    with patch.dict("sys.modules", {"speech_recognition": mock_sr}):
        # Without manual preference -> defaults to Realtek (or best score)
        adm.set_manual_device(None)
        best_sr = adm.get_best_sr_device_index()
        assert best_sr in (1, 2)

        # With manual preference -> returns Blue Yeti index 2
        adm.set_manual_device("Blue Yeti")
        best_sr = adm.get_best_sr_device_index()
        assert best_sr == 2


def test_settings_view_microphone_ui_and_persistence(tmp_path):
    """Integration test: SettingsView combo box population, manual selection, and persistence."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
voice:
  enabled: true
  voice_name: hi-IN-SwaraNeural
  preferred_microphone: auto
""")

    mock_core = MagicMock()
    mock_core.config_path = str(cfg_file)
    mock_core.config = {
        "voice": {
            "enabled": True,
            "voice_name": "hi-IN-SwaraNeural",
            "preferred_microphone": "auto",
        }
    }
    mock_core.learning_manager = None

    dev_bt = AudioDeviceInfo(
        index=0, name="Galaxy Buds (Bluetooth)", clean_name="Galaxy Buds (Bluetooth)",
        is_bluetooth=True, is_earbuds=True, is_usb=False, is_default=False,
        score=100, hostapi_name="WASAPI", max_input_channels=1, default_samplerate=16000.0
    )
    dev_usb = AudioDeviceInfo(
        index=1, name="Rode PodMic USB", clean_name="Rode PodMic USB",
        is_bluetooth=False, is_earbuds=False, is_usb=True, is_default=False,
        score=70, hostapi_name="WASAPI", max_input_channels=1, default_samplerate=48000.0
    )

    adm = AudioDeviceManager()
    with patch.object(adm, "get_unique_input_devices", return_value=[dev_bt, dev_usb]):
        view = SettingsView(jarvis_core=mock_core)

        # Check widgets exist
        assert hasattr(view, "combo_mic")
        assert hasattr(view, "btn_refresh_mic")
        assert hasattr(view, "btn_test_mic")
        assert hasattr(view, "mic_status")

        # Dropdown should have 3 items: Auto-Detect, Galaxy Buds, Rode PodMic
        assert view.combo_mic.count() == 3
        assert view.combo_mic.itemData(0) == "auto"
        assert view.combo_mic.itemData(1) == "Galaxy Buds (Bluetooth)"
        assert view.combo_mic.itemData(2) == "Rode PodMic USB"
        assert view.combo_mic.currentIndex() == 0  # Starts on auto

        # User selects Rode PodMic USB
        view.combo_mic.setCurrentIndex(2)
        assert view.combo_mic.currentData() == "Rode PodMic USB"

        # User saves settings
        view._save_settings()

        # Config should be updated
        assert mock_core.config["voice"]["preferred_microphone"] == "Rode PodMic USB"
        assert "✓ Active mic locked to: Rode PodMic USB" in view.mic_status.text()
        assert adm.get_manual_device() == "Rode PodMic USB"

        # Test Mic diagnostic simulation
        mock_result = {
            "success": True,
            "peak": 0.05,
            "rms": 0.02,
            "message": "Signal strong",
            "device_name": "Rode PodMic USB"
        }
        view._on_mic_test_done(mock_result)
        assert "Signal strong" in view.mic_status.text()
