# tests/test_confirmation_manager.py
"""
Comprehensive test suite for Jarvis V2.1 Confirmation Architecture.
Validates:
1. Positive confirmation phrases (English, Roman Hindi, Devanagari, Hinglish) -> YES
2. Negative confirmation phrases (English, Roman Hindi, Devanagari, Hinglish) -> NO
3. Ambiguity handling (clarification requested, confirmation retained)
4. Expiration handling (auto-cancellation after timeout)
5. Restart & Shutdown execution verification (subprocess mock verification)
6. Unrelated command safety (no accidental execution of destructive action)
7. STT variations normalization ("haan", "han", "haa", "ha")
8. Multi-turn end-to-end dialog with JarvisCore
"""

from unittest.mock import MagicMock, patch
import pytest
import time

from core.confirmation import (
    ConfirmationType,
    classify_confirmation,
    is_affirmation,
    is_cancellation,
    is_ambiguous,
    normalize_confirmation_text
)
from core.confirmation_manager import ConfirmationManager, PendingConfirmation
from main import create_jarvis


# ==============================================================================
# Unit Tests: Classifier & Normalization
# ==============================================================================

@pytest.mark.parametrize("phrase", [
    "yes",
    "y",
    "yeah",
    "yep",
    "sure",
    "okay",
    "ok",
    "alright",
    "haan",
    "han",
    "ha",
    "haa",
    "ji",
    "ji haan",
    "bilkul",
    "theek hai",
    "thik hai",
    "kar do",
    "haan kar do",
    "ha kar do",
    "yes please",
    "okay do it",
    "go ahead",
    "proceed",
    "confirm",
    "confirmed",
    "haan restart kar do",
    "ha bhai kar do",
    "ji restart kar do",
    "bilkul kar do",
    "theek hai kar do",
    "haan bhai",
    "yes kar do",
    "Haan!!!",
    "HAAN",
    "हाँ",
    "हां",
    "जी",
    "जी हाँ",
    "बिल्कुल",
    "ठीक है",
    "कर दो",
    "हाँ कर दो",
])
def test_positive_confirmation_phrases(phrase):
    """Verifies all specified positive phrases resolve to AFFIRMATIVE (YES)."""
    assert is_affirmation(phrase) is True, f"Failed for positive phrase: {phrase}"
    assert classify_confirmation(phrase) == ConfirmationType.AFFIRMATIVE, f"Failed classification for: {phrase}"


@pytest.mark.parametrize("phrase", [
    "no",
    "n",
    "nope",
    "nah",
    "nahi",
    "nahin",
    "nhi",
    "na",
    "mat karo",
    "cancel",
    "cancel it",
    "don't",
    "don't do it",
    "stop",
    "rehne do",
    "chhod do",
    "abhi nahi",
    "not now",
    "nahi karna",
    "nahi karo",
    "cancel kar do",
    "restart mat karo",
    "abhi mat karo",
    "नहीं",
    "नही",
    "ना",
    "मत करो",
    "रहने दो",
    "छोड़ दो",
    "अभी नहीं",
    "नही कर दो",
])
def test_negative_confirmation_phrases(phrase):
    """Verifies all specified negative phrases resolve to NEGATIVE (NO)."""
    assert is_cancellation(phrase) is True, f"Failed for negative phrase: {phrase}"
    assert classify_confirmation(phrase) == ConfirmationType.NEGATIVE, f"Failed classification for: {phrase}"


@pytest.mark.parametrize("phrase", [
    "maybe",
    "dekhta hoon",
    "pata nahi",
    "shayad",
    "not sure",
    "kya pata",
    "देखता हूँ",
    "पता नहीं",
    "शायद",
])
def test_ambiguous_confirmation_phrases(phrase):
    """Verifies ambiguous responses are detected as AMBIGUOUS."""
    assert is_ambiguous(phrase) is True, f"Failed ambiguity detection for: {phrase}"
    assert classify_confirmation(phrase) == ConfirmationType.AMBIGUOUS, f"Failed classification for: {phrase}"


# ==============================================================================
# State Machine Tests: ConfirmationManager
# ==============================================================================

def test_confirmation_manager_affirmative_restart():
    """Test 14: Confirmation with pending restart -> restart executes."""
    mgr = ConfirmationManager(default_timeout_seconds=30.0)
    core = MagicMock()
    core.plugin_manager.execute_action.return_value = MagicMock(success=True)

    prompt = mgr.request_confirmation(
        action="restart_computer",
        parameters={"restart": True},
        prompt="Are you sure you want to restart the computer? Please confirm.",
        language="en",
        target_plugin="system",
        target_action="shutdown_pc",
    )
    assert "Are you sure" in prompt
    assert mgr.has_pending_confirmation() is True

    handled, resp = mgr.handle_confirmation("haan", core)
    assert handled is True
    assert "restarting" in resp.lower()
    assert mgr.has_pending_confirmation() is False

    core.plugin_manager.execute_action.assert_called_once()
    args, kwargs = core.plugin_manager.execute_action.call_args
    assert args[0] == "system"
    assert args[1] == "shutdown_pc"
    assert args[2]["confirmed"] is True
    assert args[2]["restart"] is True


def test_confirmation_manager_affirmative_shutdown():
    """Test 15: Confirmation with pending shutdown -> shutdown executes."""
    mgr = ConfirmationManager(default_timeout_seconds=30.0)
    core = MagicMock()
    core.plugin_manager.execute_action.return_value = MagicMock(success=True)

    mgr.request_confirmation(
        action="shutdown_computer",
        parameters={"restart": False},
        prompt="Kya computer shutdown kar doon?",
        language="hi",
        target_plugin="system",
        target_action="shutdown_pc",
    )
    assert mgr.has_pending_confirmation() is True

    handled, resp = mgr.handle_confirmation("kar do", core)
    assert handled is True
    assert "shutdown" in resp.lower()
    assert mgr.has_pending_confirmation() is False

    core.plugin_manager.execute_action.assert_called_once()
    args, kwargs = core.plugin_manager.execute_action.call_args
    assert args[2]["confirmed"] is True
    assert args[2]["restart"] is False


def test_confirmation_manager_negative_cancellation():
    """Test 8, 9, 11: Negative confirmation cancels without execution."""
    mgr = ConfirmationManager()
    core = MagicMock()

    mgr.request_confirmation(
        action="restart_computer",
        parameters={"restart": True},
        language="hi"
    )
    handled, resp = mgr.handle_confirmation("nahi", core)
    assert handled is True
    assert "cancel" in resp.lower()
    assert mgr.has_pending_confirmation() is False
    core.plugin_manager.execute_action.assert_not_called()


def test_confirmation_manager_ambiguous_clarification():
    """Test 12: Ambiguous response asks for clarification and keeps confirmation pending."""
    mgr = ConfirmationManager()
    core = MagicMock()

    mgr.request_confirmation(
        action="restart_computer",
        parameters={"restart": True},
        language="hi"
    )
    handled, resp = mgr.handle_confirmation("shayad", core)
    assert handled is True
    assert "please confirm" in resp.lower() or "haan ya nahi" in resp.lower()
    # Confirmation MUST stay active!
    assert mgr.has_pending_confirmation() is True
    core.plugin_manager.execute_action.assert_not_called()

    # Next turn user clarifies with "haan" -> now executes
    handled2, resp2 = mgr.handle_confirmation("haan", core)
    assert handled2 is True
    assert "restart" in resp2.lower()
    assert mgr.has_pending_confirmation() is False


def test_confirmation_manager_expiration():
    """Test 13: Expired confirmation does not execute."""
    mgr = ConfirmationManager(default_timeout_seconds=0.1)
    core = MagicMock()

    mgr.request_confirmation(
        action="restart_computer",
        parameters={"restart": True},
        language="hi",
        timeout_seconds=0.1
    )
    time.sleep(0.15)  # Wait for expiration

    handled, resp = mgr.handle_confirmation("haan", core)
    assert handled is True
    assert "timeout" in resp.lower()
    assert mgr.has_pending_confirmation() is False
    core.plugin_manager.execute_action.assert_not_called()


def test_confirmation_manager_unrelated_command_safety():
    """Test 16: Unrelated command while confirmation is pending clears safely without execution."""
    mgr = ConfirmationManager()
    core = MagicMock()

    mgr.request_confirmation(
        action="restart_computer",
        parameters={"restart": True},
        language="hi"
    )
    handled, resp = mgr.handle_confirmation("chrome kholo", core)
    assert handled is False
    assert resp == ""
    # Safe: confirmation is cleared so user isn't stuck, but action was NOT executed!
    assert mgr.has_pending_confirmation() is False
    core.plugin_manager.execute_action.assert_not_called()


# ==============================================================================
# End-to-End Integration Tests with JarvisCore
# ==============================================================================

@pytest.fixture
def jarvis():
    return create_jarvis()


def test_e2e_restart_confirmation_haan(jarvis):
    """End-to-end verification of user's exact reported scenario."""
    # Step 1: User requests restart
    resp1 = jarvis.process_input("computer restart kar do", source="gui")
    assert any(w in resp1.lower() for w in ["sure", "restart", "confirm"])
    assert jarvis.confirmation_manager.has_pending_confirmation() is True

    # Step 2: User confirms with "haan"
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("haan", source="gui")
        assert resp2 != "", "Jarvis response must not be empty!"
        assert any(w in resp2.lower() for w in ["restarting", "restart ho raha hai", "theek hai boss"])
        assert jarvis.confirmation_manager.has_pending_confirmation() is False


def test_e2e_restart_confirmation_english_yes(jarvis):
    """End-to-end verification of English confirmation flow."""
    resp1 = jarvis.process_input("restart the computer", source="gui")
    assert "are you sure" in resp1.lower() or "confirm" in resp1.lower()
    assert jarvis.confirmation_manager.has_pending_confirmation() is True

    # Safety: test me real OS restart/shutdown kabhi execute nahi hona chahiye.
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("yes please", source="gui")
        mock_popen.assert_not_called()
        assert resp2 != ""
        assert "restarting" in resp2.lower()
        assert jarvis.confirmation_manager.has_pending_confirmation() is False


def test_e2e_devanagari_confirmation(jarvis):
    """End-to-end verification of Devanagari Hindi confirmation."""
    resp1 = jarvis.process_input("system restart karo", source="gui")
    assert jarvis.confirmation_manager.has_pending_confirmation() is True

    # Safety: test me real OS restart/shutdown kabhi execute nahi hona chahiye.
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("हाँ कर दो", source="gui")
        mock_popen.assert_not_called()
        assert resp2 != ""
        assert "restart" in resp2.lower()
        assert jarvis.confirmation_manager.has_pending_confirmation() is False


def test_e2e_cancellation_flow(jarvis):
    """End-to-end verification of rejection with 'nahi'."""
    resp1 = jarvis.process_input("system restart karo", source="gui")
    assert jarvis.confirmation_manager.has_pending_confirmation() is True

    resp2 = jarvis.process_input("nahi", source="gui")
    assert "cancel" in resp2.lower()
    assert jarvis.confirmation_manager.has_pending_confirmation() is False
