# core/task_engine/models.py
"""
Data models and contracts for the Jarvis Long-Horizon Task Continuity Engine.
Defines persistent TaskState, TaskStep, StepExecutionReport, and TaskStatus.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from typing import Any, Dict, List, Optional
import uuid


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskStep:
    """Individual atomic step within an explicit execution plan."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    plugin_name: str = ""
    action_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_permission: str = "EXECUTE"
    depends_on: List[str] = field(default_factory=list)
    critical: bool = True
    verification_type: str = "default"  # default, file_exists, file_content, window_focus, custom
    verification_params: Dict[str, Any] = field(default_factory=dict)
    fallback_strategy: Optional[str] = None  # e.g. alternate_format, alternate_app, search_and_retry
    max_retries: int = 3
    timeout_seconds: float = 30.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "plugin_name": self.plugin_name,
            "action_name": self.action_name,
            "parameters": dict(self.parameters),
            "required_permission": self.required_permission,
            "depends_on": list(self.depends_on),
            "critical": self.critical,
            "verification_type": self.verification_type,
            "verification_params": dict(self.verification_params),
            "fallback_strategy": self.fallback_strategy,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        return cls(
            step_id=data.get("step_id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            description=data.get("description", ""),
            plugin_name=data.get("plugin_name", ""),
            action_name=data.get("action_name", ""),
            parameters=dict(data.get("parameters", {})),
            required_permission=data.get("required_permission", "EXECUTE"),
            depends_on=list(data.get("depends_on", [])),
            critical=bool(data.get("critical", True)),
            verification_type=data.get("verification_type", "default"),
            verification_params=dict(data.get("verification_params", {})),
            fallback_strategy=data.get("fallback_strategy"),
            max_retries=int(data.get("max_retries", 3)),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        )


@dataclass
class StepExecutionReport:
    """Outcome and verification record for an executed step."""
    step_id: str
    step_name: str
    success: bool
    verified: bool = False
    data: Any = None
    error: Optional[str] = None
    attempt: int = 1
    strategy_used: str = "primary"
    verification_details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "success": self.success,
            "verified": self.verified,
            "data": self.data,
            "error": self.error,
            "attempt": self.attempt,
            "strategy_used": self.strategy_used,
            "verification_details": dict(self.verification_details),
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepExecutionReport":
        return cls(
            step_id=data.get("step_id", ""),
            step_name=data.get("step_name", ""),
            success=bool(data.get("success", False)),
            verified=bool(data.get("verified", False)),
            data=data.get("data"),
            error=data.get("error"),
            attempt=int(data.get("attempt", 1)),
            strategy_used=data.get("strategy_used", "primary"),
            verification_details=dict(data.get("verification_details", {})),
            duration_ms=float(data.get("duration_ms", 0.0)),
            timestamp=float(data.get("timestamp", time.time())),
        )


@dataclass
class TaskState:
    """
    Persistent active workflow state satisfying the explicit contract:
    - task_id: unique task identifier
    - goal: high-level user goal
    - plan: explicit step-by-step plan
    - current_step: 0-indexed index of step currently executing
    - completed_steps: verified step execution records
    - remaining_steps: upcoming planned steps
    - failed_steps: failure records with diagnosis and attempted strategies
    - retry_count: aggregate retry attempts
    - execution_context: intermediate data, dynamic variables, environment state
    - required_entities: resolved entities and parameters
    - dependencies: dependency mapping between steps
    - final_status: current lifecycle state
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    plan: List[TaskStep] = field(default_factory=list)
    current_step: int = 0
    completed_steps: List[StepExecutionReport] = field(default_factory=list)
    remaining_steps: List[TaskStep] = field(default_factory=list)
    failed_steps: List[Dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    execution_context: Dict[str, Any] = field(default_factory=dict)
    required_entities: Dict[str, Any] = field(default_factory=dict)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    final_status: TaskStatus = TaskStatus.PENDING

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    suspension_stack: List[Dict[str, Any]] = field(default_factory=list)
    step_retry_counts: Dict[str, int] = field(default_factory=dict)
    final_verification: Optional[Dict[str, Any]] = None

    @property
    def total_steps(self) -> int:
        return len(self.plan)

    @property
    def is_finished(self) -> bool:
        return self.final_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def current_step_obj(self) -> Optional[TaskStep]:
        if 0 <= self.current_step < len(self.plan):
            return self.plan[self.current_step]
        return None

    def advance_step(self, report: StepExecutionReport) -> None:
        """Records completed verified step and advances cursor to next step."""
        self.completed_steps.append(report)
        self.current_step += 1
        self.remaining_steps = [s for s in self.plan[self.current_step:]]
        self.updated_at = time.time()

    def record_step_failure(self, step: TaskStep, error: str, strategy: str, diagnosis: str) -> None:
        """Records a step attempt failure with diagnostic details."""
        self.retry_count += 1
        self.step_retry_counts[step.step_id] = self.step_retry_counts.get(step.step_id, 0) + 1
        self.failed_steps.append({
            "step_id": step.step_id,
            "step_name": step.name or step.description,
            "attempt": self.step_retry_counts[step.step_id],
            "error": error,
            "strategy_attempted": strategy,
            "diagnosis": diagnosis,
            "timestamp": time.time(),
        })
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "plan": [s.to_dict() for s in self.plan],
            "current_step": self.current_step,
            "completed_steps": [c.to_dict() for c in self.completed_steps],
            "remaining_steps": [r.to_dict() for r in self.remaining_steps],
            "failed_steps": list(self.failed_steps),
            "retry_count": self.retry_count,
            "execution_context": dict(self.execution_context),
            "required_entities": dict(self.required_entities),
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "final_status": self.final_status.value if isinstance(self.final_status, TaskStatus) else str(self.final_status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "suspension_stack": list(self.suspension_stack),
            "step_retry_counts": dict(self.step_retry_counts),
            "final_verification": self.final_verification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        plan_steps = [TaskStep.from_dict(s) for s in data.get("plan", [])]
        completed = [StepExecutionReport.from_dict(c) for c in data.get("completed_steps", [])]
        remaining = [TaskStep.from_dict(r) for r in data.get("remaining_steps", [])]

        # In case remaining_steps was not explicitly serialized, infer from current_step
        curr_step = int(data.get("current_step", 0))
        if not remaining and plan_steps and curr_step < len(plan_steps):
            remaining = plan_steps[curr_step:]

        status_str = data.get("final_status", TaskStatus.PENDING.value)
        try:
            status = TaskStatus(status_str)
        except Exception:
            status = TaskStatus.PENDING

        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            goal=data.get("goal", ""),
            plan=plan_steps,
            current_step=curr_step,
            completed_steps=completed,
            remaining_steps=remaining,
            failed_steps=list(data.get("failed_steps", [])),
            retry_count=int(data.get("retry_count", 0)),
            execution_context=dict(data.get("execution_context", {})),
            required_entities=dict(data.get("required_entities", {})),
            dependencies=dict(data.get("dependencies", {})),
            final_status=status,
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            suspension_stack=list(data.get("suspension_stack", [])),
            step_retry_counts=dict(data.get("step_retry_counts", {})),
            final_verification=data.get("final_verification"),
        )
