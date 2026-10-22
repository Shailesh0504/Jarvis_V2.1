"""Response finalization and contextual enhancement for JarvisCore."""

import logging
import time
from typing import Any, Dict, List, Optional
from core.state import SystemState

logger = logging.getLogger("jarvis.response")


class ResponseFinalizer:
    """Handles response guarantees, spell acknowledgment consumption, and turn finalization."""

    @staticmethod
    def ensure_response(response: Any) -> str:
        """Guarantees that every accepted command produces visible/spoken feedback."""
        if response is None or not str(response).strip():
            return "Command process nahi ho paya, Boss. Please dobara try kijiye."
        return str(response).strip()

    @staticmethod
    def consume_spell_ack(resp: str, core: Any) -> str:
        """
        If a silent spelling correction was applied this turn, prepend or return the spoken
        acknowledgement ("Ji, Microsoft Excel khol raha hoon.") to the pipeline response.
        Clears _last_spell_ack after consuming it so it never bleeds to the next turn.
        """
        ack = getattr(core, "_last_spell_ack", None)
        setattr(core, "_last_spell_ack", None)
        if ack:
            # If the underlying execution succeeded or confirms the action, let the natural ack be the response
            if not resp or any(phrase in resp.lower() for phrase in ["open ho gaya", "open kar raha hoon", "khol raha hoon", "launched", "chalu ho gaya"]):
                return ack
            if ack not in resp:
                return f"{ack} {resp}"
        return resp

    @classmethod
    def finalize_fast_turn(
        cls,
        core: Any,
        turn: Any,
        resp: str,
        start_time: float,
        tracker: Any,
        intent_name: str,
        source: str
    ) -> str:
        """Finalizes a sub-15ms fast-path turn."""
        resp = cls.ensure_response(resp)
        resp = cls.consume_spell_ack(resp, core)
        if hasattr(core, "state_machine") and core.state_machine:
            core.state_machine.transition_to(SystemState.RESPONDING)
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        if hasattr(core, "conversation_manager") and core.conversation_manager:
            core.conversation_manager.complete_turn(turn, resp)
        if hasattr(core, "state_machine") and core.state_machine:
            core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_success(resp, turn.execution_time_ms)
        if tracker:
            tracker.mark_first_response()
            tracker.log_breakdown(extra_info=f"FastPath={intent_name}")
        if getattr(core, "memory_manager", None):
            try:
                core.memory_manager.record_interaction(turn.raw_input, resp, intent=f"fast_{intent_name}", source=source)
            except Exception:
                pass
        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp})
        return resp

    @classmethod
    def attach_contextual_suggestion(
        cls, core: Any, raw_input: str, response: str, source: str = "cli"
    ) -> str:
        """
        Evaluates turn context, user question, goal, and capability availability.
        If a relevant, high-scoring next-step suggestion is permitted, appends it
        and registers pending follow-up in DialogManager.
        """
        if not hasattr(core, "suggestion_manager") or not core.suggestion_manager:
            return response
        if not response or not isinstance(response, str):
            return response

        # If there is already an active dialog lock / system confirmation / learning approval, skip
        if hasattr(core, "dialog_manager") and core.dialog_manager:
            if (
                core.dialog_manager.has_pending_system_action()
                or core.dialog_manager.has_active_lock()
                or core.dialog_manager.has_pending_proposal()
                or core.dialog_manager.has_pending_learning()
                or getattr(core.dialog_manager, "pending_spelling", None)
            ):
                return response

        ctx = getattr(core, "active_context", None)
        try:
            sug = core.suggestion_manager.evaluate_conversational_suggestion(
                user_input=raw_input,
                answer=response,
                source=source,
                active_context=ctx,
            )
            if sug and getattr(sug, "decision", "") == "SUGGEST" and getattr(sug, "text", ""):
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_contextual_suggestion(sug)
                if sug.text not in response:
                    return f"{response}\n\n{sug.text}"
        except Exception as e:
            logger.debug("Error in attach_contextual_suggestion: %s", e)
        return response

    @classmethod
    def finalize_standard_turn(
        cls,
        core: Any,
        turn: Any,
        final_response: str,
        start_time: float,
        route_cat: str,
        primary_intent: Any,
        execution_results: Any,
        action_success: bool
    ) -> str:
        """Finalizes a standard execution turn with suggestions, workflow proposals, and logging."""
        final_response = cls.ensure_response(final_response)

        # Habitual Proactive Suggestion
        learning_mgr = getattr(core, "learning_manager", None)
        if learning_mgr and route_cat != "LEARNING":
            try:
                proactive_sug = learning_mgr.get_proactive_suggestion(turn.normalized_input)
                if proactive_sug and proactive_sug not in final_response:
                    final_response += f"\n\n💡 *[Suggestion]*: {proactive_sug}"
            except Exception as e:
                logger.debug("Proactive suggestion error: %s", e)

        # Record Turn Feedback
        if hasattr(core, "_record_turn_feedback"):
            core._record_turn_feedback(
                turn=turn,
                goal=turn.normalized_input,
                steps=[{"plugin": getattr(primary_intent, "target_plugin", None) or "system", "action": getattr(primary_intent, "target_action", None) or "execute"}],
                execution_results=execution_results,
                success=action_success,
                category=getattr(primary_intent, "category", "general"),
                intent_name=getattr(primary_intent, "name", "general")
            )

        # Check for newly discovered proactive workflow proposals
        if learning_mgr and hasattr(core, "dialog_manager") and core.dialog_manager:
            try:
                prop = learning_mgr.check_for_workflow_proposal()
                if prop:
                    core.dialog_manager.set_proposal(prop)
                    final_response = f"{final_response}\n\n💡 {prop.prompt_text}"
            except Exception as e:
                logger.error("Error checking workflow proposal: %s", e)

        # Finalize turn
        turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
        if hasattr(core, "conversation_manager") and core.conversation_manager:
            core.conversation_manager.complete_turn(turn, final_response)
        if hasattr(core, "state_machine") and core.state_machine:
            core.state_machine.transition_to(SystemState.IDLE)
        if hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_success(final_response, turn.execution_time_ms)
        if getattr(core, "memory_manager", None) and hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_memory("Recorded turn in SQLite episodic memory")

        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit(
                "response.completed",
                {"turn_id": turn.turn_id, "response": final_response, "time_ms": turn.execution_time_ms}
            )

        return final_response
