# core/handlers/agent_handler.py
"""
Autonomous Agent Handler for Jarvis V2.1.
Handles:
- Laya Tri-Bridge Route 3: Autonomous Agent Planner
- Multi-step goal decomposition
- Task continuity workflow activation
- Execution trace recording into episodic memory
"""

import logging
import time
from typing import Any

from core.state import SystemState

logger = logging.getLogger("jarvis.handlers.agent")


class AgentHandler:
    """Manages autonomous agent goal execution and long-horizon task workflows."""

    def __init__(self, core: Any):
        self.core = core

    def dispatch_agent_route(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str = "cli"
    ) -> str:
        """
        Laya Tri-Bridge Route 3: Autonomous Agent Planner.
        Deconstructs complex goals into task graphs and multi-step executions.
        """
        core = self.core
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.PLANNING)

        final_response = ""
        trace_data = []
        if getattr(core, "agent", None):
            agent_summary = core.agent.execute_goal(turn.normalized_input)
            final_response = getattr(agent_summary, "final_answer", "") or "Goal execution completed."
            trace_data = [
                {"success": s.success, "data": getattr(s, "observation", None), "error": getattr(s, "error", None)}
                for s in getattr(agent_summary, "trace", [])
            ]
        elif getattr(core, "task_engine", None):
            succ, msg, _ = core.task_engine.start_workflow(goal=turn.normalized_input, steps=[])
            final_response = msg
        else:
            final_response = "Agent Planner is not currently available for autonomous execution."

        final_response = core._ensure_response(final_response)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        if hasattr(core, "conversation_manager") and core.conversation_manager:
            core.conversation_manager.complete_turn(turn, final_response)
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.IDLE)
        if getattr(core, "memory_manager", None):
            try:
                core.memory_manager.record_interaction(
                    user_input=turn.raw_input,
                    response=final_response,
                    intent="agent_goal",
                    source=source,
                    execution_results=trace_data
                )
            except Exception:
                pass
        if hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_success(final_response, turn.execution_time_ms)
        if getattr(core, "event_bus", None):
            core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": final_response, "time_ms": turn.execution_time_ms})
        return final_response
