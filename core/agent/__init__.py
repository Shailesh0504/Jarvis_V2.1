"""Agent Layer Package - Autonomous Personal AI Agent for Jarvis.
===================================================================
Provides modular, decoupled agent components:
- Request classification (Fast Path vs Agent Path)
- Goal formation & task decomposition
- Tool registry wrapping existing skills
- Real OS observation & multi-layer verification
- Failure recovery & replanning
- Safety policies, dry-run, and human-in-the-loop gates
"""

from .agent_policy import AgentPolicy
from .agent_state import (
    AGENT_LIFECYCLE_ORDER,
    AgentRiskLevel,
    AgentState,
    StepStatus,
    TaskStatus,
)
from .observer import AgentObserver, SystemObservation
from .orchestrator import AgentOrchestrator, AutonomousAgent
from .planner import AgentPlanner
from .recovery import FailureRecoveryEngine, RecoveryDecision, RecoveryStrategy
from .replanner import AgentReplanner
from .request_classifier import RequestClassification, RequestClassifier, RequestType
from .task_manager import (
    AgentExecutionSummary,
    AgentStep,
    AgentStepRecord,
    AgentTask,
    render_task_tree,
)
from .tool_registry import AgentTool, ToolRegistry, ToolResult
from .verifier import AgentVerifier, VerificationOutcome

__all__ = [
    "AGENT_LIFECYCLE_ORDER",
    "AgentExecutionSummary",
    "AgentObserver",
    "AgentOrchestrator",
    "AgentPlanner",
    "AgentPolicy",
    "AgentReplanner",
    "AgentRiskLevel",
    "AgentState",
    "AgentStep",
    "AgentStepRecord",
    "AgentTask",
    "AgentTool",
    "AgentVerifier",
    "AutonomousAgent",
    "FailureRecoveryEngine",
    "RecoveryDecision",
    "RecoveryStrategy",
    "RequestClassification",
    "RequestClassifier",
    "RequestType",
    "StepStatus",
    "SystemObservation",
    "TaskStatus",
    "ToolRegistry",
    "ToolResult",
    "VerificationOutcome",
    "render_task_tree",
]
