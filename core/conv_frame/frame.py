# core/conv_frame/frame.py
"""
ConversationFrame Bridge & Decision Contract for JARVIS V2.

Provides two things:
  1. FrameDecisionType  — canonical enum of pipeline decision outcomes.
  2. ConversationFrameBridge — static enrichment methods that populate
     HumanConversationFrame fields from the outputs of existing subsystems.

Design invariants:
  - Frame is produced ONCE per turn by HumanConversationModel.analyze_turn().
  - Each subsystem ENRICHES the same frame object; it does not create a new one.
  - This module never creates its own intent/context/reference logic.
    It only BRIDGES outputs from existing authoritative components into the frame.
  - Circular import safe: imports HumanConversationFrame lazily inside methods.

Layer boundary:
  HumanConversationFrame lives in brain/ (model layer).
  This bridge lives in core/conversation/ (service/adapter layer).
  core/app.py calls this bridge after each subsystem produces output.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional

logger = logging.getLogger("jarvis.core.conversation.frame")

if TYPE_CHECKING:
    # Only for type hints — not imported at runtime to avoid circular imports.
    from brain.conversation.model import HumanConversationFrame


class FrameDecisionType(str, Enum):
    """
    Canonical decision type for the unified JARVIS pipeline.
    Written to HumanConversationFrame.decision_type by derive_decision().

    Maps to routing in core/app.py _process_input:
      EXECUTE_FAST   -> _try_fast_command_path / DecisionCore.plan_action
      EXECUTE_AGENT  -> AgentOrchestrator.execute_goal
      ANSWER         -> response_engine / knowledge engine
      CONVERSE       -> ConversationEngine / response_engine
      CLARIFY        -> ask user for missing info
      MEMORY_UPDATE  -> memory manager write
      WAIT           -> pending slot fill; do not execute yet
      CANCEL         -> user cancelled pending operation
      REJECT         -> explicitly rejected by policy / negation
      NO_ACTION      -> no action needed (ack, filler, etc.)
    """
    EXECUTE_FAST   = "EXECUTE_FAST"
    EXECUTE_AGENT  = "EXECUTE_AGENT"
    ANSWER         = "ANSWER"
    CONVERSE       = "CONVERSE"
    CLARIFY        = "CLARIFY"
    MEMORY_UPDATE  = "MEMORY_UPDATE"
    WAIT           = "WAIT"
    CANCEL         = "CANCEL"
    REJECT         = "REJECT"
    NO_ACTION      = "NO_ACTION"


class ConversationFrameBridge:
    """
    Static enrichment methods that populate HumanConversationFrame fields
    from the outputs of existing JARVIS subsystems.

    USAGE IN core/app.py _process_input:
      1. frame = human_conversation_model.analyze_turn(...)          # produces frame
      2. ConversationFrameBridge.enrich_from_speech_result(frame, speech_result)
      3. ConversationFrameBridge.enrich_from_dialogue_act(frame, da_res)
      4. ConversationFrameBridge.enrich_from_reference(frame, resolved_ref)
      5. ConversationFrameBridge.enrich_from_context(frame, ...)
      6. decision = ConversationFrameBridge.derive_decision(frame)   # sets frame.decision_type
    """

    # ── Speech Understanding enrichment ────────────────────────────────────────

    @staticmethod
    def enrich_from_speech_result(
        frame: "HumanConversationFrame",
        speech_result: Any
    ) -> None:
        """
        Writes SpeechUnderstandingEngine output into the frame.
        Populates: input_quality, interpretation_status, recovery_status.
        Owner: Speech layer.
        """
        if frame is None or speech_result is None:
            return
        try:
            iq = speech_result.input_quality
            frame.input_quality = iq.value if hasattr(iq, "value") else str(iq)
        except Exception:
            pass

        try:
            if speech_result.recovered_interpretation:
                frame.interpretation_status = "RECOVERED"
                frame.recovery_status = str(speech_result.context_used or "context_repair")
            elif frame.input_quality in ("ambiguous",):
                frame.interpretation_status = "AMBIGUOUS"
        except Exception:
            pass

        logger.debug(
            "[FrameBridge] enrich_from_speech_result: input_quality=%s status=%s",
            frame.input_quality, frame.interpretation_status
        )

    # ── Dialogue Act enrichment ────────────────────────────────────────────────

    @staticmethod
    def enrich_from_dialogue_act(
        frame: "HumanConversationFrame",
        da_res: Any
    ) -> None:
        """
        Syncs DialogueActResult into the frame.
        Populates/confirms: dialogue_act.
        Owner: Dialogue layer.
        Note: dialogue_act is already set by HumanConversationModel; this method
              is a confirmation sync to ensure consistency when the pipeline calls
              DialogueActClassifier again after the frame is produced.
        """
        if frame is None or da_res is None:
            return
        try:
            da = da_res.act
            frame.dialogue_act = da
        except Exception:
            pass

        logger.debug(
            "[FrameBridge] enrich_from_dialogue_act: dialogue_act=%s",
            getattr(da_res, "act", None)
        )

    # ── Reference Resolution enrichment ───────────────────────────────────────

    @staticmethod
    def enrich_from_reference(
        frame: "HumanConversationFrame",
        resolved_ref: Any
    ) -> None:
        """
        Writes ReferenceResolver output into the frame.
        Populates: resolved_reference, reference_confidence, reference_source, resolver_used.
        Owner: Reference layer.
        """
        if frame is None or resolved_ref is None:
            return
        try:
            if resolved_ref.resolved:
                frame.resolved_reference = resolved_ref.target_name or ""
                frame.reference_confidence = resolved_ref.confidence
                frame.reference_source = resolved_ref.target_type.value if hasattr(
                    resolved_ref.target_type, "value"
                ) else str(resolved_ref.target_type)
                frame.resolver_used = "ReferenceResolver"
                # If the frame target is empty, populate from resolved reference
                if not frame.target and frame.resolved_reference:
                    frame.target = frame.resolved_reference
        except Exception as exc:
            logger.debug("[FrameBridge] enrich_from_reference error: %s", exc)

        logger.debug(
            "[FrameBridge] enrich_from_reference: resolved=%s conf=%.2f",
            frame.resolved_reference, frame.reference_confidence
        )

    # ── Context enrichment ─────────────────────────────────────────────────────

    @staticmethod
    def enrich_from_context(
        frame: "HumanConversationFrame",
        active_context: Optional[Any] = None,
        conversation_state: Optional[Any] = None,
        topic_tracker: Optional[Any] = None,
        dialog_manager: Optional[Any] = None,
    ) -> None:
        """
        Writes runtime context into the frame.
        Populates: active_workflow, active_goal, pending_question, pending_goal,
                   missing_slot, slot_values, confirmation_state, cancellation_state.
        Owner: Context layer.
        """
        if frame is None:
            return

        # Active workflow from ConversationState
        if conversation_state:
            try:
                mode = conversation_state.conversation_mode
                mode_val = mode.value if hasattr(mode, "value") else str(mode)
                if mode_val == "WORKFLOW":
                    frame.active_workflow = conversation_state.active_topic or ""
            except Exception:
                pass

        # Topic from topic tracker
        if topic_tracker:
            try:
                frame.topic = topic_tracker.get_active_topic() or frame.topic
            except Exception:
                pass

        # Slot and pending state from dialog manager
        if dialog_manager:
            try:
                if hasattr(dialog_manager, "awaits_user_followup") and dialog_manager.awaits_user_followup():
                    pending = getattr(dialog_manager, "pending_question", None)
                    if pending:
                        frame.pending_question = str(pending)
                    pending_goal = getattr(dialog_manager, "pending_goal", None)
                    if pending_goal:
                        frame.pending_goal = str(pending_goal)
                    missing = getattr(dialog_manager, "missing_slot", None)
                    if missing:
                        frame.missing_slot = str(missing)
                    slots = getattr(dialog_manager, "slot_values", None)
                    if slots and isinstance(slots, dict):
                        frame.slot_values = dict(slots)
            except Exception:
                pass

            try:
                if hasattr(dialog_manager, "confirmation_manager"):
                    cm = dialog_manager.confirmation_manager
                    if cm and hasattr(cm, "has_pending_confirmation") and cm.has_pending_confirmation():
                        frame.confirmation_state = "PENDING"
            except Exception:
                pass

        logger.debug(
            "[FrameBridge] enrich_from_context: workflow=%r pending_q=%r",
            frame.active_workflow, frame.pending_question
        )

    # ── Decision derivation ────────────────────────────────────────────────────

    @staticmethod
    def derive_decision(frame: "HumanConversationFrame") -> str:
        """
        Maps the enriched ConversationFrame state to a canonical FrameDecisionType.
        Writes: frame.decision_type, frame.execution_allowed, frame.agent_required,
                frame.clarification_required, frame.decision_reason.

        Priority order (highest first):
          1. Cancellation
          2. Explicit negation → REJECT
          3. Pragmatic ambiguity → CLARIFY
          4. Low confidence → CLARIFY
          5. Ambiguous / missing slot → CLARIFY / WAIT
          6. Capability question / status question → ANSWER
          7. Conversational / small-talk → CONVERSE
          8. Multi-step / complex → EXECUTE_AGENT
          9. Simple executable command → EXECUTE_FAST
          10. Information question → ANSWER
          11. Fallback → CONVERSE
        """
        if frame is None:
            return FrameDecisionType.NO_ACTION.value

        dt = FrameDecisionType.CONVERSE  # safe fallback

        # 1. Cancellation
        if frame.cancellation_state or getattr(frame, "intention", None) and \
                str(getattr(frame, "intention", "")).find("CANCELLATION") != -1:
            dt = FrameDecisionType.CANCEL
            frame.execution_allowed = False
            frame.decision_reason = "User cancelled pending operation."

        # 2. Explicit negation
        elif frame.is_negated:
            dt = FrameDecisionType.REJECT
            frame.execution_allowed = False
            frame.decision_reason = f"Negated action: {frame.negated_action or 'action'} on '{frame.target}'."

        # 3. Pragmatic ambiguity (implicit intent)
        elif frame.pragmatic_goal and not frame.is_executable_command:
            dt = FrameDecisionType.CLARIFY
            frame.clarification_required = True
            frame.execution_allowed = False
            frame.decision_reason = f"Pragmatic subtext detected: {frame.pragmatic_goal}. Clarification needed."

        # 4. Low confidence
        elif frame.confidence and frame.confidence.composite < 0.60:
            dt = FrameDecisionType.CLARIFY
            frame.clarification_required = True
            frame.execution_allowed = False
            frame.interpretation_status = "LOW_CONFIDENCE"
            frame.decision_reason = f"Low confidence ({frame.confidence.composite:.2f}). Clarifying."

        # 5. Ambiguous or missing slot (but executable intent known)
        elif frame.interpretation_status == "AMBIGUOUS" or frame.missing_slot:
            dt = FrameDecisionType.CLARIFY
            frame.clarification_required = True
            frame.execution_allowed = False
            frame.decision_reason = frame.ambiguity_reason or f"Missing slot: {frame.missing_slot}."

        # 6. Pending question answer (slot fill)
        elif frame.pending_question and frame.previous_turn_relation in ("ANSWER", "CONTINUATION"):
            dt = FrameDecisionType.WAIT
            frame.execution_allowed = False
            frame.decision_reason = "Turn is a slot-fill answer to pending question."

        # 7. Capability / status / troubleshooting / information question
        elif str(getattr(frame, "intention", "")).upper() in (
            "CAPABILITY_QUESTION", "STATUS_QUESTION", "STATUS_AFTER_ACTION",
            "INFORMATION_QUESTION", "TROUBLESHOOTING", "SYSTEM_INFORMATION",
        ):
            dt = FrameDecisionType.ANSWER
            frame.execution_allowed = False
            frame.decision_reason = "Non-executable speech act: question or information request."

        # 8. Small talk / greeting / casual
        elif str(getattr(frame, "intention", "")).upper() in (
            "GREETING", "CONVERSATION", "SMALL_TALK", "EXPRESSED_DESIRE",
            "STATEMENT", "GENERAL_CONVERSATION",
        ):
            dt = FrameDecisionType.CONVERSE
            frame.execution_allowed = False
            frame.decision_reason = "Conversational / social exchange."

        # 9. Executable command — determine fast vs agent
        elif frame.is_executable_command:
            # Agent path if the communicative goal implies multi-step complexity
            is_multi_step = (
                "AND" in (frame.communicative_goal or "").upper()
                or len(frame.modifiers) > 2
                or bool(frame.active_goal)
            )
            if is_multi_step:
                dt = FrameDecisionType.EXECUTE_AGENT
                frame.agent_required = True
                frame.execution_allowed = True
                frame.decision_reason = "Multi-step goal detected; routing to AgentOrchestrator."
            else:
                dt = FrameDecisionType.EXECUTE_FAST
                frame.execution_allowed = True
                frame.agent_required = False
                frame.decision_reason = "Single deterministic command; routing to FastPath."

        # 10. Information request
        elif str(getattr(frame, "intention", "")).upper() in ("INFORMATION_REQUEST", "QUESTION"):
            dt = FrameDecisionType.ANSWER
            frame.execution_allowed = False
            frame.decision_reason = "Information or knowledge query."

        # 11. Fallback: converse
        else:
            dt = FrameDecisionType.CONVERSE
            frame.execution_allowed = False
            frame.decision_reason = "No specific decision matched; defaulting to conversation."

        frame.decision_type = dt.value
        logger.debug(
            "[FrameBridge] derive_decision: decision_type=%s execution_allowed=%s agent=%s reason=%r",
            frame.decision_type, frame.execution_allowed, frame.agent_required, frame.decision_reason
        )
        return frame.decision_type

    # ── Action parameter extraction ────────────────────────────────────────────

    @staticmethod
    def to_action_params(frame: "HumanConversationFrame") -> Dict[str, Any]:
        """
        Extracts the relevant action parameters from the frame for DecisionCore.plan_action().
        Avoids duplicate parameter extraction scattered across _process_input.
        """
        if frame is None:
            return {}
        return {
            "action": frame.action or "execute",
            "target": frame.target or frame.resolved_reference or "",
            "target_type": frame.target_type or frame.entity or "general",
            "confidence": frame.confidence.composite if frame.confidence else frame.certainty,
            "communicative_goal": frame.communicative_goal,
            "negated": frame.is_negated,
            "negation_scope": frame.negation_scope,
            "exclusions": frame.exclusions,
            "constraints": frame.constraints,
            "quantity": frame.quantity,
            "time_context": frame.time_context,
        }
