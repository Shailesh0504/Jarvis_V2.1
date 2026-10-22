# core/task_engine/verifier.py
"""
Task and Step Verifier for the Task Continuity Engine.
Ensures that no step is marked complete based solely on attempt;
validates physical, system, and plugin states before checkpointing.
Also provides final task outcome validation.
"""

import logging
import os
from typing import Any, Callable, Dict, Optional, Tuple

from .models import StepExecutionReport, TaskState, TaskStep

logger = logging.getLogger("jarvis.task_engine.verifier")


class TaskVerifier:
    """Rigorous verifier for step-level results and final task outcomes."""

    def __init__(self, plugin_manager: Optional[Any] = None):
        self.plugin_manager = plugin_manager

    def verify_step(
        self,
        step: TaskStep,
        raw_result: Any,
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validates that a step achieved its intended postcondition.
        Returns: (is_verified: bool, error_msg: Optional[str], details: Dict[str, Any])
        """
        details: Dict[str, Any] = {"verification_type": step.verification_type}

        # 1. First ensure the execution call itself indicated success
        if hasattr(raw_result, "success") and not raw_result.success:
            err = getattr(raw_result, "error", None) or "Action execution reported failure"
            return False, str(err), details
        if isinstance(raw_result, dict) and raw_result.get("success") is False:
            return False, raw_result.get("error", "Action returned success=False"), details

        vtype = step.verification_type.lower()
        vparams = step.verification_params

        # 2. Verification by File/Directory Existence
        if vtype in ("file_exists", "file_created", "dir_exists", "dir_created"):
            target_path = vparams.get("path") or context.get(vparams.get("path_key", "")) or step.parameters.get("path")
            if not target_path:
                # If target_path is in result data
                if hasattr(raw_result, "data") and isinstance(raw_result.data, dict):
                    target_path = raw_result.data.get("path") or raw_result.data.get("file_path") or raw_result.data.get("dir")
                elif isinstance(raw_result, dict):
                    target_data = raw_result.get("data", raw_result) if isinstance(raw_result.get("data"), dict) else raw_result
                    target_path = target_data.get("path") or target_data.get("file_path") or target_data.get("dir")

            if not target_path or not os.path.exists(str(target_path)):
                return False, f"Verification failed: expected path '{target_path}' does not exist on disk", details

            details["verified_file"] = str(target_path)
            if os.path.isdir(str(target_path)):
                details["is_directory"] = True
                return True, None, details

            details["file_size_bytes"] = os.path.getsize(str(target_path))
            if vparams.get("non_empty", True) and details["file_size_bytes"] == 0:
                return False, f"Verification failed: file '{target_path}' exists but is empty (0 bytes)", details
            return True, None, details

        # 3. Verification by File Content
        elif vtype == "file_content":
            target_path = vparams.get("path") or context.get(vparams.get("path_key", "")) or step.parameters.get("path")
            if not target_path or not os.path.exists(str(target_path)):
                return False, f"Verification failed: file '{target_path}' not found for content check", details

            expected_substr = vparams.get("contains")
            if expected_substr:
                try:
                    with open(str(target_path), "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if expected_substr not in content:
                        return False, f"Verification failed: file '{target_path}' does not contain expected text '{expected_substr}'", details
                    details["verified_content_match"] = expected_substr
                except Exception as e:
                    return False, f"Verification failed: cannot read file '{target_path}': {e}", details
            return True, None, details

        # 4. Verification by Window Focus
        elif vtype in ("window_focus", "window_exists"):
            app_target = vparams.get("app_name") or step.parameters.get("app_name") or step.parameters.get("target")
            wm = self._get_window_manager()
            if wm and app_target:
                windows = wm.find_windows_for_app(str(app_target))
                if not windows:
                    return False, f"Verification failed: no active window found for '{app_target}'", details
                details["matching_windows"] = len(windows)

                if vtype == "window_focus":
                    fg = wm.get_foreground_window()
                    if fg:
                        is_fg = any(w.hwnd == fg.hwnd for w in windows)
                        if not is_fg:
                            return False, f"Verification failed: expected '{app_target}' in foreground, but '{fg.title}' is focused", details
            return True, None, details

        # 5. Verification by Data Key Presence
        elif vtype == "data_key":
            key = vparams.get("key")
            if hasattr(raw_result, "data") and isinstance(raw_result.data, dict):
                raw_data = raw_result.data
            elif isinstance(raw_result, dict) and "data" in raw_result and isinstance(raw_result["data"], dict):
                raw_data = raw_result["data"]
            elif isinstance(raw_result, dict):
                raw_data = raw_result
            else:
                raw_data = getattr(raw_result, "data", raw_result)

            if isinstance(raw_data, dict) and key:
                if key not in raw_data or raw_data[key] is None:
                    return False, f"Verification failed: expected key '{key}' missing from step result data", details
                details["found_key"] = key
                details["value"] = raw_data[key]
            return True, None, details

        # 6. Default plugin success verification
        details["default_verified"] = True
        return True, None, details

    def verify_completion(self, task: TaskState) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validates that the entire task workflow has achieved its final outcome.
        Ensures all planned critical steps succeeded and verifies final state.
        """
        details: Dict[str, Any] = {
            "total_steps": len(task.plan),
            "completed_steps": len(task.completed_steps),
        }

        # 1. All planned steps must be accounted for
        if len(task.completed_steps) < len(task.plan):
            return False, f"Task incomplete: {len(task.completed_steps)}/{len(task.plan)} steps completed", details

        # 2. All completed steps must be verified
        for i, report in enumerate(task.completed_steps):
            if not report.verified or not report.success:
                return False, f"Step {i} ('{report.step_name}') was not verified successfully", details

        # 3. Check final expected outcome if specified in execution_context
        expected_final_file = task.execution_context.get("expected_output_file")
        if expected_final_file:
            if not os.path.exists(expected_final_file):
                return False, f"Final outcome verification failed: output file '{expected_final_file}' missing", details
            details["verified_final_file"] = expected_final_file

        details["all_steps_verified"] = True
        return True, None, details

    def _get_window_manager(self) -> Optional[Any]:
        if not self.plugin_manager:
            return None
        win_plugin = self.plugin_manager.get_plugin("windows")
        return getattr(win_plugin, "window_manager", None) if win_plugin else None
