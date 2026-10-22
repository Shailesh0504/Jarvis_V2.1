# learning/workflow_layer.py
"""Layer 3: Composite Workflows & Learned Macros."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.workflow")


class WorkflowLayer:
    """Layer 3: Manages multi-step composite macro workflows backed by workflows table."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._workflows: Dict[str, Dict[str, Any]] = {}
        self._init_default_workflows()
        self._load_workflows()

    def _init_default_workflows(self) -> None:
        """Seeds built-in composite workflows like Excel clean."""
        excel_clean_steps = [
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "select_used_range"}, "description": "1. Select used range"},
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "autofit"}, "description": "2. Auto-fit column widths"},
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "alignment"}, "description": "3. Align text & headers"},
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "borders"}, "description": "4. Apply standard grid borders"},
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "remove_blanks"}, "description": "5. Remove empty rows & columns"},
            {"plugin": "excel", "action": "clean_sheet", "parameters": {"operation": "save"}, "description": "6. Save sanitized spreadsheet"}
        ]
        self.register_workflow(
            name="excel_clean",
            trigger_phrases=["excel clean karo", "clean excel", "sanitize spreadsheet", "clean sheet", "excel format karo"],
            steps=excel_clean_steps
        )

    def register_workflow(
        self,
        name: str,
        trigger_phrases: List[str],
        steps: List[Dict[str, Any]],
        description: str = ""
    ) -> None:
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
        triggers_str = json.dumps([p.lower() for p in trigger_phrases])
        steps_str = json.dumps(steps)
        self.db.execute_update(sql, (name.lower(), description, triggers_str, steps_str, now, now))
        self._workflows[name.lower()] = {
            "name": name,
            "description": description,
            "triggers": [p.lower() for p in trigger_phrases],
            "steps": steps
        }
        logger.info(f"Layer 3 Workflow registered: '{name}' with {len(steps)} steps.")

    def _load_workflows(self) -> None:
        try:
            sql = "SELECT workflow_name, triggers, steps_json FROM workflows"
            rows = self.db.execute_query(sql)
            for r in rows:
                self._workflows[r["workflow_name"].lower()] = {
                    "name": r["workflow_name"],
                    "triggers": json.loads(r["triggers"]),
                    "steps": json.loads(r["steps_json"])
                }
        except Exception as e:
            logger.error(f"Failed to load workflows: {e}")

    def match_workflow(self, query: str) -> Optional[Dict[str, Any]]:
        lower = query.strip().lower()
        for wf_name, data in self._workflows.items():
            for trigger in data["triggers"]:
                if trigger in lower:
                    return data
        return None

    def get_all_workflows(self) -> Dict[str, Any]:
        return dict(self._workflows)
