# core/experience/safeguards.py
"""
Safeguards Engine for the Experience Learning System.
Guards against memory pollution, contradictory knowledge, and duplicate records.
Enforces versioning, confidence decay, and high-value correction priority.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import ExperienceItem, MemoryType

logger = logging.getLogger("jarvis.experience.safeguards")


class ExperienceSafeguards:
    """Provides memory quality control, deduplication, and contradiction resolution."""

    # Trivial phrases that should not pollute procedural or failure memory
    POLLUTION_BLACK_LIST = {
        "hi", "hello", "hey", "test", "ok", "yes", "no", "haan", "theek hai",
        "kya haal hai", "who are you", "what is your name", "status"
    }

    @classmethod
    def is_pollution(cls, item: ExperienceItem) -> bool:
        """
        Determines whether a proposed memory item is transient noise,
        unverified trivia, or empty execution trace.
        """
        query_norm = (item.query_pattern or "").strip().lower()

        # 1. Blacklisted trivial queries
        if query_norm in cls.POLLUTION_BLACK_LIST:
            return True

        # 2. Insufficient payload content
        if not item.content:
            return True

        # 3. Procedural memory must have actual steps
        if item.memory_type == MemoryType.PROCEDURAL:
            steps = item.content.get("steps", [])
            if not steps:
                return True

        # 4. Failure memory must have identifiable root cause
        if item.memory_type == MemoryType.FAILURE:
            err = item.content.get("error") or item.content.get("root_cause")
            if not err:
                return True

        return False

    @classmethod
    def find_duplicate(
        cls,
        new_item: ExperienceItem,
        existing_items: List[ExperienceItem]
    ) -> Optional[ExperienceItem]:
        """
        Detects if an existing active item represents the exact same knowledge.
        Matches by memory type, category, and normalized signature.
        """
        new_sig = cls._compute_signature(new_item)

        for existing in existing_items:
            if not existing.is_active:
                continue
            if existing.memory_type != new_item.memory_type:
                continue
            if existing.category != new_item.category:
                continue

            existing_sig = cls._compute_signature(existing)
            if new_sig == existing_sig:
                return existing

        return None

    @classmethod
    def merge_duplicate(cls, existing: ExperienceItem, new_item: ExperienceItem) -> ExperienceItem:
        """
        Merges duplicate experience by boosting confidence and updating counts
        rather than inserting redundant rows into the database.
        """
        existing.success_count += new_item.success_count
        existing.failure_count += new_item.failure_count

        # Confidence update: reinforce with positive usage
        boost = 0.05 * new_item.success_count
        existing.confidence = min(1.0, round(existing.confidence + boost, 4))
        existing.updated_at = new_item.updated_at or existing.updated_at

        # Merge metadata
        if new_item.task_metadata:
            existing.task_metadata.update(new_item.task_metadata)

        logger.info("ExperienceSafeguards: Merged duplicate experience '%s' (New confidence: %.2f)",
                    existing.id, existing.confidence)
        return existing

    @classmethod
    def detect_contradiction(
        cls,
        new_item: ExperienceItem,
        existing_items: List[ExperienceItem]
    ) -> Optional[ExperienceItem]:
        """
        Detects direct contradictions between new and existing active memories.
        Example: Preference 'default_browser=chrome' vs 'default_browser=edge'.
        Example: Procedural steps with conflicting target plugins for same goal.
        """
        for existing in existing_items:
            if not existing.is_active:
                continue
            if existing.id == new_item.id:
                continue

            # Check Preference Contradictions
            if new_item.memory_type == MemoryType.PREFERENCE and existing.memory_type == MemoryType.PREFERENCE:
                new_key = new_item.content.get("key")
                exist_key = existing.content.get("key")
                if new_key and exist_key and new_key.lower() == exist_key.lower():
                    new_val = new_item.content.get("value")
                    exist_val = existing.content.get("value")
                    if new_val != exist_val:
                        return existing

            # Check Procedural / Concept Contradictions
            if new_item.memory_type == MemoryType.PROCEDURAL and existing.memory_type == MemoryType.PROCEDURAL:
                if new_item.query_pattern and existing.query_pattern:
                    if new_item.query_pattern.strip().lower() == existing.query_pattern.strip().lower():
                        # Same trigger phrase with different primary plugin/procedure
                        new_first = cls._get_primary_action(new_item)
                        exist_first = cls._get_primary_action(existing)
                        if new_first and exist_first and new_first != exist_first:
                            return existing

        return None

    @classmethod
    def resolve_contradiction(
        cls,
        new_item: ExperienceItem,
        contradictory_existing: ExperienceItem
    ) -> Tuple[ExperienceItem, ExperienceItem]:
        """
        Resolves a contradiction without blind deletion:
        1. Deprecates / supersedes older item (is_active = False, superseded_by = new_item.id).
        2. Versions new item (version = older.version + 1, confidence boosted if from correction).
        """
        contradictory_existing.is_active = False
        contradictory_existing.superseded_by = new_item.id
        contradictory_existing.confidence = max(0.1, round(contradictory_existing.confidence * 0.5, 4))

        new_item.version = contradictory_existing.version + 1
        if new_item.source == "user_correction":
            new_item.confidence = 0.98
        else:
            new_item.confidence = max(new_item.confidence, 0.90)

        logger.info("ExperienceSafeguards: Resolved contradiction. Superseded '%s' (v%d) with '%s' (v%d).",
                    contradictory_existing.id, contradictory_existing.version,
                    new_item.id, new_item.version)
        return new_item, contradictory_existing

    @staticmethod
    def _compute_signature(item: ExperienceItem) -> str:
        """Computes a deterministic MD5 fingerprint of the item's core semantics."""
        raw = f"{item.memory_type.value}:{item.category}:{item.query_pattern.strip().lower()}"
        if item.memory_type == MemoryType.PREFERENCE:
            raw += f":{item.content.get('key')}"
        elif item.memory_type == MemoryType.PROCEDURAL:
            steps_sig = []
            for s in item.content.get("steps", []):
                steps_sig.append(f"{s.get('plugin')}.{s.get('action')}")
            raw += f":{'-'.join(steps_sig)}"
        elif item.memory_type == MemoryType.FAILURE:
            raw += f":{item.content.get('failed_action')}:{item.content.get('error')}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_primary_action(item: ExperienceItem) -> Optional[str]:
        steps = item.content.get("steps", [])
        if steps and isinstance(steps[0], dict):
            return f"{steps[0].get('plugin')}.{steps[0].get('action')}"
        return None
