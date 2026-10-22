# core/recovery/manager.py
"""
Recovery Manager for Jarvis V2.1.
Implements bounded, loop-prevented post-execution & verification recovery.
Flow: Execution -> Verification -> Failure -> RecoveryManager -> RecoveryDecision.
"""

from collections import defaultdict
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.contracts import RecoveryAction, RecoveryDecision, Target, ExecutionPlan
from core.execution.models import ActionPlan, ExecutionResult, VerificationResult

logger = logging.getLogger("jarvis.core.recovery")


class RecoveryManager:
    """
    Central recovery coordinator ensuring that execution or verification failures
    trigger bounded, intelligent healing without infinite loops or unhandled crashes.
    """

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        # Track attempted strategies per plan/turn to prevent infinite cycles
        self._attempt_history: Dict[str, Set[str]] = defaultdict(set)
        # Strategy fallback hierarchy
        self._strategy_fallbacks: Dict[str, str] = {
            "win32_api": "process_spawner",
            "process_spawner": "powershell_launcher",
            "powershell_launcher": "plugin_fallback",
            "direct_launch": "win32_api",
        }

    def evaluate_failure(
        self,
        plan: Any,
        execution_result: ExecutionResult,
        verification_result: Optional[VerificationResult] = None,
        retry_count: int = 0
    ) -> RecoveryDecision:
        """
        Determines the appropriate recovery action for a failed execution or verification turn.
        Enforces maximum retry limits and loop avoidance.
        """
        action = getattr(plan, "action", "")
        target = getattr(plan, "target", "")
        plan_id = getattr(plan, "plan_id", str(time.time()))
        current_strategy = getattr(execution_result, "strategy_used", "primary")

        # Record this attempt
        self._attempt_history[plan_id].add(current_strategy)

        # 1. Hard retry limit reached
        if retry_count >= self.max_retries:
            logger.warning(
                f"[Recovery] Plan '{plan_id}' reached max retries ({self.max_retries}). Aborting."
            )
            return RecoveryDecision(
                action=RecoveryAction.ABORT,
                reason=f"Maximum retry limit ({self.max_retries}) reached without successful verification.",
                retry_count=retry_count,
                max_retries=self.max_retries,
                diagnostics=list(getattr(execution_result, "diagnostics", []))
            )

        err_msg = (execution_result.error or (verification_result.error if verification_result else "") or "").lower()
        reason_msg = (execution_result.reason or (verification_result.message if verification_result else "") or "").lower()
        combined_err = f"{err_msg} {reason_msg}"

        # 2. Ambiguity / multiple candidates -> Ask user for clarification
        if "ambiguous" in combined_err or "multiple candidates" in combined_err:
            prompt = f"Multiple matching targets found for '{target}'. Which one would you like me to use?"
            return RecoveryDecision(
                action=RecoveryAction.ASK_USER,
                reason="Target ambiguity cannot be resolved automatically.",
                user_prompt=prompt,
                retry_count=retry_count,
                max_retries=self.max_retries
            )

        # 3. Target not found / window title changed -> Target Re-discovery
        if any(k in combined_err for k in ["not found", "window_not_found", "process_not_found", "hwnd invalid"]):
            # Check if rediscovery already attempted
            if "rediscover" not in self._attempt_history[plan_id]:
                self._attempt_history[plan_id].add("rediscover")
                return RecoveryDecision(
                    action=RecoveryAction.REDISCOVER_TARGET,
                    reason="Target process or window handle not found; re-discovering active desktop targets.",
                    retry_count=retry_count + 1,
                    max_retries=self.max_retries,
                    target_strategy="rediscover"
                )

        # 4. Strategy fallback -> Try alternate execution strategy
        next_strategy = self._strategy_fallbacks.get(current_strategy)
        if next_strategy and next_strategy not in self._attempt_history[plan_id]:
            return RecoveryDecision(
                action=RecoveryAction.RETRY_ALTERNATE,
                reason=f"Strategy '{current_strategy}' failed; failing over to alternate strategy '{next_strategy}'.",
                target_strategy=next_strategy,
                retry_count=retry_count + 1,
                max_retries=self.max_retries
            )

        # 5. Transient timing error (e.g. process still starting up) -> Retry
        if any(k in combined_err for k in ["timeout", "still starting", "busy", "initializing"]):
            return RecoveryDecision(
                action=RecoveryAction.RETRY,
                reason="Transient startup delay; retrying physical verification.",
                retry_count=retry_count + 1,
                max_retries=self.max_retries
            )

        # 6. Unrecoverable / Unknown failure -> Abort cleanly
        return RecoveryDecision(
            action=RecoveryAction.ABORT,
            reason=f"Unrecoverable execution failure: {execution_result.error or 'Verification failed'}",
            retry_count=retry_count,
            max_retries=self.max_retries,
            diagnostics=list(getattr(execution_result, "diagnostics", []))
        )

    def clear_history(self, plan_id: Optional[str] = None) -> None:
        if plan_id:
            self._attempt_history.pop(plan_id, None)
        else:
            self._attempt_history.clear()
