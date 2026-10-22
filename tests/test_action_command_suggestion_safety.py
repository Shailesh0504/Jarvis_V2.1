# tests/test_action_command_suggestion_safety.py
"""
Test Suite: Protection against Command Hijacking by Pending Proactive Suggestions & Confirmations.
Validates that explicit user ACTION_COMMANDs (e.g. 'YouTube open karo', 'Chrome open kar do')
are never hijacked into executing unrelated pending proactive suggestions (e.g. 'python')
or pending system confirmations (e.g. computer restart / shutdown).
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.confirmation import is_affirmation, is_cancellation, classify_confirmation, ConfirmationType
from core.intelligence import ProactiveIntelligenceCoordinator, ProactiveSuggestion, SuggestionState


def test_command_phrases_not_treated_as_affirmations():
    """Verifies action commands targeting entities are NEVER treated as affirmations."""
    action_commands = [
        "YouTube open karo",
        "Chrome open kar do",
        "WhatsApp open kardo",
        "Excel open karo",
        "Calculator open karo",
        "Spotify open karo",
        "PC restart kar do",
        "Computer shutdown kar do",
        "VLC band kar do",
    ]
    for cmd in action_commands:
        assert is_affirmation(cmd) is False, f"Erroneously classified as affirmation: '{cmd}'"
        assert classify_confirmation(cmd) != ConfirmationType.AFFIRMATIVE, f"Erroneously classified as AFFIRMATIVE: '{cmd}'"


def test_troubleshooting_questions_with_negation_not_cancellations():
    """Verifies questions and troubleshooting inquiries containing 'nahi' are NOT treated as cancellations."""
    queries = [
        "system lock kyun nahi ho raha",
        "system lock kyun nahi ho raha?",
        "WiFi connect kyun nahi ho raha",
        "domain user login kyun nahi kar paa raha",
        "Chrome khula hai ya nahi",
    ]
    for q in queries:
        assert is_cancellation(q) is False, f"Erroneously classified as cancellation: '{q}'"
        assert classify_confirmation(q) != ConfirmationType.NEGATIVE, f"Erroneously classified as NEGATIVE: '{q}'"


def test_youtube_open_not_hijacked_by_pending_python_suggestion():
    """
    CRITICAL BUG REGRESSION TEST:
    When a background proactive suggestion exists for 'python', saying 'YouTube open karo'
    must open YouTube and MUST NOT execute Python.
    """
    core = JarvisCore()
    coord = ProactiveIntelligenceCoordinator(app_core=core)
    core.proactive_coordinator = coord

    # Background learned suggestion for python
    sug = ProactiveSuggestion(
        suggestion_id="sug_python_test",
        intent="LAUNCH_APP",
        action="launch_app",
        target="python"
    )
    coord.suggestion_manager.register_presented(sug)
    assert coord.suggestion_manager.get_pending_suggestion() is not None

    with patch.object(core.target_engine, "execute", return_value=MagicMock(success=True, message="Opening Youtube.")) as mock_target_exec:
        resp = core.process_input("YouTube open karo")
        assert "python" not in resp.lower(), f"Erroneously executed Python: {resp}"
        # Target engine was called to open YouTube
        assert mock_target_exec.called
        # Suggestion was cleared / ignored
        assert coord.suggestion_manager.get_pending_suggestion() is None


def test_chrome_open_not_hijacked_by_pending_restart_confirmation():
    """
    SAFETY TEST:
    When ConfirmationManager has a pending destructive confirmation (e.g. computer restart),
    saying 'Chrome open karo' must clear the confirmation safely and open Chrome without restarting.
    """
    core = JarvisCore()
    core.confirmation_manager.request_confirmation(
        action="restart_computer",
        prompt="Kya aap restart karna chahte hain?"
    )
    assert core.confirmation_manager.has_pending_confirmation() is True

    resp = core.process_input("Chrome open karo")
    assert "restart" not in resp.lower()
    assert "chrome" in resp.lower() or "open" in resp.lower()
    # Confirmation cleared safely without restart execution
    assert core.confirmation_manager.has_pending_confirmation() is False
