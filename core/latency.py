# core/latency.py
"""
High-Precision Pipeline Latency Tracking and Telemetry Subsystem.
Tracks latency breakdown across all conversational stages:
STT -> Normalization -> Intent Detection -> Planning -> Action Execution -> TTS Startup -> Total Response.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.core.latency")


@dataclass
class StageMetrics:
    stt_latency_ms: float = 0.0
    intent_detection_latency_ms: float = 0.0
    planning_latency_ms: float = 0.0
    action_latency_ms: float = 0.0
    tts_startup_latency_ms: float = 0.0
    total_response_latency_ms: float = 0.0
    is_fast_path: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stt_latency_ms": round(self.stt_latency_ms, 2),
            "intent_detection_latency_ms": round(self.intent_detection_latency_ms, 2),
            "planning_latency_ms": round(self.planning_latency_ms, 2),
            "action_latency_ms": round(self.action_latency_ms, 2),
            "tts_startup_latency_ms": round(self.tts_startup_latency_ms, 2),
            "total_response_latency_ms": round(self.total_response_latency_ms, 2),
            "is_fast_path": self.is_fast_path,
            "details": self.details,
        }


class PipelineLatencyTracker:
    """
    High-precision stage timer measuring and logging performance bottlenecks.
    Uses time.perf_counter() for sub-millisecond precision.
    """

    def __init__(self, query: str = "", source: str = "cli"):
        self.query = query
        self.source = source
        self.start_time = time.perf_counter()
        self.metrics = StageMetrics()

        self._stage_marks: Dict[str, float] = {"start": self.start_time}

    def mark(self, stage_name: str) -> None:
        """Records the timestamp when a stage begins or ends."""
        self._stage_marks[stage_name] = time.perf_counter()

    def record_stt(self, duration_s: float) -> None:
        """Records STT transcription duration in milliseconds."""
        self.metrics.stt_latency_ms = duration_s * 1000.0

    def start_intent(self) -> None:
        self._stage_marks["intent_start"] = time.perf_counter()

    def end_intent(self) -> None:
        if "intent_start" in self._stage_marks:
            self.metrics.intent_detection_latency_ms = (
                time.perf_counter() - self._stage_marks["intent_start"]
            ) * 1000.0

    def start_planning(self) -> None:
        self._stage_marks["planning_start"] = time.perf_counter()

    def end_planning(self) -> None:
        if "planning_start" in self._stage_marks:
            self.metrics.planning_latency_ms = (
                time.perf_counter() - self._stage_marks["planning_start"]
            ) * 1000.0

    def start_action(self) -> None:
        self._stage_marks["action_start"] = time.perf_counter()

    def end_action(self) -> None:
        if "action_start" in self._stage_marks:
            self.metrics.action_latency_ms = (
                time.perf_counter() - self._stage_marks["action_start"]
            ) * 1000.0

    def record_tts_startup(self, latency_ms: float) -> None:
        """Records time from response ready to first audible audio chunk."""
        self.metrics.tts_startup_latency_ms = latency_ms

    def mark_first_response(self) -> float:
        """
        Marks when the user experiences the first response (speech or text output).
        Calculates and returns total response latency in milliseconds.
        """
        now = time.perf_counter()
        self.metrics.total_response_latency_ms = (now - self.start_time) * 1000.0
        return self.metrics.total_response_latency_ms

    def log_breakdown(self, extra_info: str = "") -> None:
        """Outputs a structured log of the complete pipeline timing."""
        m = self.metrics
        info_str = f" ({extra_info})" if extra_info else ""
        logger.info(
            f"[LATENCY_METRICS]{info_str} "
            f"Query='{self.query[:30]}' | "
            f"STT={m.stt_latency_ms:.1f}ms | "
            f"Intent={m.intent_detection_latency_ms:.1f}ms | "
            f"Planning={m.planning_latency_ms:.1f}ms | "
            f"Action={m.action_latency_ms:.1f}ms | "
            f"TTS_Startup={m.tts_startup_latency_ms:.1f}ms | "
            f"TOTAL_RESPONSE={m.total_response_latency_ms:.1f}ms | "
            f"FastPath={m.is_fast_path}"
        )


_active_tracker: Optional[PipelineLatencyTracker] = None


def get_current_tracker() -> Optional[PipelineLatencyTracker]:
    return _active_tracker


def set_current_tracker(tracker: Optional[PipelineLatencyTracker]) -> None:
    global _active_tracker
    _active_tracker = tracker
