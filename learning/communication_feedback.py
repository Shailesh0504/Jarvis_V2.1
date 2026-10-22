# learning/communication_feedback.py
"""Feedback Detection, User Correction Parser, and Confidence Adjustment for LCE."""

import re
from typing import Optional, Tuple


class CommunicationFeedback:
    """Classifies user feedback and computes bounded confidence adjustments."""

    POSITIVE_EXPLICIT_PATTERNS = [
        r"\b(?:haan|yes|sahi|bilkul|correct|perfect|good|haan\s+yehi|kar\s+do|wahi|ha|yeah|yup)\b"
    ]

    NEGATIVE_REJECTION_PATTERNS = [
        r"\b(?:nahi|galat|wrong|ye\s+nahi|dusra\s+wala|maine\s+ye\s+nahi\s+kaha|phir\s+se\s+suno|no|nah|nope|stop)\b"
    ]

    CORRECTION_LEAD_PATTERNS = [
        r"\b(?:nahi|galat|wrong|not|instead|par)\b[,\s]+(.*)",
        r"(.*?)\s+\b(?:bola\s+tha|kaha\s+tha|karna\s+tha|open\s+karo)\b"
    ]

    @classmethod
    def classify_feedback(cls, text: str) -> Optional[str]:
        """Classifies text as positive, negative rejection, or negative correction."""
        lowered = text.strip().lower()
        if not lowered:
            return None

        # Check for explicit correction (e.g. "nahi, excel bola tha", "galat word kholo")
        if (lowered.startswith("nahi ") or lowered.startswith("nahi,") or lowered.startswith("galat ") or lowered.startswith("wrong ")) and len(lowered.split()) > 1:
            return "negative_correction"

        for pat in cls.NEGATIVE_REJECTION_PATTERNS:
            if re.fullmatch(pat, lowered) or lowered in ["nahi", "galat", "wrong", "no"]:
                return "negative_rejection"

        for pat in cls.POSITIVE_EXPLICIT_PATTERNS:
            if re.fullmatch(pat, lowered) or lowered in ["haan", "yes", "sahi", "bilkul", "correct", "perfect", "kar do", "ha"]:
                return "positive_explicit"

        return None

    @classmethod
    def extract_correction_target(cls, text: str) -> Optional[str]:
        """Extracts corrected intent or entity from phrases like 'Nahi, Excel bola tha' -> 'Excel'."""
        lowered = text.strip().lower()
        # "nahi, excel bola tha" -> "excel"
        m1 = re.search(r"\b(?:nahi|galat|wrong)\b[,\s]+(.+?)(?:\s+(?:bola\s+tha|kaha\s+tha|karna\s+tha|chahiye))?$", lowered)
        if m1:
            res = m1.group(1).strip()
            # remove fillers
            res = re.sub(r"\b(?:bola|kaha|tha|karna|chahiye|mein|me|ko|ka|ki)\b", "", res).strip()
            if res:
                return res
        return None

    @staticmethod
    def get_confidence_delta(feedback_type: str) -> float:
        """Returns the recommended confidence adjustment step."""
        deltas = {
            "positive_explicit": +0.15,
            "positive_implicit": +0.05,
            "negative_rejection": -0.10,
            "negative_correction": -0.15,
        }
        return deltas.get(feedback_type, 0.0)
