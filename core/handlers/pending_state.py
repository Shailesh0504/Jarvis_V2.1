# core/handlers/pending_state.py
"""
Pending State Handler for Jarvis V2.1.
Evaluates active locks and pending confirmations before generic intent routing:
- Destructive/Sensitive action confirmations (ConfirmationManager)
- Multi-turn workflow lock (DialogManager active lock)
- Multi-turn container and slot followups
- Learning approvals & spelling confirmations
- Proactive proposals
"""

import logging
import time
from typing import Any, Optional, Tuple

from core.state import SystemState

logger = logging.getLogger("jarvis.handlers.pending")


class PendingStateHandler:
    """Orchestrates all active dialogue locks, confirmations, and follow-up states."""

    def __init__(self, core: Any):
        self.core = core

    def check_pre_routing_pending(self, turn: Any, raw_input: str, start_time: float, source: str = "cli") -> Tuple[bool, Optional[str]]:
        """
        Evaluates early multi-turn dialog context and active confirmations.
        Returns:
            (handled, response)
        """
        core = self.core

        # 1. Step 2.ConversationalState: Pre-Routing Turn N+1 Answer
        if hasattr(core, "dialog_manager") and core.dialog_manager and (
            core.dialog_manager.awaits_user_followup()
            or core.dialog_manager.is_container_followup(turn.normalized_input, core)
        ):
            handled_turn, turn_resp = core.dialog_manager.interpret_turn_n_plus_1(
                turn.normalized_input, core, raw_input=raw_input
            )
            if handled_turn:
                turn_resp = core._ensure_response(turn_resp)
                core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                core.conversation_manager.complete_turn(turn, turn_resp)
                core.state_machine.transition_to(SystemState.IDLE)
                core.action_logger.log_success(turn_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, turn_resp, intent="multi_turn_slot_answer", source=source
                    )
                if getattr(core, "event_bus", None):
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": turn_resp})
                return True, turn_resp

        # 2. Step 2.Pending: Confirmation State Machine Check
        conf_mgr = getattr(core, "confirmation_manager", None) or getattr(getattr(core, "dialog_manager", None), "confirmation_manager", None)
        if conf_mgr and conf_mgr.has_pending_confirmation():
            handled_conf, conf_resp = conf_mgr.handle_confirmation(turn.normalized_input, core)
            if handled_conf:
                conf_resp = core._ensure_response(conf_resp)
                core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                core.conversation_manager.complete_turn(turn, conf_resp)
                core.state_machine.transition_to(SystemState.IDLE)
                core.action_logger.log_success(conf_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, conf_resp, intent="destructive_action_confirmation", source=source)
                return True, conf_resp

        # 3. Step 2.WorkflowLock: Multi-turn Active Workflow Lock (Rule 15)
        if hasattr(core, "dialog_manager") and core.dialog_manager and core.dialog_manager.has_active_lock():
            handled_by_lock, lock_resp = core.dialog_manager.process_locked_turn(turn.normalized_input, core)
            if handled_by_lock:
                lock_resp = core._ensure_response(lock_resp)
                core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                core.conversation_manager.complete_turn(turn, lock_resp)
                core.state_machine.transition_to(SystemState.IDLE)
                core.action_logger.log_success(lock_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, lock_resp, intent="workflow_lock_slot", source=source)
                if getattr(core, "event_bus", None):
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": lock_resp})
                return True, lock_resp

        return False, None
