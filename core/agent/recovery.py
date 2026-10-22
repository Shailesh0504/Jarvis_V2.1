"""Agent Failure Recovery Engine diagnosing step failures and formulating targeted recovery actions.
===================================================================================================
Distinguishes:
- Transient delays (app taking time to load) -> Retry
- State adaptation (app already running -> restore/focus instead of re-launching)
- Target mismatch / Replanning (re-enumerate windows or web fallback)
- Safety confirmation required
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, Optional

from core.agent.observer import SystemObservation
from core.agent.task_manager import AgentStep
from core.agent.verifier import VerificationOutcome

logger = logging.getLogger("jarvis.agent.recovery")


class FailureType(str, Enum):
    """Categorized diagnosis of a step failure."""
    TRANSIENT_DELAY = "TRANSIENT_DELAY"           # OS slow to launch/render -> Retry with wait
    ALREADY_IN_STATE = "ALREADY_IN_STATE"         # Already running or minimized -> Adapt state
    WRONG_TARGET = "WRONG_TARGET"                 # Misspelled or uninstalled app -> Alternative lookup
    PERMISSION_DENIED = "PERMISSION_DENIED"       # High-integrity/Admin window -> Ask permission
    RESOURCE_MISSING = "RESOURCE_MISSING"         # File not found -> Clarify or skip
    PERMANENT_ERROR = "PERMANENT_ERROR"           # Non-recoverable error -> Fail or replan


class RecoveryStrategy(str, Enum):
    """Prescribed recovery strategy."""
    RETRY = "RETRY"
    ADAPT_STATE = "ADAPT_STATE"
    REPLAN = "REPLAN"
    ASK_USER = "ASK_USER"
    FAIL = "FAIL"


@dataclass
class RecoveryDecision:
    """Action prescription to recover from a diagnosed failure."""
    strategy: RecoveryStrategy
    reason: str
    alternative_action: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryAction:
    """Backward-compatible action prescription."""
    should_retry: bool
    should_replan: bool
    recovery_tool: Optional[str] = None
    recovery_parameters: Optional[Dict[str, Any]] = None
    user_clarification: Optional[str] = None
    diagnostic_reason: str = ""


class FailureRecoveryEngine:
    """Diagnoses step execution failures and determines whether to retry,
    substitute a fallback tool, adapt to existing state, or replan.
    """

    def __init__(self, observer: Optional[Any] = None):
        self.observer = observer

    def diagnose_and_decide(
        self,
        step: AgentStep,
        tool_result: Optional[Any] = None,
        observation: Optional[SystemObservation] = None,
        current_retry: int = 0,
    ) -> RecoveryDecision:
        """Analyzes failure context and returns a RecoveryDecision."""
        action = self.diagnose(
            step=step,
            outcome=VerificationOutcome(
                verified=False,
                actual_state="FAILURE",
                failure_reason=tool_result.error if tool_result else "Execution failed",
            ),
            observation=observation or SystemObservation(),
        )

        if action.recovery_tool:
            return RecoveryDecision(
                strategy=RecoveryStrategy.ADAPT_STATE,
                reason=action.diagnostic_reason,
                alternative_action=action.recovery_tool,
                parameters=action.recovery_parameters or {},
            )
        elif action.should_replan:
            return RecoveryDecision(
                strategy=RecoveryStrategy.REPLAN,
                reason=action.diagnostic_reason,
            )
        elif action.should_retry:
            return RecoveryDecision(
                strategy=RecoveryStrategy.RETRY,
                reason=action.diagnostic_reason,
            )
        else:
            return RecoveryDecision(
                strategy=RecoveryStrategy.FAIL,
                reason=action.diagnostic_reason,
            )

    def diagnose(
        self,
        step: AgentStep,
        outcome: VerificationOutcome,
        observation: SystemObservation,
    ) -> RecoveryAction:
        """Analyzes failure context and returns a concrete recovery strategy."""
        tool = step.tool_name
        params = step.parameters or getattr(step, "input_data", {})

        # 1. Check if max retries exceeded
        if step.retry_count >= step.max_retries:
            logger.warning("Step %s exceeded max retries (%d). Triggering replanning.", step.step_id, step.max_retries)
            return RecoveryAction(
                should_retry=False,
                should_replan=True,
                diagnostic_reason=f"Exceeded max retries: {outcome.failure_reason}",
            )

        # 2. Case: Application Launch Failure
        if tool == "desktop.open_application":
            target = params.get("target", "")

            # If the process is already running (e.g. background or minimized)
            if observation.is_target_running:
                logger.info("Recovery: Target '%s' is already running; switching to window restore/focus.", target)
                return RecoveryAction(
                    should_retry=True,
                    should_replan=False,
                    recovery_tool="desktop.window_operation",
                    recovery_parameters={"target": target, "operation": "restore"},
                    diagnostic_reason="Application is already running; restoring window",
                )

            # If app launch failed completely, retry with small backoff
            return RecoveryAction(
                should_retry=True,
                should_replan=False,
                diagnostic_reason=f"Application '{target}' did not appear in time; retrying verification",
            )

        # 3. Case: Window Operation Failure
        if tool == "desktop.window_operation":
            target = params.get("target", "")
            op = params.get("operation", "")

            # If minimizing a window that is already minimized
            if op.lower() == "minimize" and observation.is_target_minimized:
                return RecoveryAction(
                    should_retry=False,
                    should_replan=False,
                    diagnostic_reason=f"Window '{target}' is already minimized; treating as satisfied",
                )

            # If target window wasn't found by exact name, retry with universal resolver fallback
            return RecoveryAction(
                should_retry=True,
                should_replan=False,
                diagnostic_reason=f"Window operation '{op}' failed; retrying with refreshed enumeration",
            )

        # 4. Default transient retry
        return RecoveryAction(
            should_retry=True,
            should_replan=False,
            diagnostic_reason=outcome.failure_reason or "Transient step failure",
        )
