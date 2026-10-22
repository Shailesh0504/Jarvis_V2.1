# core/execution/feedback.py
"""
User Negative Feedback and Diagnostic Query Handler for Jarvis V2.
Interprets user expressions of dissatisfaction, failure reports ("nahi hua", "open nahi hua"),
and diagnostic questions ("check karo kyun nahi hua"), links them to previous actions,
runs root-cause diagnostics, and selects improved alternative strategies without repetition.
"""

from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .diagnostics import ExecutionDiagnosticEngine
from .models import ExecutionResult, ExecutionState
from .strategies import ExecutionStrategyEngine

logger = logging.getLogger("jarvis.execution.feedback")


@dataclass
class FeedbackInterpretation:
    """Interpreted feedback intention from conversational input."""
    is_feedback: bool
    is_diagnostic: bool = False
    is_retry_request: bool = False
    target_mentioned: Optional[str] = None
    raw_text: str = ""


class ExecutionFeedbackHandler:
    """
    Detects and handles negative user feedback about previous commands and diagnostic queries.
    """

    NEGATIVE_FEEDBACK_PATTERNS = [
        re.compile(r'\b(?:nahi\s+hua|nhi\s+hua|open\s+nahi\s+hua|open\s+nhi\s+hua|ye\s+kaam\s+nahi\s+hua|kaam\s+nahi\s+hua|nahi\s+khula|nhi\s+khula)\b', re.IGNORECASE),
        re.compile(r'\b(?:it\s+didn\'?t\s+work|didn\'?t\s+work|did\s+not\s+work|not\s+working|fail\s+ho\s+gaya|fail\s+hua|galat\s+hua|galat\s+hai)\b', re.IGNORECASE),
        re.compile(r'\b(?:phir\s+se\s+karo|dobara\s+karo|try\s+again|wapas\s+karo|retry)\b', re.IGNORECASE),
        re.compile(r'\b(?P<target>[\w\-]+)\s+(?:folder\s+)?(?:open\s+nahi\s+hua|nahi\s+khula|open\s+nhi\s+hua)\b', re.IGNORECASE),
    ]

    DIAGNOSTIC_PATTERNS = [
        re.compile(r'\b(?:check\s+karo\s+(?:kyun|kyu|kya\s+dikkat|kya\s+issue|kya\s+problem|fail)|dekho\s+(?:kyun|kyu|kya\s+dikkat|kya\s+issue)|kyun\s+nahi\s+hua|kyu\s+nahi\s+hua|why\s+didn\'?t\s+it\s+work|kya\s+dikkat\s+hai|kya\s+issue\s+hai|kya\s+problem\s+hai)\b', re.IGNORECASE),
        re.compile(r'\b(?:check\s+karo\s+kyun|dekho\s+kyun|kyun\s+open\s+nahi\s+ho|kyun\s+nahi\s+khul)\b', re.IGNORECASE),
        re.compile(r'\bcheck\s+karo\s+kyun\s+open\s+nahi\s+ho\s+paa\s+raha\s+hai\s+(?P<target>.+)\b', re.IGNORECASE),
        re.compile(r'\bwhy\s+is\s+(?P<target2>.+)\s+not\s+opening\b', re.IGNORECASE),
    ]

    def __init__(
        self,
        strategy_engine: Optional[ExecutionStrategyEngine] = None,
        diagnostic_engine: Optional[ExecutionDiagnosticEngine] = None
    ):
        self.strategy_engine = strategy_engine or ExecutionStrategyEngine()
        self.diagnostic_engine = diagnostic_engine or ExecutionDiagnosticEngine(window_manager=self.strategy_engine.verifier.window_manager)

    def interpret_feedback(self, text: str) -> FeedbackInterpretation:
        """Determines if conversational input is negative feedback or diagnostic query."""
        cleaned = text.strip().lower()

        # Check diagnostic intent
        is_diag = any(pat.search(cleaned) for pat in self.DIAGNOSTIC_PATTERNS)
        target = None

        for pat in self.DIAGNOSTIC_PATTERNS:
            m = pat.search(cleaned)
            if m:
                groups = m.groupdict()
                target = groups.get("target") or groups.get("target2")
                if target:
                    target = target.strip().replace("folder", "").strip()
                    break

        # Check negative feedback intent
        is_neg = any(pat.search(cleaned) for pat in self.NEGATIVE_FEEDBACK_PATTERNS)
        is_retry = bool(re.search(r'\b(phir\s+se|dobara|again|retry)\b', cleaned))

        for pat in self.NEGATIVE_FEEDBACK_PATTERNS:
            m = pat.search(cleaned)
            if m:
                groups = m.groupdict()
                t = groups.get("target")
                if t:
                    target = t.strip().replace("folder", "").strip()
                    break

        # Specific phrase matching: e.g. "startup folder open nahi hua" or "excel open nahi hua"
        if "open nahi hua" in cleaned or "nahi khula" in cleaned:
            is_neg = True
            for fld in ("startup", "downloads", "documents", "desktop", "pictures", "videos", "recycle bin", "trash", "temp"):
                if fld in cleaned:
                    target = fld
                    break

        is_feedback = is_neg or is_diag or is_retry

        # Only resolve application target if input actually expresses feedback/retry/diagnostic intent
        if is_feedback and not target:
            from core.apps import get_application_registry
            app_reg = get_application_registry()
            matched_app, _ = app_reg.parse_query(cleaned)
            if matched_app:
                target = matched_app.app_id

        return FeedbackInterpretation(
            is_feedback=is_feedback,
            is_diagnostic=is_diag,
            is_retry_request=is_retry,
            target_mentioned=target,
            raw_text=text
        )

    def handle_feedback(
        self,
        interpretation: FeedbackInterpretation,
        last_execution: Optional[ExecutionResult],
        core: Optional[Any] = None
    ) -> Tuple[bool, str, Optional[ExecutionResult]]:
        """
        Executes negative feedback workflow:
        PREVIOUS ACTION
        -> MARK FAILED
        -> INSPECT FAILURE & RUN DIAGNOSTICS
        -> CHOOSE DIFFERENT/IMPROVED STRATEGY
        -> EXECUTE
        -> VERIFY ACTUAL SYSTEM STATE
        -> REPORT
        """
        if not interpretation.is_feedback:
            return False, "", None

        from core.apps import get_application_registry
        app_reg = get_application_registry()

        # Resolve target from interpretation or previous execution
        target = interpretation.target_mentioned or (last_execution.target if last_execution else "")
        failed_strategy = last_execution.strategy_used if last_execution else "direct_executable"

        if not target and last_execution:
            target = last_execution.target or last_execution.requested_action

        if not target:
            return True, "Aap kis command ya action ke baare me baat kar rahe hain, Boss? Please batayein.", None

        # Check if target is an application
        is_app = bool(
            (last_execution and (
                last_execution.action_type == "application"
                or "launch_app" in (last_execution.requested_action or "")
                or "launch_app" in (last_execution.executed_action or "")
            ))
            or app_reg.get_app(str(target))
            or app_reg.find_by_alias(str(target))
        )

        # 1. Mark previous action as FAILED
        if last_execution:
            last_execution.status = ExecutionState.FAILED
            last_execution.success = False
            logger.info("PREVIOUS_ACTION_MARKED_FAILED: target='%s' strategy='%s'", target, failed_strategy)

        if is_app:
            app_def = app_reg.get_app(str(target)) or app_reg.find_by_alias(str(target))
            disp_name = app_def.display_name if app_def else str(target).capitalize()
            app_id = app_def.app_id if app_def else str(target).lower()

            available_alt = [s for s in ExecutionStrategyEngine.APP_STRATEGIES if s != failed_strategy]
            next_strategy = available_alt[0] if available_alt else "shell_start"

            logger.info("APP_RECOVERY_EXECUTION: app='%s' previous_failed='%s' next_strategy='%s'", app_id, failed_strategy, next_strategy)
            recovery_result = self.strategy_engine.launch_application_verified(
                app_name=app_id,
                preferred_strategy=next_strategy,
                max_retries=1
            )

            if recovery_result.success:
                resp = f"Previous attempt fail ho gaya tha. Maine alternative strategy ('{recovery_result.strategy_used}') use karke '{disp_name}' launch kar diya hai aur verify kar liya hai, Boss."
            else:
                resp = f"Maine alternative strategy se '{disp_name}' launch karne ki koshish ki, lekin verify nahi ho paya. Reason: {recovery_result.error or recovery_result.reason}, Boss."
            return True, resp, recovery_result

        # 2. Inspect failure & run root-cause diagnostics
        diag_report = self.diagnostic_engine.diagnose_folder_operation(
            target=target,
            attempted_strategy=failed_strategy,
            raw_error=last_execution.error if last_execution else "User reported non-completion"
        )

        # Record failure into Experience Learning System
        if core and hasattr(core, "experience_system") and core.experience_system:
            try:
                core.experience_system.record_task_failure(
                    goal=f"open {target} folder",
                    failed_step={"plugin": "files", "action": "open_folder", "target": target},
                    error_msg=f"User reported failure for strategy '{failed_strategy}': {diag_report.root_cause}",
                    attempted_strategy=failed_strategy,
                    category="files",
                    diagnosis=diag_report.root_cause
                )
            except Exception as e:
                logger.debug("Failed to record user feedback failure to experience: %s", e)

        # 3. If User asked for Diagnostic ("check karo kyun nahi hua", etc.)
        if interpretation.is_diagnostic:
            logger.info("DIAGNOSTIC_MODE_ACTIVATED for target='%s'", target)
            summary_header = f"Maine investigate kiya ki '{target}' open kyun nahi ho raha tha:\n"
            reasons_text = "\n".join([f"- {f}" for f in diag_report.diagnostics[:4]])
            root_str = f"\nRoot Cause: {diag_report.root_cause}."

            # Attempt recovery with improved strategy
            alt_strategy = diag_report.suggested_recovery_strategy or "physical_path"
            if alt_strategy == failed_strategy:
                alt_strategy = "com_shell" if failed_strategy != "com_shell" else "powershell"

            logger.info("DIAGNOSTIC_RECOVERY_ATTEMPT: trying alternative strategy='%s'", alt_strategy)
            recovery_result = self.strategy_engine.open_folder_verified(
                target=target,
                preferred_strategy=alt_strategy,
                max_retries=1
            )

            if recovery_result.success:
                resp = (
                    f"{summary_header}{reasons_text}{root_str}\n\n"
                    f"Maine alternative method ('{recovery_result.strategy_used}') use karke '{target}' folder open kar diya hai aur screen par verify kar liya hai, Boss."
                )
                return True, resp, recovery_result
            else:
                resp = (
                    f"{summary_header}{reasons_text}{root_str}\n\n"
                    f"Maine alternative recovery try ki lekin '{target}' open verify nahi ho saka ({recovery_result.error})."
                )
                return True, resp, recovery_result

        # 4. User reported "nahi hua" / "open nahi hua" / "phir se karo"
        # Select a DIFFERENT strategy from what failed
        available_alternatives = [s for s in ExecutionStrategyEngine.FOLDER_STRATEGIES if s != failed_strategy]
        next_strategy = diag_report.suggested_recovery_strategy if (diag_report.suggested_recovery_strategy and diag_report.suggested_recovery_strategy != failed_strategy) else (available_alternatives[0] if available_alternatives else "physical_path")

        logger.info("RECOVERY_EXECUTION: target='%s' previous_failed='%s' next_strategy='%s'", target, failed_strategy, next_strategy)
        recovery_result = self.strategy_engine.open_folder_verified(
            target=target,
            preferred_strategy=next_strategy,
            max_retries=2
        )

        if recovery_result.success:
            resp = (
                f"Previous attempt fail ho gaya tha. Maine improved strategy ('{recovery_result.strategy_used}') se '{target}' folder open kar diya hai aur verify kar liya hai, Boss."
            )
            return True, resp, recovery_result
        else:
            resp = (
                f"Maine alternative method try kiya, lekin '{target}' open nahi ho paya. Reason: {recovery_result.reason or recovery_result.error}, Boss."
            )
            return True, resp, recovery_result
