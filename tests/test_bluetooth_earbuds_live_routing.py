# tests/test_bluetooth_earbuds_live_routing.py
"""
Comprehensive test suite verifying live Bluetooth Earbuds connection detection,
automatic prioritization, dual audio routing (MIC input + TTS output), physical headset
pairing recognition, honest capability feedback, thread-safe state machine,
and seamless graceful fallback when disconnected.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from voice.device_manager import (
    AudioDeviceManager,
    AudioDeviceInfo,
    PhysicalAudioHeadset,
    DeviceRole,
    AudioConnectionState,
    extract_base_headset_identity,
)
from voice.tts import TextToSpeech, TTSManager
from voice.listener import PersistentAudioStream, VoiceListener, VoiceMode
from core.context import RuntimeContext
from core.event_bus import EventBus, EventTopics, AudioDeviceChanged


class TestBluetoothEarbudsDualRouting:
    """Tests for Bluetooth Earbuds live hot-plug detection, pairing, and dual audio routing."""

    def setup_method(self):
        # Reset AudioDeviceManager singleton state between tests
        adm = AudioDeviceManager()
        adm.stop_hotplug_watcher()
        adm._device_change_callbacks.clear()
        adm._output_device_change_callbacks.clear()
        adm._topology_change_callbacks.clear()
        adm._cached_devices.clear()
        adm._cached_output_devices.clear()
        adm._last_scan_time = 0.0
        adm._last_output_scan_time = 0.0
        adm._last_detected_identity = None
        adm._last_detected_output_identity = None
        adm._last_detected_pygame_output = None
        adm._active_headset = None
        adm._active_input_device = None
        adm._active_output_device = None
        adm._fallback_input_device = None
        adm._fallback_output_device = None
        adm._connection_state = AudioConnectionState.STABLE
        adm.auto_switch_headset = True
        adm.preferred_headset = "auto"
        adm.restore_previous_device = True
        adm.announce_device_changes = True
        adm._tts_engine = None

    def teardown_method(self):
        AudioDeviceManager().stop_hotplug_watcher()

    # --- Test A: Headset Identity Extraction & Normalization ---
    def test_extract_base_headset_identity(self):
        test_cases = [
            ("Headset (CMF Buds 2)", "CMF Buds 2"),
            ("Headphones (CMF Buds 2)", "CMF Buds 2"),
            ("@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0 ;(CMF Buds 2)", "CMF Buds 2"),
            ("CMF Buds 2 Hands-Free AG Audio", "CMF Buds 2"),
            ("CMF Buds 2 Stereo", "CMF Buds 2"),
            ("Headphones (AirPods Pro)", "AirPods Pro"),
            ("Headset (AirPods Pro)", "AirPods Pro"),
            ("Sony WF-1000XM5 Hands-Free AG Audio", "Sony WF-1000XM5"),
            ("boAt Airdopes 141 (Bluetooth)", "boAt Airdopes 141"),
        ]
        for raw, expected in test_cases:
            assert extract_base_headset_identity(raw) == expected, f"Failed for {raw}: got {extract_base_headset_identity(raw)}"

    # --- Test B: Device Role Classification ---
    def test_device_role_classification(self):
        adm = AudioDeviceManager()
        earbuds_in = AudioDeviceInfo(
            index=1,
            name="Headset (CMF Buds 2)",
            clean_name="Headset (CMF Buds 2)",
            is_bluetooth=True,
            is_earbuds=True,
            is_usb=False,
            is_default=False,
            score=105,
            hostapi_name="Windows WASAPI",
            max_input_channels=1,
            is_output=False
        )
        roles_in = adm.classify_device_roles(earbuds_in)
        assert DeviceRole.INPUT in roles_in
        assert DeviceRole.MICROPHONE in roles_in
        assert DeviceRole.BLUETOOTH in roles_in
        assert DeviceRole.HEADSET in roles_in
        assert DeviceRole.EARBUD in roles_in

        speaker_out = AudioDeviceInfo(
            index=2,
            name="Speakers (Realtek(R) Audio)",
            clean_name="Speakers (Realtek(R) Audio)",
            is_bluetooth=False,
            is_earbuds=False,
            is_usb=False,
            is_default=True,
            score=50,
            hostapi_name="Windows WASAPI",
            max_output_channels=2,
            is_output=True
        )
        roles_out = adm.classify_device_roles(speaker_out)
        assert DeviceRole.OUTPUT in roles_out
        assert DeviceRole.SPEAKER in roles_out
        assert DeviceRole.DEFAULT in roles_out
        assert DeviceRole.BLUETOOTH not in roles_out

    # --- Test C: Physical Headset Pairing Recognition ---
    def test_physical_headset_pairing_recognition(self):
        adm = AudioDeviceManager()
        mock_inputs = [
            AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            AudioDeviceInfo(2, "Microphone (Realtek)", "Microphone (Realtek)", False, False, False, True, 50, "WASAPI", 2, 48000.0, 0, False),
        ]
        mock_outputs = [
            AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            AudioDeviceInfo(5, "Speakers (Realtek)", "Speakers (Realtek)", False, False, False, True, 50, "WASAPI", 0, 48000.0, 2, True),
        ]

        with patch.object(adm, "list_input_devices", return_value=mock_inputs), \
             patch.object(adm, "list_output_devices", return_value=mock_outputs):
            headsets = adm.get_paired_physical_headsets(force_refresh=True)

            assert len(headsets) == 1
            cmf = headsets[0]
            assert cmf.base_name == "CMF Buds 2"
            assert cmf.has_microphone is True
            assert cmf.has_speaker is True
            assert cmf.input_device.index == 14
            assert cmf.output_device.index == 13

    # --- Test D: Dual Switch on Headset Connect ---
    def test_dual_switch_on_headset_connect(self):
        adm = AudioDeviceManager()
        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )

        adm._handle_headset_connected(headset)

        assert adm.get_audio_state() == AudioConnectionState.ACTIVE_HEADSET
        assert adm.get_active_headset() == headset
        assert adm.get_active_input_device().index == 14
        assert adm.get_active_output_device().index == 13

    # --- Test E: Honest Degradation (Output Only) ---
    def test_honest_degradation_output_only(self):
        adm = AudioDeviceManager()
        fallback_mic = AudioDeviceInfo(2, "Microphone (Realtek)", "Microphone (Realtek)", False, False, False, True, 50, "WASAPI", 2, 48000.0, 0, False)
        adm._fallback_input_device = fallback_mic

        output_only_headset = PhysicalAudioHeadset(
            hardware_id="bt_speaker",
            base_name="Bluetooth Speaker",
            display_name="Bluetooth Speaker",
            input_device=None,
            output_device=AudioDeviceInfo(10, "Bluetooth Speaker", "Bluetooth Speaker", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=False,
            has_speaker=True
        )

        adm._handle_headset_connected(output_only_headset)

        # Output switched to headset, but input remains fallback mic
        assert adm.get_active_output_device().index == 10
        assert adm.get_active_input_device().index == 2

        # Check announcement mentions mic not available
        msg = adm.generate_connection_announcement(output_only_headset, is_connected=True)
        assert "microphone available nahi hai" in msg

    # --- Test F: State Machine Lifecycle Transitions ---
    def test_state_machine_transitions(self):
        adm = AudioDeviceManager()
        assert adm.get_audio_state() == AudioConnectionState.STABLE

        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )

        adm._handle_headset_connected(headset)
        assert adm.get_audio_state() == AudioConnectionState.ACTIVE_HEADSET

        adm._handle_headset_disconnected()
        assert adm.get_audio_state() == AudioConnectionState.STABLE

    # --- Test G: EventBus AudioDeviceChanged Published ---
    def test_eventbus_audio_device_changed_published(self):
        adm = AudioDeviceManager()
        bus = EventBus()
        adm.set_event_bus(bus)
        published_events = []

        def on_event(event):
            published_events.append(event)

        bus.subscribe(EventTopics.AUDIO_DEVICE_CHANGED, on_event)

        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )

        adm._handle_headset_connected(headset)

        assert len(published_events) >= 1
        last_event = published_events[-1]
        assert last_event.event_type == "headset_connected"
        assert "CMF Buds 2" in last_event.device_name
        assert last_event.is_bluetooth is True
        assert last_event.input_index == 14
        assert last_event.output_index == 13

        # Test disconnect publication
        adm._handle_headset_disconnected()
        disconn_event = published_events[-1]
        assert disconn_event.event_type == "headset_disconnected"

        bus.unsubscribe(EventTopics.AUDIO_DEVICE_CHANGED, on_event)

    # --- Test H: RuntimeContext Audio State Updated ---
    def test_runtime_context_audio_updated(self):
        adm = AudioDeviceManager()
        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )

        adm._handle_headset_connected(headset)

        ctx = RuntimeContext.get_instance()
        assert ctx.audio.is_headset_connected is True
        assert ctx.audio.headset_name == "CMF Buds 2"
        assert ctx.audio.connection_state == "active_headset"
        assert ctx.audio.has_microphone is True
        assert ctx.audio.has_speaker is True

        adm._handle_headset_disconnected()
        assert ctx.audio.is_headset_connected is False
        assert ctx.audio.headset_name is None

    # --- Test I: Natural Hinglish Announcements ---
    def test_natural_hinglish_announcements(self):
        adm = AudioDeviceManager()

        # Dual channel headset
        headset_full = PhysicalAudioHeadset("cmf", "CMF Buds 2", "CMF Buds 2", has_microphone=True, has_speaker=True)
        msg_full = adm.generate_connection_announcement(headset_full, is_connected=True)
        assert msg_full == "Ji, earbuds connect ho gaye. Ab main earbuds se sununga aur wahi par bolunga."

        # Speaker only headset
        headset_spk = PhysicalAudioHeadset("cmf", "CMF Buds 2", "CMF Buds 2", has_microphone=False, has_speaker=True)
        msg_spk = adm.generate_connection_announcement(headset_spk, is_connected=True)
        assert msg_spk == "Ji, earbuds connect ho gaye hain, lekin microphone available nahi hai. Main current microphone use kar raha hoon."

        # Mic only headset
        headset_mic = PhysicalAudioHeadset("cmf", "CMF Buds 2", "CMF Buds 2", has_microphone=True, has_speaker=False)
        msg_mic = adm.generate_connection_announcement(headset_mic, is_connected=True)
        assert msg_mic == "Ji, earbuds microphone connect ho gaya hai. Output current speaker par rahega."

        # Disconnect
        msg_disc = adm.generate_connection_announcement(None, is_connected=False)
        assert msg_disc == "Ji, earbuds disconnect ho gaye. Main default microphone aur speaker par aa gaya hoon."

    # --- Test J: Graceful Fallback on Disconnect ---
    def test_graceful_fallback_on_disconnect(self):
        adm = AudioDeviceManager()
        fallback_mic = AudioDeviceInfo(2, "Microphone (Realtek)", "Microphone (Realtek)", False, False, False, True, 50, "WASAPI", 2, 48000.0, 0, False)
        fallback_spk = AudioDeviceInfo(5, "Speakers (Realtek)", "Speakers (Realtek)", False, False, False, True, 50, "WASAPI", 0, 48000.0, 2, True)
        adm._fallback_input_device = fallback_mic
        adm._fallback_output_device = fallback_spk

        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )

        adm._handle_headset_connected(headset)
        assert adm.get_active_input_device().index == 14
        assert adm.get_active_output_device().index == 13

        with patch.object(adm, "list_input_devices", return_value=[fallback_mic]), \
             patch.object(adm, "list_output_devices", return_value=[fallback_spk]):
            adm._handle_headset_disconnected()

            assert adm.get_active_input_device().index == 2
            assert adm.get_active_output_device().index == 5
            assert adm.get_active_headset() is None

    # --- Test K: COM Endpoint Notification Debounce Mock ---
    def test_com_endpoint_notification_debounce(self):
        adm = AudioDeviceManager()
        trigger_count = 0

        def mock_refresh():
            nonlocal trigger_count
            trigger_count += 1

        adm._trigger_device_refresh = mock_refresh

        # Simulate 5 rapid COM events within 50ms
        for i in range(5):
            adm._on_windows_endpoint_event("state_changed", f"device_{i}")
            time.sleep(0.01)

        # Before debounce (300ms), refresh should NOT have fired yet
        assert trigger_count == 0

        # Wait for debounce timer to fire
        time.sleep(0.4)
        assert trigger_count == 1

    # --- Test L: Device Validation Helpers ---
    def test_device_validation_helpers(self):
        adm = AudioDeviceManager()
        # Invalid index returns False without raising exception
        assert adm.validate_input_device(-9999) is False
        assert adm.validate_output_device(-9999) is False

    # --- Test M: Architectural SSOT from core.audio ---
    def test_ssot_core_audio_module(self):
        from core.audio import AudioDeviceManager as CoreADM, PhysicalAudioHeadset as CorePAH
        from voice.device_manager import AudioDeviceManager as VoiceADM, PhysicalAudioHeadset as VoicePAH

        assert CoreADM is VoiceADM
        assert CorePAH is VoicePAH

    # --- Existing Regression Tests Preserved ---
    @patch("sounddevice.query_devices")
    @patch("sounddevice.query_hostapis")
    def test_output_devices_prioritizes_bluetooth_earbuds(self, mock_hostapis, mock_devices):
        mock_hostapis.return_value = [
            {"name": "MME"},
            {"name": "Windows WASAPI"}
        ]
        mock_devices.return_value = [
            {"name": "Speakers (Realtek(R) Audio)", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 48000.0},
            {"name": "Headphones (CMF Buds 2)", "max_output_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
            {"name": "Microsoft Sound Mapper - Output", "max_output_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        ]

        adm = AudioDeviceManager()
        outputs = adm.list_output_devices(force_refresh=True)

        assert len(outputs) == 3
        best = adm.get_best_output_device(force_refresh=True)
        assert best is not None
        assert best.is_bluetooth is True
        assert "CMF Buds 2" in best.clean_name
        assert best.score >= 100

    @patch("pygame._sdl2.audio.get_audio_device_names")
    def test_pygame_output_devicename_resolution(self, mock_sdl_names):
        mock_sdl_names.return_value = [
            "Speakers (Realtek(R) Audio)",
            "Headphones (CMF Buds 2)"
        ]

        adm = AudioDeviceManager()
        best_pygame_name = adm.get_best_pygame_output_devicename(force_refresh=True)

        assert best_pygame_name == "Headphones (CMF Buds 2)"

    def test_tts_engine_output_device_switch_mock(self):
        tts = TextToSpeech(engine="mock")
        assert tts._current_output_device_name is None

        success = tts.switch_output_device("Headphones (CMF Buds 2)")
        assert success is True
        assert tts._current_output_device_name == "Headphones (CMF Buds 2)"

        success = tts.switch_output_device(None)
        assert success is True
        assert tts._current_output_device_name is None

    def test_tts_manager_automatic_listener_registration_and_dispatch(self):
        adm = AudioDeviceManager()
        tts = TextToSpeech(engine="mock")
        manager = TTSManager(tts_engine=tts)

        assert manager._on_output_device_changed in adm._output_device_change_callbacks

        earbuds_dev = AudioDeviceInfo(
            index=13,
            name="Headphones (CMF Buds 2)",
            clean_name="Headphones (CMF Buds 2)",
            is_bluetooth=True,
            is_earbuds=True,
            is_usb=False,
            is_default=False,
            score=105,
            hostapi_name="Windows WASAPI",
            max_output_channels=2,
            is_output=True
        )
        adm._notify_output_device_changed(earbuds_dev, "Headphones (CMF Buds 2)")

        assert tts._current_output_device_name == "Headphones (CMF Buds 2)"

        speakers_dev = AudioDeviceInfo(
            index=5,
            name="Speakers (Realtek(R) Audio)",
            clean_name="Speakers (Realtek(R) Audio)",
            is_bluetooth=False,
            is_earbuds=False,
            is_usb=False,
            is_default=True,
            score=50,
            hostapi_name="Windows WASAPI",
            max_output_channels=2,
            is_output=True
        )
        adm._notify_output_device_changed(speakers_dev, None)
        assert tts._current_output_device_name is None

        manager.shutdown()
        assert manager._on_output_device_changed not in adm._output_device_change_callbacks

    def test_unified_topology_summary_contains_both_input_and_output(self):
        adm = AudioDeviceManager()
        summary = adm.get_status_summary()

        assert "earbuds_connected" in summary
        assert "earbuds_input_name" in summary
        assert "earbuds_output_name" in summary
        assert "active_device_name" in summary
        assert "active_output_name" in summary
        assert "pygame_output_name" in summary
        assert "total_input_devices" in summary
        assert "total_output_devices" in summary
        assert "connection_state" in summary

    def test_hotplug_watcher_dispatches_topology_and_output_events(self):
        adm = AudioDeviceManager()
        events_received = []

        def on_topology(summary):
            events_received.append(summary)

        adm.register_topology_change_listener(on_topology)

        test_summary = {"status": "earbuds_connected", "active_output_name": "Headphones (CMF Buds 2)"}
        adm._notify_topology_changed(test_summary)

        assert len(events_received) == 1
        assert events_received[0]["active_output_name"] == "Headphones (CMF Buds 2)"

        adm.unregister_topology_change_listener(on_topology)
        adm._notify_topology_changed(test_summary)
        assert len(events_received) == 1

    def test_voice_listener_noise_gate_adapts_for_earbuds(self):
        listener = VoiceListener(enable_audio_stream=False)

        eb_dev = AudioDeviceInfo(
            index=1,
            name="Headset (CMF Buds 2)",
            clean_name="Headset (CMF Buds 2)",
            is_bluetooth=True,
            is_earbuds=True,
            is_usb=False,
            is_default=False,
            score=105,
            hostapi_name="Windows WASAPI",
            max_input_channels=1
        )
        listener._on_audio_device_changed(eb_dev)
        assert listener.noise_gate.minimum_threshold == 15.0
        assert listener.noise_gate.noise_ratio == 1.10

        int_dev = AudioDeviceInfo(
            index=2,
            name="Microphone (Realtek(R) Audio)",
            clean_name="Microphone (Realtek(R) Audio)",
            is_bluetooth=False,
            is_earbuds=False,
            is_usb=False,
            is_default=True,
            score=50,
            hostapi_name="Windows WASAPI",
            max_input_channels=2
        )
        listener._on_audio_device_changed(int_dev)
        assert listener.noise_gate.minimum_threshold == 12.0
        assert listener.noise_gate.noise_ratio == 1.08

    def test_audio_device_status_inquiry_fast_path(self):
        from core.app import JarvisCore
        core = JarvisCore()

        adm = AudioDeviceManager()
        headset = PhysicalAudioHeadset(
            hardware_id="cmf_buds_2",
            base_name="CMF Buds 2",
            display_name="CMF Buds 2",
            input_device=AudioDeviceInfo(14, "Headset (CMF Buds 2)", "Headset (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 1, 16000.0, 0, False),
            output_device=AudioDeviceInfo(13, "Headphones (CMF Buds 2)", "Headphones (CMF Buds 2)", True, True, False, False, 105, "WASAPI", 0, 48000.0, 2, True),
            has_microphone=True,
            has_speaker=True
        )
        adm._handle_headset_connected(headset)

        # 1. Ask in Hindi/Hinglish
        resp_hi = core.process_input("kaunse mic se sun rahe ho")
        assert "CMF Buds 2" in resp_hi
        assert "microphone se sun raha hoon" in resp_hi

        # 2. Ask in English
        resp_en = core.process_input("which microphone are you using")
        assert "CMF Buds 2" in resp_en
        assert "listening through" in resp_en
