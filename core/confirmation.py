# core/confirmation.py
"""
Centralized Affirmation and Cancellation Intent Detection for Jarvis V2.1.
Authoritative source of truth for user confirmations and rejections across
DialogManager, ProactiveActionExecutor, and DecisionCore.
"""

from enum import Enum
import re
from typing import Optional


class ConfirmationType(str, Enum):
    """Normalized confirmation status."""
    AFFIRMATIVE = "AFFIRMATIVE"
    NEGATIVE = "NEGATIVE"
    AMBIGUOUS = "AMBIGUOUS"
    UNSPECIFIED = "UNSPECIFIED"


def normalize_confirmation_text(text: str) -> str:
    """
    Normalizes confirmation input:
    - Lowercase & trim
    - Strip apostrophes (e.g. don't -> dont)
    - Remove punctuation (preserving letters, digits, whitespace, Devanagari \\u0900-\\u097F)
    - Collapse repeated spaces
    """
    if not text:
        return ""
    clean = str(text).strip().lower()
    # Strip apostrophes first so contractions like don't become dont rather than 'don t'
    clean = clean.replace("'", "")
    # Remove punctuation except letters, digits, spaces, and Hindi Devanagari range
    clean = re.sub(r"[^\w\s\u0900-\u097F]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


# Optional polite / conversational prefix (e.g. "sir haan", "boss kar do", "theek hai kar do")
_CONVERSATIONAL_PREFIX = r"(?:(?:sir|boss|bhai|yaar|ji|please|arey|arrey|achha|theek hai|thik hai)\s+)*"

# Precompiled regex for complete affirmative matching in English, Roman Hindi, Hinglish, and Devanagari
_AFFIRMATION_BODY = (
    # Exact single/short affirmative words
    r"y|yes|yeah|yep|yup|sure|ok|okay|alright|proceed|confirm|confirmed|accept|continue|please|"
    r"ha|haan|han|haa|ji|bilkul|karo|"
    # Devanagari words
    r"हाँ|हां|जी|बिल्कुल|अवश्य|"
    # Multi-word affirmative phrases
    r"why\s+not|go\s+ahead|do\s+it|yes\s+please|okay\s+do\s+it|sure\s+thing|"
    r"ji\s+haan|theek\s+hai|thik\s+hai|sahi\s+hai|bilkul\s+kar\s+do|theek\s+hai\s+kar\s+do|"
    r"kar\s+do|kardo|kr\s+do|haan\s+kar\s+do|ha\s+kar\s+do|han\s+kar\s+do|haan\s+kar|"
    r"haan\s+bhai|ha\s+bhai|ha\s+bhai\s+kar\s+do|haan\s+bhai\s+kar\s+do|yes\s+kar\s+do|"
    r"haan\s+restart\s+kar\s+do|ha\s+restart\s+kar\s+do|ji\s+restart\s+kar\s+do|restart\s+kar\s+do|restart\s+karo|"
    r"haan\s+shutdown\s+kar\s+do|shutdown\s+kar\s+do|shutdown\s+karo|band\s+kar\s+do|pc\s+band\s+kar\s+do|"
    r"chala\s+do|chalado|khol\s+do|kholdo|kholo|khol\s+de|play\s+karo|yaad\s+rakho|save\s+kar\s+lo|bana\s+do|automate\s+kar\s+do|"
    r"open\s+kar\s+do|open\s+kardo|open\s+karo|open\s+it|yes\s+open\s+it|haan\s+open\s+kar\s+do|haan\s+open\s+karo|ha\s+open\s+kar\s+do|"
    r"wahi|wahi\s+wali|wahi\s+kholo|wahi\s+chalao|"
    # Devanagari multi-word phrases
    r"जी\s+हाँ|जी\s+हां|ठीक\s+है|कर\s+दो|हाँ\s+कर\s+दो|हां\s+कर\s+दो|हाँ\s+कर|हाँ\s+भाई"
)

AFFIRMATION_PATTERN = re.compile(
    rf"^{_CONVERSATIONAL_PREFIX}(?:{_AFFIRMATION_BODY})$",
    re.IGNORECASE
)

# Precompiled regex for complete negation/cancellation matching in English, Roman Hindi, Hinglish, and Devanagari
_CANCELLATION_BODY = (
    # Exact single/short cancellation words
    r"n|no|nope|nah|cancel|abort|stop|reject|"
    r"nahi|nahin|nhi|na|naa|"
    # Devanagari single words
    r"नहीं|नही|ना|रद्द|"
    # Multi-word cancellation phrases
    r"cancel\s+it|cancel\s+karo|cancel\s+kar\s+do|don\'?t|dont|don\'?t\s+do\s+it|dont\s+do\s+it|not\s+now|nevermind|"
    r"mat\s+karo|matkaro|mat\s+kar|rehne\s+do|rehnedo|rehne\s+de|chhod\s+do|chhod\s+de|"
    r"nahi\s+rehne\s+do|nahi\s+karna|nahi\s+karo|nahi\s+chahiye|kuch\s+nahi|"
    r"open\s+mat\s+karo|mat\s+kholo|nahi\s+kholna|abhi\s+mat\s+kholo|"
    r"abhi\s+nahi|abhi\s+mat\s+karo|restart\s+mat\s+karo|shutdown\s+mat\s+karo|"
    r"baad\s+me|baad\s+mein|dusri\s+wali|dusra|dusri|other|change\s+it|koi\s+aur|new\s+one|nayi\s+wali|blank|"
    r"ruk\s+jao|"
    # Devanagari multi-word phrases
    r"मत\s+करो|रहने\s+दो|छोड़\s+दो|छोड़\s+दो|अभी\s+नहीं|रद्द\s+करो|रोक\s+दो|नहीं\s+करना|नहीं\s+करो"
)

CANCELLATION_PATTERN = re.compile(
    rf"^{_CONVERSATIONAL_PREFIX}(?:{_CANCELLATION_BODY})$",
    re.IGNORECASE
)

# Precompiled regex for ambiguous phrases where clarification should be requested
AMBIGUOUS_PATTERN = re.compile(
    r"^(?:"
    r"maybe|perhaps|not\s+sure|unsure|"
    r"dekhta\s+hoon|dekhte\s+hain|dekh\s+ke\s+batata\s+hoon|dekh\s+ke\s+bataunga|"
    r"pata\s+nahi|kya\s+pata|shayad|shyd|sochta\s+hoon|soch\s+raha\s+hoon|baad\s+me\s+batata\s+hoon|"
    r"देखता\s+हूँ|देखते\s+हैं|पता\s+नहीं|शायद|क्या\s+पता"
    r")$|"
    r"\b(?:maybe|pata\s+nahi|shayad|dekhta\s+hoon|not\s+sure|kya\s+pata|पता\s+नहीं|देखता\s+हूँ|शायद)\b",
    re.IGNORECASE
)


def is_ambiguous(text: str) -> bool:
    """Returns True if the text represents an unclear or ambiguous confirmation."""
    clean = normalize_confirmation_text(text)
    if not clean:
        return False
    return bool(AMBIGUOUS_PATTERN.search(clean))


def is_cancellation(text: str) -> bool:
    """Returns True if the text represents a negative cancellation/rejection."""
    clean = normalize_confirmation_text(text)
    if not clean:
        return False
    # If phrase matches ambiguous pattern (e.g. "pata nahi"), do not treat as cancellation
    if bool(AMBIGUOUS_PATTERN.search(clean)):
        return False
    # Check regex match
    if bool(CANCELLATION_PATTERN.match(clean)):
        return True
    # Fast token checks for common Roman & Devanagari cancellations
    # Strictly for short responses (<= 3 words) without question or action command words
    tokens = clean.split()
    if len(tokens) <= 3 and any(t in {"nahi", "nahin", "nhi", "cancel", "नहीं", "नही"} for t in tokens):
        if not any(q in tokens for q in {"kyun", "kaise", "kya", "kab", "kaha", "why", "how", "what", "where", "when", "open", "kholo", "close", "band"}):
            return True
    return False


def is_affirmation(text: str) -> bool:
    """Returns True if the text represents an affirmative confirmation."""
    clean = normalize_confirmation_text(text)
    if not clean:
        return False
    # If phrase matches ambiguous pattern, do not treat as affirmation
    if bool(AMBIGUOUS_PATTERN.search(clean)):
        return False
    # Cancellation takes precedence if negation word exists
    if is_cancellation(text):
        return False
    # Check regex match
    if bool(AFFIRMATION_PATTERN.match(clean)):
        return True
    # Fast token checks for common Roman & Devanagari affirmations
    # Strictly for short responses (<= 3 words) without command verbs or question words
    tokens = clean.split()
    if len(tokens) <= 3 and any(t in {"haan", "han", "ha", "haa", "yes", "yep", "yeah", "bilkul", "हाँ", "हां", "बिल्कुल"} for t in tokens):
        if not any(cmd in tokens for cmd in {"kholo", "open", "band", "close", "restart", "shutdown", "chalao", "play", "kyun", "kaise", "kya"}):
            return True
    return False


def classify_confirmation(text: str) -> ConfirmationType:
    """Classifies user utterance into AFFIRMATIVE, NEGATIVE, AMBIGUOUS, or UNSPECIFIED."""
    if is_ambiguous(text):
        return ConfirmationType.AMBIGUOUS
    if is_cancellation(text):
        return ConfirmationType.NEGATIVE
    if is_affirmation(text):
        return ConfirmationType.AFFIRMATIVE
    return ConfirmationType.UNSPECIFIED

