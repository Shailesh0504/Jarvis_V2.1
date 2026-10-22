# learning/communication_engine.py
"""Production-grade Learning Communication Engine (LCE) for Jarvis V2."""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from memory.database import DatabaseManager
from .communication_memory import CommunicationMemory
from .communication_normalizer import CommunicationNormalizer, UtteranceTokens
from .communication_matcher import CommunicationMatcher
from .communication_feedback import CommunicationFeedback

logger = logging.getLogger("jarvis.learning.lce")


class LearningCommunicationEngine:
    """
    Continuous communication learning engine for natural Hindi/Hinglish/English interactions.
    Manages vocabulary evolution, phonetic fixes, contextual aliases, user corrections,
    and confidence thresholding without bypassing safety guards.
    """

    DANGEROUS_ACTIONS = {
        "shutdown_system", "restart_system", "format_drive", "delete_file",
        "empty_recycle_bin", "financial_transaction", "place_trading_order",
        "disable_security", "change_password", "execute_shell_root"
    }

    def __init__(self, db: DatabaseManager, enabled: bool = True):
        self.enabled = enabled
        self.memory = CommunicationMemory(db)
        self.normalizer = CommunicationNormalizer()
        self.matcher = CommunicationMatcher()
        self.feedback = CommunicationFeedback()
        self._last_utterance_tokens: Optional[UtteranceTokens] = None
        self._last_interpreted_intent: Optional[str] = None
        self._last_context_key: str = "global"

    def preprocess(self, raw_input: str, context_key: str = "global") -> UtteranceTokens:
        """
        Step 1 in the communication pipeline:
        Tokenizes raw utterance into raw, normalized, and phonetically corrected forms.
        """
        if not self.enabled:
            return UtteranceTokens(raw_text=raw_input, normalized_text=raw_input.strip().lower(), corrected_text=raw_input.strip().lower())

        learned_vocab = self.memory.get_all_vocabulary()
        tokens = self.normalizer.tokenize_utterance(
            raw_text=raw_input,
            context_key=context_key,
            learned_vocab=learned_vocab
        )
        self._last_utterance_tokens = tokens
        self._last_context_key = context_key
        logger.debug("[LCE_LOOKUP] Raw: '%s' | Corrected: '%s' | Context: %s", tokens.raw_text, tokens.corrected_text, context_key)
        return tokens

    def resolve_contextual_candidate(self, tokens: UtteranceTokens, context_key: str = "global") -> Optional[Dict[str, Any]]:
        """
        Step 2 in the communication pipeline:
        Checks for learned communication patterns or aliases for the current context.
        """
        if not self.enabled:
            return None

        # 1. Check exact alias match
        alias_cmd = self.memory.get_alias(tokens.corrected_text, context_key=context_key)
        if alias_cmd:
            logger.info("[LCE_MATCH] Alias '%s' -> Command '%s' (Context: %s)", tokens.corrected_text, alias_cmd, context_key)
            return {"intent": "ALIASED_COMMAND", "canonical_command": alias_cmd, "confidence": 0.95, "source": "alias"}

        # 2. Check learned communication patterns
        patterns = self.memory.get_all_patterns(min_confidence=0.70)
        match_res = self.matcher.match_best_pattern(
            text=tokens.corrected_text,
            patterns=patterns,
            current_context=context_key,
            min_threshold=0.72
        )
        if match_res:
            pat, score = match_res
            logger.info("[LCE_MATCH] Pattern match: '%s' -> Intent: %s (Confidence: %.2f)", pat.get("normalized_phrase"), pat.get("intent"), score)
            return {
                "pattern_id": pat.get("id"),
                "intent": pat.get("intent"),
                "entities": pat.get("entities", {}),
                "confidence": score,
                "status": pat.get("status", "candidate"),
                "source": "pattern"
            }
        return None

    def record_success(
        self,
        tokens: UtteranceTokens,
        intent: str,
        entities: Optional[Dict[str, Any]] = None,
        context_key: str = "global",
        explicit_confirmation: bool = False
    ) -> None:
        """
        Step 3 in the communication pipeline:
        Reinforces successful pattern and increases confidence.
        """
        if not self.enabled or not intent:
            return

        # Never auto-learn dangerous actions without explicit confirmation
        if intent.lower() in self.DANGEROUS_ACTIONS and not explicit_confirmation:
            return

        conf_initial = 0.95 if explicit_confirmation else 0.75
        status = "user_confirmed" if explicit_confirmation else "candidate"

        pat_id = self.memory.save_pattern(
            user_phrase=tokens.raw_text,
            normalized_phrase=tokens.corrected_text,
            intent=intent,
            entities=entities,
            context_key=context_key,
            confidence=conf_initial,
            source="user_confirmed" if explicit_confirmation else "interaction",
            status=status
        )

        delta = self.feedback.get_confidence_delta("positive_explicit" if explicit_confirmation else "positive_implicit")
        new_conf = self.memory.update_pattern_confidence(pat_id, delta=delta, success=True)
        self.memory.record_feedback(
            utterance=tokens.raw_text,
            interpretation=intent,
            feedback_type="positive_explicit" if explicit_confirmation else "positive_implicit",
            context_key=context_key,
            conf_before=new_conf - delta,
            conf_after=new_conf
        )
        logger.info("[LCE_REINFORCE] Pattern #%d ('%s' -> %s) updated to confidence %.2f", pat_id, tokens.corrected_text, intent, new_conf)

    def handle_correction_or_feedback(
        self,
        feedback_text: str,
        context_key: str = "global"
    ) -> Tuple[bool, Optional[str]]:
        """
        Handles negative feedback (e.g. 'Nahi, Excel bola tha' or 'galat').
        Returns (is_handled, response_message).
        """
        if not self.enabled or not self._last_utterance_tokens:
            return False, None

        fb_type = self.feedback.classify_feedback(feedback_text)
        if not fb_type:
            return False, None

        if fb_type == "negative_correction":
            target = self.feedback.extract_correction_target(feedback_text)
            if target:
                orig = self._last_utterance_tokens.raw_text
                wrong = self._last_interpreted_intent or "UNKNOWN"
                self.memory.record_correction(
                    original_text=orig,
                    wrong_interpretation=wrong,
                    correct_interpretation=target,
                    context_key=context_key,
                    reason="user_spoken_correction"
                )
                # Learn new corrected vocabulary/alias mapping
                self.memory.save_vocabulary_term(spoken_form=orig, canonical_form=target, confidence=0.85)
                logger.info("[LCE_CORRECTION] Learned correction: '%s' was mistaken as '%s', corrected to '%s'", orig, wrong, target)
                return True, f"Maine note kar liya Boss. Aage se '{orig}' ko '{target}' hi samjhunga."

        elif fb_type == "negative_rejection":
            orig_norm = self._last_utterance_tokens.corrected_text
            pat = self.memory.get_pattern(orig_norm, context_key=context_key)
            if pat:
                new_conf = self.memory.update_pattern_confidence(pat["id"], delta=-0.15, success=False)
                self.memory.record_feedback(
                    utterance=self._last_utterance_tokens.raw_text,
                    interpretation=pat.get("intent", ""),
                    feedback_type="negative_rejection",
                    context_key=context_key,
                    conf_before=new_conf + 0.15,
                    conf_after=new_conf
                )
                logger.info("[LCE_DECAY] Negative feedback reduced confidence of '%s' to %.2f", orig_norm, new_conf)
                return True, "Maafi chahta hoon Boss. Maine is pattern ka confidence kam kar diya hai."

        return False, None

    def get_audit_summary(self) -> Dict[str, Any]:
        """Returns structured audit information about all learned communication patterns."""
        patterns = self.memory.get_all_patterns()
        vocab = self.memory.get_all_vocabulary()
        return {
            "total_patterns": len(patterns),
            "trusted_count": len([p for p in patterns if p.get("status") in ("trusted", "user_confirmed")]),
            "candidate_count": len([p for p in patterns if p.get("status") == "candidate"]),
            "patterns": patterns[:20],
            "vocabulary": vocab
        }

    def forget_phrase(self, phrase: str, context_key: Optional[str] = None) -> bool:
        """Granularly deletes a learned phrase pattern."""
        deleted = self.memory.delete_pattern_by_phrase(phrase, context_key=context_key)
        return deleted > 0

    def reset_all_learning(self) -> bool:
        """Resets all candidate and learned communication patterns."""
        self.memory.reset_all_patterns()
        return True
