# core/knowledge/models.py
"""
Data models and type definitions for the Jarvis General Knowledge Engine.
Defines entity, relation, reasoning, question type classifications,
confidence vectors, disambiguation models, and query results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class KnowledgeCategory(str, Enum):
    COUNTRIES = "countries"
    CAPITALS = "capitals"
    STATES = "states"
    CITIES = "cities"
    CURRENCIES = "currencies"
    CONTINENTS = "continents"
    PLANETS = "planets"
    ELEMENTS = "elements"
    HISTORY = "history"
    IMPORTANT_DATES = "important_dates"
    FAMOUS_PEOPLE = "famous_people"
    ABBREVIATIONS = "abbreviations"
    SCIENCE_BASICS = "science_basics"
    GEOGRAPHY = "geography"
    INDIAN_GK = "indian_gk"
    COMPUTER_TECH = "computer_tech"
    FESTIVALS = "festivals"          # Indian festivals, religious observances
    NATIONAL_DAYS = "national_days"  # Republic Day, Independence Day, etc.
    GENERAL = "general"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"        # >= 0.80: Answer directly and concisely
    MEDIUM = "MEDIUM"    # 0.60 - 0.79: Answer with qualified context
    LOW = "LOW"          # < 0.60: State reliable info unavailable, no hallucination


class KnowledgeSourceType(str, Enum):
    STATIC_FACT = "STATIC_FACT"
    SEMANTIC_RELATION = "SEMANTIC_RELATION"
    REASONING = "REASONING"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    USER_TAUGHT = "USER_TAUGHT"
    UNKNOWN = "UNKNOWN"


class GKQuestionType(str, Enum):
    FACTUAL = "FACTUAL"                      # "India ki capital kya hai?", "Water formula"
    DEFINITION = "DEFINITION"                # "What is an atom?", "CPU kya hai?"
    EXPLANATION = "EXPLANATION"              # "Photosynthesis kya hota hai?"
    WHY = "WHY"                              # "Sky blue kyun dikhta hai?", "Gravity kyun hoti hai?"
    HOW = "HOW"                              # "Rain kaise hoti hai?", "Rainbow kaise banta hai?"
    WHEN = "WHEN"                            # "India kab independent hua?"
    WHERE = "WHERE"                          # "Eiffel Tower kahan hai?"
    WHO = "WHO"                              # "Einstein kaun the?", "First PM kaun the?"
    WHICH = "WHICH"                          # "Which planet is largest?"
    COMPARISON = "COMPARISON"                # "Which planet is larger, Earth or Mars?"
    SPATIAL_RELATION = "SPATIAL_RELATION"    # "If India is north of Sri Lanka, which country is south of India?"
    MATHEMATICAL_RATE = "MATHEMATICAL_RATE"  # "If train travels 60km in 1h, how far in 3h?"
    CAUSE_EFFECT = "CAUSE_EFFECT"            # "Grahan kyun lagta hai?"
    HISTORICAL = "HISTORICAL"                # "1947 mein kya hua tha?"
    SCIENTIFIC = "SCIENTIFIC"                # "Speed of light kitni hai?"
    GEOGRAPHICAL = "GEOGRAPHICAL"            # "Mount Everest kitna uncha hai?"
    POLITICAL = "POLITICAL"                  # "President of India kaun hain?"
    TECHNOLOGICAL = "TECHNOLOGICAL"          # "RAM kya hota hai?"
    CURRENT_FRESH = "CURRENT_FRESH"          # "Today's weather", "Latest updates", "2026"
    AMBIGUOUS = "AMBIGUOUS"                  # "Java kya hai?" (language vs island)
    MULTI_STEP = "MULTI_STEP"                # "India kab independent hua aur first PM kaun the?"
    TRICK_WORDPLAY = "TRICK_WORDPLAY"        # "Kya suraj raat ko nikal sakta hai?"
    CROSSOVER = "CROSSOVER"                  # IT and general technical crossover
    FESTIVAL_DATE = "FESTIVAL_DATE"          # "Ganpati kab hai?", "Diwali 2026 mein kab?"
    FESTIVAL_INFO = "FESTIVAL_INFO"          # "Ganesh Chaturthi kya hai?"
    UPCOMING_EVENT = "UPCOMING_EVENT"        # "Agla festival kaunsa hai?"


@dataclass
class ConfidenceVector:
    """Multi-factor confidence scoring vector."""
    language: float = 1.0
    transcription: float = 1.0
    correction: float = 1.0
    classification: float = 1.0
    entity: float = 1.0
    relation: float = 1.0
    knowledge: float = 1.0
    answer: float = 1.0
    composite: float = 1.0


@dataclass
class DisambiguationOption:
    """Represents one possible meaning for an ambiguous entity."""
    entity_id: str
    label_en: str
    label_hi: str
    domain: str
    summary: str


@dataclass
class KnowledgeEntity:
    """Represents a canonical knowledge entity (e.g., India, Jupiter, Photosynthesis, Python)."""
    entity_id: str
    canonical_name: str
    entity_type: str  # "country", "state", "city", "planet", "element", "person", "technology", "organization", "concept"
    aliases: List[str] = field(default_factory=list)
    categories: List[KnowledgeCategory] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    summary_en: str = ""
    summary_hi: str = ""
    last_verified: Optional[str] = None
    is_dynamic: bool = False  # If True, indicates properties might be time-dependent (e.g., current leader)


@dataclass
class KnowledgeRelation:
    """Represents a semantic triple (subject - relation - object)."""
    subject_id: str
    relation_type: str  # e.g., "is_capital_of", "is_in_continent", "invented_by", "orbits", "is_north_of"
    object_id: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConceptReasoning:
    """Represents a scientific or conceptual topic requiring structured explanation."""
    concept_id: str
    title: str
    category: str
    simple_explanation_en: str
    simple_explanation_hi: str
    detailed_explanation_en: str = ""
    detailed_explanation_hi: str = ""
    key_principles: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class KnowledgeQueryResult:
    """Result of querying the Knowledge Engine."""
    found: bool
    confidence: ConfidenceLevel
    confidence_score: float
    source_type: KnowledgeSourceType
    answer_text: str = ""
    question_type: GKQuestionType = GKQuestionType.FACTUAL
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    property_name: Optional[str] = None
    property_value: Optional[Any] = None
    concept_id: Optional[str] = None
    is_time_sensitive: bool = False
    needs_fresh_fetch: bool = False
    clarification_prompt: Optional[str] = None
    confidence_vector: Optional[ConfidenceVector] = None
    disambiguation_options: List[DisambiguationOption] = field(default_factory=list)
    sub_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
