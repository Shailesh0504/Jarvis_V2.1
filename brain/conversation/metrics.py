# brain/conversation/metrics.py
"""
Quality Metrics and Structured Logging for Conversation Intelligence.
Tracks intent classification confidence, context resolution success rate,
clarification rates, and state transitions without exposing chain-of-thought to users.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.brain.conversation.metrics")


@dataclass
class TurnMetric:
    """Metrics recorded for a single dialogue turn."""
    turn_id: str
    timestamp: float
    raw_input: str
    detected_intent: str
    confidence: float
    strategy_used: str
    context_resolved: bool
    is_clarification: bool
    execution_time_ms: float
    state_transition: str


class ConversationMetricsLogger:
    """Aggregates conversation quality metrics and transition histories."""

    def __init__(self):
        self._history: List[TurnMetric] = []
        self._repeated_response_counter: Dict[str, int] = {}

    def log_turn(
        self,
        turn_id: str,
        raw_input: str,
        detected_intent: str,
        confidence: float,
        strategy_used: str,
        context_resolved: bool = False,
        is_clarification: bool = False,
        execution_time_ms: float = 0.0,
        state_transition: str = "IDLE->RESPONDING"
    ) -> TurnMetric:
        metric = TurnMetric(
            turn_id=turn_id,
            timestamp=time.time(),
            raw_input=raw_input,
            detected_intent=detected_intent,
            confidence=confidence,
            strategy_used=strategy_used,
            context_resolved=context_resolved,
            is_clarification=is_clarification,
            execution_time_ms=execution_time_ms,
            state_transition=state_transition
        )
        self._history.append(metric)
        logger.debug(
            f"ConversationMetric: Turn={turn_id} | Intent={detected_intent} | "
            f"Conf={confidence:.2f} | Strategy={strategy_used} | Resolved={context_resolved} | Time={execution_time_ms:.1f}ms"
        )
        return metric

    def track_response(self, response_text: str) -> bool:
        """Returns True if response was recently repeated."""
        cleaned = response_text.strip().lower()
        count = self._repeated_response_counter.get(cleaned, 0)
        self._repeated_response_counter[cleaned] = count + 1
        return count > 1

    def get_summary(self) -> Dict[str, Any]:
        """Returns statistical summary of recorded conversation quality metrics."""
        total = len(self._history)
        if total == 0:
            return {
                "total_turns": 0,
                "avg_confidence": 0.0,
                "context_resolution_rate": 0.0,
                "clarification_rate": 0.0,
                "avg_execution_time_ms": 0.0
            }

        avg_conf = sum(m.confidence for m in self._history) / total
        resolved_count = sum(1 for m in self._history if m.context_resolved)
        clarification_count = sum(1 for m in self._history if m.is_clarification)
        avg_time = sum(m.execution_time_ms for m in self._history) / total

        return {
            "total_turns": total,
            "avg_confidence": round(avg_conf, 3),
            "context_resolution_rate": round(resolved_count / total, 3),
            "clarification_rate": round(clarification_count / total, 3),
            "avg_execution_time_ms": round(avg_time, 2)
        }
