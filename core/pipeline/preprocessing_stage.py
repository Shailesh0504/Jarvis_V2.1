# core/pipeline/preprocessing_stage.py
"""
Preprocessing Stage for Jarvis V2.1 Pipeline.
Handles:
- ASR speech repair
- TurnContext creation and registration
- LCE vocabulary correction
- Spelling resolution and clarification
"""

import logging
from typing import Any, Optional, Tuple

from core.event_bus import UserInputReceived
from core.state import SystemState

logger = logging.getLogger("jarvis.pipeline.preprocessing")


class PreprocessingStage:
    """Preprocesses input text, creates turn context, and resolves vocabulary/spelling."""

    def __init__(self, core: Any):
        self.core = core

    def repair_and_create_turn(self, raw_input: str, effective_input: str, source: str = "cli") -> Tuple[Any, str]:
        """
        Runs speech repair and creates initialized TurnContext.
        """
        core = self.core
        # 1. Speech repair engine
        from core.speech_repair import get_speech_repair_engine
        repair_engine = get_speech_repair_engine()
        repair_res = repair_engine.repair_transcript(
            effective_input,
            context=getattr(core, "active_context", None)
        )
        repaired_text = repair_res.final_text if repair_res.repaired else effective_input

        # 2. Transition state and create turn
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.PROCESSING)

        turn = core.conversation_manager.process_incoming_input(
            raw_input, source=source, repaired_text=repaired_text
        )
        if hasattr(turn, "metadata"):
            turn.metadata["speech_repair"] = repair_res

        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit_domain_event(
                UserInputReceived(text=turn.normalized_input, source=source, turn_id=turn.turn_id)
            )

        if hasattr(core, "action_logger") and core.action_logger:
            core.action_logger.log_input(turn.normalized_input)

        return turn, repaired_text

    def apply_vocabulary_and_spelling(self, turn: Any) -> Tuple[bool, Optional[str]]:
        """
        Applies LCE preprocessing, vocabulary mapping, and spelling resolution.
        Returns:
            (handled, clarification_response)
        """
        core = self.core
        # 1. LCE preprocessing
        ctx_key = core.active_context.get_context_key() if hasattr(core, "active_context") and core.active_context else "global"
        if hasattr(core, "learning_manager") and core.learning_manager and hasattr(core.learning_manager, "lce") and core.learning_manager.lce:
            try:
                lce_tokens = core.learning_manager.lce.preprocess(turn.normalized_input, context_key=ctx_key)
                if (
                    lce_tokens
                    and lce_tokens.corrected_text
                    and lce_tokens.corrected_text.lower().strip() != lce_tokens.raw_text.lower().strip()
                    and lce_tokens.corrected_text != turn.normalized_input
                ):
                    turn.normalized_input = lce_tokens.corrected_text
            except Exception as _lce_err:
                logger.debug("LCE preprocessing note: %s", _lce_err)

        # 2. Vocabulary resolution
        if getattr(core, "learning_manager", None):
            try:
                turn.normalized_input = core.learning_manager.resolve_vocabulary(turn.normalized_input)
            except Exception as _vocab_err:
                logger.debug("Vocabulary resolution note: %s", _vocab_err)

        # 3. Spelling Resolver
        from brain.spelling_resolver import SpellingResolver, SpellingClarificationFormatter
        try:
            spelling = SpellingResolver.resolve(
                turn.normalized_input,
                getattr(core, "plugin_manager", None),
                getattr(core, "_rejected_fuzzy_candidates", None)
            )
        except Exception as e:
            logger.debug("SpellingResolver resolution note: %s", e)
            spelling = None

        if spelling and getattr(spelling, "needs_confirmation", False):
            # Never interrogate spelling on a clear executable command
            # ("Meeting schedule karo", "Ek baar phir batao") — route it instead.
            try:
                from core.conversational_intent import ConversationalIntentClassifier as _CIC
                _is_cmd, _v, _t = _CIC._detect_action_command((turn.normalized_input or "").lower().strip())
            except Exception:
                _is_cmd = False
            if _is_cmd:
                spelling = None

        if spelling:
            if spelling.needs_confirmation and hasattr(core, "dialog_manager") and core.dialog_manager:
                core.dialog_manager.set_pending_spelling(
                    spelling.typo, spelling.correction, spelling.corrected_text
                )
                user_name = "Boss"
                if getattr(core, "memory_manager", None):
                    try:
                        fact = core.memory_manager.get_fact("user_name")
                        if fact and isinstance(fact, dict) and fact.get("value"):
                            user_name = fact["value"]
                    except Exception:
                        pass
                clarify_resp = SpellingClarificationFormatter.format_clarification(
                    typo=spelling.typo,
                    correction=spelling.correction,
                    original_text=turn.normalized_input,
                    alt_candidate=spelling.alt_candidate,
                    user_name=user_name,
                )
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, clarify_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(clarify_resp)
                return True, clarify_resp

            # High-confidence silent correction: learn it and prepare spoken ack
            if getattr(core, "learning_manager", None):
                try:
                    core.learning_manager.vocabulary.learn_term(
                        spelling.typo, spelling.correction, category="auto_spelling"
                    )
                except Exception:
                    pass
            turn.normalized_input = spelling.corrected_text
            core._last_spell_ack = SpellingClarificationFormatter.format_auto_ack(
                typo=spelling.typo,
                correction=spelling.correction,
                original_text=spelling.original_text,
            )
        else:
            core._last_spell_ack = None

        return False, None
