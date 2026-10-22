# tests/test_standalone_wake_echo_prevention.py
"""
Tests for standalone wake word reply and acoustic echo prevention:
1. Saying 'Jarvis' triggers standalone wake response 'Yes, I'm listening.' and transitions gate to LISTENING.
2. Acoustic feedback of Jarvis's own TTS output ('Yes, I'm listening.') within the post-playback window
   is suppressed as an echo and does NOT consume the active session.
3. The subsequent user command is accepted and answered.
"""

import time
import pytest
from core.interaction_gate import InteractionGate, InteractionState, GateDecision
from core.app import JarvisCore


def test_standalone_wake_and_post_playback_echo_prevention():
    gate = InteractionGate(max_session_commands=1)
    assert gate.state == InteractionState.IDLE

    # 1. User says "Jarvis"
    d1 = gate.evaluate("Jarvis", is_explicit_listen=False)
    assert d1.accepted is True
    assert d1.is_standalone_wake is True
    assert gate.state == InteractionState.LISTENING
    assert gate._remaining_commands == 1

    # 2. Jarvis speaks "Yes, I'm listening."
    gate.set_tts_speaking(True, text="Yes, I'm listening.")
    assert gate.state == InteractionState.RESPONDING
    assert gate._last_spoken_text == "Yes, I'm listening."

    # TTS finishes
    gate.set_tts_speaking(False)
    assert gate.state == InteractionState.LISTENING
    assert gate._remaining_commands == 1

    # 3. Microphone picks up the echo of "Yes, I'm listening." 0.3s after playback
    time.sleep(0.1)
    d_echo = gate.evaluate("Yes, I'm listening.", is_explicit_listen=False)
    assert d_echo.accepted is False
    assert d_echo.reason == "suppressed_echo"
    # Session MUST NOT be consumed by the echo!
    assert gate.state == InteractionState.LISTENING
    assert gate._remaining_commands == 1

    # 4. User now speaks their real follow-up command
    d_cmd = gate.evaluate("Chrome kholo", is_explicit_listen=False)
    assert d_cmd.accepted is True
    assert d_cmd.command == "Chrome kholo"
    assert gate.state == InteractionState.IDLE  # Consumed 1 of 1 command


def test_core_process_input_voice_gated_standalone_wake():
    core = JarvisCore()
    resp = core.process_input("Jarvis", source="voice_gated")
    assert "Yes, I'm listening." in resp
