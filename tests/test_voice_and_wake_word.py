# tests/test_voice_and_wake_word.py
"""Unit tests for the Independent Universal Wake-Word Detector & 7-State Machine."""

import pytest
from core.state import StateMachine, SystemState
from voice.wake_word import WakeWordDetector


def test_wake_word_prefix():
    detector = WakeWordDetector(["jarvis"])
    res = detector.detect("Jarvis, Chrome kholo")
    assert res.detected is True
    assert res.position == "prefix"
    assert res.cleaned_command == "Chrome kholo"
    assert res.is_standalone is False


def test_wake_word_suffix_with_comma():
    detector = WakeWordDetector(["jarvis"])
    res = detector.detect("Chrome kholo, Jarvis")
    assert res.detected is True
    assert res.position == "suffix"
    assert res.cleaned_command == "Chrome kholo"
    assert res.is_standalone is False


def test_wake_word_suffix_without_comma():
    detector = WakeWordDetector(["jarvis"])
    res = detector.detect("Chrome kholo Jarvis")
    assert res.detected is True
    assert res.position == "suffix"
    assert res.cleaned_command == "Chrome kholo"
    assert res.is_standalone is False


def test_wake_word_standalone():
    detector = WakeWordDetector(["jarvis"])
    res = detector.detect("Jarvis")
    assert res.detected is True
    assert res.position == "standalone"
    assert res.is_standalone is True
    assert res.cleaned_command == ""


def test_wake_word_embedded():
    detector = WakeWordDetector(["jarvis"])
    res = detector.detect("Hey Jarvis please open Chrome")
    assert res.detected is True
    assert "open Chrome" in res.cleaned_command


def test_7_state_lifecycle_transitions():
    sm = StateMachine(initial_state=SystemState.IDLE)
    assert sm.current_state == SystemState.IDLE

    # IDLE -> WAKE_DETECTED
    assert sm.transition_to(SystemState.WAKE_DETECTED) is True
    assert sm.current_state == SystemState.WAKE_DETECTED

    # WAKE_DETECTED -> LISTENING
    assert sm.transition_to(SystemState.LISTENING) is True
    assert sm.current_state == SystemState.LISTENING

    # LISTENING -> PROCESSING
    assert sm.transition_to(SystemState.PROCESSING) is True
    assert sm.current_state == SystemState.PROCESSING

    # PROCESSING -> EXECUTING
    assert sm.transition_to(SystemState.EXECUTING) is True
    assert sm.current_state == SystemState.EXECUTING

    # EXECUTING -> RESPONDING
    assert sm.transition_to(SystemState.RESPONDING) is True
    assert sm.current_state == SystemState.RESPONDING

    # RESPONDING -> IDLE
    assert sm.transition_to(SystemState.IDLE) is True
    assert sm.current_state == SystemState.IDLE
