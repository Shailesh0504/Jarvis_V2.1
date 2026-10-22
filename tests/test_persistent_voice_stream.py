# tests/test_persistent_voice_stream.py
"""
Unit tests for Persistent-but-Lightweight Audio Stream & Voice Listening Lifecycle.
Verifies continuous audio capture, energy-based VAD filtering, zero-flicker TTS echo suppression,
and mode transitions without opening/closing audio hardware per utterance.
"""

import struct
import time
import pytest

from voice.listener import PersistentAudioStream, VoiceListener, VoiceMode
from voice.stt import AdaptiveNoiseGate, NoiseGate, SpeechToText, TranscribeResult
from voice.wake_word import WakeWordDetector, WakeWordState


def _generate_pcm_frame(amplitude: int = 500, num_samples: int = 1024) -> bytes:
    """Generates synthetic 16-bit PCM audio frame."""
    return struct.pack(f"{num_samples}h", *([amplitude] * num_samples))


def test_persistent_audio_stream_lifecycle():
    """Verifies that PersistentAudioStream initializes and starts/stops cleanly in mock/simulated mode."""
    frames_received = []

    def on_frame(data: bytes):
        frames_received.append(data)

    stream = PersistentAudioStream(sample_rate=16000, chunk_size=1024, on_frame=on_frame)
    assert stream.is_active is False

    started = stream.start()
    assert started is True
    assert stream.is_active is True

    # Stop stream
    stream.stop()
    assert stream.is_active is False


def test_noise_gate_filters_silence():
    """Verifies that NoiseGate discards low-energy ambient noise below the threshold."""
    gate = NoiseGate(energy_threshold=250.0)

    silence_frame = _generate_pcm_frame(amplitude=50) # RMS ~ 50 < 250
    assert gate.is_speech(silence_frame) is False

    speech_frame = _generate_pcm_frame(amplitude=800)  # RMS ~ 800 >= 250
    assert gate.is_speech(speech_frame) is True


def test_adaptive_gate_detects_quiet_earbud_voice_without_accepting_silence():
    gate = AdaptiveNoiseGate(minimum_threshold=45.0, noise_ratio=1.8, initial_noise_floor=20.0)
    for _ in range(20):
        assert gate.is_speech(_generate_pcm_frame(amplitude=18)) is False
    assert gate.is_speech(_generate_pcm_frame(amplitude=70)) is True


def test_voice_listener_feed_frame_silence_discarded():
    """Verifies that silence frames are quickly discarded without calling STT transcription."""
    listener = VoiceListener(enable_audio_stream=False)
    silence_frame = _generate_pcm_frame(amplitude=30)

    # Feed 10 silence frames
    for _ in range(10):
        result = listener.feed_audio_frame(silence_frame)
        assert result is None

    assert listener._speech_in_progress is False
    assert len(listener._current_utterance_frames) == 0


def test_voice_listener_tts_suppression_drops_frames():
    """Verifies that during active TTS speech, audio frames are dropped with zero processing."""
    captured = []
    listener = VoiceListener(
        on_command_captured=lambda cmd: captured.append(cmd),
        enable_audio_stream=False
    )

    listener.set_tts_speaking(True)
    assert listener.is_suppressed() is True
    assert listener.state == WakeWordState.RESPONDING

    # Loud speech frame while TTS is speaking
    speech_frame = _generate_pcm_frame(amplitude=1200)
    for _ in range(5):
        res = listener.feed_audio_frame(speech_frame)
        assert res is None

    # Nothing should be buffered or captured
    assert len(listener._current_utterance_frames) == 0
    assert listener._speech_in_progress is False
    assert len(captured) == 0

    # End TTS speaking
    listener.set_tts_speaking(False)
    # Inside 0.4s cooldown window
    assert listener.is_suppressed() is True


def test_voice_listener_mode_switch_preserves_listener_state():
    """Verifies mode switching from STANDBY to ACTIVE and timeout back to STANDBY."""
    listener = VoiceListener(session_timeout=0.2, enable_audio_stream=False)
    listener.start_listening()

    assert listener.mode == VoiceMode.STANDBY
    assert listener.state == WakeWordState.IDLE

    # Switch to ACTIVE
    listener.set_mode(VoiceMode.ACTIVE)
    assert listener.mode == VoiceMode.ACTIVE
    assert listener.state == WakeWordState.LISTENING

    # Wait for session timeout
    time.sleep(0.35)
    assert listener.mode == VoiceMode.STANDBY
    assert listener.state == WakeWordState.IDLE

    listener.stop_listening()
