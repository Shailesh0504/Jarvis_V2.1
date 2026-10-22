# brain/conversation/normalizer.py
"""
Hinglish, Hindi, and English Conversational Text Normalizer.
Cleans casing, punctuation, repeated letters, phonetic variations, and transliteration differences
without losing the conversational nuance or intent.
"""

import re
from typing import Dict, List, Set


class ConversationNormalizer:
    """Normalizes informal, spoken, or imperfect speech-to-text Hinglish/English transcripts."""

    TRANSLITERATION_MAP: Dict[str, str] = {
        # Transliteration variations for Affirmations & Negations
        "haa": "haan",
        "ha": "haan",
        "han": "haan",
        "haaa": "haan",
        "haaan": "haan",
        "yes": "haan",
        "yeah": "haan",
        "yep": "haan",
        "nhi": "nahi",
        "nahin": "nahi",
        "naa": "nahi",
        "nah": "nahi",
        "no": "nahi",
        "nope": "nahi",
        "mat": "nahi",

        # Transliteration variations for Acknowledgements
        "accha": "achha",
        "acha": "achha",
        "axha": "achha",
        "thik": "theek",
        "thik hai": "theek hai",
        "theekh": "theek",
        "thnx": "thanks",
        "thx": "thanks",
        "tq": "thanks",
        "thanku": "thanks",
        "thankyou": "thanks",
        "shukriya": "thanks",
        "sukriya": "thanks",
        "dhanyawad": "thanks",
        "dhanyavad": "thanks",

        # Question Words
        "kyu": "kyun",
        "kyuu": "kyun",
        "kyoon": "kyun",
        "kyo": "kyun",
        "kese": "kaise",
        "kase": "kaise",
        "kaise?": "kaise",
        "kaha": "kahan",
        "kidhar": "kahan",
        "kon": "kaun",
        "kaunsa": "kaunsa",
        "konsa": "kaunsa",

        # Fillers & Informal Terms
        "jarvis": "jarvis",
        "jarwis": "jarvis",
        "jarvis ji": "jarvis",
        "zara": "zara",
        "jara": "zara",
        "suno": "sun",
        "sunna": "sun",
        "sun na": "sun",
        "bata": "batao",
        "bata na": "batao",
        "bataiye": "batao",
    }

    FILLER_WORDS: Set[str] = {
        "uh", "um", "ah", "er", "arre", "arey", "bhai", "yaar", "dost", "please", "zara", "na", "toh"
    }

    @classmethod
    def collapse_repeated_characters(cls, text: str) -> str:
        """
        Collapses 3+ consecutive repeated characters into 1.
        e.g. 'haaaan' -> 'han' (which maps to 'haan'), 'sooooorry' -> 'sorry', 'pleaaase' -> 'please'.
        """
        return re.sub(r'([a-zA-Z])\1{2,}', r'\1', text)

    @classmethod
    def normalize_transliteration(cls, text: str) -> str:
        """Applies word-level phonetic and transliteration standardizations."""
        words = text.split()
        normalized_words = []
        for w in words:
            clean_w = w.lower()
            replacement = cls.TRANSLITERATION_MAP.get(clean_w, clean_w)
            normalized_words.append(replacement)
        return " ".join(normalized_words)

    @classmethod
    def clean(cls, text: str, remove_fillers: bool = False) -> str:
        """
        Full conversational normalization pipeline:
        1. Lowercasing & trimming
        2. Repeated character collapsing
        3. Punctuation handling
        4. Transliteration mapping
        5. Optional filler stripping
        """
        if not text:
            return ""

        raw = text.strip().lower()

        # Collapse repeated characters (e.g. 'haaaan' -> 'haan')
        collapsed = cls.collapse_repeated_characters(raw)

        # Replace punctuation with spaces
        cleaned = re.sub(r'[,!;\.:\?]', ' ', collapsed)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Word-level transliteration normalization
        normalized = cls.normalize_transliteration(cleaned)

        if remove_fillers:
            words = [w for w in normalized.split() if w not in cls.FILLER_WORDS]
            normalized = " ".join(words)

        return re.sub(r'\s+', ' ', normalized).strip()

    @classmethod
    def is_question(cls, text: str) -> bool:
        """Detects whether user text is a question (via '?' or wh-question words)."""
        raw = text.strip().lower()
        if "?" in raw:
            return True
        question_words = [
            "kya", "kyun", "kaise", "kab", "kahan", "kaun", "kitna", "kitne",
            "what", "why", "how", "when", "where", "who", "which", "whose", "can you", "could you"
        ]
        words = raw.split()
        return any(qw in words for qw in question_words)
