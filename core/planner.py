# core/planner.py
"""Task planner for decomposing user intents into executable action graphs."""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from .intent import Intent, IntentType
from .permissions import PermissionLevel

logger = logging.getLogger("jarvis.planner")


class PlanStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class PlanStep:
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    plugin_name: str = ""
    action_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    required_permission: PermissionLevel = PermissionLevel.READ
    description: str = ""
    depends_on: List[str] = field(default_factory=list)  # list of step_ids
    critical: bool = True  # If True, failure stops the whole plan


@dataclass
class ExecutionPlan:
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    user_query: str = ""
    intent: Optional[Intent] = None
    steps: List[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0


class TaskPlanner:
    """Plans single-step and multi-step execution graphs from Intent."""

    def __init__(self, permission_guard: Optional[Any] = None):
        self.permission_guard = permission_guard

    def create_single_step_plan(
        self,
        intent: Intent,
        plugin_name: str,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        permission_level: PermissionLevel = PermissionLevel.EXECUTE,
        description: str = ""
    ) -> ExecutionPlan:
        step = PlanStep(
            plugin_name=plugin_name,
            action_name=action_name,
            parameters=parameters or intent.entities,
            required_permission=permission_level,
            description=description or f"Execute {plugin_name}.{action_name}"
        )
        return ExecutionPlan(
            title=f"Execute {action_name}",
            user_query=intent.raw_query,
            intent=intent,
            steps=[step]
        )

    def create_plan_from_intent(self, intent: Intent) -> ExecutionPlan:
        """Derives an execution plan from a classified intent."""
        if intent.target_plugin and intent.target_action:
            return self.create_single_step_plan(
                intent=intent,
                plugin_name=intent.target_plugin,
                action_name=intent.target_action,
                parameters=intent.entities,
                description=f"Action requested: {intent.name}"
            )

        # Non-plugin intents (like pure chat, memory queries, etc.)
        return ExecutionPlan(
            title="Non-plugin task",
            user_query=intent.raw_query,
            intent=intent,
            steps=[]
        )

    def create_multi_step_plan(
        self,
        title: str,
        user_query: str,
        steps: List[PlanStep],
        intent: Optional[Intent] = None
    ) -> ExecutionPlan:
        return ExecutionPlan(
            title=title,
            user_query=user_query,
            intent=intent,
            steps=steps
        )
