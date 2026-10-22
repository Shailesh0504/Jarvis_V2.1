# core/task_engine/experience.py
"""
Experience Learning and Procedural Recall for the Task Continuity Engine.
Stores reusable procedures, proven strategies, and failure modes from previous tasks.
Evaluates historical patterns against the active environment before reusing them.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .models import TaskState, TaskStep
from .persistence import TaskPersistenceManager

logger = logging.getLogger("jarvis.task_engine.experience")


class ExperienceLearner:
    """Manages experience learning, storage, retrieval, and contextual applicability validation."""

    def __init__(self, persistence_manager: TaskPersistenceManager, plugin_manager: Optional[Any] = None):
        self.persistence = persistence_manager
        self.plugin_manager = plugin_manager

    def record_completed_workflow(self, task: TaskState) -> None:
        """Records a successful workflow experience with strategies used."""
        strategies = []
        for s in task.completed_steps:
            if s.strategy_used and s.strategy_used != "primary":
                strategies.append(s.strategy_used)

        self.persistence.record_experience(
            goal=task.goal,
            plan=task.plan,
            success=True,
            strategies=list(set(strategies)),
            failure_modes=task.failed_steps
        )
        logger.info("ExperienceLearner: Learned successful procedure for goal '%s' (%d steps)",
                    task.goal, len(task.plan))

    def record_failed_workflow(self, task: TaskState) -> None:
        """Records failure modes to prevent repeating identical dead-end paths."""
        self.persistence.record_experience(
            goal=task.goal,
            plan=task.plan,
            success=False,
            failure_modes=task.failed_steps
        )
        logger.info("ExperienceLearner: Recorded failure patterns for goal '%s'", task.goal)

    def validate_environmental_applicability(
        self,
        experience: Dict[str, Any],
        current_environment: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Validates that a historical procedure is executable in current environment."""
        if not experience:
            return False
        env = current_environment or {}
        avail_plugins = env.get("available_plugins")
        for step_dict in experience.get("procedure", []):
            plugin = step_dict.get("plugin_name")
            if not plugin:
                continue
            if avail_plugins is not None:
                if plugin not in avail_plugins:
                    return False
            elif self.plugin_manager:
                if not self.plugin_manager.get_plugin(plugin):
                    return False
        return True

    def retrieve_applicable_experience(
        self,
        goal: str,
        current_environment: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves relevant experience and validates that it applies to the current environment.
        Does NOT blindly return historical plans if required plugins or targets are missing.
        """
        matches = self.persistence.retrieve_experience(goal, limit=3)
        if not matches:
            return None

        for match in matches:
            if match.get("success_rate", 0) < 0.5:
                continue

            if self.validate_environmental_applicability(match, current_environment=current_environment):
                logger.info("ExperienceLearner: Found valid applicable experience for goal '%s' (success rate: %.2f)",
                            goal, match.get("success_rate", 1.0))
                return match

        return None
