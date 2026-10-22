# core/experience/storage.py
"""
SQLite Storage Engine for the Persistent Experience Learning System.
Manages transactional persistence, version history, active status,
and query filtering across all 4 cognitive experience tiers.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from memory.database import DatabaseManager
from .models import ExperienceItem, MemoryType

logger = logging.getLogger("jarvis.experience.storage")


class ExperienceStorageManager:
    """Manages SQLite CRUD operations for experience_memories table."""

    def __init__(self, db_or_path: Any = "data/jarvis.db"):
        if isinstance(db_or_path, str):
            self.db = DatabaseManager(db_path=db_or_path)
        else:
            self.db = db_or_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensures the experience_memories table and indices are initialized."""
        with self.db._lock:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS experience_memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    query_pattern TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    superseded_by TEXT,
                    source TEXT NOT NULL,
                    task_metadata_json TEXT,
                    embedding_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_type_active ON experience_memories (memory_type, is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_category ON experience_memories (category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_query ON experience_memories (query_pattern)")
                conn.commit()

    def save_item(self, item: ExperienceItem) -> None:
        """Saves or updates an ExperienceItem in SQLite."""
        sql = """
        INSERT INTO experience_memories (
            id, memory_type, category, query_pattern, content_json,
            confidence, success_count, failure_count, version, is_active,
            superseded_by, source, task_metadata_json, embedding_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            memory_type = excluded.memory_type,
            category = excluded.category,
            query_pattern = excluded.query_pattern,
            content_json = excluded.content_json,
            confidence = excluded.confidence,
            success_count = excluded.success_count,
            failure_count = excluded.failure_count,
            version = excluded.version,
            is_active = excluded.is_active,
            superseded_by = excluded.superseded_by,
            source = excluded.source,
            task_metadata_json = excluded.task_metadata_json,
            embedding_json = excluded.embedding_json,
            updated_at = excluded.updated_at
        """
        now = time.time()
        item.updated_at = now

        type_val = item.memory_type.value if isinstance(item.memory_type, MemoryType) else str(item.memory_type)
        content_str = json.dumps(item.content)
        meta_str = json.dumps(item.task_metadata)
        emb_str = json.dumps(item.embedding) if item.embedding is not None else None

        self.db.execute_update(sql, (
            item.id,
            type_val,
            item.category,
            item.query_pattern,
            content_str,
            item.confidence,
            item.success_count,
            item.failure_count,
            item.version,
            1 if item.is_active else 0,
            item.superseded_by,
            item.source,
            meta_str,
            emb_str,
            item.created_at,
            now
        ))
        logger.debug("ExperienceStorage: Saved item '%s' (type: %s, active: %s, v%d)",
                     item.id, type_val, item.is_active, item.version)

    def get_item(self, item_id: str) -> Optional[ExperienceItem]:
        """Loads an ExperienceItem by ID."""
        sql = "SELECT * FROM experience_memories WHERE id = ?"
        rows = self.db.execute_query(sql, (item_id,))
        if not rows:
            return None
        return self._row_to_item(rows[0])

    def get_active_items(
        self,
        memory_type: Optional[MemoryType] = None,
        category: Optional[str] = None
    ) -> List[ExperienceItem]:
        """Retrieves active (non-superseded) experience items with optional filters."""
        clauses = ["is_active = 1"]
        params = []

        if memory_type:
            clauses.append("memory_type = ?")
            type_val = memory_type.value if isinstance(memory_type, MemoryType) else str(memory_type)
            params.append(type_val)

        if category:
            clauses.append("category = ?")
            params.append(category)

        sql = f"SELECT * FROM experience_memories WHERE {' AND '.join(clauses)} ORDER BY confidence DESC, updated_at DESC"
        rows = self.db.execute_query(sql, tuple(params))
        return [self._row_to_item(r) for r in rows]

    def get_all_items(self) -> List[ExperienceItem]:
        """Retrieves all experience items, including superseded versions for audit."""
        sql = "SELECT * FROM experience_memories ORDER BY updated_at DESC"
        rows = self.db.execute_query(sql)
        return [self._row_to_item(r) for r in rows]

    def delete_item(self, item_id: str) -> bool:
        """Hard deletes an experience item."""
        sql = "DELETE FROM experience_memories WHERE id = ?"
        return self.db.execute_update(sql, (item_id,)) > 0

    def _row_to_item(self, r: Dict[str, Any]) -> ExperienceItem:
        """Converts an SQLite row dict into an ExperienceItem."""
        emb = None
        if r.get("embedding_json"):
            try:
                emb = json.loads(r["embedding_json"])
            except Exception:
                emb = None

        content = {}
        if r.get("content_json"):
            try:
                content = json.loads(r["content_json"])
            except Exception:
                content = {}

        meta = {}
        if r.get("task_metadata_json"):
            try:
                meta = json.loads(r["task_metadata_json"])
            except Exception:
                meta = {}

        return ExperienceItem(
            id=r["id"],
            memory_type=MemoryType(r["memory_type"]),
            category=r["category"],
            query_pattern=r["query_pattern"],
            content=content,
            confidence=float(r["confidence"]),
            success_count=int(r["success_count"]),
            failure_count=int(r["failure_count"]),
            version=int(r["version"]),
            is_active=bool(r["is_active"]),
            superseded_by=r.get("superseded_by"),
            source=r["source"],
            task_metadata=meta,
            embedding=emb,
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )
