# core/semantic/resolution.py
"""
Data contracts for the Universal Meaning -> Goal -> Capability Resolution Layer.
Derives 11 internal decision fields for every user utterance prior to command execution.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.semantic.models import IntentName, SemanticAction


class ResolutionDecision(str, Enum):
    """Authoritative decision emitted by the Universal Goal Resolver."""
    EXECUTE = "EXECUTE"
    ASK_PRECISE_CLARIFICATION = "ASK_PRECISE_CLARIFICATION"
    CLARIFY = "ASK_PRECISE_CLARIFICATION"
    ANSWER = "ANSWER"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


@dataclass
class MultiDimensionalConfidence:
    """Multi-dimensional confidence vector avoiding single-threshold brittle checks."""
    intent_confidence: float = 1.0
    entity_confidence: float = 1.0
    context_confidence: float = 1.0
    capability_confidence: float = 1.0
    action_confidence: float = 1.0

    @property
    def combined(self) -> float:
        """Weighted aggregate confidence score (0.0 to 1.0)."""
        # Intent and capability carry the highest weights, followed by entity and action
        return round(
            (
                self.intent_confidence * 0.30
                + self.capability_confidence * 0.25
                + self.entity_confidence * 0.20
                + self.action_confidence * 0.15
                + self.context_confidence * 0.10
            ),
            2,
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "intent": self.intent_confidence,
            "entity": self.entity_confidence,
            "context": self.context_confidence,
            "capability": self.capability_confidence,
            "action": self.action_confidence,
            "combined": self.combined,
        }


@dataclass
class SemanticResolution:
    """
    11-Field Unified Decision Model for Jarvis NLU.
    Every utterance is mapped from raw words to user goal, capability, and execution plan.
    """
    raw_input: str
    meaning: str
    speech_act: str
    goal: str
    intent: str
    entities: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    context_dependencies: List[str] = field(default_factory=list)
    capability_required: str = ""
    capability_available: bool = True
    confidence: float = 1.0
    confidence_breakdown: Optional[MultiDimensionalConfidence] = None
    action_plan: Optional[Dict[str, Any]] = None
    decision: ResolutionDecision = ResolutionDecision.EXECUTE
    clarification_prompt: Optional[str] = None
    response_text: Optional[str] = None
    needs_clarification: bool = False

    @property
    def primary_goal(self) -> str:
        return self.goal

    @property
    def slots(self) -> Dict[str, Any]:
        return self.parameters

    def __post_init__(self):
        if self.confidence_breakdown is None:
            self.confidence_breakdown = MultiDimensionalConfidence(
                intent_confidence=self.confidence,
                entity_confidence=self.confidence,
                context_confidence=1.0 if not self.context_dependencies else 0.9,
                capability_confidence=1.0 if self.capability_available else 0.0,
                action_confidence=self.confidence,
            )

    def to_debug_string(self) -> str:
        """
        Structured internal debug representation (Section 20 requirement).
        Must NOT leak into normal user-facing responses.
        """
        entity_val = (
            self.entities.get("entity")
            or self.entities.get("target")
            or self.entities.get("app_name")
            or self.entities.get("site")
            or "none"
        )
        ctx_desc = ", ".join(self.context_dependencies) if self.context_dependencies else "none required"
        dec_val = self.decision.value if hasattr(self.decision, "value") else str(self.decision)
        return (
            f"INPUT:\n\"{self.raw_input}\"\n\n"
            f"MEANING:\n{self.meaning}\n\n"
            f"SPEECH ACT:\n{self.speech_act}\n\n"
            f"GOAL:\n{self.goal}\n\n"
            f"INTENT:\n{self.intent}\n\n"
            f"ENTITY:\n{entity_val}\n\n"
            f"CONTEXT:\n{ctx_desc}\n\n"
            f"CAPABILITY:\n{self.capability_required}\n\n"
            f"CONFIDENCE:\n{self.confidence:.2f}\n\n"
            f"DECISION:\n{dec_val}"
        )

    def to_semantic_action(self) -> Optional[SemanticAction]:
        """Converts resolution into a drop-in SemanticAction for executor backward-compatibility."""
        if self.decision == ResolutionDecision.CAPABILITY_UNAVAILABLE:
            return None

        needs_clarify = bool(
            self.decision in (ResolutionDecision.ASK_PRECISE_CLARIFICATION, ResolutionDecision.CLARIFY)
            or self.needs_clarification
        )
        plan = self.action_plan or {}
        service = plan.get("service") or (self.capability_required.split(".")[0] if "." in self.capability_required else "system")
        action = plan.get("action") or (self.capability_required.split(".")[-1] if "." in self.capability_required else "execute")

        merged_params = dict(self.parameters)
        merged_params.update(self.entities)
        if plan.get("parameters"):
            merged_params.update(plan["parameters"])
        if self.response_text:
            merged_params["response_text"] = self.response_text

        return SemanticAction(
            intent=IntentName(self.intent) if self.intent else "UNKNOWN",
            service=service,
            action=action,
            query=merged_params.get("query") or self.raw_input,
            parameters=merged_params,
            needs_clarification=needs_clarify,
            clarification_prompt=self.clarification_prompt,
            missing_slot=plan.get("missing_slot"),
            confidence=self.confidence,
        )
