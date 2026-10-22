"""Test suite for the explicit Task Lifecycle State Engine.
================================================================
Covers:
1. Canonical lifecycle ordering (TASK CREATED -> ... -> COMPLETE)
2. Persistent task state contract (task id, goal, steps, current/completed/failed
   steps, retries, artifacts, context, user approval, result, timestamps)
3. Stage history recorded end-to-end and persisted to SQLite
4. Live task-tree rendering
5. Human-in-the-loop approval gate (approve / deny / fail-safe / policy override)
6. Retry aggregation and serialization round-trip
"""

from __future__ import annotations

import json

import pytest

from core.agent.agent_policy import AgentPolicy
from core.agent.agent_state import (
    AGENT_LIFECYCLE_ORDER,
    AgentRiskLevel,
    AgentState,
    StepStatus,
    TaskStatus,
)
from core.agent.orchestrator import AgentOrchestrator
from core.agent.task_manager import AgentStep, AgentTask, render_task_tree
from core.agent.tool_registry import AgentTool, ToolRegistry, ToolResult


GOAL = "AntiGravity kholo aur usko minimize karo"

REQUIRED_STATE_FIELDS = (
    "task_id",
    "goal",
    "status",
    "steps",
    "current_step",
    "completed_steps",
    "failed_steps",
    "retries",
    "artifacts",
    "context",
    "user_approval",
    "result",
    "created_at",
    "updated_at",
    "timestamp",
)


def _registry_with_risk(risk: AgentRiskLevel, executed: list) -> ToolRegistry:
    """Deterministic registry: open_application carries the given risk, window op stays LOW."""
    registry = ToolRegistry()

    def _open_handler(target=None, **kwargs) -> ToolResult:
        executed.append(target)
        return ToolResult(
            success=True,
            data={"opened": target},
            verified=True,
            observation={"opened": True, "target": target},
        )

    def _window_handler(target=None, operation=None, **kwargs) -> ToolResult:
        executed.append(f"{operation}:{target}")
        return ToolResult(
            success=True,
            data={"operation": operation, "target": target},
            verified=True,
            observation={"operation": operation, "target": target},
        )

    registry.register(AgentTool(
        name="desktop.open_application",
        description="Risk-tier test tool",
        risk_level=risk,
        handler=_open_handler,
    ))
    registry.register(AgentTool(
        name="desktop.window_operation",
        description="Window test tool",
        risk_level=AgentRiskLevel.LOW,
        handler=_window_handler,
    ))
    return registry


def _run_and_get_task(tmp_path, goal: str = GOAL, **orchestrator_kwargs):
    """Runs a goal through an orchestrator backed by SQLite and returns the reloaded task."""
    from core.task_engine.persistence import TaskPersistenceManager

    db_path = str(tmp_path / "lifecycle.db")
    persistence = TaskPersistenceManager(db_or_path=db_path)
    orchestrator = AgentOrchestrator(persistence=persistence, **orchestrator_kwargs)
    summary = orchestrator.execute_goal(goal)

    rows = persistence.db.execute_query(
        "SELECT task_state_json FROM task_workflows ORDER BY updated_at DESC"
    )
    assert rows, "expected the task to be persisted"
    task = AgentTask.from_dict(json.loads(rows[0]["task_state_json"]))
    return summary, task, persistence


# ---------------------------------------------------------------------------
# 1. Lifecycle contract
# ---------------------------------------------------------------------------

class TestLifecycleContract:
    def test_canonical_lifecycle_order(self):
        assert [s.name for s in AGENT_LIFECYCLE_ORDER] == [
            "TASK_CREATED",
            "UNDERSTANDING",
            "PLANNING",
            "GATHERING_CONTEXT",
            "WAITING_FOR_APPROVAL",
            "EXECUTING",
            "VERIFYING",
            "RECOVERING",
            "COMPLETED",
        ]

    def test_state_snapshot_exposes_every_required_field(self):
        task = AgentTask(
            task_id="1042",
            user_goal="Chrome kholo",
            steps=[AgentStep(step_id="s1", description="Open Chrome", status=StepStatus.COMPLETED)],
        )
        task.sync_progress()
        snapshot = task.to_state_snapshot()
        for key in REQUIRED_STATE_FIELDS:
            assert key in snapshot, f"missing persistent field '{key}'"
        assert snapshot["task_id"] == "1042"
        assert snapshot["completed_steps"] == ["s1"]

    def test_roundtrip_preserves_new_lifecycle_fields(self):
        task = AgentTask(
            task_id="t1",
            user_goal="goal",
            completed_steps=["s1"],
            failed_steps=["s2"],
            retries=3,
            artifacts={"file": "report.md"},
            user_approval={"required": True, "approved": True},
            result={"success": True},
        )
        restored = AgentTask.from_dict(task.to_dict())
        assert restored.completed_steps == ["s1"]
        assert restored.failed_steps == ["s2"]
        assert restored.retries == 3
        assert restored.artifacts == {"file": "report.md"}
        assert restored.user_approval["approved"] is True
        assert restored.result == {"success": True}

    def test_sync_progress_aggregates_steps_and_retries(self):
        task = AgentTask(steps=[
            AgentStep(step_id="s1", status=StepStatus.COMPLETED, retry_count=0),
            AgentStep(step_id="s2", status=StepStatus.RECOVERED, retry_count=2),
            AgentStep(step_id="s3", status=StepStatus.FAILED, retry_count=1),
            AgentStep(step_id="s4", status=StepStatus.PENDING),
        ])
        task.sync_progress()
        assert task.completed_steps == ["s1", "s2"]
        assert task.failed_steps == ["s3"]
        assert task.retries == 3


# ---------------------------------------------------------------------------
# 2. End-to-end lifecycle + persistence
# ---------------------------------------------------------------------------

class TestLifecycleExecutionAndPersistence:
    def test_full_run_records_lifecycle_stages(self, tmp_path):
        summary, task, _ = _run_and_get_task(
            tmp_path, tool_registry=_registry_with_risk(AgentRiskLevel.LOW, [])
        )

        assert summary.success is True
        stages = [h["stage"] for h in task.stage_history]
        assert stages[0] == "TASK_CREATED"
        assert "UNDERSTANDING" in stages
        assert "PLANNING" in stages
        assert "GATHERING_CONTEXT" in stages
        assert stages[-1] == "COMPLETED"

    def test_full_run_populates_persistent_state(self, tmp_path):
        summary, task, _ = _run_and_get_task(
            tmp_path, tool_registry=_registry_with_risk(AgentRiskLevel.LOW, [])
        )

        assert task.status == TaskStatus.COMPLETED
        assert len(task.completed_steps) == 2
        assert task.failed_steps == []
        assert task.retries == 0
        assert task.result["success"] is True
        assert "progress_tree" in task.result
        assert task.artifacts, "step observations should be recorded as artifacts"
        assert task.completed_at is not None
        assert task.updated_at >= task.created_at

    def test_sqlite_row_carries_lifecycle_counters(self, tmp_path):
        _summary, _task, persistence = _run_and_get_task(
            tmp_path, tool_registry=_registry_with_risk(AgentRiskLevel.LOW, [])
        )
        rows = persistence.db.execute_query(
            "SELECT goal, final_status, total_steps, retry_count FROM task_workflows"
        )
        assert rows[0]["goal"] == GOAL
        assert rows[0]["final_status"] == "COMPLETED"
        assert rows[0]["total_steps"] == 2
        assert rows[0]["retry_count"] == 0


# ---------------------------------------------------------------------------
# 3. Human-in-the-loop approval gate
# ---------------------------------------------------------------------------

class TestApprovalGate:
    def test_high_risk_fails_safe_without_handler(self, tmp_path):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.HIGH, executed)

        summary, task, _ = _run_and_get_task(tmp_path, tool_registry=registry)

        assert executed == [], "an unapproved HIGH risk tool must never execute"
        assert summary.success is False
        assert task.status == TaskStatus.CANCELLED
        assert task.steps[0].status == StepStatus.BLOCKED
        assert task.user_approval["required"] is True
        assert task.user_approval["approved"] is False
        stages = [h["stage"] for h in task.stage_history]
        assert "WAITING_FOR_APPROVAL" in stages
        assert stages[-1] == "CANCELLED"

    def test_high_risk_executes_when_approved(self, tmp_path):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.HIGH, executed)
        calls: list = []

        def _approve(task, step, risk) -> bool:
            calls.append((step.step_num, risk.name))
            return True

        summary, task, _ = _run_and_get_task(
            tmp_path, tool_registry=registry, approval_callback=_approve
        )

        assert calls == [(1, "HIGH")]
        assert executed == ["antigravity", "minimize:antigravity"]
        assert summary.success is True
        assert task.status == TaskStatus.COMPLETED
        assert task.user_approval["approved"] is True
        events = [e["event"] for e in task.user_approval["events"]]
        assert "requested" in events and "granted" in events

    def test_high_risk_blocks_when_denied(self, tmp_path):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.HIGH, executed)

        summary, task, _ = _run_and_get_task(
            tmp_path, tool_registry=registry, approval_callback=lambda t, s, r: False
        )

        assert executed == []
        assert summary.success is False
        assert task.status == TaskStatus.CANCELLED
        events = [e["event"] for e in task.user_approval["events"]]
        assert "denied" in events

    def test_approval_handler_exception_is_fail_safe(self, tmp_path):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.HIGH, executed)

        def _boom(task, step, risk) -> bool:
            raise RuntimeError("approval channel down")

        summary, task, _ = _run_and_get_task(
            tmp_path, tool_registry=registry, approval_callback=_boom
        )

        assert executed == []
        assert task.status == TaskStatus.CANCELLED

    def test_policy_can_allow_missing_approval(self):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.HIGH, executed)
        orchestrator = AgentOrchestrator(
            tool_registry=registry,
            policy=AgentPolicy(on_missing_approval="allow"),
        )
        summary = orchestrator.execute_goal(GOAL)

        assert summary.success is True
        assert executed == ["antigravity", "minimize:antigravity"]

    def test_low_and_safe_risk_steps_never_gate(self, tmp_path):
        executed: list = []
        registry = _registry_with_risk(AgentRiskLevel.LOW, executed)

        summary, task, _ = _run_and_get_task(tmp_path, tool_registry=registry)

        assert summary.success is True
        assert task.user_approval.get("required", False) is False


# ---------------------------------------------------------------------------
# 4. Live task-tree renderer
# ---------------------------------------------------------------------------

class TestTaskTreeRenderer:
    def test_renderer_matches_lifecycle_view(self):
        task = AgentTask(
            task_id="1042",
            user_goal="Chrome kholo, Gmail open karo aur unread mails ka summary do",
            status=TaskStatus.IN_PROGRESS,
            steps=[
                AgentStep(step_id="s1", step_num=1, description="Open Chrome", status=StepStatus.COMPLETED),
                AgentStep(step_id="s2", step_num=2, description="Open Gmail", status=StepStatus.COMPLETED),
                AgentStep(step_id="s3", step_num=3, description="Read emails", status=StepStatus.IN_PROGRESS),
                AgentStep(step_id="s4", step_num=4, description="Speak result", status=StepStatus.PENDING),
            ],
        )
        tree = render_task_tree(task)
        lines = tree.splitlines()

        assert lines[0] == "Task #1042  [IN_PROGRESS]"
        assert "├─ Open Chrome" in tree
        assert "└─ Speak result" in tree
        assert tree.count("✓") == 2
        assert "→" in tree
        assert "·" in tree

    def test_renderer_marks_blocked_and_retries(self):
        task = AgentTask(task_id="7", status=TaskStatus.CANCELLED, steps=[
            AgentStep(step_id="s1", description="Delete file", status=StepStatus.BLOCKED, retry_count=2),
        ])
        tree = render_task_tree(task)
        assert "⊘" in tree
        assert "(retry x2)" in tree

    def test_renderer_handles_empty_plan(self):
        task = AgentTask(task_id="x", status=TaskStatus.PENDING)
        assert "no steps planned" in render_task_tree(task)
