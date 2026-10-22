# core/knowledge/calendar/year_inference.py
"""
Year Inference Engine for the Jarvis Calendar Knowledge Engine.

CRITICAL DESIGN INVARIANT:
  - The current year is ALWAYS derived from datetime.now().year at call time.
  - NEVER store or hardcode CURRENT_YEAR = <any constant> in this module.
  - Relative references ("agle saal", "pichle saal") are computed from the
    actual OS system clock at query time.
"""

import re
from datetime import datetime
from typing import Optional, Tuple


# Relative year signals
_NEXT_YEAR_TOKENS = [
    "agle saal", "agle sal", "agle year", "next year", "next saal",
    "agla saal", "agla sal", "coming year", "aane wale saal"
]
_PREV_YEAR_TOKENS = [
    "pichle saal", "pichle sal", "pichle year", "last year", "last saal",
    "pichhle saal", "guzre saal", "beet gaye saal", "previous year"
]
_CURRENT_YEAR_TOKENS = [
    "is saal", "is sal", "is year", "this year", "current year",
    "abhi", "aaj kal", "2026 mein"   # NOTE: the literal "2026" here is an alias hint
                                      # only — actual year comes from datetime.now()
]

# Explicit 4-digit year pattern
_EXPLICIT_YEAR_RE = re.compile(r'\b(20[2-9]\d)\b')


class YearInferenceEngine:
    """
    Determines the target year a user is asking about.

    Resolution order:
      1. Explicit 4-digit year mentioned by user ("2027 mein Diwali")
      2. Relative reference ("agle saal", "pichle saal", "is saal")
      3. Default → current year from datetime.now().year (no hardcoding)

    Returns (year, is_inferred) where is_inferred=True means the year was
    not explicitly mentioned by the user.
    """

    @classmethod
    def infer_year(cls, query: str) -> Tuple[int, bool]:
        """
        Returns (target_year: int, is_year_inferred: bool).
        is_year_inferred=False means the user explicitly stated the year.
        is_year_inferred=True means we inferred from context or system clock.
        """
        lowered = query.strip().lower()

        # 1. Explicit 4-digit year ("2027 mein Ganpati kab hai?")
        match = _EXPLICIT_YEAR_RE.search(lowered)
        if match:
            explicit_year = int(match.group(1))
            return explicit_year, False

        # 2. Relative references
        # "pichle saal" → current_year - 1
        if any(tok in lowered for tok in _PREV_YEAR_TOKENS):
            return datetime.now().year - 1, True

        # "agle saal" → current_year + 1
        if any(tok in lowered for tok in _NEXT_YEAR_TOKENS):
            return datetime.now().year + 1, True

        # "is saal" / "this year" → current year (same as default but explicit in query)
        if any(tok in lowered for tok in _CURRENT_YEAR_TOKENS):
            return datetime.now().year, True

        # 3. Default: use system clock — NEVER a hardcoded constant
        return datetime.now().year, True

    @classmethod
    def extract_explicit_year(cls, query: str) -> Optional[int]:
        """Returns the explicitly mentioned year, or None if none found."""
        match = _EXPLICIT_YEAR_RE.search(query.lower())
        return int(match.group(1)) if match else None
