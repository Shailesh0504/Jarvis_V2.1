# tests/test_wake_word_universal.py
"""
Comprehensive Unit and Regression Tests for Universal Multi-Position Wake-Word Detection,
Phonetic Variants, Conversation Session Management, and Speech Presence Queries.
"""

import time
import pytest

from voice.wake_word import WakeWordDetector, WakeWordState, ConversationSessionManager
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_wake_app.db")
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


def test_wake_word_all_positions():
    """Verifies wake word extraction across beginning, middle, end, and standalone positions."""
    detector = WakeWordDetector()

    # 1. Beginning
    res1 = detector.detect("Jarvis, meri awaaz sun rahe ho?")
    assert res1.detected is True
    assert res1.position in ("prefix", "beginning")
    assert res1.cleaned_command == "meri awaaz sun rahe ho"

    # 2. End
    res2 = detector.detect("meri awaaz sun rahe ho Jarvis?")
    assert res2.detected is True
    assert res2.position in ("suffix", "end")
    assert res2.cleaned_command == "meri awaaz sun rahe ho"

    # 3. Middle
    res3 = detector.detect("meri awaaz Jarvis sun rahe ho?")
    assert res3.detected is True
    assert res3.position in ("embedded", "middle")
    assert res3.cleaned_command == "meri awaaz sun rahe ho"

    # 4. Complex sentence with Hindi grammar
    res4 = detector.detect("kya tum meri awaaz sun rahe ho, Jarvis")
    assert res4.detected is True
    assert res4.position in ("suffix", "end")
    assert res4.cleaned_command == "kya tum meri awaaz sun rahe ho"

    # 5. Standalone
    res5 = detector.detect("Jarvis")
    assert res5.detected is True
    assert res5.is_standalone is True
    assert res5.cleaned_command == ""


def test_wake_word_command_passthrough():
    """Verifies that command text is cleanly isolated regardless of wake word position."""
    detector = WakeWordDetector()

    # Beginning
    res1 = detector.detect("Jarvis Chrome kholo")
    assert res1.detected is True
    assert res1.cleaned_command == "Chrome kholo"

    # End
    res2 = detector.detect("Chrome kholo Jarvis")
    assert res2.detected is True
    assert res2.cleaned_command == "Chrome kholo"

    # Middle
    res3 = detector.detect("Chrome Jarvis kholo")
    assert res3.detected is True
    assert res3.cleaned_command == "Chrome kholo"

    # With courtesy word
    res4 = detector.detect("Jarvis Chrome kholo please")
    assert res4.detected is True
    assert res4.cleaned_command == "Chrome kholo please"

    # With discourse connector 'to'
    res5 = detector.detect("Jarvis to meri awaaz sun rahe ho")
    assert res5.detected is True
    assert res5.cleaned_command == "meri awaaz sun rahe ho"


def test_wake_word_stt_variations():
    """Verifies recognition of phonetic variations and honorifics."""
    detector = WakeWordDetector()

    for variant in ["jarvis", "jarwis", "jarvis ji", "jarvis bhai", "zervis", "jarves", "hey jarvis"]:
        res = detector.detect(f"{variant} screen lock karo")
        assert res.detected is True, f"Failed for variant: {variant}"
        assert res.cleaned_command == "screen lock karo"


def test_wake_word_repeated_deduplication():
    """Verifies that multiple wake words in the same utterance are cleanly stripped."""
    detector = WakeWordDetector()
    res = detector.detect("Jarvis Chrome kholo Jarvis")
    assert res.detected is True
    assert res.cleaned_command == "Chrome kholo"


def test_false_positive_resistance():
    """Verifies that phonetically distinct phrases are not misidentified as wake words."""
    detector = WakeWordDetector()

    assert detector.detect("java is a programming language").detected is False
    assert detector.detect("the jar on the table is full").detected is False
    assert detector.detect("take the car to customer service").detected is False


def test_conversation_session_lifecycle():
    """Verifies active session management and stop listening phrases."""
    session = ConversationSessionManager(session_timeout=2.0)
    assert session.is_session_active is False

    # Activate
    session.activate_session()
    assert session.is_session_active is True
    assert session.state == WakeWordState.LISTENING

    # Stop command detection
    assert session.is_stop_command("stop listening") is True
    assert session.is_stop_command("bas jarvis") is True
    assert session.is_stop_command("shant ho jao") is True
    assert session.is_stop_command("kholo excel") is False

    # End session
    session.end_session()
    assert session.is_session_active is False


def test_end_to_end_presence_and_no_fallback_trap(core_app):
    """
    End-to-end tests proving that 'Jarvis, meri awaaz sun rahe ho?' and its variations
    return friendly speech-confirmation responses and never trigger the conversational fallback trap.
    """
    # 1. Beginning position
    resp1 = core_app.process_input("Jarvis, meri awaaz sun rahe ho?")
    assert "Main samajh gaya Boss! Bataiye" not in resp1
    assert "saaf sun raha hoon" in resp1

    # 2. End position
    resp2 = core_app.process_input("meri awaaz sun rahe ho Jarvis?")
    assert "Main samajh gaya Boss! Bataiye" not in resp2
    assert "saaf sun raha hoon" in resp2

    # 3. Middle position
    resp3 = core_app.process_input("meri awaaz Jarvis sun rahe ho?")
    assert "Main samajh gaya Boss! Bataiye" not in resp3
    assert "saaf sun raha hoon" in resp3

    # 4. Complex sentence with Hindi grammar
    resp4 = core_app.process_input("kya tum meri awaaz sun rahe ho, Jarvis")
    assert "Main samajh gaya Boss! Bataiye" not in resp4
    assert "saaf sun raha hoon" in resp4

    # 5. Standalone Jarvis
    resp5 = core_app.process_input("Jarvis")
    assert "Yes, I'm listening" in resp5
    assert "yaar" not in resp5.lower()
    assert "Boss" not in resp5

    # 6. Stop command
    resp6 = core_app.process_input("bas Jarvis")
    assert "listening stopped" in resp6.lower()


def test_wake_word_payload_preservation():
    """Verifies that when 'Jarvis' is part of typed/written content or search query, it is preserved."""
    detector = WakeWordDetector()

    # 1. Typing command payload
    res1 = detector.detect("desktop pe ek test.txt file banao or usme Jarvis type karo")
    assert "Jarvis" in res1.cleaned_command
    assert "Jarvis type karo" in res1.cleaned_command

    # 2. Search query payload with initial wake word
    res2 = detector.detect("Jarvis, search Jarvis on google")
    assert res2.detected is True
    assert "search Jarvis on google" in res2.cleaned_command

    # 3. Write command payload
    res3 = detector.detect("file me likho Jarvis")
    assert "Jarvis" in res3.cleaned_command
