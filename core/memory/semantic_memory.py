# core/memory/semantic_memory.py
"""
Semantic Memory Tier Facade for Jarvis V2 Conversation Redesign.
Backward-compatible facade over the authoritative memory.memory_manager.MemoryManager.
Stores durable learned information:
- stable user preferences
- preferred language style
- recurring workflows
- important user choices
- project-related facts
- frequently used application patterns
"""

import logging
from typing import Any, Dict, List, Optional

from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager

logger = logging.getLogger("jarvis.core.memory.semantic")


class SemanticConversationMemory:
    """Backward-compatible facade delegating semantic operations to authoritative MemoryManager."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        memory_manager: Optional[MemoryManager] = None,
    ):
        if memory_manager is not None:
            self._manager = memory_manager
            self.db = memory_manager.db
        elif db is not None:
            self.db = db
            self._manager = MemoryManager(db_path=db.db_path)
        else:
            self._manager = MemoryManager()
            self.db = self._manager.db

    def store_fact(
        self,
        key: str,
        value: str,
        category: str = "facts",
        tags: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Stores durable semantic fact via authoritative MemoryManager."""
        self._manager.store_conversation_fact(
            key=key,
            value=value,
            category=category,
            tags=tags,
            confidence=confidence,
            user_id="default_user",
        )

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves a durable semantic fact by key via authoritative MemoryManager."""
        return self._manager.get_conversation_fact(key=key)

    def search_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches durable semantic facts via authoritative MemoryManager."""
        return self._manager.search_conversation_facts(query=query, limit=limit)

    def delete_fact(self, key: str) -> bool:
        """Deletes a fact via authoritative MemoryManager."""
        return self._manager.delete_conversation_fact(key=key)

    def get_all_facts(self) -> List[Dict[str, Any]]:
        """Returns all facts via authoritative MemoryManager."""
        return self._manager.get_all_conversation_facts()

