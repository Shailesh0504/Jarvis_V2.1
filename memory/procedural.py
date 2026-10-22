# memory/procedural.py
"""Procedural Memory Tier: How the user likes tasks performed, composite workflows, and SOP routines."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.procedural")


class ProceduralMemory:
    """Manages learned macro routines, procedural workflows, and custom domain entities."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # 1. Workflows & SOP Routines (workflows table)
    def register_workflow(self, workflow_name: str, trigger_phrases: List[str], steps: List[Dict[str, Any]], description: str = "") -> None:
        sql = """
        INSERT INTO workflows (workflow_name, description, triggers, steps_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(workflow_name) DO UPDATE SET
            description = excluded.description,
            triggers = excluded.triggers,
            steps_json = excluded.steps_json,
            updated_at = excluded.updated_at
        """
        now = time.time()
        triggers_json = json.dumps([p.lower() for p in trigger_phrases])
        steps_json = json.dumps(steps)
        self.db.execute_update(sql, (workflow_name.lower(), description, triggers_json, steps_json, now, now))
        logger.info(f"Procedural Memory: Saved workflow routine '{workflow_name}' with {len(steps)} steps.")

    def get_workflow(self, workflow_name: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT workflow_name, description, triggers, steps_json FROM workflows WHERE workflow_name = ?"
        rows = self.db.execute_query(sql, (workflow_name.lower(),))
        if not rows:
            return None
        r = rows[0]
        return {
            "name": r["workflow_name"],
            "description": r["description"],
            "triggers": json.loads(r["triggers"]),
            "steps": json.loads(r["steps_json"])
        }

    def get_all_workflows(self) -> List[Dict[str, Any]]:
        sql = "SELECT workflow_name, description, triggers, steps_json FROM workflows"
        rows = self.db.execute_query(sql)
        workflows = []
        for r in rows:
            workflows.append({
                "name": r["workflow_name"],
                "description": r["description"],
                "triggers": json.loads(r["triggers"]),
                "steps": json.loads(r["steps_json"])
            })
        return workflows

    # 2. Domain Entities & Aliases (entities table)
    def learn_entity(self, name: str, normalized_value: str, entity_type: str = "vocabulary", metadata: Optional[Dict[str, Any]] = None) -> None:
        sql = """
        INSERT INTO entities (entity_type, name, normalized_value, context_id, metadata, updated_at)
        VALUES (?, ?, ?, '', ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            normalized_value = excluded.normalized_value,
            entity_type = excluded.entity_type,
            metadata = excluded.metadata,
            updated_at = excluded.updated_at
        """
        meta_str = json.dumps(metadata or {})
        self.db.execute_update(sql, (entity_type, name.strip().lower(), normalized_value.strip(), meta_str, time.time()))

    def resolve_entity(self, name: str) -> Optional[str]:
        sql = "SELECT normalized_value FROM entities WHERE name = ?"
        rows = self.db.execute_query(sql, (name.strip().lower(),))
        return rows[0]["normalized_value"] if rows else None

    def get_all_entities(self, entity_type: Optional[str] = None) -> Dict[str, str]:
        if entity_type:
            sql = "SELECT name, normalized_value FROM entities WHERE entity_type = ?"
            rows = self.db.execute_query(sql, (entity_type,))
        else:
            sql = "SELECT name, normalized_value FROM entities"
            rows = self.db.execute_query(sql)
        return {r["name"]: r["normalized_value"] for r in rows}
