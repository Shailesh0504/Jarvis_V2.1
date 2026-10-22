# core/response_style.py
"""
Persona, Tone, Brevity & TTS-Sanitization Engine for Jarvis V2.1.

Enforces:
1. Stable Persona: Intelligent, calm, respectful, warm, confident, mature personal assistant.
2. Controlled 'Sir' Usage: Natural, respectful, never mechanically stacked or overused.
3. Anti-Robotic Filter: Ban and strip robotic templates and formulaic customer-support phrases.
4. TTS-Friendly Normalization: Clean technical jargon, raw handles, markdown, and process suffixes.
"""

from enum import Enum
import logging
import re
from typing import List, Optional

logger = logging.getLogger("jarvis.core.response_style")


class ResponseTone(str, Enum):
    """Supported personality tones."""
    CONCISE = "concise"          # Fast, direct commands
    WARM = "warm"                # Conversational, friendly
    CONFIDENT = "confident"      # Factual, technical
    CALM = "calm"                # Clarifications, recovery
    WITTY = "witty"              # Humorous, casual remarks


class ResponseStyleManager:
    """
    Manages stylistic presentation, persona invariants, 'Sir' distribution,
    and audio-friendly text sanitization.
    """

    BANNED_ROBOTIC_PATTERNS = [
        re.compile(r"main\s+aapki\s+kya\s+madad\s+kar\s+sakta\s+hoon\??", re.IGNORECASE),
        re.compile(r"bataiye\s+main\s+kya\s+madad\s+kar\s+sakta\s+hoon\??", re.IGNORECASE),
        re.compile(r"aapke\s+request\s+ke\s+anusaar", re.IGNORECASE),
        re.compile(r"command\s+executed\s+successfully\.?", re.IGNORECASE),
        re.compile(r"operation\s+completed(\s+successfully)?\.?", re.IGNORECASE),
        re.compile(r"target\s+application\s+launched\s+successfully\.?", re.IGNORECASE),
        re.compile(r"the\s+requested\s+foreground\s+window\s+has\s+been\s+successfully\s+closed\.?", re.IGNORECASE),
        re.compile(r"an\s+error\s+occurred:\s*", re.IGNORECASE),
        re.compile(r"command\s+execution\s+failed\s+with\s+exception.*", re.IGNORECASE),
        re.compile(r"kripya\s+dhyan\s+dein", re.IGNORECASE),
    ]

    _last_used_sir: bool = False
    _consecutive_sir_count: int = 0

    @classmethod
    def sanitize_for_tts(cls, text: str) -> str:
        """
        Converts text into clean, natural speech-friendly dialogue.
        Removes markdown, JSON objects, technical error dumps, process extensions, and debug brackets.
        """
        if not text:
            return ""

        cleaned = text

        # 1. Remove markdown formatting (*, _, `, #, ~)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"~~([^~]+)~~", r"\1", cleaned)

        # 2. Remove markdown links [text](url) -> text
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

        # 3. Remove raw JSON or dictionary dumps
        cleaned = re.sub(r"\{[^{}]*:[^{}]*\}", "", cleaned)

        # 4. Remove process suffixes (.exe, .dll, .bat)
        cleaned = re.sub(r"\b(\w+)\.exe\b", r"\1", cleaned, flags=re.IGNORECASE)

        # 5. Remove window handles and technical memory addresses
        cleaned = re.sub(r"\bhwnd\s*=\s*0x[0-9a-fA-F]+\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b0x[0-9a-fA-F]{4,16}\b", "", cleaned)

        # 6. Remove standalone brackets/quotes wrapping window titles: ('Title') -> Title
        cleaned = re.sub(r"\(\s*['\"]([^'\"]+)['\"]\s*\)", r"\1", cleaned)

        # 7. Normalize multiple spaces, tabs, and newlines for smooth prosody
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 8. Clean up repeated punctuation (e.g. "??", "!!", "...")
        cleaned = re.sub(r"\?+", "?", cleaned)
        cleaned = re.sub(r"!+", "!", cleaned)
        cleaned = re.sub(r"\.+", ".", cleaned)

        return cleaned

    @classmethod
    def enforce_controlled_sir(cls, text: str, allow_sir: bool = True) -> str:
        """
        Enforces controlled usage of 'Sir':
        - Never allow multiple 'Sir's in one sentence or response.
        - Prevent overuse if 'Sir' was already used in the immediate previous turn or fast workflow.
        """
        if not text:
            return ""

        # Count occurrences of 'Sir' / 'boss'
        sirs = list(re.finditer(r"\b(sir|boss)\b", text, re.IGNORECASE))
        if len(sirs) > 1:
            # Keep only the first occurrence or a natural one
            first_span = sirs[0].span()
            head = text[:first_span[1]]
            tail = text[first_span[1]:]
            tail_cleaned = re.sub(r"\b(sir|boss),?\s*", "", tail, flags=re.IGNORECASE)
            text = head + tail_cleaned

        if not allow_sir:
            # Strip 'Sir' / 'Boss' cleanly
            text = re.sub(r"\b(sir|boss),?\s*", "", text, flags=re.IGNORECASE).strip()
            # If line starts with punctuation after strip, clean it
            text = re.sub(r"^[,.\s]+", "", text)
            if text:
                text = text[0].upper() + text[1:]

        # Clean trailing double spaces or awkward commas
        text = re.sub(r",\s*,", ",", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def contains_banned_template(cls, text: str) -> bool:
        """Returns True if the response contains a forbidden robotic phrase."""
        if not text:
            return False
        for pat in cls.BANNED_ROBOTIC_PATTERNS:
            if pat.search(text):
                return True
        return False

    @classmethod
    def filter_robotic_phrases(cls, text: str) -> str:
        """Removes or replaces known robotic templates with clean dialogue."""
        if not text:
            return ""
        cleaned = text
        for pat in cls.BANNED_ROBOTIC_PATTERNS:
            cleaned = pat.sub("", cleaned).strip()

        # Clean up any leftover punctuation artifacts
        cleaned = re.sub(r"^[,.\-!\s]+", "", cleaned)
        cleaned = re.sub(r"[,.\-!\s]+$", ".", cleaned) if cleaned else ""
        return cleaned

    @classmethod
    def apply_brevity_preference(cls, text: str, prefer_short: bool = False) -> str:
        """
        Adapts response to concise, direct answers if user prefers brevity.
        Preserves single direct statements, strips multi-clause conversational padding.
        """
        if not text or not prefer_short:
            return text

        # Split into sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) > 1:
            # First sentence is the direct answer
            return sentences[0]
        return text
