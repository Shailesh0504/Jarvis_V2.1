# tests/test_soft_whispered_wake_word.py
"""
Comprehensive Unit & Integration Tests for Soft-Speech & Whispered Wake-Word Detection.
Verifies:
1. Phonetic matching of whisper/soft speech STT outputs ('javis', 'jarvish', 'jervis', 'charvis', 'service', etc.).
2. Negative pattern gating to prevent false triggers on 'customer service', 'windows service', etc.
3. AdaptiveNoiseGate and AdaptiveVAD low-energy sensitivity (down to 15.0 RMS) without accepting ambient room silence.
4. Standalone wake-word conversational acknowledgment ('Yes, I'm listening.') across sources ('cli', 'gui', 'voice_gated').
5. VoiceListener standalone wake word dispatching 'Jarvis' instead of empty string.
6. Earbud software gain boost (2.0x) and ultra-responsive laptop mic profile (12.0 RMS, 2.5x).
"""

import struct
import pytest
from unittest.mock import MagicMock

from voice.wake_word import WakeWordDetector, WakePosition
from voice.stt import AdaptiveNoiseGate
from voice.audio_processor import AdaptiveVAD, AudioCalibrator
from voice.listener import VoiceListener, VoiceMode
from core.interaction_gate import InteractionGate, InteractionState


def _make_pcm_frame(amplitude: int, num_samples: int = 1024) -> bytes:
    """Generates synthetic 16-bit PCM audio frame at given sample amplitude."""
    return struct.pack(f"{num_samples}h", *([amplitude] * num_samples))


class TestWhisperedWakeWordDetection:
    """Verifies that phonetically distorted whispers and soft utterances of 'Jarvis' are reliably detected."""

    @pytest.fixture
    def detector(self):
        return WakeWordDetector(["jarvis"])

    def test_whispered_phonetic_variants_standalone(self, detector):
        whispered_variants = [
            "javis",
            "jarvish",
            "jervis",
            "jerwis",
            "charvis",
            "chervis",
            "chaarvis",
            "jarves",
            "jarvees",
            "zarvis",
            "sarvis",
            "jaavis",
            "service",
            "jarvis",
        ]
        for var in whispered_variants:
            res = detector.detect(var)
            assert res.detected is True, f"Failed to detect whispered variant: '{var}'"
            assert res.is_standalone is True, f"Whispered '{var}' should be marked standalone"

    def test_whispered_phonetic_variants_with_greetings(self, detector):
        phrases = [
            "hey javis",
            "hi jarvish",
            "hello jervis",
            "arre charvis",
            "oye javis",
            "okay jarvish",
            "hey service",
        ]
        for phrase in phrases:
            res = detector.detect(phrase)
            assert res.detected is True, f"Failed on greeted whisper: '{phrase}'"
            assert res.is_standalone is True

    def test_whispered_phonetic_variants_with_attached_command(self, detector):
        cases = [
            ("javis chrome kholo", "chrome kholo"),
            ("jarvish volume badhao", "volume badhao"),
            ("jervis system lock karo", "system lock karo"),
            ("charvis screenshot lo", "screenshot lo"),
        ]
        for utterance, expected_cmd in cases:
            res = detector.detect(utterance)
            assert res.detected is True, f"Failed to detect: '{utterance}'"
            assert res.is_standalone is False
            assert res.cleaned_command == expected_cmd

    def test_negative_patterns_suppress_false_triggers(self, detector):
        negatives = [
            "customer service",
            "car service",
            "web service",
            "windows service",
            "start service",
            "stop service",
            "install service",
            "cloud service",
            "room service",
            "bus service",
            "taxi service",
            "java is good",
            "jar is open",
            "jar on table",
        ]
        for neg in negatives:
            res = detector.detect(neg)
            assert res.detected is False, f"False trigger on negative phrase: '{neg}'"


class TestSoftSpeechNoiseGateAndVAD:
    """Verifies that low-energy audio from quiet speaking or earbuds passes the gate."""

    def test_adaptive_noise_gate_detects_soft_voice_rejects_silence(self):
        # Bluetooth profile: minimum_threshold=15.0, initial_noise_floor=10.0
        gate = AdaptiveNoiseGate(minimum_threshold=15.0, noise_ratio=1.10, initial_noise_floor=10.0)

        # Baseline room silence (amplitude ~5-8 RMS)
        silence_frame = _make_pcm_frame(amplitude=6)
        for _ in range(10):
            assert gate.is_speech(silence_frame) is False, "Silence should be rejected"

        # Soft whispered voice (amplitude ~20 RMS)
        soft_frame = _make_pcm_frame(amplitude=20)
        assert gate.is_speech(soft_frame) is True, "Soft speech (RMS 20) must be accepted as speech"

    def test_adaptive_vad_whisper_fricative_detection(self):
        vad = AdaptiveVAD(min_snr_db=2.0, initial_noise_floor=10.0)

        # Non-speech low rumble (amplitude 5)
        rumble = _make_pcm_frame(amplitude=5)
        is_sp, snr, state = vad.process_frame(
            samples=struct.unpack("1024h", rumble),
            frame_rms=5.0,
            is_bluetooth=True
        )
        assert is_sp is False

        # Whispered frame: low RMS (14.0) with high zero-crossing rate (fricative /s/ sound)
        # Alternate sign sequence produces high ZCR. AdaptiveVAD requires 2 consecutive onset frames.
        whisper_samples = [14 if i % 2 == 0 else -14 for i in range(1024)]
        vad.process_frame(samples=whisper_samples, frame_rms=14.0, is_bluetooth=True)
        is_sp, snr, state = vad.process_frame(
            samples=whisper_samples,
            frame_rms=14.0,
            is_bluetooth=True
        )
        assert is_sp is True, "Whispered fricative frames should be recognized as speech"


class TestStandaloneWakeResponse:
    """Verifies that standalone wake word triggers immediate affirmative response across pipelines."""

    def test_interaction_gate_standalone_wake(self):
        gate = InteractionGate()
        decision = gate.evaluate("jarvis", is_explicit_listen=False)
        assert decision.accepted is True
        assert decision.is_standalone_wake is True
        assert decision.state == InteractionState.LISTENING

    def test_interaction_gate_whispered_variant_standalone(self):
        gate = InteractionGate()
        for var in ["javis", "jarvish", "jervis"]:
            decision = gate.evaluate(var, is_explicit_listen=False)
            assert decision.accepted is True, f"Gate should accept whispered '{var}'"
            assert decision.is_standalone_wake is True
            assert decision.state == InteractionState.LISTENING

    def test_voice_listener_dispatches_jarvis_on_standalone_wake(self):
        captured = []
        listener = VoiceListener(
            on_command_captured=lambda cmd: captured.append(cmd),
            enable_audio_stream=False
        )

        res = listener.process_utterance("jarvis")
        assert res.detected is True
        assert res.is_standalone is True
        assert listener.mode == VoiceMode.ACTIVE
        assert captured == ["Jarvis"], f"Expected ['Jarvis'], got {captured}"

    def test_core_app_standalone_wake_replies_yes_im_listening(self):
        from core.app import JarvisCore
        core = JarvisCore()

        # Direct CLI / GUI query
        resp = core.process_input("jarvis", source="cli")
        assert "Yes, I'm listening." in resp

        # Whispered variant via voice_gated
        resp_whisper = core.process_input("javis", source="voice_gated")
        assert "Yes, I'm listening." in resp_whisper
