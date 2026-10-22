# core/knowledge/__init__.py
"""
Jarvis General Knowledge Subsystem.
Knowledge-based architecture with Entity, Relation, and Conceptual Reasoning stores.
Includes Calendar & Festival Knowledge Engine for year-aware date resolution.
"""

from .models import (
    KnowledgeEntity,
    KnowledgeRelation,
    ConceptReasoning,
    KnowledgeQueryResult,
    KnowledgeCategory,
    ConfidenceLevel,
    KnowledgeSourceType
)
from .entity_store import EntityStore
from .reasoning_store import ReasoningStore
from .router import KnowledgeRouter
from .formatter import KnowledgeResponseFormatter
from .engine import KnowledgeEngine, get_knowledge_engine
from .calendar import FestivalCalendarEngine, get_festival_calendar_engine

__all__ = [
    "KnowledgeEntity",
    "KnowledgeRelation",
    "ConceptReasoning",
    "KnowledgeQueryResult",
    "KnowledgeCategory",
    "ConfidenceLevel",
    "KnowledgeSourceType",
    "EntityStore",
    "ReasoningStore",
    "KnowledgeRouter",
    "KnowledgeResponseFormatter",
    "KnowledgeEngine",
    "get_knowledge_engine",
    "FestivalCalendarEngine",
    "get_festival_calendar_engine",
]
