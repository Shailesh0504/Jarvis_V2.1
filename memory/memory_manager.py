# memory/memory_manager.py
"""Unified Cognitive Memory Manager orchestrating all 5 memory tiers."""

import logging
from typing import Any, Dict, List, Optional

from .database import DatabaseManager
from .short_term import ShortTermMemory
from .working import WorkingMemory
from .long_term import LongTermMemory
from .episodic import EpisodicMemory
from .procedural import ProceduralMemory
from .preferences import PreferencesMemory

logger = logging.getLogger("jarvis.memory")


class MemoryManager:
    """Central coordinator for the 5 Cognitive Memory Tiers."""

    def __init__(self, db_path: str = "data/jarvis.db", event_bus: Optional[Any] = None):
        self.db = DatabaseManager(db_path=db_path)
        self.event_bus = event_bus

        # 1. Short-Term Memory Tier
        self.short_term = ShortTermMemory(self.db)

        # 2. Working Memory Tier
        self.working = WorkingMemory(self.db)

        # 3. Long-Term Memory Tier
        self.long_term = LongTermMemory(self.db)

        # 4. Episodic Memory Tier
        self.episodic = EpisodicMemory(self.db)

        # 5. Procedural Memory Tier
        self.procedural = ProceduralMemory(self.db)

        # 6. Persistent Experience Learning System
        from core.experience import ExperienceLearningSystem
        self.experience = ExperienceLearningSystem(db_or_path=self.db)

        # 7. Dedicated User Preferences Memory
        self.preferences = PreferencesMemory(self.db)

        # Aliases for backward compatibility
        self.semantic = self.long_term

        logger.info("Cognitive MemoryManager with Experience Learning System successfully initialized.")

    # Facade methods for seamless system-wide access
    def store_fact(self, key: str, value: str, category: str = "facts", tags: str = "") -> None:
        self.long_term.store_fact(key=key, value=value, category=category, tags=tags)
        if self.event_bus:
            from core.event_bus import MemoryCreated
            self.event_bus.emit_domain_event(MemoryCreated(memory_type="long_term", key=key, value=value))

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        return self.long_term.get_fact(key)

    def search_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.long_term.search_facts(query=query, limit=limit)

    def record_interaction(
        self,
        user_input: str,
        response: str,
        intent: Optional[str] = None,
        source: str = "cli",
        session_id: Optional[str] = None,
        execution_results: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        self.episodic.record(
            user_input=user_input,
            response=response,
            intent=intent,
            source=source,
            session_id=session_id,
            execution_results=execution_results
        )
        if self.event_bus:
            from core.event_bus import MemoryCreated
            self.event_bus.emit_domain_event(
                MemoryCreated(memory_type="episodic", key=user_input, value=response)
            )
        # Update short-term in-memory sliding buffer
        self.short_term._active_turns.append({"role": "user", "content": user_input, "intent": intent})
        self.short_term._active_turns.append({"role": "assistant", "content": response, "intent": intent})
        if len(self.short_term._active_turns) > (self.short_term.window_size * 2):
            self.short_term._active_turns = self.short_term._active_turns[-(self.short_term.window_size * 2):]

    def get_recent_interactions(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.episodic.get_recent(limit=limit)

    def set_preference(self, key: str, value: Any) -> None:
        self.long_term.set_preference(key, value)

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.long_term.get_preference(key, default)

    # Experience Learning System facade methods
    def retrieve_experience(self, query: str, category: Optional[str] = None):
        return self.experience.retrieve_experience(query=query, category=category)

    def record_experience_success(
        self,
        goal: str,
        steps: List[Dict[str, Any]],
        execution_context: Optional[Dict[str, Any]] = None,
        category: str = "general"
    ):
        return self.experience.record_task_success(
            goal=goal,
            steps=steps,
            execution_context=execution_context,
            category=category
        )

    def record_experience_failure(
        self,
        goal: str,
        failed_step: Dict[str, Any],
        error_msg: str,
        diagnosis: Optional[str] = None,
        category: str = "general"
    ):
        return self.experience.record_task_failure(
            goal=goal,
            failed_step=failed_step,
            error_msg=error_msg,
            diagnosis=diagnosis,
            category=category
        )

    def record_user_correction(
        self,
        concept: str,
        old_value: str,
        new_value: str,
        context: Optional[str] = None
    ):
        return self.experience.record_user_correction(
            concept=concept,
            old_value=old_value,
            new_value=new_value,
            context=context
        )

    # =========================================================================
    # Conversation Redesign Accessors (Phase 2.1 - Non-Breaking Adapter Methods)
    # Allows MemoryManager to serve episodic_memory and semantic_memory tables
    # directly using self.db, maintaining strict one-way dependency (no core.memory imports).
    # =========================================================================

    def record_episodic_event(
        self,
        event_type: str,
        topic: str,
        fact: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        user_id: str = "default_user",
    ) -> int:
        """Stores a structured conversation event into episodic_memory table."""
        import json
        import time

        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds else None
        meta_str = json.dumps(metadata or {})

        # Check existing columns to ensure compatibility with both clean and legacy schemas
        cols = {c["name"] for c in self.db.execute_query("PRAGMA table_info(episodic_memory)")}
        if "user_input" in cols and "assistant_response" in cols and "timestamp" in cols:
            sql = """
            INSERT INTO episodic_memory (
                user_id, type, topic, fact, confidence, created_at, last_seen_at, expires_at, metadata_json,
                user_input, assistant_response, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.db.execute_update(
                sql,
                (user_id, event_type, topic, fact, confidence, now, now, expires_at, meta_str, fact, "", now),
            )
        else:
            sql = """
            INSERT INTO episodic_memory (user_id, type, topic, fact, confidence, created_at, last_seen_at, expires_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.db.execute_update(sql, (user_id, event_type, topic, fact, confidence, now, now, expires_at, meta_str))
        rows = self.db.execute_query("SELECT MAX(id) as id FROM episodic_memory WHERE user_id = ?", (user_id,))
        event_id = rows[0]["id"] if (rows and rows[0]["id"] is not None) else 0
        logger.debug("[MEMORY_MANAGER] Stored episodic event #%d [%s:%s] %s", event_id, event_type, topic, fact)
        return event_id

    def get_recent_episodic_events(
        self,
        topic: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieves active, non-expired events from episodic_memory table."""
        import time

        now = time.time()
        if topic:
            sql = """
            SELECT id, type, topic, fact, confidence, created_at, last_seen_at, metadata_json
            FROM episodic_memory
            WHERE topic = ? AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC
            LIMIT ?
            """
            return self.db.execute_query(sql, (topic, now, limit))
        else:
            sql = """
            SELECT id, type, topic, fact, confidence, created_at, last_seen_at, metadata_json
            FROM episodic_memory
            WHERE (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC
            LIMIT ?
            """
            return self.db.execute_query(sql, (now, limit))

    def store_conversation_fact(
        self,
        key: str,
        value: str,
        category: str = "facts",
        tags: str = "",
        confidence: float = 1.0,
        user_id: str = "default_user",
    ) -> None:
        """Stores a durable semantic fact into the semantic_memory table."""
        import time

        sql = """
        INSERT INTO semantic_memory (user_id, category, key, value, confidence, tags, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            tags = excluded.tags,
            confidence = excluded.confidence,
            updated_at = excluded.updated_at
        """
        now = time.time()
        self.db.execute_update(
            sql,
            (user_id, category, key.strip().lower(), value.strip(), confidence, tags, now, now),
        )
        logger.debug("[MEMORY_MANAGER] Stored conversation fact: [%s] %s = %s", category, key, value)

    def get_conversation_fact(self, key: str, user_id: str = "default_user") -> Optional[Dict[str, Any]]:
        """Retrieves a durable semantic fact by key, prioritizing canonical memories table."""
        norm_key = key.strip().lower()
        # 1. Check canonical memories first
        mem_fact = self.long_term.get_fact(norm_key, user_id=user_id)
        if mem_fact:
            return {
                "id": mem_fact.get("id"),
                "category": mem_fact.get("category", "facts"),
                "key": mem_fact.get("key", norm_key),
                "value": mem_fact.get("value", ""),
                "confidence": float(mem_fact.get("confidence", 1.0)),
                "tags": mem_fact.get("tags", ""),
                "updated_at": mem_fact.get("updated_at", 0.0),
                "source_store": "canonical_memories",
            }

        # 2. Fallback to semantic_memory table for backward compatibility
        sql = "SELECT id, category, key, value, confidence, tags, updated_at FROM semantic_memory WHERE key = ?"
        rows = self.db.execute_query(sql, (norm_key,))
        if rows:
            res = dict(rows[0])
            res["source_store"] = "semantic_memory"
            return res
        return None

    def search_conversation_facts(self, query: str, limit: int = 5, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """
        Federated semantic search across canonical `memories` and legacy `semantic_memory`.
        Deduplicates by normalized key, prioritizing canonical `memories` facts.
        Preserves existing dict structure and ordering expectations.
        """
        cleaned = query.strip().lower()
        wildcard = f"%{cleaned}%"
        seen_keys = set()
        deduped_results: List[Dict[str, Any]] = []

        # 1. Query canonical memories store (primary truth)
        sql_mem = """
        SELECT id, category, key, value, confidence, tags, updated_at
        FROM memories
        WHERE (user_id = ? OR user_id IS NULL) AND (key LIKE ? OR value LIKE ? OR category LIKE ? OR tags LIKE ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """
        mem_rows = self.db.execute_query(sql_mem, (user_id, wildcard, wildcard, wildcard, wildcard, limit))
        for row in mem_rows:
            k = str(row.get("key", "")).strip().lower()
            if k and k not in seen_keys:
                seen_keys.add(k)
                item = dict(row)
                item["source_store"] = "canonical_memories"
                deduped_results.append(item)

        # 2. Query legacy/compatibility semantic_memory store
        sql_sem = """
        SELECT id, category, key, value, confidence, tags, updated_at
        FROM semantic_memory
        WHERE key LIKE ? OR value LIKE ? OR category LIKE ? OR tags LIKE ?
        ORDER BY updated_at DESC
        LIMIT ?
        """
        sem_rows = self.db.execute_query(sql_sem, (wildcard, wildcard, wildcard, wildcard, limit))
        for row in sem_rows:
            k = str(row.get("key", "")).strip().lower()
            if k and k not in seen_keys:
                seen_keys.add(k)
                item = dict(row)
                item["source_store"] = "semantic_memory"
                deduped_results.append(item)

        # 3. Sort federated results by updated_at descending and cap at limit
        deduped_results.sort(key=lambda x: float(x.get("updated_at") or 0.0), reverse=True)
        return deduped_results[:limit]

    def delete_conversation_fact(self, key: str, user_id: str = "default_user") -> bool:
        """Deletes a fact from semantic_memory table (and memories if present)."""
        norm_key = key.strip().lower()
        sql_sem = "DELETE FROM semantic_memory WHERE key = ?"
        count_sem = self.db.execute_update(sql_sem, (norm_key,))
        count_mem = self.long_term.delete_fact(norm_key, user_id=user_id)
        return (count_sem > 0) or count_mem

    def get_all_conversation_facts(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Returns all federated facts from canonical memories and semantic_memory, deduplicated by key."""
        seen_keys = set()
        all_results: List[Dict[str, Any]] = []

        # Canonical memories first
        mem_rows = self.long_term.get_all_facts(user_id=user_id)
        for row in mem_rows:
            k = str(row.get("key", "")).strip().lower()
            if k and k not in seen_keys:
                seen_keys.add(k)
                all_results.append(dict(row))

        # Legacy semantic_memory
        sql = "SELECT id, category, key, value, confidence, tags, updated_at FROM semantic_memory ORDER BY category, key"
        sem_rows = self.db.execute_query(sql)
        for row in sem_rows:
            k = str(row.get("key", "")).strip().lower()
            if k and k not in seen_keys:
                seen_keys.add(k)
                all_results.append(dict(row))

        all_results.sort(key=lambda x: (x.get("category", "facts"), x.get("key", "")))
        return all_results

    def link_memory_events(
        self,
        source_id: Any,
        target_id: Any,
        relation_type: str = "UPDATED_BY",
        confidence: float = 1.0,
        source_type: str = "episodic_memory",
        target_type: str = "episodic_memory",
    ) -> None:
        """Records a relationship link in memory_links table."""
        import time

        link_sql = """
        INSERT INTO memory_links (source_type, source_id, target_type, target_id, relation_type, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute_update(
            link_sql,
            (source_type, str(source_id), target_type, str(target_id), relation_type, confidence, time.time()),
        )
        logger.debug("[MEMORY_MANAGER] Linked memory %s #%s -[%s]-> %s #%s", source_type, source_id, relation_type, target_type, target_id)

