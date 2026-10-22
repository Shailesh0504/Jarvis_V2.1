# tests/test_system_confirmation.py
"""Tests for Human-like System Restart & Shutdown Confirmation Multi-turn Dialogs."""

from unittest.mock import patch

import pytest
from main import create_jarvis


@pytest.fixture
def jarvis():
    return create_jarvis()


def test_system_restart_affirmative_flow(jarvis):
    # Step 1: User requests system restart
    resp1 = jarvis.process_input("system restart karo")
    assert "kya aap sach me system restart" in resp1.lower() or "confirm" in resp1.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is True

    # Step 2: User confirms with "haan"
    # Safety: test me real OS restart/shutdown kabhi execute nahi hona chahiye.
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("haan")
        mock_popen.assert_not_called()
    assert "restart ho raha hai" in resp2.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is False


def test_system_shutdown_cancellation_flow(jarvis):
    # Step 1: User requests system shutdown
    resp1 = jarvis.process_input("system shutdown karo")
    assert "kya main computer shutdown" in resp1.lower() or "confirm" in resp1.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is True

    # Step 2: User cancels with "nahi"
    resp2 = jarvis.process_input("nahi")
    assert "cancel" in resp2.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is False


def test_system_restart_english_flow(jarvis):
    # Step 1: User requests in English
    resp1 = jarvis.process_input("restart the computer")
    assert "are you sure you want to restart" in resp1.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is True

    # Step 2: User confirms with "yes"
    # Safety: test me real OS restart/shutdown kabhi execute nahi hona chahiye.
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("yes")
        mock_popen.assert_not_called()
    assert "restarting" in resp2.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is False


def test_system_shutdown_english_cancel_flow(jarvis):
    # Step 1: User requests in English
    resp1 = jarvis.process_input("shut down the computer")
    assert "are you sure you want to shut down" in resp1.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is True

    # Step 2: User cancels with "cancel"
    resp2 = jarvis.process_input("cancel")
    assert "cancelled" in resp2.lower() or "aborted" in resp2.lower()
    assert jarvis.dialog_manager.has_pending_system_action() is False


def test_hinglish_variations_flow(jarvis):
    # "pc band karo" -> "haan kar do"
    resp1 = jarvis.process_input("pc band karo")
    assert "shutdown" in resp1.lower() or "confirm" in resp1.lower()
    # Safety: test me real OS restart/shutdown kabhi execute nahi hona chahiye.
    with patch("subprocess.Popen") as mock_popen:
        resp2 = jarvis.process_input("haan kar do")
        mock_popen.assert_not_called()
    assert "shutdown kar raha hoon" in resp2.lower()

    # "computer restart karo" -> "mat karo"
    resp3 = jarvis.process_input("computer restart karo")
    assert "restart" in resp3.lower() or "confirm" in resp3.lower()
    resp4 = jarvis.process_input("mat karo")
    assert "cancel" in resp4.lower()
