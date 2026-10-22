"""Agent Task and Step models, execution records, and state tracking.
===================================================================
Represents autonomous agent tasks, decomposed steps, execution summaries,
and legacy record contracts for seamless backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional
import uuid

from core.agent.agent_state import StepStatus, TaskStatus


@dataclass
class AgentStepRecord:
    """Backward-compatible step record for legacy callers."""
    step_num: int
    thought: str
    action_plugin: str
    action_name: str
    parameters: Dict[str, Any]
    observation: Any = None
    success: bool = True
    error: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class AgentExecutionSummary:
    """Backward-compatible execution summary for legacy callers."""
    goal: str
    success: bool
    final_answer: str
    total_steps: int
    trace: List[AgentStepRecord] = field(default_factory=list)
    total_time_ms: float = 0.0


@dataclass
class AgentStep:
    """Represents a single executable atomic step within an Agent Task."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_num: int = 1
    description: str = ""
    tool_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    expected_outcome: str = ""
    actual_outcome: Any = None
    status: StepStatus = StepStatus.PENDING
    verified: bool = False
    retry_count: int = 0
    max_retries: int = 2
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    observation: Optional[Dict[str, Any]] = None
    thought: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def input_data(self) -> Dict[str, Any]:
        return self.parameters

    @input_data.setter
    def input_data(self, val: Dict[str, Any]) -> None:
        self.parameters = val

    @property
    def retries(self) -> int:
        return self.retry_count

    @retries.setter
    def retries(self, val: int) -> None:
        self.retry_count = val

    @property
    def actual_output(self) -> Any:
        return self.actual_outcome

    @actual_output.setter
    def actual_output(self, val: Any) -> None:
        self.actual_outcome = val

    def to_record(self, step_num: int) -> AgentStepRecord:
        """Converts to legacy AgentStepRecord."""
        plugin = self.tool_name.split(".")[0] if "." in self.tool_name else self.tool_name
        action = self.tool_name.split(".")[1] if "." in self.tool_name else "execute"
        return AgentStepRecord(
            step_num=step_num,
            thought=self.thought or self.description,
            action_plugin=plugin,
            action_name=action,
            parameters=dict(self.parameters),
            observation=self.observation or self.actual_outcome,
            success=(self.status in (StepStatus.SUCCESS, StepStatus.RECOVERED, StepStatus.COMPLETED)),
            error=self.error,
            execution_time_ms=self.execution_time_ms,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the AgentStep to a dictionary."""
        return {
            "step_id": self.step_id,
            "step_num": self.step_num,
            "description": self.description,
            "tool_name": self.tool_name,
            "parameters": dict(self.parameters),
            "depends_on": list(self.depends_on),
            "expected_outcome": self.expected_outcome,
            "actual_outcome": str(self.actual_outcome) if self.actual_outcome is not None else None,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "verified": self.verified,
            "retry_count": self.retry_count,
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
            "thought": self.thought,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentStep":
        """Deserializes an AgentStep from a dictionary."""
        status_val = data.get("status", "PENDING")
        try:
            status = StepStatus(status_val)
        except Exception:
            status = StepStatus.PENDING
        return cls(
            step_id=str(data.get("step_id", str(uuid.uuid4())[:8])),
            step_num=int(data.get("step_num", 1)),
            description=data.get("description", ""),
            tool_name=data.get("tool_name", ""),
            parameters=dict(data.get("parameters", {})),
            depends_on=list(data.get("depends_on", [])),
            expected_outcome=data.get("expected_outcome", ""),
            actual_outcome=data.get("actual_outcome"),
            status=status,
            verified=bool(data.get("verified", False)),
            retry_count=int(data.get("retry_count", 0)),
            execution_time_ms=float(data.get("execution_time_ms", 0.0)),
            error=data.get("error"),
            thought=data.get("thought", ""),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )


@dataclass
class AgentTask:
    """Represents an active multi-step autonomous goal with tracking and lifecycle."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_goal: str = ""
    raw_input: str = ""
    status: TaskStatus = TaskStatus.PENDING
    steps: List[AgentStep] = field(default_factory=list)
    current_step_index: int = 0
    constraints: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    final_answer: str = ""
    error: Optional[str] = None
    is_dry_run: bool = False
    # --- Explicit persistent lifecycle state (single source of truth per task) ---
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    retries: int = 0
    artifacts: Dict[str, Any] = field(default_factory=dict)
    user_approval: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    stage_history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def goal(self) -> str:
        return self.user_goal

    @goal.setter
    def goal(self, val: str) -> None:
        self.user_goal = val

    def get_current_step(self) -> Optional[AgentStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self) -> Optional[AgentStep]:
        self.current_step_index += 1
        return self.get_current_step()

    # --- Lifecycle state tracking -------------------------------------------------

    def record_stage(self, stage: Any, reason: str = "") -> None:
        """Appends a lifecycle stage transition to the persistent audit trail."""
        stage_name = stage.value if hasattr(stage, "value") else str(stage)
        self.stage_history.append({
            "stage": stage_name,
            "reason": reason,
            "timestamp": time.time(),
        })
        self.updated_at = time.time()

    def sync_progress(self) -> None:
        """Recomputes completed/failed step ids and aggregate retry count from live steps."""
        completed_statuses = (StepStatus.SUCCESS, StepStatus.COMPLETED, StepStatus.RECOVERED)
        failed_statuses = (StepStatus.FAILURE, StepStatus.FAILED, StepStatus.BLOCKED)
        self.completed_steps = [s.step_id for s in self.steps if s.status in completed_statuses]
        self.failed_steps = [s.step_id for s in self.steps if s.status in failed_statuses]
        self.retries = sum(int(s.retry_count or 0) for s in self.steps)
        self.updated_at = time.time()

    def record_approval_required(self, step: Optional[AgentStep], risk_level: Any) -> None:
        """Marks that a step is paused pending explicit user approval."""
        risk_name = risk_level.value if hasattr(risk_level, "value") else str(risk_level)
        events = list(self.user_approval.get("events", []))
        events.append({
            "event": "requested",
            "step_id": getattr(step, "step_id", None),
            "risk_level": risk_name,
            "timestamp": time.time(),
        })
        self.user_approval = {
            "required": True,
            "approved": None,
            "step_id": getattr(step, "step_id", None),
            "step_description": getattr(step, "description", ""),
            "risk_level": risk_name,
            "requested_at": time.time(),
            "events": events,
        }
        self.updated_at = time.time()

    def record_approval_decision(self, approved: bool, reason: str = "") -> None:
        """Finalizes the human-in-the-loop approval decision for the active task."""
        if not self.user_approval:
            self.user_approval = {"required": False, "approved": None, "events": []}
        self.user_approval["approved"] = bool(approved)
        self.user_approval["decided_at"] = time.time()
        self.user_approval["reason"] = reason
        self.user_approval.setdefault("events", []).append({
            "event": "granted" if approved else "denied",
            "reason": reason,
            "timestamp": time.time(),
        })
        self.updated_at = time.time()

    def record_artifact(self, key: str, value: Any) -> None:
        """Records a produced artifact (output data, file path, summary) keyed by step/tool."""
        self.artifacts[key] = value
        self.updated_at = time.time()

    def to_state_snapshot(self) -> Dict[str, Any]:
        """Returns the explicit persistent task state contract as a flat dictionary."""
        status_val = self.status.value if hasattr(self.status, "value") else str(self.status)
        return {
            "task_id": self.task_id,
            "goal": self.user_goal,
            "status": status_val,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step_index,
            "completed_steps": list(self.completed_steps),
            "failed_steps": list(self.failed_steps),
            "retries": self.retries,
            "artifacts": dict(self.artifacts),
            "context": dict(self.context),
            "user_approval": dict(self.user_approval),
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "timestamp": self.updated_at,
        }

    def to_progress_tree(self) -> str:
        """Renders the live task tree (Task #<id> with per-step status glyphs)."""
        return render_task_tree(self)

    def to_summary(self) -> AgentExecutionSummary:
        """Converts to legacy AgentExecutionSummary."""
        trace = [step.to_record(i + 1) for i, step in enumerate(self.steps)]
        success = self.status == TaskStatus.COMPLETED
        total_time = (self.completed_at - self.created_at) * 1000 if self.completed_at else 0.0
        return AgentExecutionSummary(
            goal=self.user_goal,
            success=success,
            final_answer=self.final_answer,
            total_steps=len(self.steps),
            trace=trace,
            total_time_ms=total_time,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the AgentTask and all steps to a dictionary."""
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "raw_input": self.raw_input,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "current_step_index": self.current_step_index,
            "total_steps": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
            "constraints": list(self.constraints),
            "context": dict(self.context),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "final_answer": self.final_answer,
            "error": self.error,
            "is_dry_run": self.is_dry_run,
            "updated_at": self.updated_at,
            "completed_steps": list(self.completed_steps),
            "failed_steps": list(self.failed_steps),
            "retries": self.retries,
            "artifacts": dict(self.artifacts),
            "user_approval": dict(self.user_approval),
            "result": self.result,
            "stage_history": list(self.stage_history),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentTask":
        """Deserializes an AgentTask from a dictionary."""
        status_val = data.get("status", "PENDING")
        try:
            status = TaskStatus(status_val)
        except Exception:
            status = TaskStatus.PENDING
        steps = [AgentStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            user_goal=data.get("user_goal", ""),
            raw_input=data.get("raw_input", ""),
            status=status,
            steps=steps,
            current_step_index=int(data.get("current_step_index", 0)),
            constraints=list(data.get("constraints", [])),
            context=dict(data.get("context", {})),
            created_at=float(data.get("created_at", time.time())),
            completed_at=data.get("completed_at"),
            final_answer=data.get("final_answer", ""),
            error=data.get("error"),
            is_dry_run=bool(data.get("is_dry_run", False)),
            updated_at=float(data.get("updated_at", data.get("created_at", time.time()))),
            completed_steps=list(data.get("completed_steps", [])),
            failed_steps=list(data.get("failed_steps", [])),
            retries=int(data.get("retries", 0)),
            artifacts=dict(data.get("artifacts", {})),
            user_approval=dict(data.get("user_approval", {})),
            result=data.get("result"),
            stage_history=list(data.get("stage_history", [])),
        )


# Status glyphs used by the live task-tree renderer.
_STEP_GLYPHS: Dict[Any, str] = {
    StepStatus.COMPLETED: "✓",
    StepStatus.SUCCESS: "✓",
    StepStatus.RECOVERED: "✓",
    StepStatus.FAILED: "✗",
    StepStatus.FAILURE: "✗",
    StepStatus.BLOCKED: "⊘",
    StepStatus.SKIPPED: "–",
    StepStatus.RUNNING: "→",
    StepStatus.IN_PROGRESS: "→",
    StepStatus.PENDING: "·",
}


def render_task_tree(task: "AgentTask") -> str:
    """Renders a human-readable live task tree, e.g.:

    Task #1042  [IN_PROGRESS]
     ├─ Open Chrome   ✓
     └─ Speak result  →
    """
    status_val = task.status.value if hasattr(task.status, "value") else str(task.status)
    lines = [f"Task #{task.task_id}  [{status_val}]"]
    if not task.steps:
        lines.append(" └─ (no steps planned)")
        return "\n".join(lines)

    labels = [s.description or s.tool_name or f"Step {s.step_num}" for s in task.steps]
    width = max(len(lbl) for lbl in labels)
    last_index = len(task.steps) - 1
    for idx, step in enumerate(task.steps):
        branch = "└─" if idx == last_index else "├─"
        glyph = _STEP_GLYPHS.get(step.status, "·")
        retry = f"  (retry x{step.retry_count})" if step.retry_count else ""
        lines.append(f" {branch} {labels[idx].ljust(width)}  {glyph}{retry}")
    return "\n".join(lines)
