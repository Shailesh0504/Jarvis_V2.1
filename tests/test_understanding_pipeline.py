# tests/test_understanding_pipeline.py
"""
Comprehensive automated tests for Jarvis NLU Understanding Pipeline.

Validates:
1. "retstart the system" -> restart confirmation workflow
2. "restat computer" -> restart confirmation workflow
3. "restard computer" -> restart confirmation workflow
4. Confirmed execution of restart after typo correction
5. "chrom kholo" -> Chrome launch
6. "youtub kholo" -> YouTube open
7. Unknown command -> honest natural clarification (no fake "Main samajh gaya")
8. Ambiguous command -> natural clarification question
9. Valid command -> direct execution / confirmation without false clarification
"""

import os
import pytest
from main import create_jarvis


@pytest.fixture
def jarvis():
    os.environ["JARVIS_TEST_MODE"] = "1"
    return create_jarvis()


def test_retstart_the_system_triggers_restart_confirmation(jarvis):
    """Typo 'retstart the system' must resolve to restart intent and request confirmation."""
    response = jarvis.process_input("retstart the system")
    resp_lower = response.lower()

    # Must ask confirmation (English or Hindi)
    assert any(w in resp_lower for w in ["restart", "confirm", "sure"])
    assert jarvis.dialog_manager.has_pending_system_action() is True


def test_restat_computer_triggers_restart_confirmation(jarvis):
    """Typo 'restat computer' must resolve to restart intent and request confirmation."""
    response = jarvis.process_input("restat computer")
    resp_lower = response.lower()

    assert any(w in resp_lower for w in ["restart", "confirm", "sure"])
    assert jarvis.dialog_manager.has_pending_system_action() is True


def test_restard_computer_triggers_restart_confirmation(jarvis):
    """Typo 'restard computer' must resolve to restart intent and request confirmation."""
    response = jarvis.process_input("restard computer")
    resp_lower = response.lower()

    assert any(w in resp_lower for w in ["restart", "confirm", "sure"])
    assert jarvis.dialog_manager.has_pending_system_action() is True


def test_restart_confirmation_affirmative_executes_after_typo(jarvis):
    """After typo 'retstart the system', confirming with 'yes' or 'haan' executes restart safely."""
    resp1 = jarvis.process_input("retstart the system")
    assert jarvis.dialog_manager.has_pending_system_action() is True

    # User confirms with 'yes'
    resp2 = jarvis.process_input("yes")
    assert "restart" in resp2.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is False


def test_chrom_kholo_launches_chrome(jarvis):
    """Hinglish typo 'chrom kholo' must resolve to opening Google Chrome."""
    response = jarvis.process_input("chrom kholo")
    resp_lower = response.lower()

    assert "chrome" in resp_lower or "launch" in resp_lower


def test_youtub_kholo_opens_youtube(jarvis):
    """Hinglish typo 'youtub kholo' must resolve to opening YouTube."""
    response = jarvis.process_input("youtub kholo")
    resp_lower = response.lower()

    assert "youtube" in resp_lower


def test_unknown_command_asks_honest_clarification(jarvis):
    """
    Unknown or nonsense command must NOT return fake understanding
    'Main samajh gaya! Bataiye...', but rather an honest clarification request.
    """
    response = jarvis.process_input("asdfghjkl zxcvbnm qwerty123")
    resp_lower = response.lower()

    # Must NOT pretend to understand
    assert "main samajh gaya" not in resp_lower
    # Must ask for clarification
    assert any(w in resp_lower for w in ["clarify", "samajh nahi", "clear nahi", "dobara", "understand"])


def test_ambiguous_command_asks_clarification(jarvis):
    """
    Ambiguous / uncertain command prompts for natural clarification.
    """
    from brain.spelling_resolver import SpellingResolver
    # Verify SpellingResolver produces needs_confirmation for uncertain candidate
    resolution = SpellingResolver.resolve("spofy chalao")
    assert resolution is not None
    assert resolution.needs_confirmation is True
    assert resolution.correction == "spotify"

    # In JarvisCore, uncertain command prompts the user with natural clarification
    response = jarvis.process_input("spofy chalao")
    resp_lower = response.lower()
    assert "spotify" in resp_lower or "chahte" in resp_lower


def test_valid_command_direct_execution(jarvis):
    """Valid command 'open chrome' executes directly without false clarification question."""
    response = jarvis.process_input("open chrome")
    resp_lower = response.lower()

    assert "kya aap" not in resp_lower
    assert "clarify" not in resp_lower
    assert "chrome" in resp_lower or "launch" in resp_lower
