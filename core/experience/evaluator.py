# core/experience/evaluator.py
"""
Outcome Evaluator for the Experience Learning System.
Analyzes task execution results, filters out transient trivia,
and distills genuinely reusable procedural recipes, semantic facts,
and failure anti-patterns for long-term retention.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import ExperienceItem, MemoryType

logger = logging.getLogger("jarvis.experience.evaluator")


class OutcomeEvaluator:
    """Evaluates executed tasks and tool traces to extract reusable lessons."""

    def evaluate_successful_task(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        execution_context: Optional[Dict[str, Any]] = None,
        category: str = "general",
        source: str = "execution"
    ) -> Optional[ExperienceItem]:
        """
        Evaluates a successful workflow.
        Returns a procedural ExperienceItem if the workflow has reusable value.
        """
        if not steps or len(steps) == 0:
            return None

        # Clean and parameterize steps for future generalization
        parameterized_steps = []
        for s in steps:
            p_name = s.get("plugin") or s.get("plugin_name", "")
            a_name = s.get("action") or s.get("action_name", "")
            raw_params = dict(s.get("parameters", {}))

            # Generalize specific instance values to context variables
            generalized_params = self._generalize_parameters(raw_params)

            step_entry = {
                "plugin": p_name,
                "action": a_name,
                "parameters": generalized_params,
                "description": s.get("description") or s.get("name", f"{p_name}.{a_name}"),
            }
            if s.get("strategy_used") and s.get("strategy_used") != "primary":
                step_entry["strategy_used"] = s["strategy_used"]

            parameterized_steps.append(step_entry)

        content = {
            "goal": goal,
            "steps": parameterized_steps,
            "step_count": len(parameterized_steps),
            "execution_context_keys": list((execution_context or {}).keys())
        }

        # Infer domain category from plugin names if default
        if category == "general" and parameterized_steps:
            category = parameterized_steps[0]["plugin"] or "general"

        item = ExperienceItem(
            memory_type=MemoryType.PROCEDURAL,
            category=category,
            query_pattern=goal.strip().lower(),
            content=content,
            confidence=0.90,
            success_count=1,
            source=source,
            task_metadata={"parameterized": True}
        )
        return item

    def evaluate_failed_task(
        self,
        goal: str,
        failed_step: Dict[str, Any],
        error_msg: str,
        attempted_strategy: str = "primary",
        category: str = "general",
        diagnosis: Optional[str] = None
    ) -> Optional[ExperienceItem]:
        """
        Evaluates a failed task step and distills a failure memory with avoidance advice.
        """
        if not error_msg:
            return None

        p_name = failed_step.get("plugin") or failed_step.get("plugin_name", "system")
        a_name = failed_step.get("action") or failed_step.get("action_name", "execute")

        content = {
            "goal": goal,
            "failed_action": f"{p_name}.{a_name}",
            "error": error_msg[:500],
            "root_cause": diagnosis or "execution_failure",
            "attempted_strategy": attempted_strategy,
            "parameters": dict(failed_step.get("parameters", {})),
            "avoidance_strategy": self._suggest_avoidance_strategy(p_name, a_name, error_msg, diagnosis)
        }

        if category == "general" and p_name:
            category = p_name

        item = ExperienceItem(
            memory_type=MemoryType.FAILURE,
            category=category,
            query_pattern=goal.strip().lower(),
            content=content,
            confidence=0.85,
            success_count=0,
            failure_count=1,
            source="execution_failure",
            task_metadata={"failed_action": f"{p_name}.{a_name}"}
        )
        return item

    def _generalize_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Abstracts hardcoded session-specific constants into reusable parameters.
        """
        generalized = {}
        for k, v in params.items():
            if isinstance(v, str):
                # Replace absolute temporary directories with variable placeholder
                if "Temp" in v or "tmp" in v:
                    generalized[k] = "$temp_dir"
                else:
                    generalized[k] = v
            else:
                generalized[k] = v
        return generalized

    def _suggest_avoidance_strategy(
        self,
        plugin: str,
        action: str,
        error_msg: str,
        diagnosis: Optional[str]
    ) -> str:
        """Generates pragmatic avoidance rule based on failure characteristics."""
        err_lower = (error_msg or "").lower()
        if "not found" in err_lower or "no such file" in err_lower:
            return "Verify file exists or search active directory before executing action"
        if "focus" in err_lower or "foreground" in err_lower:
            return "Force window focus and add 0.5s stabilization wait before input"
        if "timeout" in err_lower:
            return "Increase timeout threshold or verify application responsiveness"
        if "permission" in err_lower:
            return "Check user permissions or request elevated credentials"
        return f"Do not repeat exact parameters for '{plugin}.{action}'; use alternative fallback"
