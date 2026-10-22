# tests/test_self_improvement_integration.py
"""
Comprehensive test suite for Jarvis Self-Improvement & Learning/Feedback Layer Integration.
Verifies Outcome Evaluation, Correction Detection, Mistake Detection, Pattern Learning,
and Confidence Scoring across Context, Intent, Router, Executor, Memory, and Database.
Strictly adheres to the No-Duplicate-Implementation Rule (AGENTS.md §1.1).
"""

import os
import tempfile
import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.context import ActiveTargetContext, RuntimeContext, TurnContext
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.experience.models import MemoryType
from learning.learner import LearningManager
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager


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


class TestSelfImprovementFeedbackLayer:
    """Tests the 5 unified branches of the Learning/Feedback Layer."""

    def test_outcome_evaluation_verified_success(self, learning_mgr):
        """Verified success distills and stores a procedural experience recipe."""
        goal = "open chrome and navigate to github"
        steps = [
            {"plugin": "windows", "action": "launch_app", "parameters": {"name": "chrome"}},
            {"plugin": "browser", "action": "navigate", "parameters": {"url": "https://github.com"}},
        ]
        exec_results = [
            ExecutionResult(success=True, status=ExecutionState.SUCCESS, requested_action="launch_app", executed_action="launch_app"),
            ExecutionResult(success=True, status=ExecutionState.SUCCESS, requested_action="navigate", executed_action="navigate"),
        ]
        verif_results = [
            VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="process_running"),
            VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type="window_exists"),
        ]

        exp_item = learning_mgr.evaluate_outcome(
            goal=goal,
            steps=steps,
            execution_results=exec_results,
            verification_results=verif_results,
            execution_context={"source": "cli"},
            category="browser"
        )

        assert exp_item is not None
        assert exp_item.memory_type == MemoryType.PROCEDURAL
        assert exp_item.query_pattern == goal
        assert exp_item.content["step_count"] == 2
        assert exp_item.confidence >= 0.85

        # Verify it can be retrieved by retriever
        context = learning_mgr.experience_system.retrieve_experience("open chrome")
        assert len(context.procedures) > 0
        assert context.procedures[0].get("query_pattern") == goal or context.procedures[0].get("goal") == goal

    def test_mistake_detection_on_verification_failure(self, learning_mgr):
        """Unverified execution triggers mistake detection and stores failure anti-pattern."""
        goal = "open broken app"
        steps = [
            {"plugin": "windows", "action": "launch_app", "parameters": {"name": "nonexistent_app"}}
        ]
        exec_results = [
            ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action="launch_app",
                executed_action="launch_app",
                error="Process failed to start"
            )
        ]
        verif_results = [
            VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED,
                check_type="process_running",
                error="Process not found in OS table"
            )
        ]

        exp_item = learning_mgr.evaluate_outcome(
            goal=goal,
            steps=steps,
            execution_results=exec_results,
            verification_results=verif_results,
            category="windows"
        )

        assert exp_item is not None
        assert exp_item.memory_type == MemoryType.FAILURE
        assert exp_item.content["error"] != ""
        assert "Process not found in OS table" in exp_item.content["root_cause"] or "Process failed to start" in exp_item.content["error"]
        assert exp_item.content["avoidance_strategy"] != ""

        # Verify failure memory is retrieved before subsequent attempts
        context = learning_mgr.experience_system.retrieve_experience("open broken app")
        assert len(context.failures) > 0
        assert "avoidance_strategy" in context.failures[0]

    def test_correction_detection_with_active_context_inference(self, learning_mgr):
        """Verbal correction 'nahi, brave mein open karo' inherits target from active context."""
        active_ctx = ActiveTargetContext()
        active_ctx.set_website("youtube", url="https://youtube.com")

        # User gives correction without repeating 'youtube'
        corr = learning_mgr.detect_correction(
            "nahi, brave mein open karo",
            active_context=active_ctx
        )

        assert corr.is_correction is True
        assert corr.preferred_container == "brave"
        assert corr.target == "youtube"

        # Verify preference was saved in ExecutionPreferenceManager
        saved_pref = learning_mgr.get_execution_preference("youtube")
        assert saved_pref == "brave"

        # Verify versioned correction was stored in ExperienceLearningSystem
        context = learning_mgr.experience_system.retrieve_experience("youtube")
        assert len(context.preferences) > 0
        assert context.preferences.get("youtube") == "brave"

    def test_repeated_correction_supersedes_without_destructive_delete(self, learning_mgr):
        """Second correction ('nahi Edge mein kholo') creates v2 superseding v1."""
        active_ctx = ActiveTargetContext()
        active_ctx.set_website("youtube")

        # First correction: Brave
        learning_mgr.detect_correction("nahi, brave mein open karo", active_context=active_ctx)
        assert learning_mgr.get_execution_preference("youtube") == "brave"

        # Second correction: Edge
        corr2 = learning_mgr.detect_correction("nahi, Edge mein kholo", active_context=active_ctx)
        assert corr2.is_correction is True
        assert corr2.preferred_container == "edge"
        assert learning_mgr.get_execution_preference("youtube") == "edge"

        # Verify versioning in Experience storage
        items = learning_mgr.experience_system.storage.get_active_items()
        pref_items = [i for i in items if i.content.get("key") == "youtube"]
        assert len(pref_items) == 1
        assert pref_items[0].content["value"] == "edge"
        assert pref_items[0].version >= 2

    def test_evidence_based_confidence_scoring(self, learning_mgr):
        """Confidence score scales with observation frequency and penalizes failures."""
        # 1 occurrence -> 0.35
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=1) == 0.35
        # 2 occurrences -> 0.55
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=2) == 0.55
        # 3 occurrences -> 0.70
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=3) == 0.70
        # 4 occurrences -> 0.82
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=4) == 0.82
        # 5 occurrences -> 0.88
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=5) == 0.88
        # 6+ occurrences -> >= 0.90
        assert learning_mgr.score_confidence("test_pattern", success=True, frequency=6) >= 0.90

        # On failure: confidence is penalized
        penalized = learning_mgr.score_confidence("test_pattern", success=False, frequency=5)
        assert penalized < 0.88
        assert penalized == round(0.88 * 0.75, 2)

    def test_closed_loop_turn_feedback_integration(self, temp_db):
        """Tests that JarvisCore _record_turn_feedback updates Memory, Learning, and Experience."""
        from core.app import JarvisCore

        core = JarvisCore(config_path="config.yaml")
        mem_mgr = MemoryManager(db_path=temp_db.db_path)
        learn_mgr = LearningManager(db=temp_db, enabled=True)

        core.initialize_subsystems(
            memory_manager=mem_mgr,
            learning_manager=learn_mgr
        )

        turn = TurnContext(raw_input="excel open karo", normalized_input="excel open karo", source="cli")
        turn.response_text = "Excel open kar diya."

        # Simulate turn execution feedback
        core._record_turn_feedback(
            turn=turn,
            goal="Open application Excel",
            steps=[{"plugin": "windows", "action": "launch_app", "parameters": {"name": "excel"}}],
            execution_results=[{"success": True}],
            verification_results=[{"verified": True}],
            success=True,
            category="windows",
            intent_name="open_app"
        )

        # 1. Check episodic memory recorded the interaction
        recent = mem_mgr.get_recent_interactions(limit=1)
        assert len(recent) > 0
        assert recent[0]["user_input"] == "excel open karo"

        # 2. Check experience memory saved procedural item
        exp = learn_mgr.experience_system.retrieve_experience("Open application Excel")
        assert len(exp.procedures) > 0
        assert exp.procedures[0].get("category") == "windows"
