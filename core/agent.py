"""Autonomous Agent Execution Engine for Jarvis.
=================================================
Backward-compatible facade bridging legacy AutonomousAgent invocations to
the enhanced AgentOrchestrator architecture in `core.agent`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.event_bus import EventBus
from core.executor import PlanExecutor
from core.permissions import PermissionGuard
from brain.agent import AgentReasoner

# Re-export data models from core.agent for seamless backward compatibility
from core.agent.task_manager import AgentStepRecord, AgentExecutionSummary
from core.agent.orchestrator import AgentOrchestrator
from core.agent.agent_policy import AgentPolicy

logger = logging.getLogger("jarvis.core.agent")


class AutonomousAgent:
    """Executes high-level user goals through autonomous agent orchestration."""

    def __init__(
        self,
        reasoner: AgentReasoner,
        plugin_manager: Any,
        permission_guard: Optional[PermissionGuard] = None,
        event_bus: Optional[EventBus] = None,
        max_steps: int = 8,
        memory_manager: Optional[Any] = None,
        approval_callback: Optional[Any] = None,
        status_callback: Optional[Any] = None,
    ):
        self.reasoner = reasoner
        self.plugin_manager = plugin_manager
        self.permission_guard = permission_guard or PermissionGuard()
        self.event_bus = event_bus
        self.max_steps = max_steps
        self.memory_manager = memory_manager
        self.approval_callback = approval_callback
        self.status_callback = status_callback
        self.executor = PlanExecutor(
            plugin_manager=self.plugin_manager,
            permission_guard=self.permission_guard,
            event_bus=self.event_bus,
        )

        policy = AgentPolicy(max_total_steps=max_steps)
        self.orchestrator = AgentOrchestrator(
            policy=policy,
            event_bus=self.event_bus,
            reasoner=self.reasoner,
            memory_manager=self.memory_manager,
            approval_callback=self.approval_callback,
            status_callback=self.status_callback,
        )

    def execute_goal(self, goal: str) -> AgentExecutionSummary:
        """Executes a goal using the AgentOrchestrator pipeline."""
        logger.info("AutonomousAgent delegating goal: '%s'", goal)
        return self.orchestrator.execute_goal(goal)

    def _resolve_parameters(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Substitutes dynamic parameter expressions from context."""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("$"):
                var_name = v[1:]
                resolved[k] = context.get(var_name, None)
            else:
                resolved[k] = v
        return resolved


__all__ = ["AgentExecutionSummary", "AgentStepRecord", "AutonomousAgent"]
