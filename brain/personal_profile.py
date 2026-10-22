# brain/personal_profile.py
"""High-priority structured extraction for user profile facts and identity queries."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional


class EntityNamespace(str, Enum):
    PERSON_NAME = "PERSON_NAME"
    APP_NAME = "APP_NAME"
    FILE_NAME = "FILE_NAME"
    SONG_NAME = "SONG_NAME"
    LOCATION = "LOCATION"
    COMMAND_ENTITY = "COMMAND_ENTITY"
    PERSONAL_FACT = "PERSONAL_FACT"


@dataclass(frozen=True)
class StructuredInterpretation:
    intent: str
    confidence: float
    field: str
    value: Optional[str]
    namespace: EntityNamespace
    is_correction: bool = False


class PersonalProfileExtractor:
    """Extracts explicit personal facts before command or fuzzy classification."""

    # Canonical keys share the existing memories table; aliases never create
    # separate copies of the same personal fact.
    FIELDS = {
        "name": ("user_name", "naam", "name"),
        "city": ("user_city", "shehar", "city"),
        "favorite_food": ("favorite_food", "pasandida khana", "favourite food"),
        "preferred_browser": ("preferred_browser", "preferred browser", "preferred browser"),
        "interest": ("user_interest", "pasand", "interest"),
        "hobby": ("user_hobby", "hobby", "hobby"),
        "current_project": ("current_project", "current project", "current project"),
    }
    FACT_PATTERNS = {
        "city": (
            r"(?:main|mein) (.+?) (?:mein|me) reht[ai] (?:hoon|hun|hu)",
            r"i live in (.+)",
            r"(?:mera (?:shehar|shahar)|my city) (?:is )?(.+?)(?: hai)?",
        ),
        "favorite_food": (
            r"my favou?rite food is (.+)",
            r"mera (?:pasandida|favou?rite) khana (.+?) hai",
        ),
        "preferred_browser": (
            r"(?:mera|meri) (?:favou?rite|pasandida|preferred) (?:browser|brouser) (.+?)(?: hai)?",
            r"(?:mera|meri) (?:browser|brouser) (.+?) (?:favou?rite|pasandida|preferred) hai",
            r"(.+?) (?:mera|meri) (?:favou?rite|pasandida|preferred) (?:browser|brouser)(?: hai)?",
            r"my (?:favou?rite|preferred) browser is (.+)",
        ),
        "interest": (
            r"mujhe (.+?) (?:bahut |bohot |sabse zyada )?pasand hai",
            r"i (?:really )?like (.+)",
        ),
        "hobby": (
            r"(?:meri|mera) hobby (.+?) hai",
            r"my hobby is (.+)",
        ),
        "current_project": (
            r"(?:mera|meri) (?:current )?project (.+?) hai",
            r"my (?:current )?project is (.+)",
            r"(?:main|mein) (.+?) (?:par|pe) kaam kar rah[ai] (?:hoon|hun|hu)",
            r"i(?: am|'m) working on (.+)",
        ),
    }
    FACT_QUERIES = {
        "city": r"(?:main (?:kahan|kahaan) reht[ai] (?:hoon|hun|hu)|mera (?:shehar|shahar) kya hai|where do i live|what is my city)",
        "favorite_food": r"(?:mera (?:pasandida|favou?rite) khana kya hai|what is my favou?rite food)",
        "preferred_browser": r"(?:mera (?:favou?rite|pasandida|preferred) (?:browser|brouser) kya hai|what is my (?:favou?rite|preferred) browser)",
        "interest": r"(?:mujhe kya pasand hai|what do i like)",
        "hobby": r"(?:(?:meri|mera) hobby kya hai|what is my hobby)",
        "current_project": r"(?:mera (?:current )?project kya hai|main kis project (?:par|pe) kaam kar raha (?:hoon|hun|hu)|what is my (?:current )?project|what am i working on)",
    }

    NAME_QUERY_PATTERNS = (
        r"^(?:mera|my)\s+(?:naam|name)\s+kya\s+hai$",
        r"^what\s+is\s+my\s+name$",
        r"^do\s+you\s+know\s+my\s+name$",
        r"^aapko\s+mera\s+naam\s+pata\s+hai$",
        r"^maine\s+tumhe\s+apna\s+naam\s+kya\s+bataya\s+tha$",
        r"^maine\s+aapko\s+apna\s+naam\s+kya\s+bataya\s+tha$",
    )
    NAME_UPDATE_PATTERNS = (
        r"^mera\s+(?:naam|name)\s+(.+?)\s+hai(?:\s+yaad\s+rakhna)?$",
        r"^my\s+name\s+is\s+(.+?)(?:\s+remember\s+it)?$",
        r"^mujhe\s+(.+?)\s+bulao$",
        r"^call\s+me\s+(.+?)$",
        r"^main\s+(.+?)\s+hoon$",
        r"^i\s+am\s+(.+?)$",
    )
    INVALID_NAMES = {
        "kya", "kaun", "theek", "fine", "good", "ready", "yahan", "wahan",
        "khush", "sad", "bore", "online", "offline", "tired", "stressed",
        "hungry", "angry", "lonely", "sleepy", "upset", "bored", "happy",
        "thak", "gaya", "pareshan", "udaas", "nahi", "not", "working",
        "khana", "kha", "khane", "raha", "rahi", "ja", "aa", "office",
        "bhookha", "akela", "busy", "student", "programmer", "developer",
        "engineer", "doctor", "teacher", "sleeping", "eating", "home",
    }

    @classmethod
    def extract(cls, text: str, correction_field: Optional[str] = None) -> Optional[StructuredInterpretation]:
        cleaned = re.sub(r"\s+", " ", text.strip().lower().rstrip("?.!"))
        if cleaned in {"mere baare mein kya yaad hai", "tumhe mere baare mein kya yaad hai", "maine kya bataya tha", "what do you remember about me", "yaad dilao maine kya bataya tha"}:
            return StructuredInterpretation("USER_PROFILE_QUERY", 1.0, "summary", None, EntityNamespace.PERSONAL_FACT)
        # Only explicit assertions are durable facts. Questions, negation,
        # hypothetical statements and scheduled reminders must keep their owners.
        fact_text = re.sub(r"^(?:yaad rakhna[, ]+(?:ki )?|remember (?:that )?)", "", cleaned)
        fact_text = re.sub(r"[, ]+(?:yaad rakhna|remember (?:it|this))$", "", fact_text)
        for field, pattern in cls.FACT_QUERIES.items():
            if re.fullmatch(pattern, fact_text):
                return StructuredInterpretation("USER_PROFILE_QUERY", 1.0, field, None, EntityNamespace.PERSONAL_FACT)
        correction = bool(re.match(r"^(?:nahi|nahin|no|mera matlab)[, :]+", fact_text))
        if correction:
            fact_text = re.sub(r"^(?:nahi|nahin|no|mera matlab)[, :]+", "", fact_text)
        if re.match(r"^(?:maine\s+(?:bola|kaha)\s+tha\s+(?:ki\s+)?|i\s+told\s+you\s+(?:that\s+)?)", fact_text):
            correction = True
            fact_text = re.sub(r"^(?:maine\s+(?:bola|kaha)\s+tha\s+(?:ki\s+)?|i\s+told\s+you\s+(?:that\s+)?)", "", fact_text)
        if not re.search(r"\b(?:nahi|nahin|not|if|agar|kya|password|otp|pin|secret|token|kholo|chalao|remind|reminder|dilana|dilao)\b", fact_text) and "?" not in text:
            for field, patterns in cls.FACT_PATTERNS.items():
                for pattern in patterns:
                    match = re.fullmatch(pattern, fact_text)
                    if match:
                        value = match.group(1).strip(" ,.!?")
                        if 0 < len(value) <= 100 and len(value.split()) <= 12 and not re.search(r"[;\n]|https?://|\b(?:aur|and|but|lekin)\b.*\b(?:karo|open|close|delete|send)\b", value):
                            # Preserve user spelling/case for names of projects.
                            original = re.search(re.escape(value), text, re.I)
                            value = original.group() if original else value
                            return StructuredInterpretation("USER_PROFILE_UPDATE", 1.0, field, value, EntityNamespace.PERSONAL_FACT, correction)
        if any(re.fullmatch(pattern, cleaned, flags=re.IGNORECASE) for pattern in cls.NAME_QUERY_PATTERNS):
            return StructuredInterpretation(
                intent="USER_PROFILE_QUERY", confidence=1.0, field="name", value=None,
                namespace=EntityNamespace.PERSON_NAME,
            )

        correction_match = re.fullmatch(
            r"(?:nahi|nahin|no|galat|mera\s+matlab)\s*[,\-:]?\s*(?:mera\s+naam\s+)?(.+?)\s+(?:hai|hain)", cleaned,
            flags=re.IGNORECASE,
        )
        if correction_match and correction_field == "name":
            value = cls._normalize_name(correction_match.group(1))
            if value:
                return StructuredInterpretation(
                    intent="MEMORY_UPDATE", confidence=1.0, field="name", value=value,
                    namespace=EntityNamespace.PERSON_NAME, is_correction=True,
                )

        for pattern in cls.NAME_UPDATE_PATTERNS:
            match = re.fullmatch(pattern, cleaned, flags=re.IGNORECASE)
            if match:
                if "?" in text:
                    return None
                if pattern in cls.NAME_UPDATE_PATTERNS[-2:] and len(match.group(1).split()) > 2:
                    return None
                value = cls._normalize_name(match.group(1))
                if value:
                    return StructuredInterpretation(
                        intent="USER_PROFILE_UPDATE", confidence=1.0, field="name", value=value,
                        namespace=EntityNamespace.PERSON_NAME,
                    )
        return None

    @classmethod
    def _normalize_name(cls, value: str) -> Optional[str]:
        candidate = re.sub(r"\b(?:please|boss|yaad\s+rakhna)\b", "", value, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,.-")
        words = candidate.split()
        if not words or len(words) > 4 or any(word in cls.INVALID_NAMES for word in words):
            return None
        if not all(re.fullmatch(r"[^\W\d_]+", word, flags=re.UNICODE) for word in words):
            return None
        return " ".join(word.capitalize() for word in words)
