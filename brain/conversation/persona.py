# brain/conversation/persona.py
"""
Personality & Persona Configuration System for Jarvis V2.
Provides tone adaptation (Friendly, Natural, Concise, Professional, Humorous)
allowing Jarvis to switch communication styles without changing underlying logic.
"""

from enum import Enum
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger("jarvis.brain.conversation.persona")


class PersonaTone(str, Enum):
    """Supported personality tones."""
    FRIENDLY = "friendly"
    NATURAL = "natural"
    CONCISE = "concise"
    PROFESSIONAL = "professional"
    HUMOROUS = "humorous"


class PersonalityConfig:
    """Holds active personality settings and style modifiers."""

    def __init__(self, default_tone: PersonaTone = PersonaTone.NATURAL):
        self.tone: PersonaTone = default_tone
        self.user_name: str = "yaar"
        self.allow_slang: bool = True
        self.verbosity: str = "medium"  # low, medium, high

    def set_tone(self, tone_name: str) -> bool:
        """Sets active personality tone."""
        try:
            self.tone = PersonaTone(tone_name.lower().strip())
            logger.info(f"Personality tone updated to: {self.tone.value}")
            return True
        except ValueError:
            logger.warning(f"Unknown tone '{tone_name}', maintaining '{self.tone.value}'")
            return False

    def get_style_prefix(self) -> str:
        """Returns tone-specific phrasing modifier."""
        if self.tone == PersonaTone.CONCISE:
            return ""
        elif self.tone == PersonaTone.PROFESSIONAL:
            return "Sir, "
        elif self.tone == PersonaTone.HUMOROUS:
            return "Arey yaar! "
        elif self.tone == PersonaTone.FRIENDLY:
            return f"Haan {self.user_name}! "
        return ""

    def adapt_response(self, text: str) -> str:
        """Applies personality styling to a generated text."""
        if not text:
            return text

        if self.tone != PersonaTone.PROFESSIONAL:
            text = re.sub(r"\s*\bBoss\b", "", text, flags=re.I)
            text = re.sub(r"\s+([,.!?])", r"\1", text).replace("!,", "!")

        if self.tone == PersonaTone.CONCISE:
            # Shorten text, remove conversational intros
            first_sentence = text.split(".")[0].strip()
            return first_sentence if first_sentence else text

        elif self.tone == PersonaTone.PROFESSIONAL:
            # Replace informal words with formal ones
            adapted = text.replace("Boss", "Sir").replace("yaar", "").replace("mast", "excellent")
            return adapted.strip()

        elif self.tone == PersonaTone.HUMOROUS:
            if not text.endswith(("😄", "😎", "🙌")):
                return f"{text} 😄"

        return text
