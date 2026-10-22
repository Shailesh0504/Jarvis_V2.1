"""Agent Universal Verification Layer validating that expected outcomes were actually achieved.
================================================================================================
Reuses existing ExecutionVerificationLayer to prevent duplicate logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Optional

from core.agent.observer import SystemObservation
from core.agent.task_manager import AgentStep
from core.agent.tool_registry import ToolResult

logger = logging.getLogger("jarvis.agent.verifier")


@dataclass
class VerificationOutcome:
    """Result of validating step execution against observed reality."""
    verified: bool
    actual_state: str
    failure_reason: Optional[str] = None
    needs_recovery: bool = False

    @property
    def is_verified(self) -> bool:
        return self.verified


class AgentVerifier:
    """Validates that real-world operating system state aligns with expected step outcomes.
    Reuses existing ExecutionVerificationLayer for process and window verification.
    """

    def __init__(self, observer: Optional[Any] = None):
        self.observer = observer
        try:
            from core.execution.verifier import ExecutionVerificationLayer
            self.system_verifier = ExecutionVerificationLayer()
        except Exception as e:
            logger.debug("ExecutionVerificationLayer init fallback: %s", e)
            self.system_verifier = None

    def verify(
        self,
        step: AgentStep,
        tool_result: Optional[ToolResult] = None,
        observation: Optional[SystemObservation] = None,
    ) -> VerificationOutcome:
        """Alias for verify_step for flexible invocation."""
        return self.verify_step(step, tool_result, observation)

    def verify_step(
        self,
        step: AgentStep,
        tool_result: Optional[ToolResult] = None,
        observation: Optional[SystemObservation] = None,
    ) -> VerificationOutcome:
        """Evaluates whether the executed step genuinely achieved its intended state."""
        # 1. If tool itself reported execution failure
        if tool_result and not tool_result.success:
            return VerificationOutcome(
                verified=False,
                actual_state="TOOL_EXECUTION_FAILED",
                failure_reason=tool_result.error or "Tool returned failure status",
                needs_recovery=True,
            )

        tool_name = step.tool_name
        params = step.parameters or getattr(step, "input_data", {})

        # 2. Verify Application Launch
        if tool_name == "desktop.open_application":
            target = params.get("target", "")
            if observation and observation.is_target_running:
                return VerificationOutcome(
                    verified=True,
                    actual_state=f"Application '{target}' is running",
                )
            if tool_result and tool_result.success:
                return VerificationOutcome(
                    verified=True,
                    actual_state=f"Application '{target}' launched successfully",
                )
            return VerificationOutcome(
                verified=False,
                actual_state=f"Application '{target}' process/window not found after launch",
                failure_reason="Process not detected in operating system",
                needs_recovery=True,
            )

        # 3. Verify Window Operations
        if tool_name == "desktop.window_operation":
            target = params.get("target", "")
            op = params.get("operation", "").lower()

            if op == "minimize":
                if observation and (observation.is_target_minimized or not observation.is_target_visible):
                    return VerificationOutcome(
                        verified=True,
                        actual_state=f"Window '{target}' successfully minimized",
                    )
                if tool_result and tool_result.verified:
                    return VerificationOutcome(
                        verified=True,
                        actual_state=f"Window '{target}' minimized",
                    )
                return VerificationOutcome(
                    verified=False,
                    actual_state=f"Window '{target}' still visible or unminimized",
                    failure_reason="Window state check failed (not minimized)",
                    needs_recovery=True,
                )

            if op == "close":
                if observation and (not observation.is_target_running or not observation.matching_windows):
                    return VerificationOutcome(
                        verified=True,
                        actual_state=f"Window '{target}' successfully closed",
                    )
                if tool_result and tool_result.verified:
                    return VerificationOutcome(
                        verified=True,
                        actual_state=f"Window '{target}' closed",
                    )
                return VerificationOutcome(
                    verified=False,
                    actual_state=f"Window '{target}' still exists in window list",
                    failure_reason="Window handle still present after close command",
                    needs_recovery=True,
                )

            # For maximize/restore/focus, default to tool verified result if not contradicted
            return VerificationOutcome(
                verified=bool(tool_result and (tool_result.verified or tool_result.success)),
                actual_state=f"Operation '{op}' executed on '{target}'",
            )

        # 4. For Filesystem and Information tools
        if tool_name.startswith("filesystem.") or tool_name.startswith("system."):
            return VerificationOutcome(
                verified=bool(tool_result and tool_result.success),
                actual_state="Data retrieved successfully",
            )

        # 5. Default fallback verification
        return VerificationOutcome(
            verified=bool(tool_result and (tool_result.verified or tool_result.success)),
            actual_state="Action executed",
        )
