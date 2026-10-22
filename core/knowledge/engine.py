# core/knowledge/engine.py
"""
Central Knowledge Engine for Jarvis V2.1.
Facade integrating EntityStore, ReasoningStore, KnowledgeRouter, and KnowledgeResponseFormatter.
"""

from typing import Any, Optional
import logging
import threading

from .models import (
    ConfidenceLevel,
    KnowledgeCategory,
    KnowledgeQueryResult,
    KnowledgeSourceType
)
from .entity_store import EntityStore
from .reasoning_store import ReasoningStore
from .router import KnowledgeRouter
from .formatter import KnowledgeResponseFormatter
from .it import ITKnowledgeEngine, get_it_knowledge_engine, ITQueryResult

logger = logging.getLogger("jarvis.core.knowledge.engine")


class KnowledgeEngine:
    """Authoritative General Knowledge Subsystem for Jarvis."""

    _instance: Optional["KnowledgeEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.entity_store = EntityStore()
        self.reasoning_store = ReasoningStore()
        self.it_engine = get_it_knowledge_engine()
        self.router = KnowledgeRouter(
            entity_store=self.entity_store,
            reasoning_store=self.reasoning_store,
            it_engine=self.it_engine
        )
        logger.info("[KNOWLEDGE_ENGINE] Initialized General Knowledge Engine with Entity, Reasoning & IT Stores.")

    @classmethod
    def get_instance(cls) -> "KnowledgeEngine":
        """Thread-safe singleton accessor."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_knowledge_candidate(self, query: str) -> bool:
        """Determines if query is a candidate for general knowledge resolution."""
        return self.router.is_knowledge_candidate(query)

    def query(self, query: str) -> KnowledgeQueryResult:
        """Evaluates query and returns structured KnowledgeQueryResult."""
        return self.router.route_query(query)

    def query_it(self, query: str) -> ITQueryResult:
        """Direct accessor to IT Knowledge Engine."""
        return self.it_engine.query(query)

    def evaluate_query(self, query: str) -> Optional[str]:
        """
        Convenience method for conversational pipeline:
        Returns formatted response string if answer found with HIGH or MEDIUM confidence,
        or if query was recognized as time-sensitive.
        Returns None if not confident and not a strong GK query so downstream handlers may inspect.
        """
        if not self.is_knowledge_candidate(query):
            # Check if it directly matches an entity or concept anyway
            res = self.query(query)
            if res.found and res.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM):
                return res.answer_text
            return None

        result = self.query(query)
        if result.found:
            return result.answer_text

        # If it was clearly a question but unknown, give honest refusal (no hallucination)
        if result.confidence == ConfidenceLevel.LOW:
            return result.answer_text

        return None

    def learn_fact(
        self,
        entity_id: str,
        property_name: str,
        value: Any,
        category: KnowledgeCategory = KnowledgeCategory.GENERAL
    ) -> bool:
        """Allows dynamic learning and updating of knowledge facts."""
        return self.entity_store.learn_fact(entity_id, property_name, value, category)

    def teach_user_fact(self, entity_id: str, property_name: str, value: Any) -> Any:
        """Stores a user-contributed fact in the isolated user sandbox."""
        return self.router.user_knowledge_store.teach_fact(entity_id, property_name, value)

    def clear_context(self) -> None:
        """Resets active context tracker and fast path cache."""
        self.router.context_tracker.clear()
        self.router.fast_path.clear()


def get_knowledge_engine() -> KnowledgeEngine:
    """Global getter for the Knowledge Engine."""
    return KnowledgeEngine.get_instance()
