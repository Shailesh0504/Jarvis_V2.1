# core/execution/models.py
"""
Execution lifecycle models, states, and verification contracts for Jarvis V2.
Mandates that execution success is decoupled from function completion and requires
observable system state verification.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class ActionPlan:
    """
    First-class ActionPlan representing a decided, actionable operation before execution.
    Decoupled from intent detection and policy verification.
    """
    action: str                                    # e.g., "open", "close", "launch", "play", "search"
    target: str = ""                               # e.g., "antigravity", "youtube", "monthly_sales.csv"
    target_type: str = "general"                   # "application", "website", "file", "media", "system", "general"
    resolver: str = "auto"                         # "local_application", "web_service", "plugin", "system"
    parameters: Dict[str, Any] = field(default_factory=dict)
    source: str = "user"                           # "voice", "cli", "gui", "proactive", "workflow"
    confidence: float = 1.0
    context_key: str = "global"
    required_permission: str = "EXECUTE"          # "READ", "WRITE", "EXECUTE", "ADMIN"
    risk_level: str = "LOW"                        # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    confirmation_required: bool = False
    confirmation_prompt: Optional[str] = None
    verification_strategy: str = "process_running" # "process_running", "window_exists", "folder_window_open", "file_exists", "unverifiable"
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "action": self.action,
            "target": self.target,
            "target_type": self.target_type,
            "resolver": self.resolver,
            "parameters": dict(self.parameters),
            "source": self.source,
            "confidence": self.confidence,
            "context_key": self.context_key,
            "required_permission": self.required_permission,
            "risk_level": self.risk_level,
            "confirmation_required": self.confirmation_required,
            "confirmation_prompt": self.confirmation_prompt,
            "verification_strategy": self.verification_strategy,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }



class ExecutionState(str, Enum):
    """Explicit lifecycle states for any planned or executed action in Jarvis."""
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    UNVERIFIED = "UNVERIFIED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


@dataclass
class VerificationResult:
    """Detailed observation from system state verification."""
    verified: bool
    state: ExecutionState
    check_type: str                  # e.g., "folder_window_open", "window_exists", "process_running", "file_exists", "system_state", "unverifiable"
    expected: Any = None
    actual: Any = None
    details: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: Optional[str] = None

    @property
    def reason(self) -> Optional[str]:
        return self.error or self.message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "state": self.state.value if isinstance(self.state, ExecutionState) else str(self.state),
            "check_type": self.check_type,
            "expected": self.expected,
            "actual": self.actual,
            "details": dict(self.details),
            "message": self.message,
            "error": self.error,
        }


@dataclass
class ExecutionResult:
    """
    Authoritative result of an executed command with mandatory state verification.
    No verification = No success claim.
    """
    success: bool
    status: ExecutionState
    requested_action: str
    executed_action: str
    verification_result: Optional[VerificationResult] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    strategy_used: str = "primary"
    retry_count: int = 0
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    target: str = ""
    action_type: str = "general"     # "folder", "window", "application", "file", "browser", "media", "system_setting", "unverifiable"
    diagnostics: List[str] = field(default_factory=list)
    recovery_strategies: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value if isinstance(self.status, ExecutionState) else str(self.status),
            "requested_action": self.requested_action,
            "executed_action": self.executed_action,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "error": self.error,
            "reason": self.reason,
            "strategy_used": self.strategy_used,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp,
            "data": dict(self.data),
            "target": self.target,
            "action_type": self.action_type,
            "diagnostics": list(self.diagnostics),
            "recovery_strategies": list(self.recovery_strategies),
            "requires_confirmation": self.requires_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
        }
