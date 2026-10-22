# core/intent.py
"""Intent and command detection representations."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class UniversalIntentCategory(str, Enum):
    """
    15 Authoritative Universal Intent Categories for Jarvis V2.1.
    Distinguishes the user's pragmatic speech-act and conversational purpose.
    """
    COMMAND                   = "COMMAND"                    # Direct imperative instructions to perform an action
    QUESTION                  = "QUESTION"                   # Questions about capability, permission, or ability
    INFORMATION_REQUEST       = "INFORMATION_REQUEST"        # Inquiries for knowledge, definitions, how-to, facts
    GENERAL_CONVERSATION      = "GENERAL_CONVERSATION"       # Open conversational dialogue, thoughts, banter
    FOLLOW_UP                 = "FOLLOW_UP"                  # Contextual / anaphoric continuation of active dialogue
    CORRECTION                = "CORRECTION"                 # Conversational repairs / entity parameter updates
    CONFIRMATION              = "CONFIRMATION"               # Affirmations, approvals, consent to pending proposals
    REJECTION                 = "REJECTION"                  # Explicit declination / refusal
    CANCELLATION              = "CANCELLATION"               # Abort / stop active operations or workflows
    TROUBLESHOOTING           = "TROUBLESHOOTING"            # Diagnostic inquiries asking why an action failed
    REQUEST_FOR_CLARIFICATION = "REQUEST_FOR_CLARIFICATION"  # Inquiries asking Jarvis to clarify or re-explain
    SYSTEM_INFORMATION        = "SYSTEM_INFORMATION"         # Queries regarding device status, hardware, OS state
    ACTION_RESULT             = "ACTION_RESULT"              # Inquiring whether an action completed or status after action
    COMPLAINT                 = "COMPLAINT"                  # Negative feedback / dissatisfaction with performance
    SMALL_TALK                = "SMALL_TALK"                 # Social pleasantries, greetings, farewells, gratitude
    UNKNOWN                   = "UNKNOWN"                    # Unrecognized, garbled, or unintelligible input
    AMBIGUOUS                 = "AMBIGUOUS"                  # Ambiguous command requiring target/action clarification


@dataclass
class CategoryDescriptor:
    name: str
    description: str = ""
    default_executable: bool = False
    aliases: List[str] = field(default_factory=list)


class UniversalCategoryRegistry:
    """
    Extensible, centralized registry for Universal Intent Categories.
    Allows new semantic categories to be registered dynamically without duplicating
    or fragmenting the intent system.
    """
    _registry: Dict[str, CategoryDescriptor] = {}

    @classmethod
    def register_category(
        cls,
        name: str,
        description: str = "",
        default_executable: bool = False,
        aliases: Optional[List[str]] = None
    ) -> str:
        cat_key = name.strip().upper()
        cls._registry[cat_key] = CategoryDescriptor(
            name=cat_key,
            description=description,
            default_executable=default_executable,
            aliases=aliases or []
        )
        return cat_key

    @classmethod
    def get_category(cls, name: str) -> Optional[CategoryDescriptor]:
        return cls._registry.get(name.strip().upper())

    @classmethod
    def list_categories(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        return name.strip().upper() in cls._registry


# Populate default universal categories into the registry
for cat in UniversalIntentCategory:
    exec_flag = (cat == UniversalIntentCategory.COMMAND)
    UniversalCategoryRegistry.register_category(
        name=cat.value,
        description=f"Universal intent category: {cat.value}",
        default_executable=exec_flag
    )


class IntentType(str, Enum):
    COMMAND = "COMMAND"          # Direct action on system or plugin (e.g., "open chrome", "set volume 50")
    CHAT = "CHAT"                # Conversational chit-chat / general knowledge query
    MEMORY_STORE = "MEMORY_STORE"# Storing a fact / preference (e.g., "remember my birthday is May 10")
    MEMORY_QUERY = "MEMORY_QUERY"# Retrieving stored fact (e.g., "what is my birthday?")
    CONFIRMATION = "CONFIRMATION"# Yes / No / Proceed response
    CORRECTION = "CORRECTION"    # "No, I meant brave, not chrome"
    SYSTEM = "SYSTEM"            # Internal commands (exit, reload plugins, clear memory)
    UNKNOWN = "UNKNOWN"          # Unrecognized


@dataclass
class Entity:
    name: str
    value: Any
    confidence: float = 1.0
    raw_text: Optional[str] = None


@dataclass
class Intent:
    name: str
    type: IntentType = IntentType.COMMAND
    confidence: float = 1.0
    entities: Dict[str, Any] = field(default_factory=dict)
    target_plugin: Optional[str] = None
    target_action: Optional[str] = None
    raw_query: str = ""
    is_multi_step: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    universal_category: UniversalIntentCategory = UniversalIntentCategory.COMMAND


@dataclass
class IntentResult:
    primary_intent: Intent
    secondary_intents: List[Intent] = field(default_factory=list)
    confidence: float = 1.0
    matched_pattern: Optional[str] = None
    source: str = "rule"  # "rule", "fuzzy", "llm"
    universal_category: Optional[UniversalIntentCategory] = None

    def __post_init__(self):
        if self.universal_category is None and self.primary_intent:
            self.universal_category = getattr(self.primary_intent, "universal_category", UniversalIntentCategory.COMMAND)
