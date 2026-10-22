# tests/test_voice_interaction_gating.py
"""
Comprehensive Regression Tests for Voice Interaction State Machine, Standby Gating,
Active Listening, Echo/Self-Voice Suppression, and Non-Wake Speech Discarding.
"""

import time
import pytest

from voice.listener import VoiceListener, VoiceMode
from voice.wake_word import WakeWordDetector, WakeWordState, ConversationSessionManager
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_gating_app.db")
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


def test_standby_idle_discards_normal_speech(core_app):
    """
    Verifies that normal background speech without a wake word is strictly
    ignored and discarded in standby mode, never triggering conversational fallbacks.
    """
    listener = VoiceListener()
    assert listener.mode == VoiceMode.STANDBY
    assert listener.state == WakeWordState.IDLE

    # Background speech examples
    background_phrases = [
        "main jakar khata hun",
        "main kal office jaunga",
        "ye kya ho raha hai",
        "aaj mausam kaisa hai",
        "meri awaaz sun rahe ho",
        "kya chal raha hai"
    ]

    for phrase in background_phrases:
        # 1. VoiceListener gate drops it
        res = listener.process_utterance(phrase)
        assert res.detected is False, f"Phrase should have been discarded: '{phrase}'"

        # 2. Core standby pipeline returns empty and performs zero LLM fallback
        resp = core_app.process_input(phrase, source="voice_standby")
        assert resp == "", f"Standby pipeline should return empty for: '{phrase}'"


def test_standby_processes_wake_word_at_all_positions(core_app):
    """Verifies that utterances containing 'Jarvis' anywhere are detected and processed in standby."""
    listener = VoiceListener()
    assert listener.mode == VoiceMode.STANDBY

    # Beginning
    res1 = listener.process_utterance("Jarvis, meri awaaz sun rahe ho?")
    assert res1.detected is True
    assert res1.cleaned_command == "meri awaaz sun rahe ho"

    # End
    res2 = listener.process_utterance("Chrome kholo Jarvis")
    assert res2.detected is True
    assert res2.cleaned_command == "Chrome kholo"

    # Middle
    res3 = listener.process_utterance("meri awaaz Jarvis sun rahe ho?")
    assert res3.detected is True
    assert res3.cleaned_command == "meri awaaz sun rahe ho"

    # Standalone
    res4 = listener.process_utterance("Jarvis")
    assert res4.detected is True
    assert res4.is_standalone is True


def test_explicit_active_listening_mode():
    """
    Verifies that when in ACTIVE mode (Listen button pressed), speech is processed
    directly without requiring the wake word.
    """
    captured_commands = []

    def on_cmd(cmd):
        captured_commands.append(cmd)

    listener = VoiceListener(on_command_captured=on_cmd)
    listener.set_mode(VoiceMode.ACTIVE)
    assert listener.state == WakeWordState.LISTENING

    # Command without wake word
    res = listener.process_utterance("meri awaaz sun rahe ho")
    assert res.detected is True
    assert "meri awaaz sun rahe ho" in captured_commands


def test_stop_listening_phrases():
    """Verifies that saying 'stop listening', 'bas', 'cancel' transitions back to STANDBY."""
    listener = VoiceListener()
    listener.set_mode(VoiceMode.ACTIVE)
    assert listener.mode == VoiceMode.ACTIVE

    # Explicit stop
    res = listener.process_utterance("bas jarvis")
    assert res.detected is True
    assert listener.mode == VoiceMode.STANDBY
    assert listener.state == WakeWordState.IDLE


def test_tts_echo_self_voice_suppression():
    """Verifies that while TTS is speaking, captured speech is ignored to prevent feedback loops."""
    listener = VoiceListener()
    listener.set_mode(VoiceMode.ACTIVE)

    # Simulate TTS actively speaking
    listener.set_tts_speaking(True)
    assert listener.is_suppressed() is True

    # Speech heard while TTS is speaking should be dropped
    res = listener.process_utterance("Jarvis Chrome kholo")
    assert res.detected is False

    # TTS finishes
    listener.set_tts_speaking(False)
    time.sleep(0.45) # Allow cooldown window to pass
    assert listener.is_suppressed() is False

    # Speech after TTS finishes is processed
    res2 = listener.process_utterance("Chrome kholo")
    assert res2.detected is True
