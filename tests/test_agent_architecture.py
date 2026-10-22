"""Comprehensive Test Suite for Jarvis Agent Architecture.
=========================================================
Tests:
1. Request Classification (Direct Command, Information, Conversational, Multi-step, Goal, Ambiguous)
2. Fast Path vs Agent Path Gating
3. Tool Registry & Existing Skill Wrapping (desktop, filesystem, system)
4. Planning & Task Decomposition (with deictic pronoun resolution e.g. "usko" -> target)
5. Observation & Verification Layer
6. Failure Recovery Engine (retry, state adaptation, replanning)
7. Replanning Engine
8. Execution Policies, Max Retries & Dry-Run Mode
9. Human-in-the-Loop Risk Confirmation Gate
10. Task Cancellation
11. End-to-End Execution of Scenarios 1, 2, 3, 4
"""

from __future__ import annotations

import os
import pytest
from typing import Any, Dict

from core.agent.agent_policy import AgentPolicy
from core.agent.agent_state import AgentRiskLevel, AgentState, StepStatus, TaskStatus
from core.agent.observer import AgentObserver, SystemObservation
from core.agent.orchestrator import AgentOrchestrator, AutonomousAgent
from core.agent.planner import AgentPlanner
from core.agent.recovery import FailureRecoveryEngine, FailureType, RecoveryDecision, RecoveryStrategy
from core.agent.replanner import AgentReplanner
from core.agent.request_classifier import RequestClassification, RequestClassifier, RequestType
from core.agent.task_manager import AgentExecutionSummary, AgentStep, AgentStepRecord, AgentTask
from core.agent.tool_registry import AgentTool, ToolRegistry, ToolResult
from core.agent.verifier import AgentVerifier, VerificationOutcome


# ---------------------------------------------------------------------------
# 1. Request Classification Tests
# ---------------------------------------------------------------------------

class TestRequestClassification:
    """Tests the RequestClassifier distinguishing Fast Path vs Agent Path."""

    def setup_method(self):
        self.classifier = RequestClassifier()

    def test_direct_command_fast_path(self):
        samples = [
            "Chrome kholo",
            "volume 50 karo",
            "antigravity minimize karo",
            "notepad band karo",
            "open calculator",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert not res.is_agent_path, f"Expected Fast Path for '{text}', got Agent Path"
            assert res.request_type in (RequestType.DIRECT_COMMAND, RequestType.INFORMATION_REQUEST)

    def test_information_request_fast_path(self):
        samples = [
            "RAM kitni hai?",
            "Windows version kya hai?",
            "CPU usage kitna hai?",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert not res.is_agent_path, f"Expected Fast Path for '{text}'"
            assert res.request_type == RequestType.INFORMATION_REQUEST

    def test_conversational_fast_path(self):
        samples = [
            "Kaise ho?",
            "tum kaun ho",
            "namaste jarvis",
            "hello",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert not res.is_agent_path, f"Expected Fast Path for conversational '{text}'"
            assert res.request_type == RequestType.CONVERSATIONAL

    def test_multi_step_task_agent_path(self):
        samples = [
            "Chrome kholo, YouTube kholo aur mera playlist play karo.",
            "AntiGravity kholo aur usko minimize karo",
            "notepad open karo aur text type karo",
            "pehle chrome kholo phir youtube chalao",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert res.is_agent_path, f"Expected Agent Path for multi-step '{text}'"
            assert res.request_type == RequestType.MULTI_STEP_TASK

    def test_goal_oriented_task_agent_path(self):
        samples = [
            "Mujhe presentation ke liye market data collect karke summary bana do.",
            "Is folder mein jo Python files 1500 lines se badi hain unki list banao",
            "Is project ko organize karo",
            "codebase audit karo aur report banao",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert res.is_agent_path, f"Expected Agent Path for goal-oriented '{text}'"
            assert res.request_type == RequestType.GOAL_ORIENTED_TASK

    def test_ambiguous_task_agent_path(self):
        samples = [
            "Isko thik karo.",
            "isko sahi karo",
            "fix this issue",
        ]
        for text in samples:
            res = self.classifier.classify(text)
            assert res.is_agent_path, f"Expected Agent Path for ambiguous '{text}'"
            assert res.request_type == RequestType.AMBIGUOUS_TASK


# ---------------------------------------------------------------------------
# 2. Tool Registry Tests
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """Tests registration, permissions, schemas, and execution of agent tools."""

    def test_default_tools_registered(self):
        registry = ToolRegistry()
        tools = registry.list_tools()
        names = [t.name for t in tools]
        assert "desktop.open_application" in names
        assert "desktop.window_operation" in names
        assert "filesystem.find_large_files" in names
        assert "filesystem.read_file" in names
        assert "system.get_info" in names

    def test_custom_tool_registration(self):
        registry = ToolRegistry()
        custom_tool = AgentTool(
            name="test.calculator_add",
            description="Adds two numbers",
            parameters_schema={"a": "float", "b": "float"},
            risk_level=AgentRiskLevel.SAFE,
            handler=lambda params: ToolResult(success=True, output_data={"sum": params["a"] + params["b"]}),
        )
        registry.register(custom_tool)

        res = registry.execute("test.calculator_add", {"a": 10, "b": 25})
        assert res.success is True
        assert res.output_data["sum"] == 35

    def test_system_info_execution(self):
        registry = ToolRegistry()
        res = registry.execute("system.get_info", {})
        assert res.success is True
        assert "os" in res.output_data
        assert "ram_total_gb" in res.output_data


# ---------------------------------------------------------------------------
# 3. Planning & Task Decomposition Tests
# ---------------------------------------------------------------------------

class TestPlanningAndDecomposition:
    """Tests goal decomposition, ordering, and context resolution."""

    def setup_method(self):
        self.planner = AgentPlanner()

    def test_scenario_2_pronoun_resolution(self):
        # "AntiGravity kholo aur usko minimize karo"
        goal = "AntiGravity kholo aur usko minimize karo"
        task = self.planner.create_task_from_goal(goal)

        assert len(task.steps) >= 2
        step1 = task.steps[0]
        step2 = task.steps[1]

        assert "open" in step1.tool_name.lower()
        assert step1.parameters.get("target", "").lower() == "antigravity"

        assert "window" in step2.tool_name.lower()
        assert step2.parameters.get("operation", "").lower() == "minimize"
        # "usko" resolved to "antigravity"
        assert step2.parameters.get("target", "").lower() == "antigravity"
        assert step1.step_id in step2.depends_on

    def test_scenario_3_line_count_query(self):
        goal = "Is folder mein jo Python files 1500 lines se badi hain unki list banao"
        task = self.planner.create_task_from_goal(goal)

        assert len(task.steps) >= 1
        step = task.steps[0]
        assert step.tool_name == "filesystem.find_large_files"
        assert step.parameters.get("threshold_lines") == 1500
        assert step.parameters.get("extension") == ".py"

    def test_scenario_4_organize_project(self):
        goal = "Is project ko organize karo"
        task = self.planner.create_task_from_goal(goal)

        assert len(task.steps) >= 2
        # First step is safe inspection, subsequent step requires confirmation
        assert task.steps[0].tool_name == "system.get_info"


# ---------------------------------------------------------------------------
# 4. Observation & Verification Tests
# ---------------------------------------------------------------------------

class TestObservationAndVerification:
    """Tests system state observation and post-action verification."""

    def test_verifier_detects_tool_failure(self):
        verifier = AgentVerifier()
        step = AgentStep(tool_name="desktop.open_application", parameters={"target": "chrome"})
        tool_res = ToolResult(success=False, error="Executable not found")
        outcome = verifier.verify(step=step, tool_result=tool_res, observation=SystemObservation())

        assert outcome.is_verified is False
        assert outcome.needs_recovery is True
        assert outcome.actual_state == "TOOL_EXECUTION_FAILED"

    def test_verifier_validates_minimized_window(self):
        verifier = AgentVerifier()
        step = AgentStep(
            tool_name="desktop.window_operation",
            parameters={"target": "antigravity", "operation": "minimize"},
        )
        tool_res = ToolResult(success=True, verified=True)
        obs = SystemObservation(is_target_minimized=True, is_target_visible=False)
        outcome = verifier.verify(step=step, tool_result=tool_res, observation=obs)

        assert outcome.is_verified is True
        assert "minimized" in outcome.actual_state


# ---------------------------------------------------------------------------
# 5. Failure Recovery & Replanning Tests
# ---------------------------------------------------------------------------

class TestFailureRecoveryAndReplanning:
    """Tests failure diagnosis, state adaptation, and replanning."""

    def test_app_already_running_recovery_adapts_to_restore(self):
        recovery = FailureRecoveryEngine()
        step = AgentStep(tool_name="desktop.open_application", parameters={"target": "chrome"})
        # Target is already running in OS
        obs = SystemObservation(is_target_running=True)
        decision = recovery.diagnose_and_decide(step=step, observation=obs)

        assert decision.strategy == RecoveryStrategy.ADAPT_STATE
        assert decision.parameters.get("operation") == "restore" or "restor" in decision.reason.lower()

    def test_replanner_provides_alternative_on_failure(self):
        replanner = AgentReplanner()
        step = AgentStep(
            tool_name="desktop.open_application",
            parameters={"target": "youtube"},
        )
        alt_step = replanner.replan_step(step, failure_reason="Executable not found")

        assert alt_step is not None
        # Falls back to browser URL for known web apps
        assert alt_step.tool_name == "browser.open_url"
        assert "youtube.com" in alt_step.parameters.get("url", "")


# ---------------------------------------------------------------------------
# 6. Safety Policy, Confirmation & Dry-Run Tests
# ---------------------------------------------------------------------------

class TestSafetyPolicyAndGates:
    """Tests execution bounds, risk levels, human-in-the-loop, and dry-run."""

    def test_high_risk_requires_confirmation(self):
        policy = AgentPolicy()
        assert policy.requires_confirmation(AgentRiskLevel.HIGH) is True
        assert policy.requires_confirmation(AgentRiskLevel.CRITICAL) is True
        assert policy.requires_confirmation(AgentRiskLevel.LOW) is False
        assert policy.requires_confirmation(AgentRiskLevel.SAFE) is False

    def test_max_retries_limit_enforced(self):
        policy = AgentPolicy(max_retries_per_step=2)
        assert policy.can_retry_step(0) is True
        assert policy.can_retry_step(1) is True
        assert policy.can_retry_step(2) is False

    def test_dry_run_mode(self):
        policy = AgentPolicy(dry_run=True)
        orchestrator = AgentOrchestrator(policy=policy)
        summary = orchestrator.execute_goal("AntiGravity kholo aur usko minimize karo")

        assert summary.success is True
        assert "[DRY-RUN MODE]" in summary.final_answer
        # In dry run, no actual trace steps were executed against OS
        assert len(summary.trace) == 0


# ---------------------------------------------------------------------------
# 7. Task Cancellation & Lifecycle Tests
# ---------------------------------------------------------------------------

class TestLifecycleAndCancellation:
    """Tests state transitions and safe task cancellation."""

    def test_task_cancellation(self):
        orchestrator = AgentOrchestrator()
        # Simulate an active task
        task = AgentTask(user_goal="Heavy analysis", steps=[AgentStep(description="Step 1")])
        orchestrator.active_task = task
        orchestrator.current_state = AgentState.EXECUTING

        cancelled = orchestrator.cancel_task(task.task_id)
        assert cancelled is True
        assert orchestrator.current_state == AgentState.CANCELLED
        assert task.status == TaskStatus.CANCELLED


# ---------------------------------------------------------------------------
# 8. End-to-End Scenarios Tests
# ---------------------------------------------------------------------------

class TestAgentEndToEndScenarios:
    """Tests complete E2E execution of Scenarios 1 to 4."""

    def test_scenario_1_fast_path_classification(self):
        classifier = RequestClassifier()
        res = classifier.classify("Chrome kholo")
        assert not res.is_agent_path
        assert res.request_type == RequestType.DIRECT_COMMAND

    def test_scenario_2_e2e_plan_and_execution_mocked(self):
        # Mock registry with deterministic outputs for Antigravity
        registry = ToolRegistry()
        mock_open = AgentTool(
            name="desktop.open_application",
            description="Open app mock",
            risk_level=AgentRiskLevel.LOW,
            handler=lambda p: ToolResult(success=True, verified=True, output_data={"target": p.get("target")}),
        )
        mock_window = AgentTool(
            name="desktop.window_operation",
            description="Window op mock",
            risk_level=AgentRiskLevel.LOW,
            handler=lambda p: ToolResult(success=True, verified=True, output_data={"operation": p.get("operation")}),
        )
        registry.register(mock_open)
        registry.register(mock_window)

        orchestrator = AgentOrchestrator(tool_registry=registry)
        summary = orchestrator.execute_goal("AntiGravity kholo aur usko minimize karo")

        assert summary.success is True
        assert summary.total_steps == 2
        assert len(summary.trace) == 2
        assert summary.trace[0].action_name == "open_application"
        assert summary.trace[1].action_name == "window_operation"

    def test_scenario_3_e2e_large_files_line_count(self):
        orchestrator = AgentOrchestrator()
        summary = orchestrator.execute_goal("Is folder mein jo Python files 1500 lines se badi hain unki list banao")

        assert summary.success is True
        assert summary.total_steps >= 1
        assert "Python files 1500 lines se badi hain" in summary.final_answer or "1500 lines se badi koi Python file nahi mili" in summary.final_answer

    def test_autonomous_agent_facade_backward_compatibility(self):
        """Validates that AutonomousAgent backward-compatible facade works identically."""
        agent = AutonomousAgent(
            reasoner=None,
            plugin_manager=None,
        )
        summary = agent.execute_goal("Is folder mein jo Python files 1500 lines se badi hain unki list banao")
        assert isinstance(summary, AgentExecutionSummary)
        assert summary.success is True


class TestAgentPersistenceToSQLite:
    """Validates that Agent Task Memory connects to Cognitive SQLite storage."""

    def test_agent_task_and_step_serialization(self):
        step = AgentStep(
            step_id="step_123",
            step_num=1,
            description="Open browser",
            tool_name="desktop.open_application",
            parameters={"target": "chrome"},
            status=StepStatus.COMPLETED,
            verified=True,
            thought="Need to launch browser",
        )
        step_dict = step.to_dict()
        assert step_dict["step_id"] == "step_123"
        assert step_dict["verified"] is True

        reconstructed_step = AgentStep.from_dict(step_dict)
        assert reconstructed_step.step_id == step.step_id
        assert reconstructed_step.status == StepStatus.COMPLETED
        assert reconstructed_step.verified is True

        task = AgentTask(
            task_id="task_abc",
            user_goal="Research AI trends",
            status=TaskStatus.IN_PROGRESS,
            steps=[step],
            current_step_index=1,
        )
        task_dict = task.to_dict()
        assert task_dict["task_id"] == "task_abc"
        assert len(task_dict["steps"]) == 1

        reconstructed_task = AgentTask.from_dict(task_dict)
        assert reconstructed_task.task_id == task.task_id
        assert reconstructed_task.user_goal == "Research AI trends"
        assert len(reconstructed_task.steps) == 1
        assert reconstructed_task.steps[0].description == "Open browser"

    def test_orchestrator_persists_to_sqlite(self, tmp_path):
        from core.task_engine.persistence import TaskPersistenceManager
        test_db = str(tmp_path / "test_agent_task.db")
        persistence = TaskPersistenceManager(db_or_path=test_db)

        registry = ToolRegistry()
        mock_open = AgentTool(
            name="desktop.open_application",
            description="Mock open",
            risk_level=AgentRiskLevel.LOW,
            handler=lambda p: ToolResult(success=True, verified=True, output_data={"opened": p.get("target")}),
        )
        registry.register(mock_open)

        orchestrator = AgentOrchestrator(
            tool_registry=registry,
            persistence=persistence,
        )
        summary = orchestrator.execute_goal("open chrome")
        assert summary.success is True

        # Verify task was persisted in task_workflows table
        rows = persistence.db.execute_query("SELECT * FROM task_workflows")
        assert len(rows) >= 1
        assert rows[0]["final_status"] == "COMPLETED"
        assert rows[0]["goal"] == "open chrome"

        # Verify step was checkpointed in task_checkpoints table
        checkpoints = persistence.db.execute_query("SELECT * FROM task_checkpoints")
        assert len(checkpoints) >= 1
        assert checkpoints[0]["verified"] == 1

    def test_orchestrator_recovers_pending_tasks(self, tmp_path):
        from core.task_engine.persistence import TaskPersistenceManager
        test_db = str(tmp_path / "test_recovery.db")
        persistence = TaskPersistenceManager(db_or_path=test_db)

        orchestrator = AgentOrchestrator(persistence=persistence)

        # Create an incomplete/in-progress task
        pending_task = AgentTask(
            task_id="mid_crash_1",
            user_goal="Process heavy batch data",
            status=TaskStatus.IN_PROGRESS,
            steps=[
                AgentStep(step_id="s1", step_num=1, description="Step 1", status=StepStatus.COMPLETED, verified=True),
                AgentStep(step_id="s2", step_num=2, description="Step 2", status=StepStatus.IN_PROGRESS),
            ],
            current_step_index=1,
        )
        orchestrator.persist_task_state(pending_task)

        # Retrieve pending tasks
        pending = orchestrator.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0].task_id == "mid_crash_1"
        assert pending[0].user_goal == "Process heavy batch data"
        assert len(pending[0].steps) == 2
        assert pending[0].steps[0].verified is True

