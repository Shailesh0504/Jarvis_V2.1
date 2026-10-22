# core/semantic/__init__.py
"""
Core Brain Natural-Language Understanding (NLU) & Semantic Entity Extraction Engine.
Modular, decoupled, and optimized package architecture.
"""

from core.semantic.constants import (
    KNOWN_APPS,
    OPEN_VERBS,
    PLAY_VERBS,
    POSITION_KEYWORDS,
    SEARCH_VERBS,
    SERVICE_PATTERNS,
    WINDOW_OPERATIONS,
)
from core.semantic.models import SemanticAction
from core.semantic.multi_entity import (
    ActionItem,
    MultiActionPlan,
    MultiEntityCommandParser,
    get_multi_entity_parser,
)
from core.semantic.normalizer import HinglishNormalizer
from core.semantic.orchestrator import SemanticPipelineOrchestrator
from core.semantic.hindi_vocab import (
    HindiVocabEngine,
    HindiVocabCategory,
    EnrichedEntities,
    VocabMatch,
    MovementConcept,
    DirectionConcept,
    ObjectRefConcept,
    BodyStateConcept,
    EmotionConcept,
    TimeRefConcept,
    ActionVerbConcept,
    QuantityConcept,
    ReferenceConcept,
)
from core.semantic.lexicon import (
    ActionConcept,
    TargetDomain,
    LexicalAnalysis,
    LexiconEngine,
    get_lexicon_engine,
)

__all__ = [
    "SemanticAction",
    "ActionItem",
    "MultiActionPlan",
    "MultiEntityCommandParser",
    "get_multi_entity_parser",
    "HinglishNormalizer",
    "SemanticPipelineOrchestrator",
    "PLAY_VERBS",
    "OPEN_VERBS",
    "SEARCH_VERBS",
    "SERVICE_PATTERNS",
    "WINDOW_OPERATIONS",
    "POSITION_KEYWORDS",
    "KNOWN_APPS",
    # Hindi/Hinglish Vocab Engine
    "HindiVocabEngine",
    "HindiVocabCategory",
    "EnrichedEntities",
    "VocabMatch",
    "MovementConcept",
    "DirectionConcept",
    "ObjectRefConcept",
    "BodyStateConcept",
    "EmotionConcept",
    "TimeRefConcept",
    "ActionVerbConcept",
    "QuantityConcept",
    "ReferenceConcept",
    # Vocabulary & Lexicon Intelligence
    "ActionConcept",
    "TargetDomain",
    "LexicalAnalysis",
    "LexiconEngine",
    "get_lexicon_engine",
]
