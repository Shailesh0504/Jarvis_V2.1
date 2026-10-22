# core/knowledge/pipeline/normalizer.py
"""
Multilingual Speech/Text Normalizer & STT Error Recovery.
Strips filler words, normalizes whitespace, cleans colloquial markers,
recovers voice transcription/STT phonetic errors, and detects language.
"""

from typing import Tuple
import re


FILLER_PHRASES = [
    r"\b(?:can\s+you\s+tell\s+me|tell\s+me|please\s+tell\s+me|please\s+batao|bataiye|batao\s+na|batao|bata\s+do|bata\s+de)\b",
    r"\b(?:jarvis\s+bhai|jarvis\s+ji|jarvis|bhai|yaar|zara|sun|arre|bhaiya|ji)\b",
    r"\b(?:mujhe\s+ye\s+batao|mujhe\s+batao|mujhe\s+jaanna\s+hai|i\s+want\s+to\s+know)\b",
    r"\b(?:do\s+you\s+know|kya\s+aapko\s+pata\s+hai|kya\s+tumhe\s+pata\s+hai)\b",
    r"\b(?:actually|basically|matlab|jaise\s+ki)\b"
]

# Common STT phonetic and transcription errors
STT_PHONETIC_REPLACEMENTS = [
    # Hindi/Hinglish STT corruptions
    (r"\bkon\s+he\b", "kaun hai"),
    (r"\bkon\s+hai\b", "kaun hai"),
    (r"\bkon\s+si\b", "kaun si"),
    (r"\bkon\s+sa\b", "kaun sa"),
    (r"\bkya\s+h\b", "kya hai"),
    (r"\bkitne\s+time\s+lagta\b", "kitna time lagta"),
    (r"\bround\s+lagati\s+hai\b", "chakkar lagati hai"),
    (r"\bround\s+lagata\s+hai\b", "chakkar lagata hai"),
    (r"\bchakar\b", "chakkar"),
    (r"\brajdhani\s+kon\s+si\s+he\b", "rajdhani kaun si hai"),
    (r"\brajdani\b", "rajdhani"),
    (r"\bpradhan\s+mantri\s+kon\s+he\b", "pradhan mantri kaun hai"),
    (r"\brashtrapati\s+kon\s+he\b", "rashtrapati kaun hai"),

    # English STT corruptions
    (r"\bprimer\s+minister\b", "prime minister"),
    (r"\bcapitol\s+of\b", "capital of"),
    (r"\bcapitol\s+city\b", "capital city"),
    (r"\bcapitol\b", "capital"),
    (r"\bcurrensy\b", "currency"),
    (r"\bpresidant\b", "president"),
    (r"\bcontinant\b", "continent"),
    (r"\bphotosinthesis\b", "photosynthesis"),
    (r"\bgravity\s+kyu\b", "gravity kyun"),
    (r"\bwhos\b", "who is"),
    (r"\bwhats\b", "what is"),
    (r"\bwhere\s+is\s+the\s+capital\b", "what is the capital"),

    # Festival name STT corrections
    (r"\bganpathy\b", "ganpati"),
    (r"\bganapathy\b", "ganpati"),
    (r"\bganapati\b", "ganpati"),
    (r"\bdeepawali\b", "diwali"),
    (r"\bdipawali\b", "diwali"),
    (r"\bdipavali\b", "diwali"),
    (r"\bdeepavali\b", "diwali"),
    (r"\bjanmasthami\b", "janmashtami"),
    (r"\bjanmastami\b", "janmashtami"),
    (r"\bjanmashtmi\b", "janmashtami"),
    (r"\bnavratris\b", "navratri"),
    (r"\bnavaratri\b", "navratri"),
    (r"\bvijaya\s+dasami\b", "vijayadasami"),
    (r"\bdussera\b", "dussehra"),
    (r"\bdassehra\b", "dussehra"),
    (r"\bmahashivratri\b", "maha shivratri"),
    (r"\brakhi\b", "raksha bandhan"),
    (r"\bguru\s+poornima\b", "guru purnima"),
    (r"\bvaisakhi\b", "baisakhi"),
    (r"\bvaishakhi\b", "baisakhi"),
]


class GKNormalizer:
    """Normalizes noisy spoken or typed utterances for meaning-first GK interpretation."""

    @classmethod
    def normalize(cls, text: str) -> Tuple[str, str, float]:
        """
        Normalizes input text.
        Returns:
            cleaned_text: Cleaned and normalized text with filler words stripped and STT typos fixed.
            detected_language: 'hi', 'en', or 'hinglish'
            confidence: float (0.0 - 1.0)
        """
        raw = text.strip()
        if not raw:
            return "", "en", 0.0

        lowered = raw.lower()

        # 1. Apply phonetic STT corrections
        corrected = lowered
        correction_applied = False
        for pat, repl in STT_PHONETIC_REPLACEMENTS:
            if re.search(pat, corrected):
                corrected = re.sub(pat, repl, corrected)
                correction_applied = True

        # 2. Strip filler words and conversational fluff
        cleaned = corrected
        for pat in FILLER_PHRASES:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)

        # 3. Clean punctuation and normalize whitespace
        cleaned = re.sub(r"[?!.,;:\"'’‘]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 4. Detect language
        lang = cls._detect_language(cleaned or lowered)

        # Confidence: High by default, slight drop if aggressive STT correction was applied
        conf = 0.95 if not correction_applied else 0.88
        return cleaned, lang, conf

    @classmethod
    def _detect_language(cls, text: str) -> str:
        hindi_tokens = {
            "kya", "hai", "hain", "kaun", "kaunsa", "kaunsi", "kisne", "kab", "kahan", "kaha",
            "kyun", "kyu", "desh", "rajdhani", "mudra", "hota", "hoti", "hote", "pehle", "pehli",
            "sabse", "ki", "ka", "ke", "mein", "se", "ko", "par", "wahan", "unka", "unki", "unke",
            "kitna", "kitni", "kitne", "der", "ghante", "din", "saal", "batao", "suraj", "prithvi",
            "grah", "antariksh", "aasman", "taare", "paudhe", "pani", "baarish"
        }
        english_tokens = {
            "what", "is", "are", "who", "when", "where", "why", "how", "which", "does", "do",
            "capital", "currency", "president", "minister", "prime", "formula", "symbol",
            "distance", "speed", "travel", "travels", "earth", "sun", "moon", "planet", "largest",
            "smallest", "tallest", "independent", "revolution", "orbit", "takes", "light"
        }

        words = set(re.findall(r"\b\w+\b", text.lower()))
        hi_count = len(words.intersection(hindi_tokens))
        en_count = len(words.intersection(english_tokens))

        if hi_count > 0 and en_count > 0:
            return "hinglish"
        elif hi_count > 0:
            return "hi"
        return "en"
