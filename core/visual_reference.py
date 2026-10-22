# core/visual_reference.py
"""
Visual Search Memory and Follow-Up Reference Resolution Manager.

Provides:
1. `last_visual_search` session buffer:
   Stores query, window HWND, process, active tab, detected matches, and selected index.
2. Deictic reference resolution:
   Resolves 'is par', 'isko', 'ise', 'isse', 'us word', 'wahan' to the previously located target.
3. Ordinal multi-match selection:
   Resolves 'pehle wale' (1st), 'doosre wale' (2nd), 'teesre wale' (3rd), 'aakhiri wale' (last),
   'next wale' across the stored match list.
"""

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional

from core.text_matcher import VisualTextMatch

logger = logging.getLogger("jarvis.core.visual_reference")


@dataclass
class VisualSearchSession:
    query: str
    window_hwnd: int
    application: str
    tab: str = ""
    matches: List[VisualTextMatch] = field(default_factory=list)
    selected_index: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def selected_match(self) -> Optional[VisualTextMatch]:
        if self.matches and 0 <= self.selected_index < len(self.matches):
            return self.matches[self.selected_index]
        return None

    def is_valid(self, max_age_seconds: float = 300.0) -> bool:
        """Returns True if the stored visual search is recent and has matches."""
        return bool(self.matches and (time.time() - self.timestamp <= max_age_seconds))


class VisualReferenceManager:
    """Authoritative manager for visual search context and conversational reference resolution."""

    _instance = None

    # Deictic pronouns and referential phrases
    DEICTIC_PATTERNS = [
        re.compile(r"\b(?:is|iss|ispar|is\s+par|ispe|is\s+pe|isko|isse|ise|isey|us|uspar|us\s+par|uspe|us\s+pe|usko|usse|use)\b", re.IGNORECASE),
        re.compile(r"\b(?:us\s+word|is\s+word|ye\s+word|yeh\s+word|us\s+text|is\s+text)\b", re.IGNORECASE),
        re.compile(r"\b(?:wahan|idhar|yahan)\b", re.IGNORECASE),
        re.compile(r"\b(?:it|that|this)\b", re.IGNORECASE)
    ]

    # Ordinal keywords mapping to 0-indexed integers
    ORDINAL_MAP = {
        "first": 0, "1st": 0, "pehle": 0, "pehla": 0, "pehli": 0, "one": 0, "ek": 0,
        "second": 1, "2nd": 1, "doosre": 1, "doosra": 1, "doosri": 1, "dusre": 1, "dusra": 1, "two": 1, "do": 1,
        "third": 2, "3rd": 2, "teesre": 2, "teesra": 2, "teesri": 2, "tisre": 2, "tisra": 2, "three": 2, "teen": 2,
        "fourth": 3, "4th": 3, "chauthe": 3, "chautha": 3, "four": 3, "chaar": 3,
        "fifth": 4, "5th": 4, "paanchve": 4, "paanchva": 4, "five": 4, "paanch": 4,
        "last": -1, "aakhiri": -1, "antim": -1
    }

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._last_search: Optional[VisualSearchSession] = None

    def store_search(
        self,
        query: str,
        window_hwnd: int,
        application: str,
        matches: List[VisualTextMatch],
        tab: str = "",
        selected_index: int = 0
    ) -> VisualSearchSession:
        """Stores a completed visual search into memory."""
        session = VisualSearchSession(
            query=query,
            window_hwnd=window_hwnd,
            application=application,
            tab=tab,
            matches=matches,
            selected_index=max(0, min(selected_index, len(matches) - 1)) if matches else 0,
            timestamp=time.time()
        )
        self._last_search = session
        logger.info(
            f"[VISUAL_REF] Stored visual search: query='{query}' matches={len(matches)} "
            f"selected={session.selected_index} app='{application}'"
        )
        return session

    def get_last_search(self) -> Optional[VisualSearchSession]:
        """Returns the most recent visual search session if still valid."""
        if self._last_search and self._last_search.is_valid():
            return self._last_search
        return None

    def set_selected_index(self, index: int) -> bool:
        """Sets the selected match index in the active visual search session."""
        last = self.get_last_search()
        if last and last.matches:
            if index == -1:
                idx = len(last.matches) - 1
            else:
                idx = max(0, min(index, len(last.matches) - 1))
            last.selected_index = idx
            return True
        return False

    def is_deictic_reference(self, utterance: str) -> bool:
        """Checks if utterance contains a deictic reference ('is par', 'isko', 'us word', etc.)."""
        lowered = utterance.lower().strip()
        tokens = set(re.findall(r'[a-zA-Z0-9]+', lowered))
        # Direct deictic pronouns
        if tokens & {"isko", "ise", "isse", "isey", "usko", "use", "usse"}:
            return True
        for pat in self.DEICTIC_PATTERNS:
            if pat.search(lowered):
                return True
        return False

    def extract_ordinal_index(self, utterance: str) -> Optional[int]:
        """
        Extracts ordinal target index from phrase (e.g. 'doosre wale par click karo' -> 1).
        Supports English and Hindi ordinals.
        """
        lowered = utterance.lower()

        # Check for 'next wale' / 'agla'
        if any(w in lowered for w in ("next", "agla", "agli", "agle")):
            if self._last_search and self._last_search.matches:
                curr = self._last_search.selected_index
                return (curr + 1) % len(self._last_search.matches)
            return 1

        for word, idx in self.ORDINAL_MAP.items():
            pattern = rf"\b{re.escape(word)}(?:\s+wale|\s+wala|\s+wali|\s+match|\s+one)?\b"
            if re.search(pattern, lowered):
                return idx

        return None

    def resolve_reference(self, utterance: str = "", ordinal_index: Optional[int] = None) -> Optional[VisualTextMatch]:
        """
        Resolves a follow-up utterance to a VisualTextMatch using stored visual search memory.
        Handles both deictic references ('ab is par click karo') and ordinal selection ('doosre wale par').
        """
        last = self.get_last_search()
        if not last or not last.matches:
            return None

        # Check ordinal index specification
        ord_idx = ordinal_index if ordinal_index is not None else self.extract_ordinal_index(utterance)
        if ord_idx is not None:
            if ord_idx == -1:
                idx = len(last.matches) - 1
            else:
                idx = max(0, min(ord_idx, len(last.matches) - 1))
            last.selected_index = idx
            logger.info(f"[VISUAL_REF] Resolved ordinal match #{idx + 1} of {len(last.matches)}")
            return last.matches[idx]

        # Check deictic reference
        if self.is_deictic_reference(utterance):
            logger.info(f"[VISUAL_REF] Resolved deictic reference to match #{last.selected_index + 1}")
            return last.selected_match

        return None

    def clear(self):
        """Clears stored visual search context."""
        self._last_search = None


_visual_reference_instance: Optional[VisualReferenceManager] = None


def get_visual_reference_manager() -> VisualReferenceManager:
    """Returns singleton instance of VisualReferenceManager."""
    global _visual_reference_instance
    if _visual_reference_instance is None:
        _visual_reference_instance = VisualReferenceManager()
    return _visual_reference_instance
