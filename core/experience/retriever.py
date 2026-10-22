# core/experience/retriever.py
"""
Memory-Retrieval Layer for Reasoning and Planning.
Retrieves relevant prior procedures, failure pitfalls, and user preferences
using hybrid semantic vector search before executing a new task.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import ExperienceContext, ExperienceItem, MemoryType
from .storage import ExperienceStorageManager
from .vector_store import SemanticVectorEngine

logger = logging.getLogger("jarvis.experience.retriever")


class ExperienceRetriever:
    """Retrieves relevant historical experience to prime planning and reasoning."""

    def __init__(
        self,
        storage: ExperienceStorageManager,
        vector_engine: Optional[SemanticVectorEngine] = None,
        similarity_threshold: float = 0.35
    ):
        self.storage = storage
        self.vector_engine = vector_engine or SemanticVectorEngine()
        self.similarity_threshold = similarity_threshold

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        category: Optional[str] = None
    ) -> ExperienceContext:
        """
        Retrieves matching procedures, pitfalls, and preferences for the given query.
        Returns a consolidated ExperienceContext bundle.
        """
        context = ExperienceContext(query=query)
        if not query or not query.strip():
            return context

        query_norm = query.strip().lower()
        query_vec = self.vector_engine.embed_text(query_norm)

        active_items = self.storage.get_active_items(category=category)
        if not active_items:
            return context

        # 1. Direct match preferences whose category, key, or component matches query words
        for item in active_items:
            if item.memory_type == MemoryType.PREFERENCE:
                p_key = str(item.content.get("key", "")).lower()
                p_cat = str(item.category).lower()
                if (p_cat in query_norm or p_key in query_norm or
                    any(part in query_norm for part in p_key.split("_") if len(part) > 2)):
                    k = item.content.get("key")
                    v = item.content.get("value")
                    if k and k not in context.preferences:
                        context.preferences[k] = v

        scored_items: List[tuple[float, ExperienceItem]] = []
        for item in active_items:
            target_text = f"{item.query_pattern} {item.category}"
            if item.memory_type == MemoryType.PROCEDURAL and item.content.get("goal"):
                target_text = f"{target_text} {item.content.get('goal')}"
            elif item.memory_type == MemoryType.PREFERENCE:
                target_text = f"{target_text} {item.content.get('key')} {item.content.get('value')}"

            sim = self.vector_engine.hybrid_similarity(
                query=query_norm,
                target_text=target_text,
                query_vector=query_vec,
                target_vector=item.embedding
            )

            # Weight score by item confidence and usage validation
            composite_score = sim * item.confidence
            if sim >= self.similarity_threshold or query_norm in target_text or target_text in query_norm:
                scored_items.append((composite_score, item))

        # Sort descending by composite score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Populate context categories
        seen_procedures = set()
        seen_failures = set()

        for score, item in scored_items[:limit * 2]:
            if item.memory_type == MemoryType.PROCEDURAL:
                proc_key = item.query_pattern
                if proc_key not in seen_procedures and len(context.procedures) < limit:
                    seen_procedures.add(proc_key)
                    proc_data = dict(item.content)
                    proc_data["confidence"] = item.confidence
                    proc_data["query_pattern"] = item.query_pattern
                    proc_data["version"] = item.version
                    proc_data["category"] = item.category
                    context.procedures.append(proc_data)

            elif item.memory_type == MemoryType.FAILURE:
                fail_key = item.content.get("failed_action", "")
                if fail_key not in seen_failures and len(context.failures) < limit:
                    seen_failures.add(fail_key)
                    context.failures.append(dict(item.content))

            elif item.memory_type == MemoryType.PREFERENCE:
                k = item.content.get("key")
                v = item.content.get("value")
                if k and k not in context.preferences:
                    context.preferences[k] = v

            elif item.memory_type == MemoryType.SEMANTIC:
                context.facts.append(dict(item.content))

            elif item.memory_type == MemoryType.EPISODIC:
                context.episodes.append(dict(item.content))

        logger.info(
            "ExperienceRetriever: For '%s', found %d procedure(s), %d failure(s), %d preference(s)",
            query, len(context.procedures), len(context.failures), len(context.preferences)
        )
        return context
