# tests/test_conversational_contradiction_negation.py
"""
Unit and integration tests for:
1. Conversational Speech-Act Gating & State Contradiction Invariants.
   Ensures user objections, contradictions, and state negations (e.g.
   "lekin Chrome mein to open YouTube Nahin Hai") are NEVER treated as ACTION_COMMAND.
2. Honest State Verification & Confirmation Offering.
3. Persistent User Preferred Browser Learning & Recall across Restarts:
   - "mera favorite browser Firefox hai" -> "Okay Sir."
   - "browser kholo" -> opens Firefox
   - "nahi, maine bola tha Firefox mera favorite browser hai" -> "Samajh gaya Sir. Aapka preferred browser Firefox hai. Main ise yaad rakhunga."
   - Restart -> "browser kholo" -> opens Firefox persistently without being told again.
"""

import pytest
from unittest.mock import MagicMock, patch

from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
)
from brain.personal_profile import PersonalProfileExtractor
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager
from learning.learner import LearningManager
from learning.vocabulary_layer import VocabularyLayer
from learning.preferences_layer import PreferencesLayer
from learning.corrections_layer import CorrectionsLayer
from core.app import JarvisCore


class TestConversationalContradictionGating:
    """Verifies that speech-act classifier never treats contradictions or negations as action commands."""

    @pytest.mark.parametrize("query,expected_target,expected_container", [
        ("lekin Chrome mein to open YouTube Nahin Hai", "youtube", "chrome"),
        ("par Chrome mein to YouTube open nahi hai", "youtube", "chrome"),
        ("par Chrome mein to open nahi hai YouTube", "youtube", "chrome"),
        ("lekin YouTube to open nahi hai", "youtube", None),
        ("par YouTube open nahi hai", "youtube", None),
        ("lekin open to nahi hai", None, None),
        ("par open nahi hai", None, None),
        ("par khula nahi hai", None, None),
        ("but YouTube is not open in Chrome", "youtube", "chrome"),
        ("but it is not open", None, None),
    ])
    def test_contradictions_and_disputes_are_not_executable(self, query, expected_target, expected_container):
        res = ConversationalIntentClassifier.classify(query)
        assert res.intent_type == ConversationalIntentType.CORRECTION
        assert res.is_executable is False
        assert res.parameters.get("state_dispute") is True
        assert res.parameters.get("disputed_condition") == "NOT_OPEN"
        if expected_target:
            assert res.parameters.get("target") == expected_target
        if expected_container:
            assert res.parameters.get("container") == expected_container

    @pytest.mark.parametrize("query,expected_target", [
        ("Chrome open karo", "chrome"),
        ("open Chrome", "chrome"),
        ("YouTube chalao", "youtube"),
        ("system lock karo", "system"),
    ])
    def test_genuine_action_commands_remain_executable(self, query, expected_target):
        res = ConversationalIntentClassifier.classify(query)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND
        assert res.is_executable is True
        assert res.target == expected_target


class TestStateDisputeCoreIntegration:
    """Verifies JarvisCore handles state disputes truthfully without executing commands."""

    @pytest.fixture
    def test_core(self, tmp_path):
        db_path = str(tmp_path / "test_state_dispute.db")
        db = DatabaseManager(db_path=db_path)
        mem = MemoryManager(db_path=db_path)
        lm = LearningManager(db=db, enabled=True)

        core = JarvisCore()
        pm = MagicMock()
        pm.discover_and_load.return_value = None
        pm.execute_action.return_value = MagicMock(success=True, data={"message": "ok"})
        
        core.initialize_subsystems(
            memory_manager=mem,
            learning_manager=lm,
            brain=MagicMock(),
            classifier=MagicMock(),
            plugin_manager=pm,
            response_generator=MagicMock(),
        )
        return core

    def test_user_dispute_does_not_launch_chrome(self, test_core):
        """When user says 'lekin Chrome mein to open YouTube Nahin Hai', core must NOT execute open chrome."""
        with patch.object(test_core.target_engine, "execute") as mock_exec, \
             patch.object(test_core.target_engine, "check_target_status", return_value="Sir, maine check kiya, Youtube abhi kisi bhi browser mein open nahi hai. Kya aap Youtube open karna chahte hain?"):
            
            resp = test_core.process_input("lekin Chrome mein to open YouTube Nahin Hai", source="cli")
            
            # Command execution must NEVER have been called!
            mock_exec.assert_not_called()
            
            # Response must apologize and state that YouTube is not open in Chrome
            assert "maafi chahta hoon" in resp.lower() or "apologies" in resp.lower()
            assert "chrome" in resp.lower()
            assert "youtube" in resp.lower()
            assert "open nahi hai" in resp.lower()
            
            # Follow-up confirmation must be pending
            conf_mgr = test_core.confirmation_manager
            assert conf_mgr.has_pending_confirmation() is True
            assert conf_mgr.pending.parameters.get("target") == "youtube"


class TestBrowserPreferenceLearningAndPersistence:
    """Verifies the complete user preference, correction, and restart persistence lifecycle."""

    @pytest.fixture
    def core_with_db(self, tmp_path):
        db_path = str(tmp_path / "pref_test.db")
        db = DatabaseManager(db_path=db_path)
        mem = MemoryManager(db_path=db_path)
        lm = LearningManager(db=db, enabled=True)

        core = JarvisCore()
        pm = MagicMock()
        pm.discover_and_load.return_value = None
        pm.execute_action.return_value = MagicMock(success=True, data={"message": "ok"})

        core.initialize_subsystems(
            memory_manager=mem,
            learning_manager=lm,
            brain=MagicMock(),
            classifier=MagicMock(),
            plugin_manager=pm,
            response_generator=MagicMock(),
        )
        return core, db_path

    def test_browser_preference_full_lifecycle(self, core_with_db):
        core, db_path = core_with_db

        # Step 1: User states preference: "mera favorite browser Firefox hai"
        resp1 = core.process_input("mera favorite browser Firefox hai", source="cli")
        assert "okay sir" in resp1.lower()
        
        # Verify persistence in preferences and vocabulary
        assert core.learning_manager.preferences.get("preferred_browser") == "firefox"
        assert core.learning_manager.vocabulary.get_term("browser") == "firefox"

        # Step 2: "browser kholo" must resolve to "firefox kholo"
        resolved = core.learning_manager.resolve_vocabulary("browser kholo")
        assert resolved == "firefox kholo"

        # Step 3: User corrects: "nahi, maine bola tha Firefox mera favorite browser hai"
        resp3 = core.process_input("nahi, maine bola tha Firefox mera favorite browser hai", source="cli")
        assert "samajh gaya sir" in resp3.lower() or "understood sir" in resp3.lower()
        assert "firefox" in resp3.lower()
        assert "yaad rakhunga" in resp3.lower() or "remember" in resp3.lower()

        # Step 4: Simulate Jarvis restart (fresh DatabaseManager, MemoryManager, LearningManager, JarvisCore)
        new_db = DatabaseManager(db_path=db_path)
        new_mem = MemoryManager(db_path=db_path)
        new_lm = LearningManager(db=new_db, enabled=True)
        new_core = JarvisCore()
        new_pm = MagicMock()
        new_core.initialize_subsystems(
            memory_manager=new_mem,
            learning_manager=new_lm,
            brain=MagicMock(),
            classifier=MagicMock(),
            plugin_manager=new_pm,
            response_generator=MagicMock(),
        )

        # Step 5: After restart, verify preferred browser is STILL Firefox without repeating
        assert new_lm.preferences.get("preferred_browser") == "firefox"
        assert new_lm.vocabulary.get_term("browser") == "firefox"
        resolved_after_restart = new_lm.resolve_vocabulary("browser kholo")
        assert resolved_after_restart == "firefox kholo"
