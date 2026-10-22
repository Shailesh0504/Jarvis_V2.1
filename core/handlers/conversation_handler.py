# core/handlers/conversation_handler.py
"""
Conversation & Knowledge Handler for Jarvis V2.1.
Handles conversational dialogue, General Knowledge, IT Knowledge, small talk,
greetings, identity, profile statements, and empathetic chat.
"""

import logging
import time
from typing import Any, Optional

from core.state import SystemState

logger = logging.getLogger("jarvis.handlers.conversation")


class ConversationHandler:
    """Manages all conversational exchanges, knowledge queries, and profile interactions."""

    def __init__(self, core: Any):
        self.core = core

    def dispatch_chat(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str = "cli"
    ) -> str:
        """
        Laya Tri-Bridge Route 2: Chat & Reasoning.
        Handles conversational dialogue, General Knowledge, IT Knowledge, and contextual reasoning
        with selective memory retrieval and bounded context scoping.
        """
        core = self.core
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.RESPONDING)
            
        scoped_ctx = {}
        relevant_memories = []
        if laya_decision and hasattr(core, "laya_core") and core.laya_core:
            try:
                scoped_ctx = core.laya_core.get_scoped_context(laya_decision, core, turn)
                relevant_memories = core.laya_core.retrieve_memory_if_needed(laya_decision, getattr(core, "memory_manager", None))
            except Exception as _ctx_err:
                logger.debug("Laya chat context/memory note: %s", _ctx_err)

        chat_resp = None
        # 1. Check Knowledge Engine if applicable
        if laya_decision and getattr(laya_decision, "intent", None) in ("knowledge", "it_knowledge"):
            try:
                from brain.knowledge_engine import get_knowledge_engine
                ke = get_knowledge_engine()
                k_res = ke.answer(turn.normalized_input)
                if k_res and getattr(k_res, "confidence", 0.0) >= 0.60:
                    chat_resp = k_res.answer
            except Exception:
                pass

        # 2. Conversation Engine (Hindi/English/Hinglish contextual dialogue)
        if not chat_resp and hasattr(core, "conversation_engine") and core.conversation_engine:
            try:
                recent_turns = scoped_ctx.get("turns", []) or (
                    core.conversation_manager.session.get_recent_history(limit=5)
                    if hasattr(core, "conversation_manager") and core.conversation_manager and getattr(core.conversation_manager, "session", None)
                    else []
                )
                handled, c_resp, _ = core.conversation_engine.process_conversation_turn(
                    turn.normalized_input,
                    recent_turns
                )
                if handled and c_resp:
                    chat_resp = c_resp
            except Exception:
                pass

        # 3. DualBrain / LLM Fallback
        if not chat_resp and hasattr(core, "brain") and core.brain:
            try:
                recent_history = scoped_ctx.get("turns", []) or (
                    core.conversation_manager.session.get_recent_history(limit=5)
                    if hasattr(core, "conversation_manager") and core.conversation_manager and getattr(core.conversation_manager, "session", None)
                    else []
                )
                chat_resp = core.brain.chat(
                    prompt=turn.normalized_input,
                    history=recent_history,
                    memories=relevant_memories
                )
            except Exception:
                pass

        if not chat_resp:
            chat_resp = "Mujhe samajh aa gaya, Boss."

        chat_resp = core._ensure_response(chat_resp)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        if hasattr(core, "conversation_manager") and core.conversation_manager:
            core.conversation_manager.complete_turn(turn, chat_resp)
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_success(chat_resp, turn.execution_time_ms)
        if getattr(core, "memory_manager", None):
            try:
                core.memory_manager.record_interaction(
                    user_input=turn.raw_input,
                    response=chat_resp,
                    intent="chat",
                    source=source
                )
            except Exception:
                pass
        if getattr(core, "event_bus", None):
            core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": chat_resp, "time_ms": turn.execution_time_ms})
        return chat_resp

    dispatch_chat_route = dispatch_chat
