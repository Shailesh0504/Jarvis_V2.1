# core/semantic/gating.py
"""Conversational gating, chitchat filter, and verbal correction interceptor for NLU."""

import re
from typing import Set, List

GREETINGS_AND_COURTESIES: Set[str] = {
    "hi", "hello", "kya haal hai", "kaise ho", "kya kar rahe ho", "kuch nahi",
    "good morning", "good night", "bye", "thanks", "thank you", "sorry", "koi baat nahi"
}

CHITCHAT_WORDS: Set[str] = {"joke", "chutkula", "kahani", "story", "shayari"}

CORRECTION_RE = re.compile(
    r'\b(?:nahi|no|galat|wrong)\b.*?\b(?:nahi|not|instead|mat)\b',
    flags=re.IGNORECASE
)

CONVERSATIONAL_PATTERNS: List[re.Pattern] = [
    re.compile(r'\b(?:main\s+)?(?:abhi\s+)?(?:khana\s+khane|office|sone|nahane|walk\s+pe|lunch|dinner)\s+(?:ja\s+raha|nikal\s+raha|kar\s+raha)\b', re.IGNORECASE),
    re.compile(r'\b(?:meri\s+(?:baat|awaaz)\s+sun\s+rahe\s+ho|are\s+you\s+listening|can\s+you\s+hear\s+me)\b', re.IGNORECASE),
    re.compile(r'\b(?:tumhare\s+hisaab\s+se|kya\s+karna\s+chahiye|what\s+do\s+you\s+think|kya\s+opinion)\b', re.IGNORECASE),
    re.compile(r'\b(?:ek\s+baat\s+bata|suno\s+ek\s+baat|let\s+me\s+ask|aur\s+batao|phir\s+kya\s+hua)\b', re.IGNORECASE),
    re.compile(r'\b(?:main\s+theek\s+hoon|sab\s+theek\s+hai|sab\s+badhiya|all\s+good|main\s+jakar\s+khata)\b', re.IGNORECASE),
    re.compile(r'\b(?:pehle|kab\s+se|itni\s+der\s+se|tab\s+se)\b.*?\b(?:listen|sun|respond|awaz|awaaz|bol\s+raha|bol\s+rahi|response)\b', re.IGNORECASE),
    re.compile(r'\b(?:kyon|kyu|why)\b.*?\b(?:nahi\s+sun|nahi\s+listen|respond\s+nahi|reply\s+nahi|pick\s+nahi|sun\s+nahi|listen\s+nahi|response\s+nahi)\b', re.IGNORECASE),
    re.compile(r'\b(?:sun\s+nahi\s+rahi?|listen\s+nahi\s+kar\s+rahi?|awaz\s+nahi\s+aa\s+rahi|awaaz\s+nahi\s+aa\s+rahi|sunai\s+nahi\s+de\s+raha|response\s+nahi\s+de\s+rahe?)\b', re.IGNORECASE),
    re.compile(r'\b(?:listen\s+kar|sun\s+le|sun\s+na)\b.*?\b(?:nonsense|pagal|bakwas|bakwaas|bewakoof|idiot)\b', re.IGNORECASE),
    re.compile(r'\b(?:nonsense|pagal|bakwas|bakwaas|bewakoof|idiot)\b.*?\b(?:listen|sun|bol|awaz|awaaz)\b', re.IGNORECASE)
]


def should_bypass_command_parsing(lowered: str) -> bool:
    """
    Returns True if the text is conversational chitchat, greetings,
    jokes, or verbal correction that should bypass command routing.
    """
    if lowered in GREETINGS_AND_COURTESIES:
        return True

    if any(w in lowered for w in CHITCHAT_WORDS):
        return True

    # Exclude verbal corrections so the learning layer can intercept them
    if CORRECTION_RE.search(lowered) or lowered.startswith("nahi ") or lowered.startswith("nahi,"):
        return True

    # Everyday conversational statements
    if any(pat.search(lowered) for pat in CONVERSATIONAL_PATTERNS):
        return True

    return False
