# core/semantic/models.py
"""Unified data contracts for Core Brain Semantic NLU."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class IntentName(str):
    """
    Enhanced string class for Intent names that seamlessly equates
    OPEN_APPLICATION with OPEN_APP, and TEMP_FILE_CLEANUP / RECYCLE_BIN_CLEANUP
    with SYSTEM_MAINTENANCE for full backward compatibility across tests and
    subsystems while presenting canonical intent names.
    """
    OPEN_APPLICATION = "OPEN_APPLICATION"
    OPEN_APP = "OPEN_APP"
    TEMP_FILE_CLEANUP = "TEMP_FILE_CLEANUP"
    RECYCLE_BIN_CLEANUP = "RECYCLE_BIN_CLEANUP"
    SYSTEM_MAINTENANCE = "SYSTEM_MAINTENANCE"
    PLAY_MEDIA = "PLAY_MEDIA"
    SEARCH_WEB = "SEARCH_WEB"
    CLOSE_APPLICATION = "CLOSE_APPLICATION"
    EQUITY_RESEARCH = "EQUITY_RESEARCH"

    _EQUIVALENCE_SETS = (
        {"OPEN_APPLICATION", "OPEN_APP"},
        {"TEMP_FILE_CLEANUP", "SYSTEM_MAINTENANCE"},
        {"RECYCLE_BIN_CLEANUP", "SYSTEM_MAINTENANCE"},
    )

    def __eq__(self, other):
        if other is None:
            return False
        str_other = str(other)
        str_self = str(self)
        if str_other == str_self:
            return True
        for group in self._EQUIVALENCE_SETS:
            if str_self in group and str_other in group:
                return True
        return super().__eq__(other)

    def __hash__(self):
        str_self = str(self)
        for group in self._EQUIVALENCE_SETS:
            if str_self in group:
                return hash(min(group))
        return super().__hash__()


@dataclass
class SemanticAction:
    """Structured action intent emitted by the Core Brain NLU."""
    intent: str                            # e.g. "PLAY_MEDIA", "OPEN_APPLICATION", "SEARCH_WEB"
    service: str                           # e.g. "youtube", "vlc", "browser", "windows", "system"
    action: str                            # e.g. "search_and_play", "launch_app", "open_youtube"
    query: Optional[str] = None            # e.g. "Tera Surroor"
    parameters: Dict[str, Any] = field(default_factory=dict)
    needs_clarification: bool = False      # True if required parameter is missing
    clarification_prompt: Optional[str] = None
    missing_slot: Optional[str] = None
    confidence: float = 1.0

    @property
    def entity(self) -> Optional[str]:
        """Convenience property extracting the primary target entity."""
        return self.parameters.get("entity") or self.parameters.get("app_name") or self.query

    @property
    def modifier(self) -> Optional[str]:
        """Convenience property extracting conversational modifiers (e.g. ALSO)."""
        return self.parameters.get("modifier")

    @property
    def action_type(self) -> Optional[str]:
        """Convenience property extracting the canonical action type (e.g. CLEAN)."""
        return self.parameters.get("action_type") or self.parameters.get("action")
