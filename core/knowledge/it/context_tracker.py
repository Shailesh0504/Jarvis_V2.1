# core/knowledge/it/context_tracker.py
"""
Multi-Turn IT Conversation Context Tracker.
Tracks active IT workflow, domain, concept, and procedure step so that
contextual follow-ups like "ab next kya karu?", "aur kya check karu?",
or "iska port kya hai?" can resolve naturally without asking the user to repeat.
"""

from typing import Any, Dict, List, Optional
import time
import logging

from .models import ITConcept, ITDomain, ITQuestionType, ITTroubleshootingGuide

logger = logging.getLogger("jarvis.core.knowledge.it.context")


class ITContextTracker:
    """Maintains short-term conversational context for IT technical assistance."""

    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self._active_domain: Optional[ITDomain] = None
        self._active_concept: Optional[ITConcept] = None
        self._active_troubleshooting: Optional[ITTroubleshootingGuide] = None
        self._active_procedure_steps: List[str] = []
        self._current_step_index: int = 0
        self._last_interaction_time: float = 0.0

    def update_context(
        self,
        domain: Optional[ITDomain] = None,
        concept: Optional[ITConcept] = None,
        troubleshooting: Optional[ITTroubleshootingGuide] = None,
        steps: Optional[List[str]] = None
    ) -> None:
        """Updates active context with the latest resolved topic."""
        self._last_interaction_time = time.time()
        if domain:
            self._active_domain = domain
        if concept:
            self._active_concept = concept
            self._active_domain = concept.domain
            if concept.how_to_steps:
                self._active_procedure_steps = concept.how_to_steps
                self._current_step_index = 0
        if troubleshooting:
            self._active_troubleshooting = troubleshooting
            self._active_domain = troubleshooting.domain
            if troubleshooting.possible_fixes:
                self._active_procedure_steps = troubleshooting.possible_fixes
                self._current_step_index = 0
        if steps:
            self._active_procedure_steps = steps
            self._current_step_index = 0

    def is_context_active(self) -> bool:
        """Checks whether the cached context is within the TTL window."""
        if self._last_interaction_time == 0:
            return False
        return (time.time() - self._last_interaction_time) <= self.ttl_seconds

    def is_continuation_query(self, query: str) -> bool:
        """Detects if query is an anaphoric follow-up like 'ab next kya karu?'."""
        lowered = query.strip().lower()
        triggers = [
            "ab next kya", "next kya", "aur kya", "fir kya", "phir kya",
            "what next", "what is next", "next step", "agla step", "aage kya",
            "aur batao", "iska port", "iske baad"
        ]
        return any(t in lowered for t in triggers)

    def get_next_step(self) -> Optional[str]:
        """Returns the next procedure step in the ongoing workflow."""
        if not self.is_context_active() or not self._active_procedure_steps:
            return None

        self._current_step_index += 1
        if self._current_step_index < len(self._active_procedure_steps):
            return self._active_procedure_steps[self._current_step_index]
        elif self._current_step_index == len(self._active_procedure_steps):
            return "Configuration complete ho chuki hai. Verification ke liye test commands run karein."
        return None

    @property
    def active_concept(self) -> Optional[ITConcept]:
        if self.is_context_active():
            return self._active_concept
        return None

    @property
    def active_troubleshooting(self) -> Optional[ITTroubleshootingGuide]:
        if self.is_context_active():
            return self._active_troubleshooting
        return None

    @property
    def active_domain(self) -> Optional[ITDomain]:
        if self.is_context_active():
            return self._active_domain
        return None

    def clear(self) -> None:
        """Resets active context."""
        self._active_domain = None
        self._active_concept = None
        self._active_troubleshooting = None
        self._active_procedure_steps = []
        self._current_step_index = 0
        self._last_interaction_time = 0.0
