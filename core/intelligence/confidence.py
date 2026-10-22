# core/intelligence/confidence.py
"""
Accuracy & Confidence Calibration Engine for Jarvis V2.1 (`intelligence.confidence`).
Provides centralized, multi-dimensional confidence scoring and 3-tier action gating:
- HIGH (>= 0.85): Execute command or dispense answer directly.
- MEDIUM (0.60 <= conf < 0.85): Use context / verify before acting.
- LOW (< 0.60): Clarify rather than give wrong answers ("galat answer se better clarification").
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.intelligence.confidence")


class ConfidenceTier(str, Enum):
    """Authoritative operational confidence tiers."""
    HIGH = "HIGH"        # >= 0.85: Direct, high-certainty dispatch (Execute / Answer)
    MEDIUM = "MEDIUM"    # 0.60 <= conf < 0.85: Disambiguate using context or verify
    LOW = "LOW"          # < 0.60: Clarify with user; never guess or hallucinate


class ConfidenceAction(str, Enum):
    """Action recommendation based on confidence assessment."""
    EXECUTE = "EXECUTE"                    # Direct command execution
    ANSWER = "ANSWER"                      # Direct knowledge / factual response
    USE_CONTEXT = "USE_CONTEXT"            # Resolve target / pronoun using active window or turn context
    VERIFY = "VERIFY"                      # Run pre-execution state verification
    CLARIFY = "CLARIFY"                    # Prompt user for clarification


@dataclass
class InterpretationConfidence:
    """
    Multi-dimensional interpretation confidence representation.
    Maintains distinct sub-confidences with composite score and tiered action guidance.
    """
    intent_confidence: float = 0.90      # Certainty in intent determination (0.0 to 1.0)
    entity_confidence: float = 0.85      # Certainty in identified target entities (0.0 to 1.0)
    context_confidence: float = 0.80     # Alignment with active window / workflow context (0.0 to 1.0)
    action_confidence: float = 0.85      # Feasibility & safety of the planned action (0.0 to 1.0)
    answer_confidence: float = 0.85      # Factual grounding & certainty for information (0.0 to 1.0)
    language_confidence: float = 0.95    # Confidence in language / code-switching detection (0.0 to 1.0)
    speech_confidence: float = 0.95      # Speech/ASR acoustic clarity confidence (0.0 to 1.0)
    goal_confidence: float = 0.90        # High-level communicative goal confidence (0.0 to 1.0)
    reference_confidence: float = 0.85   # Deictic / anaphora resolution confidence (0.0 to 1.0)
    composite: float = 0.86              # Calibrated weighted composite score (0.0 to 1.0)
    tier: ConfidenceTier = ConfidenceTier.HIGH
    recommended_action: ConfidenceAction = ConfidenceAction.EXECUTE
    clarification_prompt: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: float = field(default_factory=time.time)

    @property
    def is_executable(self) -> bool:
        """Returns True if confidence permits direct execution."""
        return self.tier == ConfidenceTier.HIGH and self.recommended_action in (
            ConfidenceAction.EXECUTE, ConfidenceAction.ANSWER
        )

    @property
    def needs_clarification(self) -> bool:
        """Returns True if the engine mandates a clarification question."""
        return self.tier == ConfidenceTier.LOW or self.recommended_action == ConfidenceAction.CLARIFY

    @property
    def needs_context_or_verification(self) -> bool:
        """Returns True if context lookup or verification is recommended."""
        return self.tier == ConfidenceTier.MEDIUM or self.recommended_action in (
            ConfidenceAction.USE_CONTEXT, ConfidenceAction.VERIFY
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the confidence record into a structured dictionary."""
        return {
            "intent_confidence": round(self.intent_confidence, 3),
            "entity_confidence": round(self.entity_confidence, 3),
            "context_confidence": round(self.context_confidence, 3),
            "action_confidence": round(self.action_confidence, 3),
            "answer_confidence": round(self.answer_confidence, 3),
            "language_confidence": round(self.language_confidence, 3),
            "speech_confidence": round(self.speech_confidence, 3),
            "goal_confidence": round(self.goal_confidence, 3),
            "reference_confidence": round(self.reference_confidence, 3),
            "composite": round(self.composite, 3),
            "tier": self.tier.value if hasattr(self.tier, "value") else str(self.tier),
            "recommended_action": (
                self.recommended_action.value
                if hasattr(self.recommended_action, "value")
                else str(self.recommended_action)
            ),
            "clarification_prompt": self.clarification_prompt,
            "reason": self.reason,
            "metadata": dict(self.metadata),
            "evaluated_at": self.evaluated_at
        }


class ConfidenceEngine:
    """
    Accuracy & Confidence Calibration Engine (`intelligence.confidence`).
    
    Evaluates multi-dimensional interpretations and calculates calibrated composite scores.
    Enforces the 'galat answer se better clarification' principle by gating LOW confidence
    into targeted clarifications, MEDIUM into contextual verification, and HIGH into direct execution.
    """

    # Threshold constants
    HIGH_THRESHOLD = 0.85
    MEDIUM_THRESHOLD = 0.60
    CRITICAL_DIMENSION_FLOOR = 0.40  # If any critical dimension is below this, tier becomes LOW

    # Action Turn weights: intent (25%), entity (25%), context (20%), action (30%)
    ACTION_WEIGHTS = {
        "intent": 0.25,
        "entity": 0.25,
        "context": 0.20,
        "action": 0.30
    }

    # Answer / Knowledge Turn weights: intent (30%), entity (25%), context (15%), answer (30%)
    ANSWER_WEIGHTS = {
        "intent": 0.30,
        "entity": 0.25,
        "context": 0.15,
        "answer": 0.30
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._calibration_history: List[Dict[str, Any]] = []

    def evaluate(
        self,
        intent_confidence: float = 0.90,
        entity_confidence: float = 0.85,
        context_confidence: float = 0.80,
        action_confidence: float = 0.85,
        answer_confidence: float = 0.85,
        language_confidence: float = 0.95,
        speech_confidence: float = 0.95,
        goal_confidence: float = 0.90,
        reference_confidence: float = 0.85,
        turn_type: str = "action",
        raw_query: str = "",
        candidate_entities: Optional[List[str]] = None,
        is_clarification_turn: bool = False,
        is_destructive: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InterpretationConfidence:
        """
        Computes composite confidence across dimensions, determines tier,
        and assigns the authoritative action recommendation.
        """
        # Clamp all inputs to [0.0, 1.0]
        i_conf = max(0.0, min(1.0, float(intent_confidence)))
        e_conf = max(0.0, min(1.0, float(entity_confidence)))
        c_conf = max(0.0, min(1.0, float(context_confidence)))
        a_conf = max(0.0, min(1.0, float(action_confidence)))
        ans_conf = max(0.0, min(1.0, float(answer_confidence)))
        lang_conf = max(0.0, min(1.0, float(language_confidence)))
        sp_conf = max(0.0, min(1.0, float(speech_confidence)))
        g_conf = max(0.0, min(1.0, float(goal_confidence)))
        ref_conf = max(0.0, min(1.0, float(reference_confidence)))

        turn_type_clean = (turn_type or "action").lower()

        # Compute weighted composite score
        if turn_type_clean in ("answer", "knowledge", "information", "question"):
            composite = (
                self.ANSWER_WEIGHTS["intent"] * i_conf +
                self.ANSWER_WEIGHTS["entity"] * e_conf +
                self.ANSWER_WEIGHTS["context"] * c_conf +
                self.ANSWER_WEIGHTS["answer"] * ans_conf
            )
            default_action = ConfidenceAction.ANSWER
        else:
            composite = (
                self.ACTION_WEIGHTS["intent"] * i_conf +
                self.ACTION_WEIGHTS["entity"] * e_conf +
                self.ACTION_WEIGHTS["context"] * c_conf +
                self.ACTION_WEIGHTS["action"] * a_conf
            )
            default_action = ConfidenceAction.EXECUTE

        # Floor penalties: if any critical dimension is collapsed (< 0.40), cap composite
        critical_dimension = min(i_conf, e_conf)
        if turn_type_clean in ("answer", "knowledge"):
            critical_dimension = min(critical_dimension, ans_conf)
        else:
            critical_dimension = min(critical_dimension, a_conf)

        if critical_dimension < self.CRITICAL_DIMENSION_FLOOR and composite >= self.MEDIUM_THRESHOLD:
            composite = min(composite, 0.58)

        # Destructive actions require explicit verification regardless of raw score
        if is_destructive and composite >= self.HIGH_THRESHOLD:
            composite = 0.80

        # Tier Determination
        clarification_prompt = None
        reason = ""

        if composite >= self.HIGH_THRESHOLD:
            tier = ConfidenceTier.HIGH
            recommended = default_action
            reason = f"High confidence ({composite:.2f}) across all dimensions."
        elif composite >= self.MEDIUM_THRESHOLD:
            tier = ConfidenceTier.MEDIUM
            if is_destructive:
                recommended = ConfidenceAction.VERIFY
                reason = f"Destructive action requires explicit verification / confirmation ({composite:.2f})."
            elif c_conf >= 0.75:
                recommended = ConfidenceAction.USE_CONTEXT
                reason = f"Medium confidence ({composite:.2f}); active context can resolve ambiguity."
            else:
                recommended = ConfidenceAction.VERIFY
                reason = f"Medium confidence ({composite:.2f}); verification recommended before proceeding."
        else:
            tier = ConfidenceTier.LOW
            recommended = ConfidenceAction.CLARIFY
            reason = f"Low confidence ({composite:.2f}); clarification mandated to prevent wrong action/hallucination."
            clarification_prompt = self.generate_clarification(
                raw_query=raw_query,
                candidates=candidate_entities or [],
                turn_type=turn_type_clean,
                intent_conf=i_conf,
                entity_conf=e_conf,
                answer_conf=ans_conf
            )

        meta = dict(metadata or {})
        meta["turn_type"] = turn_type_clean
        meta["critical_dimension"] = round(critical_dimension, 3)

        result = InterpretationConfidence(
            intent_confidence=round(i_conf, 3),
            entity_confidence=round(e_conf, 3),
            context_confidence=round(c_conf, 3),
            action_confidence=round(a_conf, 3),
            answer_confidence=round(ans_conf, 3),
            language_confidence=round(lang_conf, 3),
            speech_confidence=round(sp_conf, 3),
            goal_confidence=round(g_conf, 3),
            reference_confidence=round(ref_conf, 3),
            composite=round(composite, 3),
            tier=tier,
            recommended_action=recommended,
            clarification_prompt=clarification_prompt,
            reason=reason,
            metadata=meta
        )

        logger.debug(
            "[CONFIDENCE_EVALUATION] composite=%.2f tier=%s action=%s (intent=%.2f, entity=%.2f, context=%.2f, act=%.2f, ans=%.2f)",
            result.composite, result.tier.value, result.recommended_action.value,
            result.intent_confidence, result.entity_confidence, result.context_confidence,
            result.action_confidence, result.answer_confidence
        )

        return result

    def evaluate_action_turn(
        self,
        intent: str,
        entity: str,
        action: str,
        raw_query: str = "",
        intent_conf: float = 0.90,
        entity_conf: float = 0.85,
        context_conf: float = 0.80,
        action_conf: float = 0.85,
        candidate_entities: Optional[List[str]] = None,
        is_destructive: bool = False,
        active_context: Optional[Any] = None,
    ) -> InterpretationConfidence:
        """Specialized evaluation for action command turns."""
        c_conf = context_conf
        # Boost context confidence if entity matches active context application
        if active_context and entity:
            cur_app = (getattr(active_context, "application", "") or "").lower()
            if entity.lower() in cur_app or cur_app in entity.lower():
                c_conf = max(c_conf, 0.95)

        return self.evaluate(
            intent_confidence=intent_conf,
            entity_confidence=entity_conf,
            context_confidence=c_conf,
            action_confidence=action_conf,
            answer_confidence=0.50,
            turn_type="action",
            raw_query=raw_query,
            candidate_entities=candidate_entities,
            is_destructive=is_destructive,
            metadata={"intent": intent, "entity": entity, "action": action}
        )

    def evaluate_answer_turn(
        self,
        query: str,
        intent_conf: float = 0.90,
        entity_conf: float = 0.85,
        context_conf: float = 0.70,
        answer_conf: float = 0.85,
        is_hallucination_risk: bool = False,
        category: str = "general_knowledge"
    ) -> InterpretationConfidence:
        """Specialized evaluation for knowledge and question answers."""
        ans_conf = answer_conf
        if is_hallucination_risk:
            ans_conf = min(ans_conf, 0.30)

        return self.evaluate(
            intent_confidence=intent_conf,
            entity_confidence=entity_conf,
            context_confidence=context_conf,
            action_confidence=0.50,
            answer_confidence=ans_conf,
            turn_type="answer",
            raw_query=query,
            metadata={"category": category, "is_hallucination_risk": is_hallucination_risk}
        )

    def generate_clarification(
        self,
        raw_query: str = "",
        candidates: Optional[List[str]] = None,
        turn_type: str = "action",
        intent_conf: float = 0.50,
        entity_conf: float = 0.50,
        answer_conf: float = 0.50
    ) -> str:
        """
        Generates a natural, human-like clarification prompt based on specific
        confidence deficit dimensions.
        """
        cand_list = [c for c in (candidates or []) if c]
        if cand_list and len(cand_list) >= 2:
            options_str = " ya ".join(cand_list[:2])
            return f"Aap {options_str} mein se kaunsa chahte hain?"

        if turn_type in ("answer", "knowledge"):
            if answer_conf < 0.40:
                return "Is baare mein mere paas authoritative jaankari nahi hai. Kya aap query ko aur specific kar sakte hain?"
            return "Aap kis vishay ke baare mein jaanna chahte hain?"

        # Action turn clarifications
        if intent_conf >= 0.70 and entity_conf < 0.50:
            return "Aap kis application ya target par ye action execute karna chahte hain?"
        elif entity_conf >= 0.70 and intent_conf < 0.50:
            return f"Aap {raw_query or 'target'} ke saath kya karna chahte hain?"

        return "Aap kya karna ya jaanna chahte hain? Thoda aur detail batayein."

    def calibrate(self, feedback_score: float, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Registers turn feedback for self-learning calibration.
        feedback_score: 1.0 (success/positive), 0.0 (mistake/correction).
        """
        with self._lock:
            record = {
                "score": max(0.0, min(1.0, float(feedback_score))),
                "details": dict(details or {}),
                "timestamp": time.time()
            }
            self._calibration_history.append(record)
            if len(self._calibration_history) > 1000:
                self._calibration_history = self._calibration_history[-500:]

    def get_calibration_stats(self) -> Dict[str, Any]:
        """Returns calibration statistics."""
        with self._lock:
            if not self._calibration_history:
                return {"count": 0, "avg_feedback": 1.0}
            scores = [r["score"] for r in self._calibration_history]
            return {
                "count": len(scores),
                "avg_feedback": round(sum(scores) / len(scores), 3)
            }


# Singleton accessor for global confidence calibration
_CONFIDENCE_ENGINE_INSTANCE: Optional[ConfidenceEngine] = None
_CONFIDENCE_ENGINE_LOCK = threading.Lock()


def get_confidence_engine() -> ConfidenceEngine:
    """Returns the singleton instance of ConfidenceEngine."""
    global _CONFIDENCE_ENGINE_INSTANCE
    if _CONFIDENCE_ENGINE_INSTANCE is None:
        with _CONFIDENCE_ENGINE_LOCK:
            if _CONFIDENCE_ENGINE_INSTANCE is None:
                _CONFIDENCE_ENGINE_INSTANCE = ConfidenceEngine()
    return _CONFIDENCE_ENGINE_INSTANCE
