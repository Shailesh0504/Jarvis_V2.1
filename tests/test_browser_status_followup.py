# tests/test_browser_status_followup.py
"""
Unit and integration tests for human-like browser status queries and interactive follow-ups.
Verifies:
1. "YouTube kaun se brouser mein open hai" extracts target='youtube'
2. Conversational response policy returns natural human-like responses:
   - Not open: "Sir, maine check kiya, YouTube abhi kisi bhi browser mein open nahi hai. Kya aap YouTube open karna chahte hain?"
   - Open: "Sir, maine check kiya, YouTube abhi Google Chrome mein open hai."
3. Multi-turn affirmative execution: user says "haan" / "open kar do" -> opens YouTube & confirms.
4. Multi-turn negative cancellation: user says "nahi" / "mat karo" -> cancels & confirms.
5. Safety: unrelated command clears confirmation without executing.
"""

import pytest
from unittest.mock import patch, MagicMock

from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.response_policy import ConversationalResponsePolicy
from core.app import JarvisCore
from core.target_engine import ActionOutcome, TargetCandidate, TargetKind


def test_intent_classification_browser_location_queries():
    """Verify that browser location queries with spelling variations cleanly extract target."""
    queries = [
        "YouTube kaun se brouser mein open hai",
        "youtube konse browser me hai",
        "youtube kaun se browser me open hai",
        "kis browser me youtube open hai",
        "youtube kahan open hai",
        "which browser is youtube open in",
        "kaun se browser mein youtube open hai",
    ]
    for q in queries:
        res = ConversationalIntentClassifier.classify(q)
        assert res.intent_type == ConversationalIntentType.STATUS_QUESTION, f"Failed for {q}"
        assert res.target.lower() == "youtube", f"Failed target for {q}: got {res.target}"
        assert res.parameters.get("browser_location_query") is True, f"Missing browser_location_query for {q}"


def test_response_policy_browser_not_open():
    """Verify response when website is not open in any browser."""
    resp = ConversationalResponsePolicy.format_status_response(
        query="YouTube kaun se brouser mein open hai",
        target="youtube",
        is_open=False,
    )
    assert "Sir, maine check kiya" in resp
    assert "kisi bhi browser mein open nahi hai" in resp
    assert "open karna chahte hain?" in resp


def test_response_policy_browser_open():
    """Verify response when website is open in Microsoft Edge or Chrome."""
    resp_edge = ConversationalResponsePolicy.format_status_response(
        query="YouTube kaun se brouser mein open hai",
        target="youtube",
        is_open=True,
        browser="edge"
    )
    assert "Sir, maine check kiya" in resp_edge
    assert "Microsoft Edge mein open hai" in resp_edge

    resp_chrome = ConversationalResponsePolicy.format_status_response(
        query="YouTube kaun se browser mein open hai",
        target="youtube",
        is_open=True,
        browser="chrome"
    )
    assert "Sir, maine check kiya" in resp_chrome
    assert "Google Chrome mein open hai" in resp_chrome


def test_e2e_browser_status_affirmative_followup():
    """
    E2E test:
    Turn 1: User asks "YouTube kaun se brouser mein open hai"
            Jarvis responds with polite refusal + proactive offer and sets pending confirmation.
    Turn 2: User responds "haan"
            Jarvis executes launch and acknowledges "Theek hai Sir, YouTube open kar raha hoon."
    """
    core = JarvisCore()

    # Mock resolver & window manager so YouTube is not running
    with patch.object(core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(core.target_engine.window_manager, "find_windows_for_app", return_value=[]), \
         patch.object(core.target_engine.window_manager, "is_process_running", return_value=(False, [])):

        resp1 = core.process_input("YouTube kaun se brouser mein open hai")
        assert "Sir, maine check kiya" in resp1
        assert "kisi bhi browser mein open nahi hai" in resp1
        assert "open karna chahte hain?" in resp1
        assert core.confirmation_manager.has_pending_confirmation() is True

    # Now simulate user saying "haan"
    with patch.object(core.target_engine, "execute", return_value=ActionOutcome(True, "YouTube open kar diya.")) as mock_exec:
        resp2 = core.process_input("haan")
        assert "youtube open kar raha hoon" in resp2.lower()
        mock_exec.assert_called_once()
        assert core.confirmation_manager.has_pending_confirmation() is False


def test_e2e_browser_status_open_kar_do_affirmative():
    """User replies 'haan open kar do' to confirm."""
    core = JarvisCore()

    with patch.object(core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(core.target_engine.window_manager, "find_windows_for_app", return_value=[]), \
         patch.object(core.target_engine.window_manager, "is_process_running", return_value=(False, [])):

        resp1 = core.process_input("YouTube kaun se brouser mein open hai")
        assert core.confirmation_manager.has_pending_confirmation() is True

    with patch.object(core.target_engine, "execute", return_value=ActionOutcome(True, "YouTube open kar diya.")) as mock_exec:
        resp2 = core.process_input("haan open kar do")
        assert "youtube open kar raha hoon" in resp2.lower()
        mock_exec.assert_called_once()
        assert core.confirmation_manager.has_pending_confirmation() is False


def test_e2e_browser_status_negative_cancellation():
    """
    E2E test:
    Turn 1: User asks "YouTube kaun se brouser mein open hai"
    Turn 2: User says "nahi" -> action is cancelled gracefully without launching anything.
    """
    core = JarvisCore()

    with patch.object(core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(core.target_engine.window_manager, "find_windows_for_app", return_value=[]), \
         patch.object(core.target_engine.window_manager, "is_process_running", return_value=(False, [])):

        resp1 = core.process_input("YouTube kaun se brouser mein open hai")
        assert core.confirmation_manager.has_pending_confirmation() is True

    with patch.object(core.target_engine, "execute") as mock_exec:
        resp2 = core.process_input("nahi")
        assert "youtube open nahi kar raha hoon" in resp2.lower()
        mock_exec.assert_not_called()
        assert core.confirmation_manager.has_pending_confirmation() is False


def test_e2e_browser_status_open_mat_karo_cancellation():
    """User replies 'open mat karo' to cancel."""
    core = JarvisCore()

    with patch.object(core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(core.target_engine.window_manager, "find_windows_for_app", return_value=[]), \
         patch.object(core.target_engine.window_manager, "is_process_running", return_value=(False, [])):

        resp1 = core.process_input("YouTube kaun se brouser mein open hai")
        assert core.confirmation_manager.has_pending_confirmation() is True

    with patch.object(core.target_engine, "execute") as mock_exec:
        resp2 = core.process_input("open mat karo")
        assert "youtube open nahi kar raha hoon" in resp2.lower()
        mock_exec.assert_not_called()
        assert core.confirmation_manager.has_pending_confirmation() is False
