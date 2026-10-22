"""Turn feedback, mistake classification, and learning experience recording."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.feedback")


class TurnFeedbackService:
    """Encapsulates outcome evaluation, mistake classification, episodic memory, and pattern learning."""

    @classmethod
    def record_turn_feedback(
        cls,
        core: Any,
        turn: Any,
        goal: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        execution_results: Optional[List[Any]] = None,
        verification_results: Optional[List[Any]] = None,
        success: bool = True,
        error_msg: Optional[str] = None,
        category: str = "general",
        intent_name: Optional[str] = None
    ) -> None:
        """
        Authoritative Feedback Loop hook.
        Feeds execution outcomes, verification results, and turn metadata
        into the Learning/Feedback Layer (LearningManager & ExperienceLearningSystem),
        updating Memory, Habits, Sequences, and Confidence Scoring.
        """
        # 1. Update Self-Improvement Engine & LearningManager outcome evaluation & mistake detection
        _is_system_error = False  # Pre-init; set inside error block if failure occurs
        if not success or error_msg:
            # Error Classification Gate:
            # Only trigger user-intent corrections for USER_UNDERSTANDING_ERROR.
            # SYSTEM_ERROR, ENVIRONMENT_ERROR, EXECUTION_ERROR must NOT update user-intent learning.
            err_lower = str(error_msg or "").lower()
            _is_system_error = any(kw in err_lower for kw in (
                "timeout", "winapi", "access denied", "permission", "unauthorized",
                "oserror", "ioerror", "connection", "network", "socket", "subprocess",
                "dll", "registry", "handle", "kernel32", "comexception", "pythoncom",
                "verification",  # post-exec verification failures are env errors
            ))
            try:
                from core.logger import log_mistake, MistakeCategory
                failing_action = steps[-1].get("action") if steps else "execute"
                failing_mod = steps[-1].get("plugin") if steps else (category or "system")
                cat_enum = MistakeCategory.EXECUTION_ERROR
                if "verification" in err_lower:
                    cat_enum = MistakeCategory.VERIFICATION_FAILURE
                elif "permission" in err_lower or "unauthorized" in err_lower:
                    cat_enum = MistakeCategory.SYSTEM_PERMISSION_ERROR
                elif "target" in err_lower or "window" in err_lower or "not found" in err_lower:
                    cat_enum = MistakeCategory.TARGET_RESOLUTION_ERROR

                log_mistake(
                    category=cat_enum,
                    user_query=getattr(turn, "raw_input", goal) or goal,
                    normalized_query=getattr(turn, "normalized_input", goal) or goal,
                    turn_id=getattr(turn, "turn_id", ""),
                    intent=intent_name or getattr(turn, "intent_name", ""),
                    confidence=getattr(turn, "confidence", 1.0),
                    attempted_action=failing_action,
                    action_parameters=steps[-1].get("parameters", {}) if steps else {},
                    error_type=error_msg.split(":")[0] if error_msg and ":" in error_msg else "ExecutionError",
                    error_message=str(error_msg or "Action execution failed"),
                    failing_module=failing_mod,
                    context={
                        "active_app": getattr(turn, "active_app", ""),
                        "source": getattr(turn, "source", "cli"),
                        "is_system_error": _is_system_error,
                    },
                    diagnosis=str(error_msg or "Failed to execute or verify command"),
                    anti_pattern=f"Executing {failing_mod}.{failing_action} without verifying preconditions.",
                    recommended_fix=f"Verify target status or dependencies before executing {failing_action}."
                )
            except Exception as _lm_err:
                logger.debug("Mistake logging note: %s", _lm_err)

        si_engine = getattr(core, "self_improvement_engine", None)
        if si_engine:
            try:
                task_steps = steps or []
                if not task_steps and goal:
                    task_steps = [{"plugin": category or "system", "action": "execute", "parameters": {"goal": goal}}]
                active_ctx = core.active_context.get_context_key() if hasattr(core, "active_context") and core.active_context else "global"
                si_engine.evaluate_interaction(
                    goal=goal or getattr(turn, "normalized_input", ""),
                    steps=task_steps,
                    execution_results=execution_results,
                    verification_results=verification_results,
                    execution_context={
                        "success": success,
                        "error": error_msg,
                        "turn_id": getattr(turn, "turn_id", ""),
                        "source": getattr(turn, "source", "cli"),
                        "active_context": active_ctx,
                        "is_system_error": _is_system_error if (not success or error_msg) else False,
                        "skip_user_correction_learning": _is_system_error if (not success or error_msg) else False,
                    },
                    category=category
                )
            except Exception as e:
                logger.debug("Self-Improvement Engine interaction evaluation note: %s", e)
        elif hasattr(core, "learning_manager") and core.learning_manager:
            try:
                task_steps = steps or []
                if not task_steps and goal:
                    task_steps = [{"plugin": category or "system", "action": "execute", "parameters": {"goal": goal}}]
                active_ctx = core.active_context.get_context_key() if hasattr(core, "active_context") and core.active_context else "global"
                core.learning_manager.evaluate_outcome(
                    goal=goal or getattr(turn, "normalized_input", ""),
                    steps=task_steps,
                    execution_results=execution_results,
                    verification_results=verification_results,
                    execution_context={
                        "success": success,
                        "error": error_msg,
                        "turn_id": getattr(turn, "turn_id", ""),
                        "source": getattr(turn, "source", "cli"),
                        "active_context": active_ctx
                    },
                    category=category
                )
            except Exception as e:
                logger.debug("Feedback Layer outcome evaluation note: %s", e)

        # 2. Update Episodic Interaction Memory
        if hasattr(core, "memory_manager") and core.memory_manager:
            try:
                formatted_results = None
                if execution_results:
                    formatted_results = [
                        {"success": getattr(r, "success", True), "data": getattr(r, "data", None), "error": getattr(r, "error", None)}
                        if hasattr(r, "success") else r
                        for r in execution_results
                    ]
                core.memory_manager.record_interaction(
                    user_input=getattr(turn, "raw_input", ""),
                    response=getattr(turn, "response_text", "") or "",
                    intent=intent_name or (turn.intent.name if hasattr(turn, "intent") and turn.intent else "command"),
                    source=getattr(turn, "source", "cli"),
                    execution_results=formatted_results
                )
            except Exception as e:
                logger.debug("MemoryManager episodic record note: %s", e)

        # 3. Observe pattern and habits
        if hasattr(core, "learning_manager") and core.learning_manager and hasattr(turn, "intent") and turn.intent:
            try:
                core.learning_manager.learn_pattern(
                    raw_input=getattr(turn, "raw_input", ""),
                    normalized_input=getattr(turn, "normalized_input", ""),
                    intent=turn.intent,
                    results=execution_results
                )
            except Exception as e:
                logger.debug("LearningManager pattern observation note: %s", e)

    @classmethod
    def record_learning_experience(
        cls,
        core: Any,
        goal: str,
        steps: List[Dict[str, Any]],
        success: bool = True,
        error_msg: Optional[str] = None,
        category: str = "general"
    ) -> Any:
        """Records task execution experience into the persistent learning system."""
        if hasattr(core, "learning_manager") and core.learning_manager:
            return core.learning_manager.evaluate_outcome(
                goal=goal,
                steps=steps,
                execution_context={"success": success, "error": error_msg},
                category=category
            )
        elif hasattr(core, "experience_system") and core.experience_system:
            if success:
                return core.experience_system.record_task_success(goal=goal, steps=steps, category=category)
            else:
                failed_step = steps[-1] if steps else {"plugin": "system", "action": "execute"}
                return core.experience_system.record_task_failure(
                    goal=goal,
                    failed_step=failed_step,
                    error_msg=error_msg or "Task execution failed",
                    category=category
                )
        return None

    @classmethod
    def retrieve_experience(cls, core: Any, query: str, category: Optional[str] = None) -> Any:
        """Retrieves relevant past experiences, procedures, and preferences from Experience Learning System."""
        if hasattr(core, "experience_system") and core.experience_system:
            return core.experience_system.retrieve_experience(query=query, category=category)
        return None
