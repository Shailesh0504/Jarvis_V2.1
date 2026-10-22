# core/experience/system.py
"""
Central Experience Learning System Coordinator.
Orchestrates SQLite storage, vector similarity embeddings, outcome evaluation,
safeguards, versioned user corrections, and planning retrieval.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .evaluator import OutcomeEvaluator
from .models import ExperienceContext, ExperienceItem, MemoryType
from .retriever import ExperienceRetriever
from .safeguards import ExperienceSafeguards
from .storage import ExperienceStorageManager
from .vector_store import SemanticVectorEngine

logger = logging.getLogger("jarvis.experience.system")


class ExperienceLearningSystem:
    """Unified system coordinating the 4 Experience Memory tiers, safeguards, and retrieval."""

    def __init__(
        self,
        db_or_path: Any = "data/jarvis.db",
        vector_engine: Optional[SemanticVectorEngine] = None
    ):
        self.storage = ExperienceStorageManager(db_or_path=db_or_path)
        self.vector_engine = vector_engine or SemanticVectorEngine()
        self.safeguards = ExperienceSafeguards()
        self.evaluator = OutcomeEvaluator()
        self.retriever = ExperienceRetriever(
            storage=self.storage,
            vector_engine=self.vector_engine
        )
        from .log_learner import LogLearningEngine
        self.log_learner = LogLearningEngine(
            storage=self.storage,
            evaluator=self.evaluator,
            safeguards=self.safeguards
        )
        logger.info("ExperienceLearningSystem initialized successfully.")

    # 1. Retrieval Layer (Before Planning)
    def retrieve_experience(self, query: str, category: Optional[str] = None) -> ExperienceContext:
        """Retrieves relevant previous procedures, failures, and preferences before planning."""
        return self.retriever.retrieve(query=query, category=category)

    # 2. Outcome Evaluation & Storage (After Execution)
    def record_task_success(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        execution_context: Optional[Dict[str, Any]] = None,
        category: str = "general",
        source: str = "execution"
    ) -> Optional[ExperienceItem]:
        """Evaluates and stores genuinely reusable lessons from a successful task execution."""
        item = self.evaluator.evaluate_successful_task(
            goal=goal,
            steps=steps,
            execution_context=execution_context,
            category=category,
            source=source
        )
        if not item or self.safeguards.is_pollution(item):
            logger.debug("ExperienceLearningSystem: Discarded trivial or non-reusable task outcome.")
            return None

        return self._safeguard_and_persist(item)

    def record_task_failure(
        self,
        goal: str,
        failed_step: Dict[str, Any],
        error_msg: str,
        attempted_strategy: str = "primary",
        category: str = "general",
        diagnosis: Optional[str] = None
    ) -> Optional[ExperienceItem]:
        """Evaluates and stores anti-patterns and pitfalls from a failed execution."""
        item = self.evaluator.evaluate_failed_task(
            goal=goal,
            failed_step=failed_step,
            error_msg=error_msg,
            attempted_strategy=attempted_strategy,
            category=category,
            diagnosis=diagnosis
        )
        if not item or self.safeguards.is_pollution(item):
            return None

        return self._safeguard_and_persist(item)

    # 3. High-Value User Correction & Feedback Handler
    def record_user_correction(
        self,
        concept: str,
        old_value: str,
        new_value: str,
        context: Optional[str] = None
    ) -> Tuple[ExperienceItem, Optional[ExperienceItem]]:
        """
        Treats user correction as high-value feedback.
        Never blindly overwrites: supersedes older item and creates new versioned item.
        """
        active_items = self.storage.get_active_items()

        # Build candidate item for corrected preference or concept mapping
        new_item = ExperienceItem(
            memory_type=MemoryType.PREFERENCE,
            category=concept or "user_preference",
            query_pattern=f"{concept}:{new_value}",
            content={"key": concept, "value": new_value, "previous_value": old_value, "context": context or ""},
            confidence=0.98,
            source="user_correction",
            task_metadata={"corrected_from": old_value}
        )
        new_item.embedding = self.vector_engine.embed_text(f"{concept} {new_value}")

        # Check for contradiction / older knowledge
        contradiction = self.safeguards.detect_contradiction(new_item, active_items)
        if contradiction:
            new_item, superseded = self.safeguards.resolve_contradiction(new_item, contradiction)
            self.storage.save_item(superseded)
            self.storage.save_item(new_item)
            logger.info("ExperienceLearningSystem: Saved correction (v%d) superseding older (v%d).",
                        new_item.version, superseded.version)
            return new_item, superseded

        # Also store procedural override if applicable
        self.storage.save_item(new_item)
        return new_item, None

    # 4. User Preference & Semantic Fact Recording
    def record_user_preference(
        self,
        key: str,
        value: Any,
        category: str = "preferences"
    ) -> ExperienceItem:
        """Stores or updates a user preference with contradiction detection."""
        item = ExperienceItem(
            memory_type=MemoryType.PREFERENCE,
            category=category,
            query_pattern=f"{key}:{value}",
            content={"key": key, "value": value},
            confidence=0.95,
            source="user_preference"
        )
        item.embedding = self.vector_engine.embed_text(f"{key} {value}")
        return self._safeguard_and_persist(item)

    def record_semantic_fact(
        self,
        key: str,
        value: str,
        category: str = "facts",
        tags: str = ""
    ) -> ExperienceItem:
        """Stores a semantic factual memory with vector embeddings."""
        item = ExperienceItem(
            memory_type=MemoryType.SEMANTIC,
            category=category,
            query_pattern=key.strip().lower(),
            content={"key": key, "value": value, "tags": tags},
            confidence=1.0,
            source="semantic_fact"
        )
        item.embedding = self.vector_engine.embed_text(f"{key} {value} {tags}")
        return self._safeguard_and_persist(item)

    # 5. Episodic Trace Recording
    def record_episode(
        self,
        task_id: str,
        goal: str,
        steps_trace: List[Dict[str, Any]],
        final_result: str,
        success: bool = True
    ) -> ExperienceItem:
        """Stores a full chronological episodic trace."""
        item = ExperienceItem(
            memory_type=MemoryType.EPISODIC,
            category="task_episode",
            query_pattern=goal.strip().lower(),
            content={
                "task_id": task_id,
                "goal": goal,
                "steps_trace": steps_trace,
                "final_result": final_result,
                "success": success
            },
            confidence=1.0 if success else 0.7,
            source="execution_episode"
        )
        item.embedding = self.vector_engine.embed_text(goal)
        self.storage.save_item(item)
        return item

    def _safeguard_and_persist(self, item: ExperienceItem) -> ExperienceItem:
        """Applies deduplication, contradiction checks, generates embeddings, and saves."""
        active_items = self.storage.get_active_items(memory_type=item.memory_type, category=item.category)

        # 1. Deduplication
        duplicate = self.safeguards.find_duplicate(item, active_items)
        if duplicate:
            merged = self.safeguards.merge_duplicate(duplicate, item)
            self.storage.save_item(merged)
            return merged

        # 2. Contradiction Detection
        contradiction = self.safeguards.detect_contradiction(item, active_items)
        if contradiction:
            item, superseded = self.safeguards.resolve_contradiction(item, contradiction)
            self.storage.save_item(superseded)

        # 3. Vector Embedding
        if not item.embedding:
            emb_text = f"{item.query_pattern} {item.category}"
            item.embedding = self.vector_engine.embed_text(emb_text)

        self.storage.save_item(item)
        return item

    # 4. Mistake Log Digestion & Reflection Layer
    def digest_log_mistakes(self, limit: int = 50) -> List[ExperienceItem]:
        """Digests pending unlearned mistake log records into Experience Memory."""
        return self.log_learner.digest_mistakes(limit=limit)

    def get_lessons_learned_summary(self, limit: int = 5) -> Dict[str, Any]:
        """Provides a structured and spoken reflection of lessons learned from past mistakes."""
        return self.log_learner.get_learned_mistakes_summary(limit=limit)

