# core/memory/episodic_memory.py
"""
Episodic Memory Tier Facade for Jarvis V2 Conversation Redesign.
Backward-compatible facade over the authoritative memory.memory_manager.MemoryManager.
Stores meaningful conversation events and facts in SQLite `episodic_memory` table,
and maintains relationship links (`memory_links`) between events.
"""

import logging
from typing import Any, Dict, List, Optional

from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager

logger = logging.getLogger("jarvis.core.memory.episodic")


class EpisodicConversationMemory:
    """Backward-compatible facade delegating episodic operations to authoritative MemoryManager."""

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

    def record_event(
        self,
        event_type: str,
        topic: str,
        fact: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> int:
        """Stores an episodic event by delegating to authoritative MemoryManager."""
        return self._manager.record_episodic_event(
            event_type=event_type,
            topic=topic,
            fact=fact,
            confidence=confidence,
            metadata=metadata,
            ttl_seconds=ttl_seconds,
            user_id="default_user",
        )

    def update_event(
        self,
        previous_event_id: int,
        new_fact: str,
        event_type: str = "USER_STATE_EVENT",
        topic: str = "food",
        relation: str = "UPDATED_BY",
        confidence: float = 1.0,
    ) -> int:
        """Records a new event and delegates memory link creation to MemoryManager."""
        new_id = self.record_event(
            event_type=event_type,
            topic=topic,
            fact=new_fact,
            confidence=confidence,
        )
        if previous_event_id and new_id:
            self._manager.link_memory_events(
                source_id=previous_event_id,
                target_id=new_id,
                relation_type=relation,
                confidence=confidence,
                source_type="episodic_memory",
                target_type="episodic_memory",
            )
            logger.debug("[EPISODIC_MEMORY] Linked event #%d -[%s]-> #%d", previous_event_id, relation, new_id)
        return new_id

    def get_recent_events(
        self,
        topic: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieves recent non-expired events via authoritative MemoryManager."""
        return self._manager.get_recent_episodic_events(topic=topic, limit=limit)

    def find_latest_event_for_topic(self, topic: str) -> Optional[Dict[str, Any]]:
        """Finds the most recent non-expired event for a specific topic."""
        events = self.get_recent_events(topic=topic, limit=1)
        return events[0] if events else None

