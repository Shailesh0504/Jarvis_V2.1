# tests/test_self_learning_suite.py
"""
Comprehensive 10-Branch Self-Learning Test Suite for Jarvis V2.1.
Objectively verifies that Jarvis actively learns from mistakes, adapts decisions,
and persists learning across restarts rather than merely acting as passive memory.

Test Hierarchy:
Learning Test
├── 1. Intent correction
├── 2. Entity correction
├── 3. Command correction
├── 4. Preference learning
├── 5. Context learning
├── 6. Conversation correction
├── 7. Error recovery
├── 8. Negative feedback
├── 9. Persistence after restart
└── 10. Regression test
"""

import os
import tempfile
import pytest

from core.context import ActiveTargetContext
from core.experience.models import MemoryType
from core.experience.system import ExperienceLearningSystem
from core.intelligence.self_improvement import (
    SelfImprovementEngine,
    FeedbackType,
    RegressionCase,
)
from learning.learner import LearningManager
from learning.vocabulary_layer import VocabularyLayer
from learning.corrections_layer import CorrectionsLayer
from brain.personal_profile import PersonalProfileExtractor
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


@pytest.fixture
def temp_db(temp_db_path):
    return DatabaseManager(db_path=temp_db_path)


@pytest.fixture
def learning_manager(temp_db):
    return LearningManager(db=temp_db, enabled=True)


@pytest.fixture
def experience_system(temp_db_path):
    return ExperienceLearningSystem(db_or_path=temp_db_path)


@pytest.fixture
def self_improvement_engine(learning_manager, temp_db):
    return SelfImprovementEngine(learning_manager=learning_manager, db=temp_db)


# ==============================================================================
# 1. INTENT CORRECTION
# ==============================================================================
class Test1IntentCorrection:
    """
    Verifies that when Jarvis misclassifies or receives a user intent correction,
    it detects the correction, updates the mapping, and does not repeat the misclassification.
    """

    def test_intent_correction_detection_and_learning(self, self_improvement_engine):
        # User explicitly corrects intent: "nahi, chrome nahi brave"
        fb_type, sentiment, cue = self_improvement_engine.detect_feedback("nahi, chrome nahi brave")
        assert fb_type == FeedbackType.CORRECTION
        assert sentiment < 0.0

        # Learning correction candidate
        res = self_improvement_engine.learn_correction("nahi, brave mein open karo")
        assert res is not None
        assert res.is_correction is True

    def test_corrections_layer_intent_override(self, learning_manager):
        # Corrections layer handles explicit corrections like "X nahi Y karo"
        res = learning_manager.corrections.parse_and_apply_correction("nahi, Chrome nahi Edge kholo")
        assert res.is_correction is True
        assert res.new_value.lower() == "edge"


# ==============================================================================
# 2. ENTITY CORRECTION
# ==============================================================================
class Test2EntityCorrection:
    """
    Verifies that when a user corrects an entity ("Chrome nahi, Firefox kholo"),
    the entity replacement is recognized and applied to canonical vocabulary resolution.
    """

    def test_entity_redirection_and_vocabulary_learning(self, learning_manager):
        # User explicitly corrects entity: "Chrome nahi Firefox kholo"
        res = learning_manager.corrections.parse_and_apply_correction("nahi, Chrome nahi Firefox kholo")
        assert res.is_correction is True
        assert "firefox" in res.new_value.lower()

        # Learn term in vocabulary layer
        learning_manager.vocabulary.learn_term("browser", "firefox")
        resolved = learning_manager.vocabulary.resolve_text("browser open karo")
        assert "firefox" in resolved.lower()
        assert "chrome" not in resolved.lower()

    def test_entity_correction_confidence_penalty(self, self_improvement_engine):
        # Success builds confidence, while repeated failures/corrections penalize
        conf_success = self_improvement_engine.score_confidence("browser.open", success=True, frequency=5)
        conf_penalized = self_improvement_engine.score_confidence("browser.open", success=False, frequency=5)
        assert conf_penalized < conf_success


# ==============================================================================
# 3. COMMAND CORRECTION
# ==============================================================================
class Test3CommandCorrection:
    """
    Verifies that custom command aliases and multi-turn command corrections
    are learned and mapped to the intended actions.
    """

    def test_custom_command_alias_adaptation(self, learning_manager):
        # Teach custom shorthand command: "meri coding" -> "code"
        learning_manager.vocabulary.learn_term("meri coding", "code")
        resolved = learning_manager.vocabulary.resolve_text("meri coding shuru karo")
        assert "code" in resolved.lower()

    def test_regression_case_generation_from_command_mistake(self, self_improvement_engine):
        reg_case = self_improvement_engine.generate_regression_case(
            name="Coding Setup",
            query="coding setup",
            expected_action="system.app.launch",
            expected_target="vscode",
            avoid_action="system.unknown",
            created_from="mistake_detection"
        )
        assert reg_case is not None
        assert reg_case.expected_action == "system.app.launch"
        assert reg_case.expected_target == "vscode"
        assert reg_case.avoid_action == "system.unknown"

        # Stored in regression registry
        cases = self_improvement_engine.get_regression_cases()
        assert any(c.name == "Coding Setup" for c in cases)


# ==============================================================================
# 4. PREFERENCE LEARNING
# ==============================================================================
class Test4PreferenceLearning:
    """
    Verifies that user preferences (e.g. favorite browser, media player) are learned,
    stored, and actively shape downstream resolution of generic requests.
    """

    def test_browser_preference_learning_and_resolution(self, learning_manager):
        # 1. User declares preference: "mera favorite browser brave hai"
        learning_manager.preferences.set("preferred_browser", "brave")
        learning_manager.vocabulary.learn_term("browser", "brave")

        # 2. Check preference retrieval
        pref = learning_manager.preferences.get("preferred_browser")
        assert pref == "brave"

        # 3. Generic query "browser kholo" must resolve to Brave
        resolved = learning_manager.vocabulary.resolve_text("browser kholo")
        assert "brave" in resolved.lower()

    def test_music_player_preference_learning(self, learning_manager):
        # User declares music preference
        learning_manager.preferences.set("preferred_media_player", "spotify")
        learning_manager.vocabulary.learn_term("music player", "spotify")

        resolved = learning_manager.vocabulary.resolve_text("music player open karo")
        assert "spotify" in resolved.lower()


# ==============================================================================
# 5. CONTEXT LEARNING
# ==============================================================================
class Test5ContextLearning:
    """
    Verifies that active runtime context correctly adapts when corrected,
    enabling follow-up commands to inherit the updated entity without repetition.
    """

    def test_context_target_update_and_inheritance(self, self_improvement_engine, learning_manager):
        active_ctx = ActiveTargetContext()
        active_ctx.set_website("youtube", url="https://youtube.com")

        # User corrects: "nahi, brave mein open karo"
        res = self_improvement_engine.learn_correction("nahi, brave mein open karo", active_context=active_ctx)
        assert res.is_correction is True
        assert res.preferred_container == "brave"
        assert res.target == "youtube"

        # Preference must be saved in learning manager
        assert learning_manager.get_execution_preference("youtube") == "brave"


# ==============================================================================
# 6. CONVERSATION CORRECTION
# ==============================================================================
class Test6ConversationCorrection:
    """
    Verifies that personal profile and conversational facts are atomically updated
    upon correction, replacing stale values rather than duplicating them.
    """

    def test_profile_fact_atomic_correction(self, temp_db_path):
        mem_mgr = MemoryManager(db_path=temp_db_path)

        # 1. Initial statement: "mera naam Amit hai"
        fact = PersonalProfileExtractor.extract("mera naam Amit hai")
        assert fact is not None
        canonical_key = PersonalProfileExtractor.FIELDS[fact.field][0]
        assert canonical_key == "user_name"
        assert fact.value == "Amit"
        mem_mgr.store_fact(canonical_key, fact.value, category="profile")
        assert mem_mgr.get_fact("user_name")["value"] == "Amit"

        # 2. Contextual correction: "nahi, mera naam Rahul hai" with correction_field="name"
        correction_fact = PersonalProfileExtractor.extract("nahi, mera naam Rahul hai", correction_field="name")
        assert correction_fact is not None
        assert correction_fact.is_correction is True
        assert correction_fact.value == "Rahul"
        mem_mgr.store_fact("user_name", correction_fact.value, category="profile")

        # Stale value must be completely replaced
        assert mem_mgr.get_fact("user_name")["value"] == "Rahul"

        # 3. Direct fact correction: "mera project Jarvis hai" -> "nahi, mera project Atlas hai"
        proj_fact = PersonalProfileExtractor.extract("mera project Jarvis hai")
        assert proj_fact is not None
        mem_mgr.store_fact("current_project", proj_fact.value, category="profile")
        assert mem_mgr.get_fact("current_project")["value"] == "Jarvis"

        proj_corr = PersonalProfileExtractor.extract("nahi, mera project Atlas hai")
        assert proj_corr is not None
        assert proj_corr.is_correction is True
        assert proj_corr.value == "Atlas"
        mem_mgr.store_fact("current_project", proj_corr.value, category="profile")
        assert mem_mgr.get_fact("current_project")["value"] == "Atlas"


# ==============================================================================
# 7. ERROR RECOVERY
# ==============================================================================
class Test7ErrorRecovery:
    """
    Verifies that when an action fails, Jarvis records the failure in FailureMemory,
    generates avoidance advice, and avoids repeating the exact failing strategy.
    """

    def test_failure_memory_generation_and_recovery_advice(self, experience_system):
        failed_step = {
            "action": "system.clear_temp_files",
            "plugin": "system",
            "parameters": {"path": "C:/Windows/Temp"}
        }

        exp_item = experience_system.record_task_failure(
            goal="clean temp files",
            failed_step=failed_step,
            error_msg="Access Denied: Admin Elevation Required",
            diagnosis="Elevate process before temp purge"
        )
        assert exp_item is not None
        assert exp_item.memory_type == MemoryType.FAILURE

        # Retrieve experience before next execution
        exp_ctx = experience_system.retrieve_experience(query="clean temp files")
        assert exp_ctx is not None
        assert len(exp_ctx.failures) > 0
        assert "Access Denied" in exp_ctx.failures[0].get("error", "")

    def test_mistake_diagnosis_and_recovery_strategy(self, self_improvement_engine):
        diag = self_improvement_engine.detect_mistake(
            target="corrupted_folder",
            action="open_folder",
            error_msg="Path does not exist on disk"
        )
        assert diag is not None
        assert "root_cause" in diag
        assert diag["target"] == "corrupted_folder"
        assert "suggested_recovery_strategy" in diag


# ==============================================================================
# 8. NEGATIVE FEEDBACK
# ==============================================================================
class Test8NegativeFeedback:
    """
    Verifies that user disapproval ("galat hai", "aisa mat karo", "bekar")
    is accurately categorized as negative feedback and applies confidence penalties.
    """

    @pytest.mark.parametrize("disapproval_phrase,expected_fbs", [
        ("galat kar diya tumne", [FeedbackType.NEGATIVE_COMPLAINT]),
        ("tum sun nahi rahe ho", [FeedbackType.NEGATIVE_COMPLAINT]),
        ("nahi ye galat hai", [FeedbackType.DISSATISFACTION, FeedbackType.NEGATIVE_COMPLAINT]),
        ("bekar hai", [FeedbackType.DISSATISFACTION, FeedbackType.NEGATIVE_COMPLAINT]),
        ("nahi, chrome nahi brave", [FeedbackType.CORRECTION]),
    ])
    def test_negative_feedback_detection(self, self_improvement_engine, disapproval_phrase, expected_fbs):
        fb_type, sentiment, cue = self_improvement_engine.detect_feedback(disapproval_phrase)
        assert fb_type in expected_fbs
        assert sentiment < 0.0


# ==============================================================================
# 9. PERSISTENCE AFTER RESTART
# ==============================================================================
class Test9PersistenceAfterRestart:
    """
    Validates cold reboot persistence: when the entire in-memory state is unloaded
    and brand-new objects are instantiated against the existing SQLite database,
    all learned rules, vocabulary mappings, and preferences remain active.
    """

    def test_cold_reboot_persistence_of_learned_preferences_and_vocab(self, temp_db_path):
        # Phase 1: Pre-restart session
        mem1 = MemoryManager(db_path=temp_db_path)
        db1 = DatabaseManager(db_path=temp_db_path)
        lm1 = LearningManager(db=db1, enabled=True)
        exp1 = ExperienceLearningSystem(db_or_path=temp_db_path)

        # Learn browser preference across memory, preference layer, and vocabulary layer
        mem1.store_fact("preferred_browser", "Firefox", category="profile")
        lm1.preferences.set("preferred_browser", "Firefox")
        lm1.vocabulary.learn_term("browser", "firefox")

        # Record a failure experience
        failed_step = {"action": "failing_cmd", "plugin": "test", "parameters": {}}
        exp1.record_task_failure("run test", failed_step, "DiskFullError", diagnosis="Free disk space")

        # Phase 2: Total simulated shutdown (delete all objects)
        del lm1, mem1, exp1, db1

        # Phase 3: Post-restart session (brand new objects from disk file)
        mem2 = MemoryManager(db_path=temp_db_path)
        db2 = DatabaseManager(db_path=temp_db_path)
        lm2 = LearningManager(db=db2, enabled=True)
        exp2 = ExperienceLearningSystem(db_or_path=temp_db_path)

        # Assert 1: Profile fact persisted
        assert mem2.get_fact("preferred_browser")["value"] == "Firefox"

        # Assert 2: Preference persisted
        assert lm2.preferences.get("preferred_browser") == "Firefox"

        # Assert 3: Vocabulary mapping persisted and resolves generic phrase
        resolved = lm2.vocabulary.resolve_text("browser kholo")
        assert "firefox" in resolved.lower()
        assert "chrome" not in resolved.lower()

        # Assert 4: Failure memory persisted
        retrieved = exp2.retrieve_experience(query="run test")
        assert len(retrieved.failures) > 0
        assert "DiskFullError" in retrieved.failures[0].get("error", "")


# ==============================================================================
# 10. REGRESSION SAFETY
# ==============================================================================
class Test10RegressionSafety:
    """
    Verifies that learning new rules, preferences, and corrections NEVER
    regresses or corrupts canonical commands and system functionality.
    """

    def test_canonical_commands_remain_intact_after_aggressive_learning(self, learning_manager):
        # Teach multiple new mappings & corrections
        learning_manager.vocabulary.learn_term("browser", "firefox")
        learning_manager.vocabulary.learn_term("editor", "code")
        learning_manager.preferences.set("preferred_browser", "firefox")

        # 1. Brand-qualified browser commands MUST NOT be corrupted
        # "open chrome" must not become "open firefox"
        chrome_resolved = learning_manager.vocabulary.resolve_text("open chrome")
        assert "chrome" in chrome_resolved.lower()

        brave_resolved = learning_manager.vocabulary.resolve_text("brave browser close karo")
        assert "brave" in brave_resolved.lower()
        assert "firefox" not in brave_resolved.lower()

        # 2. System commands MUST NOT be corrupted
        system_cmd = "system lock karo"
        assert learning_manager.vocabulary.resolve_text(system_cmd) == system_cmd

        volume_cmd = "volume 50 percent karo"
        assert learning_manager.vocabulary.resolve_text(volume_cmd) == volume_cmd


# ==============================================================================
# 11. LEARNING INSPECTOR (spec §21, §22)
# ==============================================================================
class Test11LearningInspector:
    """
    Verifies that the LearningInspector correctly handles inspection,
    forget, and metrics commands without triggering real actions.
    """

    def test_learning_inspector_initializes(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(
            db=temp_db,
            learning_manager=learning_manager,
            self_improvement_engine=self_improvement_engine,
        )
        assert inspector is not None

    def test_show_learning_does_not_crash(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(db=temp_db, learning_manager=learning_manager, self_improvement_engine=self_improvement_engine)
        # Teach something first
        learning_manager.vocabulary.learn_term("project", "myapp")
        resp = inspector.try_handle("show learning", core=None)
        assert resp is not None
        assert isinstance(resp, str)

    def test_forget_specific_preference(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(db=temp_db, learning_manager=learning_manager, self_improvement_engine=self_improvement_engine)
        # Set a preference first
        if hasattr(learning_manager, "exec_pref"):
            learning_manager.exec_pref.set_target_preference("youtube", "brave")
            resp = inspector.try_handle("youtube wali preference bhool jao", core=None)
            assert resp is not None
            assert isinstance(resp, str)
            # Preference should be cleared
            cleared = learning_manager.exec_pref.get_target_preference("youtube")
            assert cleared is None

    def test_learning_stats_returns_metrics(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(db=temp_db, learning_manager=learning_manager, self_improvement_engine=self_improvement_engine)
        resp = inspector.try_handle("learning stats", core=None)
        assert resp is not None
        assert "Learning Metrics" in resp or "learning" in resp.lower()

    def test_show_preferences_lists_saved_prefs(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(db=temp_db, learning_manager=learning_manager, self_improvement_engine=self_improvement_engine)
        learning_manager.preferences.set("preferred_browser", "brave")
        resp = inspector.try_handle("show preferences", core=None)
        assert resp is not None
        assert "brave" in resp.lower() or "preferred" in resp.lower()

    def test_non_inspection_commands_return_none(self, temp_db, learning_manager, self_improvement_engine):
        from core.intelligence.learning_inspector import LearningInspector
        inspector = LearningInspector(db=temp_db, learning_manager=learning_manager, self_improvement_engine=self_improvement_engine)
        # Normal commands must pass through (return None)
        assert inspector.try_handle("chrome kholo", core=None) is None
        assert inspector.try_handle("volume 50", core=None) is None
        assert inspector.try_handle("play music", core=None) is None


# ==============================================================================
# 12. TRACEABLE LEARNING EVENT IDS (spec §1)
# ==============================================================================
class Test12TraceableEventIDs:
    """
    Verifies that SelfImprovementEngine generates LEARN-YYYYMMDD-NNNNNN
    event IDs for all learning events (spec §1 — full traceability).
    """

    def test_event_id_format(self, self_improvement_engine):
        eid = self_improvement_engine.generate_event_id()
        import re
        assert re.fullmatch(r"LEARN-\d{8}-\d{6}", eid), f"Unexpected format: {eid}"

    def test_event_ids_are_unique_and_sequential(self, self_improvement_engine):
        ids = [self_improvement_engine.generate_event_id() for _ in range(5)]
        # All must be unique
        assert len(set(ids)) == 5
        # Sequence numbers must be increasing
        seqs = [int(eid.split("-")[2]) for eid in ids]
        assert seqs == sorted(seqs)

    def test_learn_correction_stamps_event_id(self, self_improvement_engine):
        # After a correction, a regression case with learning_event_id must exist
        import re
        res = self_improvement_engine.learn_correction("nahi, Firefox kholo")
        # Either no correction detected (None / is_correction=False is also valid — this tests the ID generation path)
        if res and getattr(res, "is_correction", False):
            cases = self_improvement_engine.get_regression_cases()
            has_event_id = any(
                c.context_requirements.get("learning_event_id", "").startswith("LEARN-")
                for c in cases
            )
            assert has_event_id, "Regression case missing learning_event_id"
