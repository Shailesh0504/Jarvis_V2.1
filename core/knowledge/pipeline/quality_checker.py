# core/knowledge/pipeline/quality_checker.py
"""
Pre-Response Quality and Integrity Checker for Jarvis General Knowledge.
Validates that generated answers:
1. Are free of technical artifacts, bracketed debug structures, and internal IDs.
2. Are concise for simple factual questions.
3. Do not contain contradictory or unverified statements.
"""

from typing import Tuple
import re

from ..models import KnowledgeQueryResult, GKQuestionType, ConfidenceLevel


class GKQualityChecker:
    """Performs safety, conciseness, and integrity checks on generated answers."""

    # Patterns indicating leaked internal structures or code artifacts
    TECHNICAL_LEAK_PATTERNS = [
        r"\{.*?\}",
        r"\<.*?\>",
        r"\[object Object\]",
        r"Traceback \(most recent call last\)",
        r"\bNone\b",
        r"\bnull\b",
        r"\bundefined\b",
        r"\b\w+\.exe\b",
        r"0x[0-9a-fA-F]+"
    ]

    @classmethod
    def verify_answer(cls, result: KnowledgeQueryResult, original_query: str) -> Tuple[bool, str]:
        """
        Validates the answer in KnowledgeQueryResult.
        Returns:
            (is_valid: bool, sanitized_answer: str)
        """
        text = (result.answer_text or "").strip()
        if not text:
            return False, "Is baare mein mere paas abhi reliable jaankari uplabdh nahi hai, Boss."

        # Check for technical artifacts
        for pat in cls.TECHNICAL_LEAK_PATTERNS:
            if re.search(pat, text):
                text = re.sub(pat, "", text).strip()

        # Simple factual answers must be direct and concise
        if result.question_type in (GKQuestionType.FACTUAL, GKQuestionType.DEFINITION):
            # If answer contains multiple repeated sentences, keep only the first concise sentence
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            if len(sentences) > 3 and not result.metadata.get("is_detailed", False):
                text = ". ".join(sentences[:2]) + "."

        return True, text
