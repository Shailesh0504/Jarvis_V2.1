# core/task_engine/diagnostics.py
"""
Failure Diagnosis and Adaptive Strategy Recovery for the Task Continuity Engine.
Analyzes execution errors, identifies root causes, and recommends
context-aware recovery strategies instead of blindly re-attempting identical calls.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import TaskState, TaskStep

logger = logging.getLogger("jarvis.task_engine.diagnostics")


class FailureDiagnosis:
    """Categorized diagnosis of a step failure."""
    def __init__(
        self,
        category: str,
        root_cause: str,
        recommended_strategy: str,
        adjusted_parameters: Optional[Dict[str, Any]] = None,
        can_recover: bool = True
    ):
        self.category = category  # FILE_NOT_FOUND, WINDOW_UNFOCUSED, TIMEOUT, PERMISSION_DENIED, etc.
        self.root_cause = root_cause
        self.recommended_strategy = recommended_strategy
        self.adjusted_parameters = adjusted_parameters or {}
        self.can_recover = can_recover

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "root_cause": self.root_cause,
            "recommended_strategy": self.recommended_strategy,
            "adjusted_parameters": dict(self.adjusted_parameters),
            "can_recover": self.can_recover,
        }


class FailureDiagnoser:
    """Diagnoses failure patterns and formulates alternate recovery strategies."""

    def diagnose(
        self,
        step: TaskStep,
        error_msg: str,
        context: Dict[str, Any],
        attempt_number: int = 1
    ) -> FailureDiagnosis:
        err_lower = (error_msg or "").lower()

        # 1. File Not Found / Path Resolution Failure
        if any(p in err_lower for p in ["not found", "no such file", "does not exist", "path"]):
            target_path = step.parameters.get("path") or step.parameters.get("file_path", "")
            base, ext = os.path.splitext(str(target_path))

            # Strategy: if .xlsx failed, try .csv fallback
            if ext.lower() in (".xlsx", ".xls"):
                csv_path = f"{base}.csv"
                if os.path.exists(csv_path):
                    return FailureDiagnosis(
                        category="FILE_FORMAT_MISMATCH",
                        root_cause=f"File '{target_path}' not found, but CSV version exists",
                        recommended_strategy="fallback_csv_format",
                        adjusted_parameters={**step.parameters, "path": csv_path}
                    )
                # Try finding in current directory
                return FailureDiagnosis(
                    category="FILE_NOT_FOUND",
                    root_cause=f"Target file '{target_path}' does not exist on disk",
                    recommended_strategy="search_recent_files",
                    adjusted_parameters={"directory": ".", "extension": ext.lstrip(".")}
                )
            return FailureDiagnosis(
                category="FILE_NOT_FOUND",
                root_cause=f"Specified file path was not found: {error_msg}",
                recommended_strategy="search_filesystem",
                adjusted_parameters=step.parameters
            )

        # 2. Window Unfocused / Wrong Window
        if any(p in err_lower for p in ["window", "focus", "not focused", "foreground"]):
            app = step.parameters.get("app_name") or step.parameters.get("target", "")
            return FailureDiagnosis(
                category="WINDOW_UNFOCUSED",
                root_cause=f"Target application '{app}' was not focused or ready for input",
                recommended_strategy="refocus_and_wait",
                adjusted_parameters={**step.parameters, "force_refocus": True, "pre_wait_seconds": 1.0}
            )

        # 3. Timeout / Process Unresponsive
        if any(p in err_lower for p in ["timeout", "timed out", "deadline"]):
            return FailureDiagnosis(
                category="TIMEOUT",
                root_cause=f"Action exceeded execution limit: {error_msg}",
                recommended_strategy="retry_with_extended_timeout",
                adjusted_parameters={**step.parameters, "timeout": step.timeout_seconds * 1.5}
            )

        # 4. Permission Denied
        if any(p in err_lower for p in ["permission", "denied", "unauthorized", "access"]):
            return FailureDiagnosis(
                category="PERMISSION_DENIED",
                root_cause=f"Insufficient permissions for action: {error_msg}",
                recommended_strategy="request_elevation",
                can_recover=False
            )

        # 5. Verification Postcondition Failed
        if "verification failed" in err_lower:
            # Check if fallback strategy was configured on the step
            if step.fallback_strategy:
                return FailureDiagnosis(
                    category="VERIFICATION_FAILED",
                    root_cause=error_msg,
                    recommended_strategy=step.fallback_strategy,
                    adjusted_parameters=step.parameters
                )
            return FailureDiagnosis(
                category="VERIFICATION_FAILED",
                root_cause=error_msg,
                recommended_strategy="retry_with_stabilization",
                adjusted_parameters={**step.parameters, "pre_wait_seconds": 0.5 * attempt_number}
            )

        # 6. Generic / Unknown failure
        return FailureDiagnosis(
            category="GENERAL_ERROR",
            root_cause=error_msg or "Unknown step execution failure",
            recommended_strategy="simple_retry",
            adjusted_parameters=step.parameters
        )
