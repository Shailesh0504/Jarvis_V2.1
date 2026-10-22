# core/pipeline/request_context.py
"""
Lightweight RequestContext object for Jarvis V2.1 Pipeline.
Pure data container for turn processing across pipeline stages with zero business logic.
"""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, Optional


@dataclass
class RequestContext:
    """Encapsulates all transient request metadata for a single user turn."""
    raw_input: str
    source: str = "cli"
    start_time: float = field(default_factory=time.perf_counter)
    normalized_input: str = ""
    repaired_input: str = ""
    turn: Optional[Any] = None
    laya_decision: Optional[Any] = None
    conversation_frame: Optional[Any] = None
    active_context: Optional[Any] = None
    response: Optional[str] = None
    handled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_completed(self, response: str) -> str:
        """Sets final response and flags context as handled."""
        self.response = response
        self.handled = True
        return response
