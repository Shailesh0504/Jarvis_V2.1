# learning/communication_normalizer.py
"""Communication Normalizer & Multi-tier Utterance Tokenizer for LCE."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Optional


@dataclass
class UtteranceTokens:
    """Preserves distinct representations of the utterance across the LCE pipeline."""
    raw_text: str
    normalized_text: str
    corrected_text: str
    language: str = "hinglish"
    confidence: float = 1.0
    context_key: str = "global"
    interpreted_meaning: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)


class CommunicationNormalizer:
    """Handles text normalization, language detection, phonetic/STT fixes, and vocabulary replacement."""

    COMMON_PHONETIC_REPLACEMENTS = {
        r"\bhe\b": "hai",
        r"\bkro\b": "karo",
        r"\bbandh\b": "band",
        r"\bmolakat\b": "mulaqat",
        r"\bmolaqat\b": "mulaqat",
        r"\bmulakat\b": "mulaqat",
        r"\bplz\b": "please",
        r"\bpls\b": "please",
        r"\byoutub\b": "youtube",
        r"\butube\b": "youtube",
        r"\bchrom\b": "chrome",
        r"\bexcl\b": "excel",
        r"\bxcel\b": "excel",
        r"\bcalculater\b": "calculator",
        r"\bnotepd\b": "notepad",
        r"\bvlc\s+player\b": "vlc",
        r"\bchala\s+na\b": "chalao",
        r"\bchala\s+do\b": "chalao",
        r"\bkhol\s+do\b": "kholo",
        r"\bkhol\s+de\b": "kholo",
    }

    HINDI_INDIC_RANGE = re.compile(r"[\u0900-\u097F]")

    @classmethod
    def detect_language(cls, text: str) -> str:
        """Heuristic language detection: 'hindi', 'english', or 'hinglish'."""
        if cls.HINDI_INDIC_RANGE.search(text):
            return "hindi"
        lowered = text.lower()
        hindi_markers = {
            "karo", "kholo", "chalao", "band", "batao", "dikhao", "hai", "kya", "ka", "ki",
            "ke", "ko", "se", "aur", "ye", "yeh", "woh", "wahi", "usko", "isko", "nahi", "haan"
        }
        words = set(re.findall(r"[a-z]+", lowered))
        overlap = words.intersection(hindi_markers)
        if overlap:
            return "hinglish"
        return "english"

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Strips noise, standardizes whitespace, and normalizes casing while preserving file paths and URLs."""
        if not text:
            return ""
        s = text.strip().lower()
        # Remove exclamation marks, question marks, and trailing periods
        s = re.sub(r"[?!;]+", " ", s)
        s = re.sub(r"(?<![a-zA-Z0-9_\\])[,]+|[,]+(?![a-zA-Z0-9_\\])", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @classmethod
    def apply_phonetic_fixes(cls, text: str) -> str:
        """Applies rule-based common STT phonetic variations."""
        res = text
        for pat, repl in cls.COMMON_PHONETIC_REPLACEMENTS.items():
            res = re.sub(pat, repl, res, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", res).strip()

    @classmethod
    def tokenize_utterance(
        cls,
        raw_text: str,
        context_key: str = "global",
        learned_vocab: Optional[Dict[str, str]] = None
    ) -> UtteranceTokens:
        """
        Builds a full UtteranceTokens object maintaining raw, normalized,
        and phonetically/vocabulary corrected forms separately.
        """
        raw = raw_text or ""
        norm = cls.normalize_text(raw)
        lang = cls.detect_language(raw)
        corr = cls.apply_phonetic_fixes(norm)

        # Apply learned user vocabulary replacements if provided
        if learned_vocab:
            for spoken, canon in learned_vocab.items():
                corr = re.sub(r"\b" + re.escape(spoken) + r"\b", canon, corr, flags=re.IGNORECASE)
            corr = re.sub(r"\s+", " ", corr).strip()

        return UtteranceTokens(
            raw_text=raw,
            normalized_text=norm,
            corrected_text=corr,
            language=lang,
            context_key=context_key
        )
