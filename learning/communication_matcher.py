# learning/communication_matcher.py
"""Fuzzy Pattern Matcher and Semantic Contextual Ranker for LCE."""

from difflib import SequenceMatcher
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.learning.communication_matcher")

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class CommunicationMatcher:
    """Fuzzy similarity evaluator and contextual candidate ranker."""

    @staticmethod
    def calculate_similarity(s1: str, s2: str) -> float:
        """Computes similarity ratio between 0.0 and 1.0."""
        s1_clean = s1.strip().lower()
        s2_clean = s2.strip().lower()
        if s1_clean == s2_clean:
            return 1.0
        if not s1_clean or not s2_clean:
            return 0.0

        if HAS_RAPIDFUZZ:
            ratio = fuzz.ratio(s1_clean, s2_clean) / 100.0
            token_ratio = fuzz.token_sort_ratio(s1_clean, s2_clean) / 100.0
            return max(ratio, token_ratio)
        else:
            return SequenceMatcher(None, s1_clean, s2_clean).ratio()

    @classmethod
    def match_best_pattern(
        cls,
        text: str,
        patterns: List[Dict[str, Any]],
        current_context: str = "global",
        min_threshold: float = 0.72
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        Finds the best matching learned communication pattern using:
        fuzzy score + context alignment + pattern confidence.
        """
        if not patterns:
            return None

        best_pattern = None
        best_score = 0.0

        for pat in patterns:
            stored_phrase = pat.get("normalized_phrase", "") or pat.get("user_phrase", "")
            base_sim = cls.calculate_similarity(text, stored_phrase)
            if base_sim < min_threshold and text not in stored_phrase and stored_phrase not in text:
                continue

            # Context boost: +0.15 if context matches exactly
            pat_context = pat.get("context_key", "global")
            context_mult = 1.15 if (pat_context != "global" and pat_context == current_context) else 1.0

            # Confidence weight
            pat_conf = float(pat.get("confidence", 0.50))
            is_confirmed = (pat.get("status") == "user_confirmed")
            confirmed_mult = 1.25 if is_confirmed else 1.0

            composite_score = (base_sim * 0.5 + pat_conf * 0.5) * context_mult * confirmed_mult
            if composite_score > best_score:
                best_score = composite_score
                best_pattern = pat

        if best_pattern and best_score >= min_threshold:
            return best_pattern, min(1.0, best_score)
        return None
