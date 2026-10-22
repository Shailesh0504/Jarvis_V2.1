# core/contracts/contracts.py
"""
Authoritative Production Data Contracts for Jarvis V2.1.
Establishes standardized, typed dataclass contracts for all stages of the pipeline:
UserRequest -> ConversationFrame -> IntentResult -> ExecutionContext -> Target ->
ExecutionPlan -> ExecutionStep -> ExecutionResult -> VerificationResult -> RecoveryDecision ->
TurnOutcome -> ResponsePayload -> AgentTask -> AgentTaskStep -> MemoryRecord -> LearningCandidate -> Event.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Union
import uuid

from core.execution.models import ExecutionState, VerificationResult, ExecutionResult
from core.context import TurnOutcomeStatus, TurnOutcome


class RequestSource(str, Enum):
    VOICE = "voice"
    CLI = "cli"
    GUI = "gui"
    API = "api"
    PROACTIVE = "proactive"
    WORKFLOW = "workflow"


@dataclass
class UserRequest:
    """Standardized representation of an incoming user request across any input source."""
    raw_input: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    normalized_input: str = ""
    source: RequestSource = RequestSource.CLI
    user_id: str = "default_user"
    session_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "raw_input": self.raw_input,
            "normalized_input": self.normalized_input,
            "source": self.source.value if isinstance(self.source, RequestSource) else str(self.source),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass
class ConversationFrame:
    """Historical and active state frame for multi-turn conversational reasoning."""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    active_intent: Optional[str] = None
    active_target_id: Optional[str] = None
    workflow_locked: bool = False
    workflow_id: Optional[str] = None
    active_slots: Dict[str, Any] = field(default_factory=dict)
    pending_confirmation: bool = False
    turn_count: int = 0
    updated_at: float = field(default_factory=time.time)


@dataclass
class IntentResult:
    """Decoupled result of intent detection and speech-act classification."""
    intent_name: str
    confidence: float = 1.0
    domain: str = "general"
    speech_act: str = "ACTION_COMMAND"  # ACTION_COMMAND, CAPABILITY_QUESTION, STATUS_QUESTION, STATUS_AFTER_ACTION, TROUBLESHOOTING, CHIT_CHAT
    slots: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    normalized_text: str = ""
    is_fallback: bool = False
    is_fast_path: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_name": self.intent_name,
            "confidence": self.confidence,
            "domain": self.domain,
            "speech_act": self.speech_act,
            "slots": dict(self.slots),
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "is_fallback": self.is_fallback,
            "is_fast_path": self.is_fast_path,
            "metadata": dict(self.metadata),
        }


@dataclass
class Target:
    """Explicit resolved target representation with physical/system anchors."""
    name: str
    target_type: str = "application"  # application, website, file, window, media, system
    identifier: str = ""              # Process name, executable path, URL, file path, HWND
    hwnd: Optional[int] = None
    pid: Optional[int] = None
    url: Optional[str] = None
    file_path: Optional[str] = None
    confidence: float = 1.0
    is_ambiguous: bool = False
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "target_type": self.target_type,
            "identifier": self.identifier,
            "hwnd": self.hwnd,
            "pid": self.pid,
            "url": self.url,
            "file_path": self.file_path,
            "confidence": self.confidence,
            "is_ambiguous": self.is_ambiguous,
            "candidates": list(self.candidates),
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionContext:
    """Runtime context passed across the execution pipeline."""
    context_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default_user"
    user_role: str = "ADMIN"
    session_id: Optional[str] = None
    active_target: Optional[Target] = None
    workflow_id: Optional[str] = None
    task_id: Optional[str] = None
    permission_level: str = "EXECUTE"
    risk_tier: str = "LOW"
    cancellation_requested: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStep:
    """Single discrete step within an execution plan."""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action: str = ""
    target: Optional[Target] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    strategy: str = "primary"  # primary, win32_api, process_spawner, plugin, direct
    verification_strategy: str = "process_running"
    timeout_s: float = 5.0
    retry_allowed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Authoritative planned operation produced by Planner or FastPath."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    steps: List[ExecutionStep] = field(default_factory=list)
    risk_level: str = "LOW"
    confirmation_required: bool = False
    confirmation_prompt: Optional[str] = None
    timeout_s: float = 10.0
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.step_id for s in self.steps],
            "risk_level": self.risk_level,
            "confirmation_required": self.confirmation_required,
            "confirmation_prompt": self.confirmation_prompt,
            "timeout_s": self.timeout_s,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    RETRY_ALTERNATE = "RETRY_ALTERNATE"
    REDISCOVER_TARGET = "REDISCOVER_TARGET"
    REPAIR_TRANSIENT_STATE = "REPAIR_TRANSIENT_STATE"
    ASK_USER = "ASK_USER"
    ABORT = "ABORT"
    ROLLBACK = "ROLLBACK"


@dataclass
class RecoveryDecision:
    """Actionable decision output by RecoveryManager after execution/verification failure."""
    action: RecoveryAction
    reason: str
    target_strategy: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    user_prompt: Optional[str] = None
    diagnostics: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value if isinstance(self.action, RecoveryAction) else str(self.action),
            "reason": self.reason,
            "target_strategy": self.target_strategy,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "user_prompt": self.user_prompt,
            "diagnostics": list(self.diagnostics),
            "metadata": dict(self.metadata),
        }


@dataclass
class ResponsePayload:
    """Standardized final output for user presentation (TTS, GUI HUD, CLI)."""
    text: str
    spoken_text: Optional[str] = None
    turn_id: str = ""
    status: TurnOutcomeStatus = TurnOutcomeStatus.VERIFIED
    execution_result: Optional[ExecutionResult] = None
    sensitive_display: Optional[Dict[str, Any]] = None
    ui_directives: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "spoken_text": self.spoken_text or self.text,
            "turn_id": self.turn_id,
            "status": self.status.value if isinstance(self.status, TurnOutcomeStatus) else str(self.status),
            "execution_result": self.execution_result.to_dict() if self.execution_result else None,
            "sensitive_display": self.sensitive_display,
            "ui_directives": dict(self.ui_directives),
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentTaskStep:
    """Discrete step within a multi-step autonomous task graph."""
    step_id: str
    task_id: str
    description: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class AgentTask:
    """Autonomous goal decomposition task graph."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    steps: List[AgentTaskStep] = field(default_factory=list)
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryRecord:
    """Standardized record for multi-tier cognitive memory storage."""
    key: str
    value: Any
    memory_type: str = "semantic"  # working, episodic, semantic, entity, correction
    confidence: float = 1.0
    provenance: str = "user_interaction"
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    ttl_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningCandidate:
    """Auditable continuous learning observation candidate."""
    pattern_type: str  # correction, preference, habit, alias
    observed_input: str
    correction: str
    confidence: float = 0.5
    status: str = "CANDIDATE"  # CANDIDATE, VALIDATED, APPROVED, REJECTED
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """Decoupled message published through EventBus."""
    event_type: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: str = "core"
    correlation_id: Optional[str] = None
