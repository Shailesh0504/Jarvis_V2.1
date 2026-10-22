# core/intelligence/models.py
"""
Data models and enumerations for the Proactive Intelligence and Pattern Learning Engine.
Defines pattern types, temporal periods, and pattern records.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
from typing import Any, Dict, Optional
import uuid


class PatternType(str, Enum):
    """Categories of learnable user habits and behavioral patterns."""
    APP_TRANSITION = "APP_TRANSITION"    # Sequential app usage: A -> B
    TIME_APP_HABIT = "TIME_APP_HABIT"    # Time-of-day app usage: e.g. morning Excel
    MEDIA_PREFERENCE = "MEDIA_PREFERENCE"# Frequent artist, channel, or video title
    VOLUME_HABIT = "VOLUME_HABIT"        # Contextual preferred volume level (e.g. night music)


class TimePeriod(str, Enum):
    """Time-of-day temporal classifications."""
    MORNING = "MORNING"        # 06:00 - 12:00
    AFTERNOON = "AFTERNOON"    # 12:00 - 18:00
    EVENING = "EVENING"        # 18:00 - 22:00
    NIGHT = "NIGHT"            # 22:00 - 06:00

    @classmethod
    def from_timestamp(cls, ts: Optional[float] = None) -> "TimePeriod":
        """Determines the TimePeriod from a unix timestamp or current time."""
        dt = datetime.fromtimestamp(ts or time.time())
        hour = dt.hour
        if 6 <= hour < 12:
            return cls.MORNING
        elif 12 <= hour < 18:
            return cls.AFTERNOON
        elif 18 <= hour < 22:
            return cls.EVENING
        else:
            return cls.NIGHT


@dataclass
class PatternRecord:
    """Structured representation of a learned user habit or behavioral pattern."""
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern_type: PatternType = PatternType.APP_TRANSITION
    pattern_key: str = ""
    frequency: int = 1
    confidence: float = 0.35
    data: Dict[str, Any] = field(default_factory=dict)
    first_observed: float = field(default_factory=time.time)
    last_observed: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the pattern record into a clean dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value if hasattr(self.pattern_type, "value") else str(self.pattern_type),
            "pattern_key": self.pattern_key,
            "frequency": self.frequency,
            "confidence": round(self.confidence, 2),
            "data": dict(self.data),
            "first_observed": self.first_observed,
            "last_observed": self.last_observed
        }


class SuggestionUrgency(str, Enum):
    """Urgency level of a proactive suggestion."""
    LOW = "LOW"        # Ambient or passive suggestion (e.g. background music, volume tweak)
    NORMAL = "NORMAL"  # Helpful contextual action (e.g. app transition, task resumption)
    HIGH = "HIGH"      # Time-critical or important reminder / alert


class SuggestionState(str, Enum):
    """Lifecycle states of a proactive suggestion."""
    PROPOSED = "PROPOSED"  # Presented to the user, awaiting feedback
    ACCEPTED = "ACCEPTED"  # Accepted by the user ("ha", "yes", "chala do")
    REJECTED = "REJECTED"  # Rejected by the user ("nahi", "no", "rehne do")
    IGNORED = "IGNORED"    # User took another unrelated action
    EXPIRED = "EXPIRED"    # Confirmation window timed out without response


@dataclass
class ProactiveSuggestion:
    """A synthesized candidate action proposed proactively by Jarvis."""
    suggestion_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    intent: str = ""                    # e.g. "MEDIA_PLAY_ARTIST", "ADJUST_VOLUME", "LAUNCH_APP", "RESUME_TASK"
    action: str = ""                    # e.g. "play_music", "set_volume", "open_app", "resume_task"
    target: str = ""                    # e.g. "Arijit Singh", "34", "youtube", "excel"
    confidence: float = 0.70
    rationale: str = ""                 # Contextual explanation (e.g. "Aap shaam ko aksar Arijit Singh sunte hain.")
    urgency: SuggestionUrgency = SuggestionUrgency.NORMAL
    state: SuggestionState = SuggestionState.PROPOSED
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the suggestion into a dictionary."""
        return {
            "suggestion_id": self.suggestion_id,
            "intent": self.intent,
            "action": self.action,
            "target": self.target,
            "confidence": round(self.confidence, 2),
            "rationale": self.rationale,
            "urgency": self.urgency.value if hasattr(self.urgency, "value") else str(self.urgency),
            "state": self.state.value if hasattr(self.state, "value") else str(self.state),
            "metadata": dict(self.metadata),
            "created_at": self.created_at
        }


class SuggestionCategory(str, Enum):
    """Categories of conversational next-step suggestions (Section 3)."""
    NEXT_STEP = "NEXT_STEP"
    USEFUL_ACTION = "USEFUL_ACTION"
    RELEVANT_INFORMATION = "RELEVANT_INFORMATION"
    CLARIFICATION = "CLARIFICATION"
    ALTERNATIVE = "ALTERNATIVE"
    PROACTIVE_HELP = "PROACTIVE_HELP"


@dataclass
class SuggestionScore:
    """
    Multi-factor relevance score for deciding whether a suggestion should be presented (Section 10).
    Evaluates goal alignment, contextual fit, capability availability, confidence, usefulness, and repetition penalty.
    """
    goal_alignment: float = 1.0
    context_alignment: float = 1.0
    capability_match: float = 1.0
    confidence: float = 1.0
    usefulness: float = 1.0
    repetition_penalty: float = 0.0

    @property
    def total(self) -> float:
        """Weighted aggregate score from 0.0 to 1.0."""
        raw = (
            self.goal_alignment * 0.25
            + self.context_alignment * 0.20
            + self.capability_match * 0.20
            + self.confidence * 0.15
            + self.usefulness * 0.20
        )
        return max(0.0, min(1.0, round(raw - self.repetition_penalty, 2)))

    def to_dict(self) -> Dict[str, float]:
        return {
            "goal_alignment": self.goal_alignment,
            "context_alignment": self.context_alignment,
            "capability_match": self.capability_match,
            "confidence": self.confidence,
            "usefulness": self.usefulness,
            "repetition_penalty": self.repetition_penalty,
            "total": self.total,
        }


@dataclass
class ContextualSuggestion:
    """A goal-aligned, capability-verified next-step suggestion accompanying an answer."""
    suggestion_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: SuggestionCategory = SuggestionCategory.NEXT_STEP
    goal: str = ""
    intent: str = ""
    text: str = ""                        # Natural, spoken suggestion
    action: Optional[str] = None          # Action identifier if accepted
    target: Optional[str] = None          # Target entity/city/topic
    target_plugin: Optional[str] = None   # Target plugin or service
    action_payload: Dict[str, Any] = field(default_factory=dict)
    capability_id: Optional[str] = None
    capability_available: bool = True
    score: Optional[SuggestionScore] = None
    reason: str = ""
    decision: str = "SUGGEST"             # "SUGGEST" or "SUPPRESS"
    created_at: float = field(default_factory=time.time)

    def to_debug_string(self) -> str:
        """Structured internal diagnostic representation per Section 20 requirements."""
        score_val = self.score.total if self.score else 0.0
        cap_str = "AVAILABLE" if self.capability_available else "UNAVAILABLE"
        return (
            f"GOAL:\n{self.goal}\n\n"
            f"SUGGESTION:\n{self.text}\n\n"
            f"CAPABILITY:\n{cap_str}\n\n"
            f"SCORE:\n{score_val:.2f}\n\n"
            f"DECISION:\n{self.decision}"
        )


@dataclass
class SuggestionChip:
    """A context-aware UI suggestion chip presenting a candidate next-step semantic command."""
    chip_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    label: str = ""                         # Human-readable display text (e.g. "YouTube kholo", "DNS check", "Chrome")
    command: str = ""                       # Semantic command string submitted to pipeline (e.g. "YouTube open karo", "check dns", "Chrome")
    category: str = "contextual"            # "slot_fill", "conversation", "active_app", "follow_up", "confirmation"
    target: Optional[str] = None            # Explicit target app or entity (for stale chip protection)
    score: float = 1.0                      # Relevance score (0.0 to 1.0)
    capability_id: Optional[str] = None
    action_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chip_id": self.chip_id,
            "label": self.label,
            "command": self.command,
            "category": self.category,
            "target": self.target,
            "score": round(self.score, 2),
            "capability_id": self.capability_id,
            "action_type": self.action_type,
        }

