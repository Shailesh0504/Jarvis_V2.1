# tests/test_wake_word_position_independent.py
"""
Comprehensive Unit & Regression Tests for Position-Independent Wake-Word Detection.
Verifies detection of 'Jarvis' anywhere in the utterance:
- Beginning, middle, end, standalone
- Uppercase, lowercase, mixed case
- Punctuation variants (commas, exclamation, quotes)
- Hinglish and Hindi natural phrasing
- Multi-command preservation
- Multiple wake-word occurrences
- False positive resistance (jarvisian, jarvises, myjarvisapp, jarvis123, jarvis-app)
- Payload preservation
- Clean extraction & JARVIS_ADDRESSED=True invariant
- Delegation via core.conversation.WakeWordDetector
"""

import logging
import pytest

from voice.wake_word import (
    WakeWordDetector,
    WakeWordMatchResult,
    WakePosition,
    contains_standalone_wake_word,
    normalize_text,
)
from core.conversation import WakeWordDetector as CoreWakeWordDetector, ConversationManager


@pytest.fixture
def detector():
    return WakeWordDetector()


# ---------------------------------------------------------------------------
# 1. Ten Core User-Specified Examples
# ---------------------------------------------------------------------------

def test_example_1_beginning(detector):
    """1. 'Jarvis YouTube open karo' -> Beginning"""
    res = detector.detect("Jarvis YouTube open karo")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.position == "prefix"
    assert res.cleaned_command == "YouTube open karo"


def test_example_2_end(detector):
    """2. 'Chrome and Brave open karo Jarvis' -> End"""
    res = detector.detect("Chrome and Brave open karo Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "end"
    assert res.position == "suffix"
    assert res.cleaned_command == "Chrome and Brave open karo"


def test_example_3_middle(detector):
    """3. 'Mujhe Mumbai jana hai Jarvis batao kaise jau' -> Middle"""
    res = detector.detect("Mujhe Mumbai jana hai Jarvis batao kaise jau")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "middle"
    assert res.position == "embedded"
    assert res.cleaned_command == "Mujhe Mumbai jana hai batao kaise jau"


def test_example_4_beginning_with_comma(detector):
    """4. 'Jarvis, Chrome kholo' -> Beginning with comma"""
    res = detector.detect("Jarvis, Chrome kholo")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "Chrome kholo"


def test_example_5_end_simple(detector):
    """5. 'Chrome kholo Jarvis' -> End"""
    res = detector.detect("Chrome kholo Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "end"
    assert res.cleaned_command == "Chrome kholo"


def test_example_6_greeting_prefix(detector):
    """6. 'Hey Jarvis YouTube chalao' -> Beginning with greeting"""
    res = detector.detect("Hey Jarvis YouTube chalao")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "YouTube chalao"


def test_example_7_beginning_hinglish(detector):
    """7. 'Jarvis mujhe ek baat batao' -> Beginning"""
    res = detector.detect("Jarvis mujhe ek baat batao")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "mujhe ek baat batao"


def test_example_8_end_hinglish(detector):
    """8. 'Mujhe ek baat batao Jarvis' -> End"""
    res = detector.detect("Mujhe ek baat batao Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "end"
    assert res.cleaned_command == "Mujhe ek baat batao"


def test_example_9_beginning_suno_zara(detector):
    """9. 'Jarvis suno zara' -> Beginning"""
    res = detector.detect("Jarvis suno zara")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "suno zara"


def test_example_10_end_zara_suno(detector):
    """10. 'Zara suno Jarvis' -> End (preserves 'Zara suno' command)"""
    res = detector.detect("Zara suno Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "end"
    assert res.cleaned_command == "Zara suno"


# ---------------------------------------------------------------------------
# 2. Case Insensitivity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("casing", ["Jarvis", "JARVIS", "jarvis", "JaRvIs", "jArViS"])
def test_case_insensitivity_standalone(detector, casing):
    res = detector.detect(casing)
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.is_standalone is True
    assert res.position == "standalone"
    assert res.cleaned_command == ""


@pytest.mark.parametrize("casing", ["Jarvis", "JARVIS", "jarvis", "JaRvIs"])
def test_case_insensitivity_in_sentence(detector, casing):
    res = detector.detect(f"open chrome {casing}")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.cleaned_command == "open chrome"


# ---------------------------------------------------------------------------
# 3. Punctuation Variants
# ---------------------------------------------------------------------------

def test_punctuation_trailing_comma(detector):
    res = detector.detect("Chrome kholo, Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "end"
    assert res.cleaned_command == "Chrome kholo"


def test_punctuation_exclamation(detector):
    res = detector.detect("Jarvis! YouTube kholo")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "YouTube kholo"


def test_punctuation_hey_comma_jarvis_comma(detector):
    res = detector.detect("Hey, Jarvis, YouTube kholo")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert res.cleaned_command == "YouTube kholo"


def test_punctuation_middle_commas(detector):
    res = detector.detect("Mujhe Mumbai jana hai, Jarvis, batao kaise jau")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "middle"
    assert res.cleaned_command == "Mujhe Mumbai jana hai batao kaise jau"


def test_punctuation_quotes(detector):
    res = detector.detect('"Jarvis" open settings')
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.cleaned_command == "open settings"


# ---------------------------------------------------------------------------
# 4. Standalone and Empty Utterances
# ---------------------------------------------------------------------------

def test_standalone_variations(detector):
    for raw in ["Jarvis", "Jarvis!", "Jarvis?", "Jarvis.", "Hey Jarvis", "Hey, Jarvis"]:
        res = detector.detect(raw)
        assert res.detected is True
        assert res.jarvis_addressed is True
        assert res.is_standalone is True
        assert res.cleaned_command == ""


def test_empty_and_whitespace(detector):
    assert detector.detect("").detected is False
    assert detector.detect("   ").detected is False
    assert detector.detect(None).detected is False


# ---------------------------------------------------------------------------
# 5. False Positive Protection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fp_word", [
    "jarvisian",
    "jarvises",
    "myjarvisapp",
    "jarvis123",
    "jarvis-app",
    "my-jarvis",
    "jarvis_core",
])
def test_false_positive_similar_tokens(detector, fp_word):
    res = detector.detect(fp_word)
    assert res.detected is False
    assert res.jarvis_addressed is False


@pytest.mark.parametrize("fp_word", [
    "use jarvisian method",
    "install myjarvisapp now",
    "run jarvis123 script",
])
def test_false_positive_in_sentence(detector, fp_word):
    res = detector.detect(fp_word)
    assert res.detected is False
    assert res.jarvis_addressed is False


def test_negative_phrases(detector):
    assert detector.detect("java is a programming language").detected is False
    assert detector.detect("the jar on the table is full").detected is False
    assert detector.detect("take the car to customer service").detected is False
    assert detector.detect("web service is running normally").detected is False


# ---------------------------------------------------------------------------
# 6. Payload Argument Preservation
# ---------------------------------------------------------------------------

def test_payload_preservation_typing(detector):
    res = detector.detect("desktop pe ek test.txt file banao or usme Jarvis type karo")
    # Should not trigger as wake address; payload is preserved
    assert res.detected is False


def test_payload_preservation_writing(detector):
    res = detector.detect("file me likho Jarvis")
    assert res.detected is False


def test_payload_preservation_with_actual_wake_word(detector):
    # Beginning is a real wake word address; inner is a search term
    res = detector.detect("Jarvis, search Jarvis on google")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.position == "beginning"
    assert "search Jarvis on google" in res.cleaned_command


# ---------------------------------------------------------------------------
# 7. Deduplication of Multiple Wake Words
# ---------------------------------------------------------------------------

def test_repeated_wake_words(detector):
    res = detector.detect("Jarvis Chrome kholo Jarvis")
    assert res.detected is True
    assert res.jarvis_addressed is True
    assert res.cleaned_command == "Chrome kholo"


# ---------------------------------------------------------------------------
# 8. Helper Functions
# ---------------------------------------------------------------------------

def test_helper_contains_standalone_wake_word():
    assert contains_standalone_wake_word("Zara suno Jarvis") is True
    assert contains_standalone_wake_word("Jarvis YouTube open karo") is True
    assert contains_standalone_wake_word("jarvisian") is False
    assert contains_standalone_wake_word("myjarvisapp") is False
    assert contains_standalone_wake_word("jarvis123") is False


def test_helper_normalize_text():
    assert normalize_text("  Jarvis   open    chrome   ") == "Jarvis open chrome"
    assert normalize_text("") == ""


# ---------------------------------------------------------------------------
# 9. Core ConversationManager Integration
# ---------------------------------------------------------------------------

def test_core_wake_word_detector_delegation():
    cwd = CoreWakeWordDetector()
    is_wake, payload = cwd.detect_and_strip("Chrome and Brave open karo Jarvis")
    assert is_wake is True
    assert payload == "Chrome and Brave open karo"

    is_wake, payload = cwd.detect_and_strip("Mujhe Mumbai jana hai Jarvis batao kaise jau")
    assert is_wake is True
    assert payload == "Mujhe Mumbai jana hai batao kaise jau"

    is_wake, payload = cwd.detect_and_strip("Jarvis YouTube open karo")
    assert is_wake is True
    assert payload == "YouTube open karo"


def test_conversation_manager_process_incoming_input():
    cm = ConversationManager()
    turn = cm.process_incoming_input("Chrome and Brave open karo Jarvis", source="voice")
    assert turn.wake_word_detected is True
    assert "Chrome and Brave open karo" in turn.normalized_input


# ---------------------------------------------------------------------------
# 10. Logging Verification
# ---------------------------------------------------------------------------

def test_structured_logging(detector, caplog):
    caplog.set_level(logging.INFO, logger="jarvis.voice.wakeword")
    res = detector.detect("Mujhe Mumbai jana hai Jarvis batao kaise jau")
    assert res.detected is True

    log_text = caplog.text
    assert "[WAKE] Wake word detected: Jarvis" in log_text
    assert "[WAKE] Position: middle" in log_text
    assert "[WAKE] JARVIS_ADDRESSED=True" in log_text
    assert '[WAKE] Clean utterance: "Mujhe Mumbai jana hai batao kaise jau"' in log_text
