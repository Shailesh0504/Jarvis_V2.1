# tests/test_conversational_response_policy.py
"""
Unit and Integration Tests for Centralized Conversational Feedback & Response Policy Engine.
Validates the invariant: DIRECT ANSWER -> OPTIONAL USEFUL DETAIL -> STOP
Ensures concise, natural, context-aware responses without exposing internal process names,
window handles, or debug parenthetical syntax.
"""

import pytest
from unittest.mock import patch, MagicMock

from core.response_policy import ConversationalResponsePolicy
from core.app import JarvisCore
from plugins.windows.window_manager import WindowInfo
from core.target_engine import TargetCandidate, TargetKind


def test_clean_window_title():
    """Verifies that technical application suffixes and quotes are cleaned for speech."""
    raw1 = "Jarvis Low Voice Fix - Google Chrome"
    assert ConversationalResponsePolicy.clean_window_title(raw1, "Chrome") == "Jarvis Low Voice Fix"

    raw2 = "Inbox (3) - Gmail - Brave"
    assert ConversationalResponsePolicy.clean_window_title(raw2, "Brave") == "Inbox (3) - Gmail"

    raw3 = "notes.txt - Notepad"
    assert ConversationalResponsePolicy.clean_window_title(raw3, "Notepad") == "notes.txt"

    raw4 = "('Standalone Window')"
    assert ConversationalResponsePolicy.clean_window_title(raw4) == "Standalone Window"


def test_policy_simple_open_question():
    """
    User: 'Chrome open hai kya?'
    Preferred: 'Haan, Chrome open hai.' (or when closed: 'Nahi, Chrome abhi open nahi hai.')
    """
    # 1. Open and normal
    r1 = ConversationalResponsePolicy.format_status_response(
        query="Chrome open hai kya?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert r1 == "Haan, Chrome open hai."

    # 2. Closed
    r2 = ConversationalResponsePolicy.format_status_response(
        query="Chrome open hai kya?",
        target="chrome",
        is_open=False,
        is_active=False,
        is_minimized=False,
        is_running=False,
    )
    assert r2 == "Nahi, Chrome abhi open nahi hai."


def test_policy_which_window_question():
    """
    User: 'Chrome kaunsa window open hai?'
    Preferred: '‘Jarvis Low Voice Fix’ wala window open hai.'
    """
    resp = ConversationalResponsePolicy.format_status_response(
        query="Chrome kaunsa window open hai?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert "Jarvis Low Voice Fix" in resp
    assert "wala window open hai" in resp


def test_policy_active_question():
    """
    User: 'Chrome active hai kya?'
    When active: 'Haan, Chrome active hai.'
    When open but not active (in background): 'Chrome open hai, lekin abhi active nahi hai.'
    When closed: 'Nahi, Chrome abhi open nahi hai.'
    """
    # Active
    r1 = ConversationalResponsePolicy.format_status_response(
        query="Chrome active hai kya?",
        target="chrome",
        is_open=True,
        is_active=True,
        is_minimized=False,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert r1 == "Haan, Chrome active hai."

    # Background (open, not active)
    r2 = ConversationalResponsePolicy.format_status_response(
        query="Chrome active hai kya?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert r2 == "Chrome open hai, lekin abhi active nahi hai."

    # Closed
    r3 = ConversationalResponsePolicy.format_status_response(
        query="Chrome active hai kya?",
        target="chrome",
        is_open=False,
        is_active=False,
        is_minimized=False,
        is_running=False,
    )
    assert r3 == "Nahi, Chrome abhi open nahi hai."


def test_policy_running_question():
    """
    User: 'Chrome chal raha hai?'
    When running: 'Haan, Chrome chal raha hai.'
    When not running: 'Nahi, Chrome abhi nahi chal raha.'
    """
    r1 = ConversationalResponsePolicy.format_status_response(
        query="Chrome chal raha hai?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
    )
    assert r1 == "Haan, Chrome chal raha hai."

    r2 = ConversationalResponsePolicy.format_status_response(
        query="Chrome chal raha hai?",
        target="chrome",
        is_open=False,
        is_active=False,
        is_minimized=False,
        is_running=False,
    )
    assert r2 == "Nahi, Chrome abhi nahi chal raha."


def test_policy_negative_check():
    """
    User: 'Chrome open nahi hai na?'
    When open: 'Nahi, Chrome open hai.'
    When closed: 'Nahi, Chrome abhi open nahi hai.'
    """
    r1 = ConversationalResponsePolicy.format_status_response(
        query="Chrome open nahi hai na?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
    )
    assert r1 == "Nahi, Chrome open hai."

    r2 = ConversationalResponsePolicy.format_status_response(
        query="Chrome open nahi hai na?",
        target="chrome",
        is_open=False,
        is_active=False,
        is_minimized=False,
        is_running=False,
    )
    assert r2 == "Nahi, Chrome abhi open nahi hai."


def test_policy_which_window_active():
    """
    User: 'Kaunsa Chrome window active hai?'
    Preferred: '‘Jarvis Low Voice Fix’ wala window active hai.'
    """
    resp = ConversationalResponsePolicy.format_status_response(
        query="Kaunsa Chrome window active hai?",
        target="chrome",
        is_open=True,
        is_active=True,
        is_minimized=False,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert "Jarvis Low Voice Fix" in resp
    assert "wala window active hai" in resp


def test_policy_minimized_state():
    """
    When app is minimized and user asks if it's open:
    Preferred: 'Chrome open hai, lekin minimized hai.'
    """
    resp = ConversationalResponsePolicy.format_status_response(
        query="Chrome open hai kya?",
        target="chrome",
        is_open=True,
        is_active=False,
        is_minimized=True,
        is_running=True,
        window_title="Jarvis Low Voice Fix - Google Chrome"
    )
    assert resp == "Chrome open hai, lekin minimized hai."


def test_policy_tab_in_browser():
    """
    When website is open in a specific browser tab:
    Preferred: 'Haan, YouTube Brave mein open hai.'
    """
    resp = ConversationalResponsePolicy.format_status_response(
        query="YouTube open hai kya?",
        target="youtube",
        is_open=True,
        is_active=False,
        is_minimized=False,
        is_running=True,
        window_title="YouTube - Watch Videos Online",
        browser="brave"
    )
    assert resp == "Haan, Youtube Brave mein open hai."


def test_end_to_end_core_chrome_open_hai_kya():
    """
    End-to-end integration: JarvisCore processes 'Chrome open hai kya?'
    and returns concise 'Haan, Chrome open hai.' without debug title parentheses.
    """
    core = JarvisCore()
    win = WindowInfo(hwnd=101, title="Jarvis Low Voice Fix - Google Chrome", process_name="chrome.exe", pid=2020)

    with patch.object(core.target_engine.resolver, "resolve", return_value=[]), \
         patch.object(core.target_engine.window_manager, "find_windows_for_app", return_value=[win]), \
         patch("win32gui.GetForegroundWindow", return_value=999), \
         patch("win32gui.IsIconic", return_value=False):

        resp = core.process_input("Chrome open hai kya?")
        assert resp == "Haan, Chrome open hai."
        assert "(" not in resp
        assert "Google Chrome" not in resp  # Does not dump raw window title
