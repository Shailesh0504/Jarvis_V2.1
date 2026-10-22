# tests/test_audio_device_manager.py
"""Unit tests for AudioDeviceManager and Bluetooth Earbuds prioritization."""

import pytest
from unittest.mock import MagicMock, patch

from voice.device_manager import (
    AudioDeviceManager,
    AudioDeviceInfo,
    BLUETOOTH_KEYWORDS,
    EXCLUDED_INPUT_KEYWORDS,
)
from voice.listener import PersistentAudioStream, VoiceListener, VoiceMode


class TestAudioDeviceManager:
    """Test suite for intelligent audio input device discovery and prioritization."""

    def test_singleton_instance(self):
        adm1 = AudioDeviceManager()
        adm2 = AudioDeviceManager()
        assert adm1 is adm2

    def test_clean_device_name_windows_driver_format(self):
        adm = AudioDeviceManager()
        raw = "@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0 ;(CMF Buds 2)"
        cleaned = adm.clean_device_name(raw)
        assert "CMF Buds 2" in cleaned
        assert "Bluetooth" in cleaned

    def test_clean_device_name_standard(self):
        adm = AudioDeviceManager()
        raw = "Headset (boAt Rockerz 450 Hands-Free AG Audio)"
        cleaned = adm.clean_device_name(raw)
        assert cleaned == "Headset (boAt Rockerz 450 Hands-Free AG Audio)"

    def test_is_bluetooth_device_recognition(self):
        adm = AudioDeviceManager()
        assert adm.is_bluetooth_device("Headset (CMF Buds 2)") is True
        assert adm.is_bluetooth_device("AirPods Hands-Free Audio") is True
        assert adm.is_bluetooth_device("Galaxy Buds Pro") is True
        assert adm.is_bluetooth_device("boAt Rockerz 550") is True
        assert adm.is_bluetooth_device("Sony WH-1000XM4 Hands-Free") is True
        assert adm.is_bluetooth_device("OnePlus Buds Z") is True
        assert adm.is_bluetooth_device("Microphone (Realtek(R) Audio)") is False

    def test_calculate_priority_score(self):
        adm = AudioDeviceManager()
        
        # Bluetooth Earbuds get top score (>= 100)
        earbuds_score = adm.calculate_priority_score("Headset (CMF Buds 2)", is_default=False, hostapi_name="Windows WASAPI")
        assert earbuds_score >= 105

        # USB mic gets 70
        usb_score = adm.calculate_priority_score("Yeti Stereo Microphone", is_default=False)
        assert usb_score == 70

        # Default system mic gets 50
        def_score = adm.calculate_priority_score("Microphone (Realtek Audio)", is_default=True)
        assert def_score == 50

        # Non-default internal mic gets 30
        internal_score = adm.calculate_priority_score("Microphone (Realtek Audio)", is_default=False)
        assert internal_score == 30

        # Excluded / virtual devices get 0
        stereo_mix_score = adm.calculate_priority_score("Stereo Mix (Realtek)", is_default=False)
        assert stereo_mix_score == 0

    @patch("sounddevice.query_devices")
    @patch("sounddevice.query_hostapis")
    def test_list_input_devices_prioritizes_earbuds(self, mock_hostapis, mock_devices):
        mock_hostapis.return_value = [
            {"name": "MME", "default_input_device": 0},
            {"name": "Windows WASAPI", "default_input_device": 1}
        ]
        mock_devices.return_value = [
            {"name": "Microphone (Realtek Audio)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
            {"name": "Headset (CMF Buds 2)", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 16000.0},
            {"name": "Stereo Mix", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        ]

        adm = AudioDeviceManager()
        devices = adm.list_input_devices(force_refresh=True)

        assert len(devices) == 3
        # First device must be the earbuds
        best = devices[0]
        assert best.is_bluetooth is True
        assert "CMF Buds 2" in best.name
        assert best.score >= 100

    def test_get_status_summary(self):
        adm = AudioDeviceManager()
        summary = adm.get_status_summary()
        assert "earbuds_connected" in summary
        assert "active_device_name" in summary
        assert "total_input_devices" in summary

    def test_hotplug_callback_registration(self):
        adm = AudioDeviceManager()
        received = []

        def dummy_cb(dev):
            received.append(dev)

        adm.register_device_change_listener(dummy_cb)
        assert dummy_cb in adm._device_change_callbacks

        adm.unregister_device_change_listener(dummy_cb)
        assert dummy_cb not in adm._device_change_callbacks


class TestPersistentAudioStreamDeviceRouting:
    """Test suite verifying audio stream routes to prioritized devices."""

    def test_persistent_stream_init_with_device(self):
        stream = PersistentAudioStream(sample_rate=16000, chunk_size=1024, device=2)
        assert stream.device == 2
        assert stream.is_active is False

    @patch("sounddevice.RawInputStream")
    def test_persistent_stream_start_sounddevice(self, mock_raw_input):
        mock_instance = MagicMock()
        mock_raw_input.return_value = mock_instance

        stream = PersistentAudioStream(sample_rate=16000, chunk_size=1024, device=14)
        started = stream.start(device=14)

        assert started is True
        assert stream.is_active is True
        mock_raw_input.assert_called_once()
        _, kwargs = mock_raw_input.call_args
        assert kwargs.get("device") == 14
        assert kwargs.get("samplerate") == 16000

        stream.stop()
        assert stream.is_active is False
        mock_instance.stop.assert_called_once()
        mock_instance.close.assert_called_once()

    @patch("sounddevice.query_devices")
    @patch("sounddevice.query_hostapis")
    def test_get_fallback_or_internal_input_device(self, mock_hostapis, mock_devices):
        mock_hostapis.return_value = [
            {"name": "MME", "default_input_device": 0},
            {"name": "Windows WASAPI", "default_input_device": 1}
        ]
        mock_devices.return_value = [
            {"name": "Headset (CMF Buds 2)", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 16000.0},
            {"name": "Microphone Array (Intel SST)", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        ]
        adm = AudioDeviceManager()
        fallback = adm.get_fallback_or_internal_input_device(force_refresh=True)
        assert fallback is not None
        assert fallback.is_bluetooth is False
        assert "Microphone Array" in fallback.clean_name

    @patch("sounddevice.rec")
    @patch("sounddevice.wait")
    def test_device_audio_measurement_safe_rms(self, mock_wait, mock_rec):
        import numpy as np
        adm = AudioDeviceManager()
        # Mock high amplitude float32 PCM to verify no RuntimeWarning overflow occurs
        mock_rec.return_value = np.array([0.5, -0.5, 0.8, -0.8], dtype=np.float32)
        res = adm.test_device_audio(device_index=1, duration=0.1)
        assert res["success"] is True
        assert res["rms"] > 0
        assert res["rms"] != float("inf")

    @patch("voice.device_manager.AudioDeviceManager.get_fallback_or_internal_input_device")
    def test_report_silent_device_suppression_and_fallback(self, mock_fallback):
        adm = AudioDeviceManager()
        mock_fb_dev = AudioDeviceInfo(
            index=2,
            name="Microphone Array",
            clean_name="Microphone Array",
            is_bluetooth=False,
            is_earbuds=False,
            is_usb=False,
            is_default=True,
            score=50,
            hostapi_name="MME"
        )
        mock_fallback.return_value = mock_fb_dev

        adm.report_silent_device(1)
        assert 1 in adm._suppressed_silent_devices
        assert adm.get_active_input_device() == mock_fb_dev

    def test_ensure_device_unmuted_execution(self):
        adm = AudioDeviceManager()
        # Should execute cleanly without throwing exceptions
        result = adm.ensure_device_unmuted(force=True)
        assert isinstance(result, bool)

