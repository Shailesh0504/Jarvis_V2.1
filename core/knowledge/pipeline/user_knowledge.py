# core/knowledge/pipeline/user_knowledge.py
"""
Isolated User-Taught Knowledge Repository.
Stores user-contributed or corrected facts in a strictly isolated sandbox.
Ensures user-taught facts:
1. Are marked with source="user", is_verified=False, and timestamp.
2. NEVER overwrite or pollute authoritative system knowledge.
3. Can be queried with qualified attribution or updated safely.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import time
import logging

logger = logging.getLogger("jarvis.core.knowledge.pipeline.user_knowledge")


@dataclass
class UserLearnedFact:
    """Represents an isolated fact taught by the user."""
    fact_id: str
    entity_id: str
    property_name: str
    value: Any
    learned_timestamp: float = field(default_factory=time.time)
    source: str = "user"
    is_verified: bool = False
    confidence: float = 0.75


class UserKnowledgeStore:
    """Isolated store for user-taught facts preventing global knowledge corruption."""

    def __init__(self):
        # entity_id -> {property_name: UserLearnedFact}
        self._learned_facts: Dict[str, Dict[str, UserLearnedFact]] = {}

    def teach_fact(self, entity_id: str, property_name: str, value: Any) -> UserLearnedFact:
        """Stores a user-contributed fact in the isolated sandbox."""
        norm_ent = entity_id.strip().lower()
        norm_prop = property_name.strip().lower()
        fact_id = f"user_{norm_ent}_{norm_prop}"

        fact = UserLearnedFact(
            fact_id=fact_id,
            entity_id=norm_ent,
            property_name=norm_prop,
            value=value,
            learned_timestamp=time.time(),
            source="user",
            is_verified=False,
            confidence=0.75
        )

        if norm_ent not in self._learned_facts:
            self._learned_facts[norm_ent] = {}
        self._learned_facts[norm_ent][norm_prop] = fact

        logger.info(f"[USER_KNOWLEDGE] Stored user fact: {norm_ent}.{norm_prop} = {value!r} (isolated)")
        return fact

    def get_fact(self, entity_id: str, property_name: str) -> Optional[UserLearnedFact]:
        """Retrieves a user-taught fact if present."""
        norm_ent = entity_id.strip().lower()
        norm_prop = property_name.strip().lower()
        return self._learned_facts.get(norm_ent, {}).get(norm_prop)

    def list_facts_for_entity(self, entity_id: str) -> List[UserLearnedFact]:
        """Returns all user facts for an entity."""
        norm_ent = entity_id.strip().lower()
        return list(self._learned_facts.get(norm_ent, {}).values())

    def clear(self) -> None:
        """Clears isolated store."""
        self._learned_facts.clear()
