# memory/working.py
"""Working Memory Tier: Current in-flight task state, intermediate variables, and execution graphs."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from .database import DatabaseManager

logger = logging.getLogger("jarvis.memory.working")


class WorkingMemory:
    """Manages active task states, dynamic variable scoping, and intermediate plan outputs."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.active_task_id: Optional[str] = None
        self.active_variables: Dict[str, Any] = {}

    def start_task(self, task_title: str, user_goal: str, total_steps: int = 1, execution_graph: Optional[List[Dict[str, Any]]] = None) -> str:
        """Initializes an active working memory task in DB and runtime state."""
        task_id = str(uuid.uuid4())
        self.active_task_id = task_id
        self.active_variables.clear()

        graph_json = json.dumps(execution_graph or [])
        sql = """
        INSERT INTO tasks (id, task_title, user_goal, status, current_step, total_steps, execution_graph_json, created_at)
        VALUES (?, ?, ?, 'IN_PROGRESS', 0, ?, ?, ?)
        """
        self.db.execute_update(sql, (task_id, task_title, user_goal, total_steps, graph_json, time.time()))
        logger.info(f"Working Memory: Started task '{task_id}' ({task_title})")
        return task_id

    def set_variable(self, key: str, value: Any) -> None:
        """Sets an intermediate computation or observation variable (e.g. latest_file)."""
        self.active_variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.active_variables.get(key, default)

    def update_task_progress(self, task_id: str, current_step: int, step_data: Optional[Dict[str, Any]] = None) -> None:
        sql = "UPDATE tasks SET current_step = ? WHERE id = ?"
        self.db.execute_update(sql, (current_step, task_id))
        if step_data:
            for k, v in step_data.items():
                self.set_variable(k, v)

    def complete_task(self, task_id: str, final_result: Optional[Dict[str, Any]] = None) -> None:
        sql = "UPDATE tasks SET status = 'COMPLETED', finished_at = ? WHERE id = ?"
        self.db.execute_update(sql, (time.time(), task_id))
        self.active_task_id = None
        logger.info(f"Working Memory: Completed task '{task_id}'")

    def fail_task(self, task_id: str, error_message: str) -> None:
        sql = "UPDATE tasks SET status = 'FAILED', finished_at = ? WHERE id = ?"
        self.db.execute_update(sql, (time.time(), task_id))
        self.active_task_id = None
        logger.warning(f"Working Memory: Failed task '{task_id}': {error_message}")

    def get_recent_tasks(self, limit: int = 5) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?"
        return self.db.execute_query(sql, (limit,))

    def bind_task_state(self, task_state: Any) -> None:
        """Binds an active TaskContinuityEngine TaskState to working memory."""
        self.active_task_id = getattr(task_state, "task_id", None)
        if hasattr(task_state, "execution_context"):
            self.active_variables.update(task_state.execution_context)

    def get_active_task_state(self) -> Optional[Any]:
        """Loads the currently bound TaskState from persistent storage."""
        if not self.active_task_id:
            return None
        from core.task_engine.persistence import TaskPersistenceManager
        persistence = TaskPersistenceManager(self.db)
        return persistence.load_task_state(self.active_task_id)

