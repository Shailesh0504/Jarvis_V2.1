# tests/test_acknowledge_sound.py
"""
Regression tests for Acknowledge Sound / Wake Chime playback:
1. Verifies that the acknowledge chime targets the active output device (e.g. Earbuds / Headphones).
2. Verifies that the volume is set to a clear, audible level (0.90).
3. Verifies that InteractionGate triggers the acknowledge chime when commands are heard in active listening mode.
4. Verifies that VoiceListener triggers the acknowledge chime in ACTIVE mode when speech is captured.
5. Verifies that active dialogue barge-in triggers the acknowledge chime.
"""

from unittest.mock import MagicMock, patch
import pytest

import voice.chime as chime
from core.interaction_gate import InteractionGate, InteractionState
from voice.listener import VoiceListener, VoiceMode


def test_chime_routes_to_best_pygame_device():
    """Verifies that chime._play_wake_chime_sync passes the active SDL2 audio device to pygame.mixer.init."""
    fake_pygame = MagicMock()
    fake_pygame.mixer.get_init.return_value = False
    fake_dm_module = MagicMock()
    fake_dm_module.AudioDeviceManager.return_value.get_best_pygame_output_devicename.return_value = "Headphones (CMF Buds 2)"

    with patch.dict("sys.modules", {"pygame": fake_pygame, "voice.device_manager": fake_dm_module}):
        chime._cached_wake_sound = None
        chime._play_wake_chime_sync()
        fake_pygame.mixer.init.assert_called_once()
        kwargs = fake_pygame.mixer.init.call_args[1]
        assert kwargs.get("devicename") == "Headphones (CMF Buds 2)"


def test_chime_volume_level():
    """Verifies that the chime volume is set to 0.90 for clear acoustic audibility."""
    fake_pygame = MagicMock()
    fake_pygame.mixer.get_init.return_value = True
    sound = fake_pygame.mixer.Sound.return_value

    with patch.dict("sys.modules", {"pygame": fake_pygame}):
        chime._cached_wake_sound = None
        chime._play_wake_chime_sync()
        sound.set_volume.assert_called_once_with(0.90)


def test_interaction_gate_plays_chime_on_active_listening_command():
    """Verifies that InteractionGate triggers the acknowledge chime on commands spoken during an active session."""
    gate = InteractionGate()
    # User activates wake word
    d1 = gate.evaluate("Jarvis")
    assert d1.accepted is True
    assert gate.state == InteractionState.LISTENING

    # User speaks follow-up command while in active listening state
    with patch("voice.chime.play_wake_chime_async") as mock_chime:
        dec = gate.evaluate("chrome kholo")
        assert dec.accepted is True
        assert dec.command == "chrome kholo"
        assert mock_chime.called is True


def test_interaction_gate_plays_chime_on_barge_in():
    """Verifies that active dialogue barge-in triggers the acknowledge chime."""
    gate = InteractionGate(barge_in_enabled=True)
    gate.set_tts_speaking(True)

    with patch("voice.chime.play_wake_chime_async") as mock_chime:
        dec = gate.evaluate("Jarvis Brave kholo")
        assert dec.accepted is True
        assert dec.is_barge_in is True
        assert mock_chime.called is True


def test_voice_listener_active_mode_triggers_chime():
    """Verifies that VoiceListener in ACTIVE mode triggers the acknowledge chime when a command is captured."""
    captured = []
    listener = VoiceListener(on_command_captured=lambda c: captured.append(c))
    listener.set_mode(VoiceMode.ACTIVE)

    with patch("voice.chime.play_wake_chime_async") as mock_chime:
        res = listener.process_utterance("open notepad")
        assert res.detected is True
        assert mock_chime.called is True
        assert "open notepad" in captured
