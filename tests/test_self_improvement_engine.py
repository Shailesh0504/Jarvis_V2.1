# tests/test_self_improvement_engine.py
"""
Comprehensive test suite for the Authoritative Self-Improvement Engine (`intelligence.self_improvement`).
Validates all 9 learning, adaptation, promotion, and regression capabilities:
1. Interaction Evaluation (evaluate_interaction)
2. Feedback Detection (detect_feedback)
3. Mistake Detection (detect_mistake)
4. Correction Learning (learn_correction)
5. Pattern Learning (learn_pattern)
6. Confidence Scoring (score_confidence)
7. Learning Promotion (promote_learning)
8. Learning Rollback (rollback_learning)
9. Regression Generation (generate_regression_case)
"""

import os
import tempfile
import pytest
from unittest.mock import MagicMock

from core.context import ActiveTargetContext, TurnContext
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.experience.models import MemoryType
from core.intelligence.self_improvement import (
    SelfImprovementEngine,
    FeedbackType,
    LearningPromotionStatus,
    RegressionCase,
    get_self_improvement_engine,
)
from learning.learner import LearningManager
from memory.database import DatabaseManager


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    yield db
    if os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


@pytest.fixture
def learning_mgr(temp_db):
    return LearningManager(db=temp_db, enabled=True)


@pytest.fixture
def si_engine(learning_mgr, temp_db):
    return SelfImprovementEngine(learning_manager=learning_mgr, db=temp_db)


class TestSelfImprovementEngineNineCapabilities:
    """Tests all 9 capabilities orchestrated by the Self-Improvement Engine."""

    # -------------------------------------------------------------------------
    # 1. Interaction Evaluation
    # -------------------------------------------------------------------------
    def test_interaction_evaluation_success_distills_procedural_memory(self, si_engine, learning_mgr):
        goal = "open notepad and write note"
        steps = [{"plugin": "windows", "action": "launch_app", "parameters": {"name": "notepad"}}]
        exec_results = [ExecutionResult(success=True, status=ExecutionState.SUCCESS, requested_action="launch_app", executed_action="launch_app")]
        verif_results = [VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="process_running")]

        exp_item = si_engine.evaluate_interaction(
            goal=goal,
            steps=steps,
            execution_results=exec_results,
            verification_results=verif_results,
            category="windows"
        )
        assert exp_item is not None
        assert exp_item.memory_type == MemoryType.PROCEDURAL
        assert exp_item.query_pattern == goal

    def test_interaction_evaluation_failure_records_anti_pattern_and_regression_case(self, si_engine):
        goal = "open nonexistent app"
        steps = [{"plugin": "windows", "action": "launch_app", "parameters": {"name": "ghost_app"}, "target": "ghost_app"}]
        exec_results = [ExecutionResult(success=False, status=ExecutionState.FAILED, requested_action="launch_app", executed_action="launch_app", error="App not found")]
        verif_results = [VerificationResult(verified=False, state=ExecutionState.UNVERIFIED, check_type="process_running", error="Process missing")]

        exp_item = si_engine.evaluate_interaction(
            goal=goal,
            steps=steps,
            execution_results=exec_results,
            verification_results=verif_results,
            category="windows"
        )
        assert exp_item is not None
        assert exp_item.memory_type == MemoryType.FAILURE

        # Auto-generated regression case must exist
        cases = si_engine.get_regression_cases()
        assert len(cases) > 0
        mistake_case = [c for c in cases if c.created_from == "mistake_detection"]
        assert len(mistake_case) > 0
        assert "Mistake Avoidance" in mistake_case[0].name

    # -------------------------------------------------------------------------
    # 2. Feedback Detection
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize("text,expected_type,expected_sentiment_sign", [
        ("shabash jarvis, bilkul sahi kaam kiya", FeedbackType.POSITIVE_AFFIRMATION, 1),
        ("perfect, thank you", FeedbackType.POSITIVE_AFFIRMATION, 1),
        ("theek hai chalega", FeedbackType.SATISFACTION, 1),
        ("galat kar diya tumne", FeedbackType.NEGATIVE_COMPLAINT, -1),
        ("tum sun nahi rahe ho", FeedbackType.NEGATIVE_COMPLAINT, -1),
        ("nahi ye galat hai", FeedbackType.DISSATISFACTION, -1),
        ("nahi, chrome nahi brave", FeedbackType.CORRECTION, -1),
        ("what is the weather today?", FeedbackType.NEUTRAL, 0),
    ])
    def test_feedback_detection(self, si_engine, text, expected_type, expected_sentiment_sign):
        fb_type, sentiment, cue = si_engine.detect_feedback(text)
        assert fb_type == expected_type
        if expected_sentiment_sign > 0:
            assert sentiment > 0.0
        elif expected_sentiment_sign < 0:
            assert sentiment < 0.0
        else:
            assert sentiment == 0.0

    # -------------------------------------------------------------------------
    # 3. Mistake Detection
    # -------------------------------------------------------------------------
    def test_mistake_detection_derives_root_cause_and_strategy(self, si_engine):
        diag = si_engine.detect_mistake(
            target="corrupted_folder",
            action="open_folder",
            error_msg="Path does not exist on disk"
        )
        assert diag is not None
        assert "root_cause" in diag
        assert diag["target"] == "corrupted_folder"
        assert "suggested_recovery_strategy" in diag

    # -------------------------------------------------------------------------
    # 4. Correction Learning
    # -------------------------------------------------------------------------
    def test_correction_learning_with_context_and_regression_generation(self, si_engine, learning_mgr):
        active_ctx = ActiveTargetContext()
        active_ctx.set_website("youtube", url="https://youtube.com")

        res = si_engine.learn_correction("nahi, brave mein open karo", active_context=active_ctx)
        assert res.is_correction is True
        assert res.preferred_container == "brave"
        assert res.target == "youtube"

        # Preference must be saved
        assert learning_mgr.get_execution_preference("youtube") == "brave"

        # Auto-generated regression case must exist
        cases = si_engine.get_regression_cases()
        corr_case = [c for c in cases if c.created_from == "user_correction"]
        assert len(corr_case) > 0
        assert corr_case[0].expected_target == "brave:youtube"

    # -------------------------------------------------------------------------
    # 5. Pattern Learning
    # -------------------------------------------------------------------------
    def test_pattern_learning_observes_habitual_intent(self, si_engine, learning_mgr):
        mock_intent = MagicMock()
        mock_intent.name = "media_play"
        mock_intent.entities = {"artist": "Arijit Singh"}
        mock_intent.target_plugin = "media"
        mock_intent.target_action = "play"

        si_engine.learn_pattern("play arijit singh", "play arijit singh", mock_intent)
        freq = learning_mgr.habits.get_frequency("media_play")
        assert freq >= 1

    # -------------------------------------------------------------------------
    # 6. Confidence Scoring
    # -------------------------------------------------------------------------
    def test_confidence_scoring_evidence_scaling_and_penalty(self, si_engine):
        assert si_engine.score_confidence("test", success=True, frequency=1) == 0.35
        assert si_engine.score_confidence("test", success=True, frequency=2) == 0.55
        assert si_engine.score_confidence("test", success=True, frequency=3) == 0.70
        assert si_engine.score_confidence("test", success=True, frequency=4) == 0.82
        assert si_engine.score_confidence("test", success=True, frequency=5) == 0.88
        assert si_engine.score_confidence("test", success=True, frequency=6) >= 0.90

        # Failure penalizes confidence
        penalized = si_engine.score_confidence("test", success=False, frequency=5)
        assert penalized < 0.88

    # -------------------------------------------------------------------------
    # 7. Learning Promotion
    # -------------------------------------------------------------------------
    def test_learning_promotion_enforces_thresholds(self, si_engine, learning_mgr):
        # 1. Staged candidate in approval manager
        pending = learning_mgr.approval.stage_learning(
            layer=1,
            pattern_type="preference",
            original_key="test_setting",
            proposed_val="dark_mode",
            confidence=0.75
        )

        # Attempt promote with insufficient frequency -> Rejected, remains candidate
        success, status, reason = si_engine.promote_learning(pending.id, frequency=1, confidence=0.75)
        assert success is False
        assert status == LearningPromotionStatus.CANDIDATE

        # Attempt promote with insufficient confidence -> Rejected, remains candidate
        success, status, reason = si_engine.promote_learning(pending.id, frequency=4, confidence=0.65)
        assert success is False
        assert status == LearningPromotionStatus.CANDIDATE

        # Satisfies both thresholds (freq >= 3, conf >= 0.80) -> PROMOTED!
        success, status, reason = si_engine.promote_learning(pending.id, frequency=3, confidence=0.85)
        assert success is True
        assert status == LearningPromotionStatus.PROMOTED

        # Verify preference was applied in layer 1
        assert learning_mgr.preferences.get("test_setting") == "dark_mode"

    # -------------------------------------------------------------------------
    # 8. Learning Rollback
    # -------------------------------------------------------------------------
    def test_learning_rollback_safely_reverts_without_data_corruption(self, si_engine, learning_mgr):
        # Set preference
        learning_mgr.set_execution_preference("netflix", "brave")
        assert learning_mgr.get_execution_preference("netflix") == "brave"

        # Execute rollback
        success, details = si_engine.rollback_learning("netflix", reason="user requested undo")
        assert success is True
        assert "Reverted execution preference" in details

        # Preference must be cleared
        assert learning_mgr.get_execution_preference("netflix") is None

        # Rollback audit history must record it
        history = si_engine.get_rollback_history()
        assert len(history) > 0
        assert history[-1]["item_id_or_key"] == "netflix"
        assert history[-1]["reason"] == "user requested undo"

    # -------------------------------------------------------------------------
    # 9. Regression Generation
    # -------------------------------------------------------------------------
    def test_regression_generation_creates_and_retrieves_cases(self, si_engine):
        case = si_engine.generate_regression_case(
            name="Test App Closure Verification",
            query="close chrome",
            expected_action="close_app",
            expected_target="chrome",
            avoid_action="kill_unrelated_process"
        )
        assert isinstance(case, RegressionCase)
        assert case.query == "close chrome"
        assert case.expected_target == "chrome"
        assert case.avoid_action == "kill_unrelated_process"

        all_cases = si_engine.get_regression_cases()
        assert case.case_id in [c.case_id for c in all_cases]


class TestJarvisCoreSelfImprovementIntegration:
    """Validates that JarvisCore coordinates SelfImprovementEngine end-to-end."""

    def test_jarvis_core_has_self_improvement_engine(self, temp_db):
        from core.app import JarvisCore
        from memory.memory_manager import MemoryManager

        core = JarvisCore(config_path="config.yaml")
        mem_mgr = MemoryManager(db_path=temp_db.db_path)
        learn_mgr = LearningManager(db=temp_db, enabled=True)

        core.initialize_subsystems(
            memory_manager=mem_mgr,
            learning_manager=learn_mgr
        )

        assert hasattr(core, "self_improvement_engine")
        assert core.self_improvement_engine is not None
        assert isinstance(core.self_improvement_engine, SelfImprovementEngine)

        # Test turn feedback recording invokes self-improvement engine
        turn = TurnContext(raw_input="open calculator", normalized_input="open calculator", source="cli")
        core._record_turn_feedback(
            turn=turn,
            goal="Launch Calculator",
            steps=[{"plugin": "windows", "action": "launch_app", "parameters": {"name": "calculator"}}],
            execution_results=[{"success": True}],
            verification_results=[{"verified": True}],
            success=True,
            category="windows"
        )

        # Verify experience memory has procedural item
        exp = learn_mgr.experience_system.retrieve_experience("Launch Calculator")
        assert len(exp.procedures) > 0
