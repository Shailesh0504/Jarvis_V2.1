# tests/test_execution_preference.py
"""
Regression tests for the Preference Memory System (ExecutionPreferenceManager).

Covers:
  - Basic set / get / clear for permanent preferences
  - Session-scope preferences (not persisted)
  - Explicit container overrides saved preference (enforced by caller)
  - CorrectionsLayer browser-preference pattern detection
  - LearningManager passthrough helpers
"""

from __future__ import annotations

import os
import sys
import tempfile
import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from memory.database import DatabaseManager
from learning.execution_preference import ExecutionPreferenceManager
from learning.corrections_layer import CorrectionsLayer, CorrectionResult
from learning.preferences_layer import PreferencesLayer
from learning.vocabulary_layer import VocabularyLayer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Isolated in-memory-like SQLite database for each test."""
    db_path = str(tmp_path / "test_jarvis.db")
    return DatabaseManager(db_path=db_path)


@pytest.fixture
def exec_pref(tmp_db):
    return ExecutionPreferenceManager(tmp_db)


@pytest.fixture
def corrections_layer(tmp_db):
    vocab = VocabularyLayer(tmp_db)
    prefs = PreferencesLayer(tmp_db)
    return CorrectionsLayer(tmp_db, vocab, prefs)


# ===========================================================================
# ExecutionPreferenceManager — unit tests
# ===========================================================================

class TestExecutionPreferenceManager:
    def test_set_and_get_permanent(self, exec_pref):
        exec_pref.set_target_preference("youtube", "brave")
        assert exec_pref.get_target_preference("youtube") == "brave"

    def test_normalization(self, exec_pref):
        """Keys and values must be normalized to lowercase."""
        exec_pref.set_target_preference("YouTube", "Brave")
        assert exec_pref.get_target_preference("youtube") == "brave"
        assert exec_pref.get_target_preference("YouTube") == "brave"

    def test_get_missing_returns_none(self, exec_pref):
        assert exec_pref.get_target_preference("gmail") is None

    def test_overwrite_existing(self, exec_pref):
        exec_pref.set_target_preference("gmail", "chrome")
        exec_pref.set_target_preference("gmail", "brave")
        assert exec_pref.get_target_preference("gmail") == "brave"

    def test_session_scope_not_persisted(self, tmp_db):
        """Session-scope preferences must NOT be written to SQLite."""
        mgr1 = ExecutionPreferenceManager(tmp_db)
        mgr1.set_target_preference("spotify", "chrome", scope="session")
        assert mgr1.get_target_preference("spotify") == "chrome"

        # A second manager on the same DB should NOT see the session pref
        mgr2 = ExecutionPreferenceManager(tmp_db)
        assert mgr2.get_target_preference("spotify") is None

    def test_session_overrides_permanent(self, exec_pref):
        exec_pref.set_target_preference("google", "chrome", scope="permanent")
        exec_pref.set_target_preference("google", "brave", scope="session")
        # Session override takes priority
        assert exec_pref.get_target_preference("google") == "brave"

    def test_clear_permanent(self, exec_pref):
        exec_pref.set_target_preference("youtube", "brave")
        exec_pref.clear_target_preference("youtube", scope="permanent")
        assert exec_pref.get_target_preference("youtube") is None

    def test_clear_session(self, exec_pref):
        exec_pref.set_target_preference("youtube", "brave", scope="session")
        exec_pref.clear_target_preference("youtube", scope="session")
        assert exec_pref.get_target_preference("youtube") is None

    def test_clear_all(self, exec_pref):
        exec_pref.set_target_preference("gmail", "chrome")
        exec_pref.set_target_preference("gmail", "firefox", scope="session")
        exec_pref.clear_target_preference("gmail", scope="all")
        assert exec_pref.get_target_preference("gmail") is None

    def test_get_all(self, exec_pref):
        exec_pref.set_target_preference("youtube", "brave")
        exec_pref.set_target_preference("gmail", "chrome")
        result = exec_pref.get_all_target_preferences()
        assert result.get("youtube") == "brave"
        assert result.get("gmail") == "chrome"

    def test_explicit_does_not_call_set(self, exec_pref):
        """Verify that the manager itself doesn't auto-set on get (caller's responsibility)."""
        exec_pref.set_target_preference("youtube", "brave")
        # Simulate explicit override scenario: caller uses 'chrome' but doesn't write it
        val = exec_pref.get_target_preference("youtube")
        assert val == "brave"  # saved pref unchanged


# ===========================================================================
# CorrectionsLayer — browser-preference pattern detection
# ===========================================================================

class TestBrowserPreferenceDetection:
    def _assert_bp(self, corr: CorrectionResult, target: str, browser: str):
        assert corr.is_correction, "Expected correction=True"
        assert corr.correction_type == "browser_preference", \
            f"Expected 'browser_preference', got '{corr.correction_type}'"
        assert corr.target == target, f"Expected target={target!r}, got {corr.target!r}"
        assert corr.preferred_container == browser, \
            f"Expected browser={browser!r}, got {corr.preferred_container!r}"

    def test_nahi_youtube_brave_mein_open_karo(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction(
            "nahi, youtube brave mein open karo"
        )
        self._assert_bp(corr, "youtube", "brave")

    def test_nahi_youtube_chrome_mein_kholo(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction(
            "nahi youtube chrome mein kholo"
        )
        self._assert_bp(corr, "youtube", "chrome")

    def test_open_youtube_in_brave_english(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction("open youtube in brave")
        self._assert_bp(corr, "youtube", "brave")

    def test_nahi_open_gmail_in_chrome(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction("nahi, open gmail in chrome")
        self._assert_bp(corr, "gmail", "chrome")

    def test_youtube_ko_brave_mein_kholo(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction(
            "youtube ko brave mein kholo"
        )
        self._assert_bp(corr, "youtube", "brave")

    def test_ab_se_youtube_brave_mein_kholna(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction(
            "ab se youtube brave mein kholna"
        )
        self._assert_bp(corr, "youtube", "brave")

    def test_youtube_brave_mein_open_karo_no_marker(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction(
            "youtube brave mein open karo"
        )
        self._assert_bp(corr, "youtube", "brave")

    def test_context_only_browser_correction(self, corrections_layer):
        """'nahi, brave mein kholo' — no target in utterance (context-dependent)."""
        corr = corrections_layer.parse_and_apply_correction("nahi, brave mein kholo")
        assert corr.is_correction
        assert corr.correction_type == "browser_preference"
        assert corr.target == ""          # caller fills from active context
        assert corr.preferred_container == "brave"

    def test_non_browser_word_not_detected(self, corrections_layer):
        """'youtube notepad mein open karo' must NOT trigger browser preference."""
        corr = corrections_layer.parse_and_apply_correction(
            "youtube notepad mein open karo"
        )
        # notepad is not a known browser — should not produce browser_preference
        assert corr.correction_type != "browser_preference" or not corr.is_correction

    def test_normal_command_not_correction(self, corrections_layer):
        corr = corrections_layer.parse_and_apply_correction("youtube kholo")
        assert not corr.is_correction

    def test_session_scope_aaj_ke_liye(self, corrections_layer):
        """'aaj ke liye' marker — session scope (checked by caller, detected via correction_type)."""
        corr = corrections_layer.parse_and_apply_correction(
            "aaj ke liye youtube brave mein open karo"
        )
        self._assert_bp(corr, "youtube", "brave")
        # Note: scope detection ('aaj ke liye') is handled by app.py, not corrections_layer.
        # This test just verifies detection works.


# ===========================================================================
# LearningManager — passthrough helpers
# ===========================================================================

class TestLearningManagerPassthrough:
    def test_set_and_get_via_manager(self, tmp_db):
        from learning.learner import LearningManager
        mgr = LearningManager(tmp_db, enabled=True)
        mgr.set_execution_preference("youtube", "brave")
        assert mgr.get_execution_preference("youtube") == "brave"

    def test_exec_pref_attribute_exists(self, tmp_db):
        from learning.learner import LearningManager
        mgr = LearningManager(tmp_db, enabled=True)
        assert hasattr(mgr, "exec_pref"), "LearningManager must expose .exec_pref"
        assert isinstance(mgr.exec_pref, ExecutionPreferenceManager)

    def test_preference_survives_new_manager_instance(self, tmp_db):
        """Permanent preference written by one LearningManager instance should be
        visible to a new instance on the same DB (simulates restart)."""
        from learning.learner import LearningManager
        mgr1 = LearningManager(tmp_db, enabled=True)
        mgr1.set_execution_preference("gmail", "chrome")

        mgr2 = LearningManager(tmp_db, enabled=True)
        assert mgr2.get_execution_preference("gmail") == "chrome"
