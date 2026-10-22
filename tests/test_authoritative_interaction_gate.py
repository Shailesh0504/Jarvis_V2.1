# tests/test_authoritative_interaction_gate.py
"""
Authoritative Regression Tests for the Interaction Gate & State Machine.
Validates:
- 20+ Arbitrary non-wake sentences in IDLE are strictly ignored and never reach Intent/LLM/Conversation.
- Wake word triggers at beginning, middle, end, and standalone.
- Explicit Listen-button activation allows subsequent commands without wake word.
- Single command execution automatically reverts to IDLE.
- Stop commands ('bas', 'stop listening', 'cancel') revert to IDLE.
- Inactivity timeout reverts to IDLE.
- TTS self-voice echo is suppressed.
"""

import time
import pytest

from core.interaction_gate import InteractionGate, InteractionState, GateDecision
from core.app import JarvisCore
from voice.wake_word import WakeWordDetector
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_gate_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


NON_WAKE_SENTENCES_20 = [
    "chalo khana kha kar aata hun",
    "main kal office jaunga",
    "ye kya ho raha hai",
    "aaj mausam kaisa hai",
    "kya kar rahe ho",
    "ye kya hai",
    "mujhe bhookh lagi hai",
    "pani lekar aao",
    "aaj kaun sa din hai",
    "chai pi li kya",
    "laptop band karo bhai",
    "gadi ki chabi kahan hai",
    "meeting kab khatam hogi",
    "kuch samajh nahi aa raha",
    "kal milte hain",
    "movie dekhne chale",
    "phone kiska baj raha hai",
    "light band kar dena",
    "gate khula hai kya",
    "market ja raha hun",
    "main jakar khata hun",
    "kya chal raha hai",
    "Sagar hospital",
    "murshida",
    "Sagar hospital hai kya",
    "PVC kya maloom",
]


def test_20_arbitrary_sentences_ignored_in_idle(core_app):
    """
    Verifies that all 20+ arbitrary everyday sentences are completely ignored in IDLE mode.
    They must produce empty output, never reach IntentDetector/LLM, and never generate
    a conversational fallback response.
    """
    gate = core_app.interaction_gate
    assert gate.state == InteractionState.IDLE

    for sentence in NON_WAKE_SENTENCES_20:
        # 1. Direct gate evaluation
        decision = gate.evaluate(sentence, is_explicit_listen=False)
        assert decision.accepted is False, f"Gate must reject: '{sentence}'"
        assert decision.reason == "ignored_idle"

        # 2. Pipeline processing with source='voice_standby'
        resp = core_app.process_input(sentence, source="voice_standby")
        assert resp == "", f"Pipeline must return empty for non-wake phrase: '{sentence}'"
        assert "Main samajh gaya Boss" not in resp


def test_wake_word_activations_at_all_positions(core_app):
    """Verifies wake word triggers at beginning, middle, end, and standalone in IDLE mode."""
    gate = core_app.interaction_gate
    gate.deactivate_listening()
    assert gate.state == InteractionState.IDLE

    # 1. Beginning: "Jarvis, kya kar rahe ho"
    d1 = gate.evaluate("Jarvis, kya kar rahe ho")
    assert d1.accepted is True
    assert d1.command == "kya kar rahe ho"

    # 2. End: "Chrome kholo Jarvis"
    gate.deactivate_listening()
    d2 = gate.evaluate("Chrome kholo Jarvis")
    assert d2.accepted is True
    assert d2.command == "Chrome kholo"

    # 3. Middle: "meri awaaz Jarvis sun rahe ho?"
    gate.deactivate_listening()
    d3 = gate.evaluate("meri awaaz Jarvis sun rahe ho?")
    assert d3.accepted is True
    assert d3.command == "meri awaaz sun rahe ho"

    # 4. Standalone: "Jarvis"
    gate.deactivate_listening()
    d4 = gate.evaluate("Jarvis")
    assert d4.accepted is True
    assert d4.is_standalone_wake is True
    assert gate.state == InteractionState.LISTENING


def test_explicit_listen_button_activation(core_app):
    """
    Listen mode monitors audio but never bypasses the wake word.
    """
    gate = core_app.interaction_gate
    gate.activate_explicit_listening()
    assert gate.state == InteractionState.IDLE

    d = gate.evaluate("kya kar rahe ho", is_explicit_listen=False)
    assert d.accepted is False
    assert d.reason == "ignored_idle"


def test_clarification_authorizes_exactly_one_wake_free_followup():
    gate = InteractionGate(max_session_commands=1)
    gate.authorize_followup()

    answer = gate.evaluate("Tum Hi Ho")
    background = gate.evaluate("office ke liye pendrive lana")

    assert answer.accepted is True
    assert answer.command == "Tum Hi Ho"
    assert answer.reason == "wake_session"
    assert background.accepted is False
    assert background.reason == "ignored_idle"


def test_wake_session_accepts_exactly_three_commands_then_reverts_to_idle():
    """One wake word authorizes three commands, including an attached command."""
    gate = InteractionGate(continuous_mode=False)
    first = gate.evaluate("Jarvis volume 50 karo")
    second = gate.evaluate("chrome kholo")
    third = gate.evaluate("time batao")
    fourth = gate.evaluate("weather batao")

    assert first.accepted and second.accepted and third.accepted
    assert fourth.accepted is False
    assert fourth.reason == "ignored_idle"
    assert gate.state == InteractionState.IDLE


def test_stop_commands_revert_to_idle():
    """Verifies that 'stop listening', 'bas', 'cancel' immediately revert gate to IDLE."""
    gate = InteractionGate(continuous_mode=True)

    for stop_phrase in ["stop listening", "bas jarvis", "cancel", "shant ho jao", "bas karo"]:
        gate.evaluate("Jarvis")
        d = gate.evaluate(stop_phrase)
        assert d.accepted is True
        assert d.reason == "stop_command"
        assert gate.state == InteractionState.IDLE


def test_inactivity_timeout_reverts_to_idle():
    """Verifies that session inactivity timeout returns gate to IDLE."""
    gate = InteractionGate(session_timeout=0.2)
    gate.evaluate("Jarvis")
    assert gate.state == InteractionState.LISTENING

    time.sleep(0.3) # Wait for timeout

    # Next utterance without explicit force should trigger timeout back to IDLE
    d = gate.evaluate("ye kya hai", is_explicit_listen=False)
    assert d.accepted is False
    assert gate.state == InteractionState.IDLE


def test_tts_self_voice_echo_suppression():
    """Verifies that when TTS is speaking, incoming STT transcripts are suppressed."""
    gate = InteractionGate()
    gate.activate_explicit_listening()

    # Simulate TTS starting
    gate.set_tts_speaking(True)
    assert gate.is_tts_suppressed() is True
    assert gate.state == InteractionState.RESPONDING

    # Audio heard while TTS is speaking must be dropped
    d = gate.evaluate("Jarvis Chrome kholo")
    assert d.accepted is False
    assert d.reason == "suppressed_tts"

    # TTS completes
    gate.set_tts_speaking(False)
    time.sleep(0.45) # Allow cooldown window to pass
    assert gate.is_tts_suppressed() is False
