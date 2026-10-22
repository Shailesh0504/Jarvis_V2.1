"""Explicit Agent State Models, Risk Levels, and Task Status Definitions for Jarvis Computer Agent.
================================================================================================
"""

from enum import Enum


class AgentState(str, Enum):
    """Authoritative Finite State Machine states for the Agent Orchestrator."""
    IDLE = "IDLE"
    TASK_CREATED = "TASK_CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    WAITING_FOR_CLARIFICATION = "WAITING_FOR_CLARIFICATION"
    PLANNING = "PLANNING"
    GATHERING_CONTEXT = "GATHERING_CONTEXT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    WAITING = "WAITING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    REPLANNING = "REPLANNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Canonical lifecycle order of an autonomous task, matching the explicit contract:
# TASK CREATED -> UNDERSTAND -> PLAN -> GET CONTEXT -> ASK CONFIRMATION ->
# EXECUTE -> VERIFY -> RECOVER/RETRY -> COMPLETE
AGENT_LIFECYCLE_ORDER: tuple = (
    AgentState.TASK_CREATED,
    AgentState.UNDERSTANDING,
    AgentState.PLANNING,
    AgentState.GATHERING_CONTEXT,
    AgentState.WAITING_FOR_APPROVAL,
    AgentState.EXECUTING,
    AgentState.VERIFYING,
    AgentState.RECOVERING,
    AgentState.COMPLETED,
)


class AgentRiskLevel(str, Enum):
    """Tool and Action Risk Tiers determining confirmation requirements."""
    SAFE = "SAFE"        # Pure observations (read system info, check window, read time)
    LOW = "LOW"          # Reversible user actions (open app, search web, focus window)
    MEDIUM = "MEDIUM"    # Stateful non-destructive actions (modify settings, create files, mute)
    HIGH = "HIGH"        # Potentially destructive actions (delete files, close apps, kill tasks)
    CRITICAL = "CRITICAL"# Irreversible actions (system restart/shutdown, format, credential resets)


class TaskStatus(str, Enum):
    """Lifecycle status of a high-level Agent Task."""
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """Execution status of an individual Agent Plan Step."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILURE = "FAILURE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    RECOVERED = "RECOVERED"
