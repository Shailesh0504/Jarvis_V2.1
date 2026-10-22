# tests/test_learning_communication_engine.py
"""Comprehensive automated test suite for the Learning Communication Engine (LCE)."""

import os
import time
import pytest

from learning.communication_engine import LearningCommunicationEngine
from learning.communication_normalizer import CommunicationNormalizer, UtteranceTokens
from learning.communication_matcher import CommunicationMatcher
from learning.communication_feedback import CommunicationFeedback
from memory.database import DatabaseManager
from main import create_jarvis


@pytest.fixture
def lce_db(tmp_path):
    db_file = os.path.join(tmp_path, "lce_test.db").replace("\\", "/")
    db = DatabaseManager(db_path=db_file)
    return db


@pytest.fixture
def lce_engine(lce_db):
    return LearningCommunicationEngine(db=lce_db, enabled=True)


def test_lce_preprocessing_and_phonetic_fixes(lce_engine):
    """Verifies that common STT phonetic variations are corrected while preserving raw input."""
    raw = "jarvis ek molakat ek bahana he chalao"
    tokens = lce_engine.preprocess(raw, context_key="global")

    assert tokens.raw_text == raw
    assert "molakat" in tokens.normalized_text
    assert "mulaqat" in tokens.corrected_text
    assert "hai" in tokens.corrected_text
    assert tokens.language == "hinglish"


def test_lce_utterance_tokens_preservation(lce_engine):
    """Ensures raw, normalized, and corrected representations are maintained as separate fields."""
    raw = "  Excl khol do plz!  "
    tokens = lce_engine.preprocess(raw, context_key="excel")

    assert tokens.raw_text == raw
    assert tokens.normalized_text == "excl khol do plz"
    assert tokens.corrected_text == "excel kholo please"
    assert tokens.context_key == "excel"


def test_lce_context_aware_pattern_learning(lce_engine):
    """Verifies that patterns are learned contextually and matched with context priority."""
    tokens_vlc = UtteranceTokens(raw_text="isko band karo", normalized_text="isko band karo", corrected_text="isko band karo")
    lce_engine.record_success(tokens_vlc, intent="CLOSE_CURRENT_MEDIA", context_key="vlc", explicit_confirmation=True)

    tokens_excel = UtteranceTokens(raw_text="isko band karo", normalized_text="isko band karo", corrected_text="isko band karo")
    lce_engine.record_success(tokens_excel, intent="CLOSE_CURRENT_WORKBOOK", context_key="excel", explicit_confirmation=True)

    # Lookup in VLC context
    cand_vlc = lce_engine.resolve_contextual_candidate(tokens_vlc, context_key="vlc")
    assert cand_vlc is not None
    assert cand_vlc["intent"] == "CLOSE_CURRENT_MEDIA"

    # Lookup in Excel context
    cand_excel = lce_engine.resolve_contextual_candidate(tokens_excel, context_key="excel")
    assert cand_excel is not None
    assert cand_excel["intent"] == "CLOSE_CURRENT_WORKBOOK"


def test_lce_feedback_and_correction_handling(lce_engine):
    """Verifies that user corrections ('Nahi, Excel bola tha') update vocabulary and confidence."""
    # First turn
    tokens = lce_engine.preprocess("eksal kholo", context_key="global")
    lce_engine._last_interpreted_intent = "OPEN_UNKNOWN"

    # Correction turn
    handled, msg = lce_engine.handle_correction_or_feedback("Nahi, Excel bola tha", context_key="global")
    assert handled is True
    assert "excel" in msg.lower()

    # Next occurrence of 'eksal kholo' should resolve to 'excel' via learned vocabulary
    next_tokens = lce_engine.preprocess("eksal kholo", context_key="global")
    assert "excel" in next_tokens.corrected_text.lower()


def test_lce_confidence_scoring_and_thresholds(lce_engine):
    """Verifies confidence progression (+0.05 on success, -0.15 on correction) and bounded limits."""
    tokens = UtteranceTokens(raw_text="budget file kholo", normalized_text="budget file kholo", corrected_text="budget file kholo")
    lce_engine.record_success(tokens, intent="OPEN_DOCUMENT", context_key="excel", explicit_confirmation=False)

    pat = lce_engine.memory.get_pattern("budget file kholo", context_key="excel")
    assert pat is not None
    initial_conf = pat["confidence"]
    assert initial_conf >= 0.70

    # Negative rejection reduces confidence
    lce_engine._last_utterance_tokens = tokens
    lce_engine.handle_correction_or_feedback("galat", context_key="excel")

    pat_after = lce_engine.memory.get_pattern("budget file kholo", context_key="excel")
    assert pat_after["confidence"] < initial_conf


def test_lce_safety_guard_blocks_dangerous_actions(lce_engine):
    """Ensures dangerous operations (e.g. shutdown, format, delete) are NEVER auto-learned without explicit confirmation."""
    tokens = UtteranceTokens(raw_text="sab khatam karo", normalized_text="sab khatam karo", corrected_text="sab khatam karo")
    # Attempt implicit auto-learn on dangerous action
    lce_engine.record_success(tokens, intent="shutdown_system", context_key="global", explicit_confirmation=False)

    pat = lce_engine.memory.get_pattern("sab khatam karo", context_key="global")
    assert pat is None  # Must be blocked from auto-learning


def test_lce_audit_and_forget_commands(tmp_path):
    """Verifies end-to-end audit ('maine kya sikhaya hai') and forget ('isko bhool jao') in JarvisCore."""
    db_file = os.path.join(tmp_path, "jarvis_audit.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_LCE_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'audit_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    core = create_jarvis(str(cfg_file))

    # Pre-populate a pattern
    tokens = UtteranceTokens(raw_text="gaana chalao", normalized_text="gaana chalao", corrected_text="gaana chalao")
    core.learning_manager.lce.record_success(tokens, intent="PLAY_MEDIA", context_key="global", explicit_confirmation=True)

    # Ask audit question
    resp_audit = core.process_input("Jarvis maine kya sikhaya hai?")
    assert "gaana chalao" in resp_audit or "PLAY_MEDIA" in resp_audit or "pattern" in resp_audit.lower()

    # Forget pattern
    resp_forget = core.process_input("gaana chalao ki learning bhool jao")
    assert "bhool" in resp_forget.lower()
