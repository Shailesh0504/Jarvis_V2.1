# core/task_engine/persistence.py
"""
SQLite Persistence and Checkpoint Manager for the Task Continuity Engine.
Ensures every verified step is checkpointed to survive crashes, restarts,
and system interruptions, and manages previous experience retrieval.
"""

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .models import StepExecutionReport, TaskState, TaskStatus, TaskStep

logger = logging.getLogger("jarvis.task_engine.persistence")


class TaskPersistenceManager:
    """Manages SQLite storage, checkpointing, crash recovery, and experience records."""

    def __init__(self, db_or_path: Any = "data/jarvis.db"):
        if isinstance(db_or_path, str):
            from memory.database import DatabaseManager
            self.db = DatabaseManager(db_path=db_or_path)
        else:
            self.db = db_or_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes tables for workflow persistence, checkpoints, and experience."""
        with self.db._lock:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Full task state storage
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_workflows (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    task_state_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 2. Verified step checkpoints
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """)

                # 3. Experience learning storage
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_experience (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_pattern TEXT NOT NULL,
                    procedure_json TEXT NOT NULL,
                    success_rate REAL DEFAULT 1.0,
                    successful_runs INTEGER DEFAULT 1,
                    failed_runs INTEGER DEFAULT 0,
                    strategies_json TEXT,
                    failure_modes_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)
                conn.commit()

    def save_task_state(self, task: TaskState) -> None:
        """Persists the complete TaskState snapshot to SQLite."""
        sql = """
        INSERT INTO task_workflows (
            task_id, goal, final_status, current_step, total_steps,
            retry_count, task_state_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
            goal = excluded.goal,
            final_status = excluded.final_status,
            current_step = excluded.current_step,
            total_steps = excluded.total_steps,
            retry_count = excluded.retry_count,
            task_state_json = excluded.task_state_json,
            updated_at = excluded.updated_at
        """
        now = time.time()
        task.updated_at = now
        state_json = json.dumps(task.to_dict())
        status_str = task.final_status.value if isinstance(task.final_status, TaskStatus) else str(task.final_status)

        self.db.execute_update(sql, (
            task.task_id,
            task.goal,
            status_str,
            task.current_step,
            task.total_steps,
            task.retry_count,
            state_json,
            task.created_at,
            now
        ))
        logger.debug("TaskPersistence: Saved task '%s' (status: %s, step: %d/%d)",
                     task.task_id, status_str, task.current_step, task.total_steps)

    def load_task_state(self, task_id: str) -> Optional[TaskState]:
        """Loads a persistent TaskState from SQLite by task_id."""
        sql = "SELECT task_state_json FROM task_workflows WHERE task_id = ?"
        rows = self.db.execute_query(sql, (task_id,))
        if not rows:
            return None
        data = json.loads(rows[0]["task_state_json"])
        return TaskState.from_dict(data)

    def checkpoint_step(self, task: TaskState, step_report: StepExecutionReport) -> int:
        """
        Records a verified checkpoint for the executed step.
        Persists both the checkpoint row and updates the active task workflow snapshot.
        """
        # Save snapshot
        self.save_task_state(task)

        sql = """
        INSERT INTO task_checkpoints (task_id, step_index, step_id, verified, checkpoint_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        checkpoint_data = {
            "task_id": task.task_id,
            "step_index": task.current_step - 1,
            "step_id": step_report.step_id,
            "step_report": step_report.to_dict(),
            "execution_context": dict(task.execution_context),
            "timestamp": time.time(),
        }
        ch_id = self.db.execute_update(sql, (
            task.task_id,
            task.current_step - 1,
            step_report.step_id,
            1 if step_report.verified else 0,
            json.dumps(checkpoint_data),
            time.time()
        ))
        logger.info("TaskPersistence: Checkpointed step %d ('%s') for task '%s'",
                    task.current_step - 1, step_report.step_name, task.task_id)
        return ch_id

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent verified checkpoint for a task."""
        sql = """
        SELECT checkpoint_json FROM task_checkpoints
        WHERE task_id = ? AND verified = 1
        ORDER BY step_index DESC, id DESC LIMIT 1
        """
        rows = self.db.execute_query(sql, (task_id,))
        if not rows:
            return None
        return json.loads(rows[0]["checkpoint_json"])

    def get_checkpoints_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieves all checkpoints for a task ordered by step_index."""
        sql = """
        SELECT id, task_id, step_index, step_id, verified, checkpoint_json, created_at
        FROM task_checkpoints
        WHERE task_id = ?
        ORDER BY step_index ASC, id ASC
        """
        return self.db.execute_query(sql, (task_id,))

    def get_incomplete_tasks(self) -> List[TaskState]:
        """Retrieves all tasks that were interrupted, in-progress, or suspended."""
        sql = """
        SELECT task_state_json FROM task_workflows
        WHERE final_status IN ('RUNNING', 'SUSPENDED', 'RETRYING', 'PLANNING')
        ORDER BY updated_at DESC
        """
        rows = self.db.execute_query(sql)
        tasks = []
        for r in rows:
            try:
                tasks.append(TaskState.from_dict(json.loads(r["task_state_json"])))
            except Exception as e:
                logger.error("Error deserializing incomplete task: %s", e)
        return tasks

    def record_experience(
        self,
        goal: str,
        plan: List[TaskStep],
        success: bool,
        strategies: Optional[List[str]] = None,
        failure_modes: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Stores reusable procedures, successful strategies, and observed failures."""
        now = time.time()
        goal_norm = goal.strip().lower()
        proc_data = [s.to_dict() for s in plan]

        # Check existing pattern
        sql_check = "SELECT id, successful_runs, failed_runs, strategies_json, failure_modes_json FROM task_experience WHERE goal_pattern = ?"
        rows = self.db.execute_query(sql_check, (goal_norm,))

        if rows:
            row = rows[0]
            succ = row["successful_runs"] + (1 if success else 0)
            fail = row["failed_runs"] + (0 if success else 1)
            rate = succ / max(1, succ + fail)

            existing_strats = json.loads(row["strategies_json"] or "[]")
            if strategies:
                existing_strats = list(set(existing_strats + strategies))

            existing_fails = json.loads(row["failure_modes_json"] or "[]")
            if failure_modes:
                existing_fails.extend(failure_modes)
                existing_fails = existing_fails[-10:]

            sql_up = """
            UPDATE task_experience
            SET procedure_json = ?, success_rate = ?, successful_runs = ?,
                failed_runs = ?, strategies_json = ?, failure_modes_json = ?, updated_at = ?
            WHERE id = ?
            """
            self.db.execute_update(sql_up, (
                json.dumps(proc_data), rate, succ, fail,
                json.dumps(existing_strats), json.dumps(existing_fails), now, row["id"]
            ))
        else:
            rate = 1.0 if success else 0.0
            succ = 1 if success else 0
            fail = 0 if success else 1
            sql_ins = """
            INSERT INTO task_experience (
                goal_pattern, procedure_json, success_rate, successful_runs,
                failed_runs, strategies_json, failure_modes_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.db.execute_update(sql_ins, (
                goal_norm, json.dumps(proc_data), rate, succ, fail,
                json.dumps(strategies or []), json.dumps(failure_modes or []), now, now
            ))

    def retrieve_experience(self, goal: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieves relevant previous experiences to guide planning."""
        sql = """
        SELECT goal_pattern, procedure_json, success_rate, strategies_json, failure_modes_json
        FROM task_experience
        ORDER BY success_rate DESC, updated_at DESC
        """
        rows = self.db.execute_query(sql)
        goal_words = set(goal.strip().lower().split())

        scored = []
        for r in rows:
            pattern_words = set(r["goal_pattern"].split())
            overlap = len(goal_words & pattern_words)
            if overlap > 0 or r["goal_pattern"] in goal.lower() or goal.lower() in r["goal_pattern"]:
                score = overlap + (2.0 if r["goal_pattern"] in goal.lower() else 0.0)
                scored.append((score, {
                    "goal_pattern": r["goal_pattern"],
                    "procedure": json.loads(r["procedure_json"]),
                    "success_rate": r["success_rate"],
                    "strategies": json.loads(r["strategies_json"] or "[]"),
                    "failure_modes": json.loads(r["failure_modes_json"] or "[]"),
                }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]
