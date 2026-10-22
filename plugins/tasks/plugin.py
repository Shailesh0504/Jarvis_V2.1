# plugins/tasks/plugin.py
"""Tasks capability plugin implementation for managing persistent todo lists, deadlines, and markdown exports."""

import datetime
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.tasks")


class TasksPlugin(BasePlugin):
    """Controls persistent tasks, todo list items, priority filtering, and productivity metrics."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.db_path = os.path.join("data", "tasks.db")
        self._init_db()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="tasks",
            version="2.0.0",
            description="Persistent task management, priority tracking, deadlines, and productivity checklist manager.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _init_db(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        priority TEXT DEFAULT 'normal',
                        due_date TEXT DEFAULT '',
                        completed INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize tasks database: %s", e)

    def _get_conn(self) -> sqlite3.Connection:
        self._init_db()
        return sqlite3.connect(self.db_path)

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "export_tasks_to_markdown":
            out_path = parameters.get("output_path")
            if out_path and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=out_path,
                    actual=f"{os.path.getsize(out_path)} bytes",
                    message="Markdown tasks export verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=out_path,
                actual=None,
                error="Exported tasks file missing or empty."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. init_persistent_storage
        if action_name == "init_persistent_storage":
            self._init_db()
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tasks")
                count = cursor.fetchone()[0]
            return PluginResult(
                success=True,
                data={"db_path": self.db_path, "total_tasks": count, "message": f"Tasks database verified at '{self.db_path}' ({count} tasks)."}
            )

        # 2. add_task
        elif action_name == "add_task":
            title = parameters.get("title", "").strip()
            priority = str(parameters.get("priority", "normal")).lower()
            due_date = parameters.get("due_date", "").strip()

            if not title:
                return PluginResult(success=False, error="Task title is required.")

            valid_priorities = ("low", "normal", "high", "urgent")
            if priority not in valid_priorities:
                priority = "normal"

            now_str = datetime.datetime.now().isoformat()
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO tasks (title, priority, due_date, completed, created_at) VALUES (?, ?, ?, 0, ?)",
                    (title, priority, due_date, now_str)
                )
                conn.commit()
                task_id = cursor.lastrowid

            task = {
                "id": task_id,
                "title": title,
                "priority": priority,
                "due_date": due_date,
                "completed": False,
                "created_at": now_str
            }
            return PluginResult(
                success=True,
                data={"task": task, "message": f"Task #{task_id} '{title}' ({priority}) added successfully."}
            )

        # 3. list_tasks
        elif action_name == "list_tasks":
            status_filter = str(parameters.get("status", "pending")).lower()
            limit = int(parameters.get("limit", 15))

            query = "SELECT id, title, priority, due_date, completed FROM tasks"
            args: List[Any] = []
            if status_filter == "pending":
                query += " WHERE completed = 0"
            elif status_filter == "completed":
                query += " WHERE completed = 1"

            query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END, id ASC LIMIT ?"
            args.append(limit)

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(query, args)
                rows = cursor.fetchall()

            tasks = [{
                "id": r[0], "title": r[1], "priority": r[2], "due_date": r[3], "completed": bool(r[4])
            } for r in rows]

            summary = ", ".join([f"#{t['id']}: {t['title']} [{t['priority']}]" for t in tasks])
            return PluginResult(
                success=True,
                data={
                    "tasks": tasks,
                    "count": len(tasks),
                    "filter": status_filter,
                    "message": f"Tasks ({len(tasks)}): {summary}" if tasks else f"No {status_filter} tasks found."
                }
            )

        # 4. complete_task
        elif action_name == "complete_task":
            task_id = int(parameters.get("task_id", -1))
            title = parameters.get("title", "").strip()

            with self._get_conn() as conn:
                cursor = conn.cursor()
                if task_id > 0:
                    cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
                elif title:
                    cursor.execute("UPDATE tasks SET completed = 1 WHERE title LIKE ? AND completed = 0", (f"%{title}%",))
                else:
                    return PluginResult(success=False, error="task_id or title is required.")
                conn.commit()
                completed = cursor.rowcount

            if completed > 0:
                return PluginResult(success=True, data={"completed_count": completed, "message": f"Task marked as completed."})
            return PluginResult(success=False, error="Matching active task not found.")

        # 5. delete_task
        elif action_name == "delete_task":
            task_id = int(parameters.get("task_id", -1))
            title = parameters.get("title", "").strip()

            with self._get_conn() as conn:
                cursor = conn.cursor()
                if task_id > 0:
                    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                elif title:
                    cursor.execute("DELETE FROM tasks WHERE title LIKE ?", (f"%{title}%",))
                else:
                    return PluginResult(success=False, error="task_id or title is required to delete task.")
                conn.commit()
                deleted = cursor.rowcount

            if deleted > 0:
                return PluginResult(success=True, data={"deleted_count": deleted, "message": f"Deleted {deleted} task(s)."})
            return PluginResult(success=False, error="Matching task not found to delete.")

        # 6. update_task_title
        elif action_name == "update_task_title":
            task_id = int(parameters.get("task_id", -1))
            new_title = parameters.get("new_title", "").strip()
            if task_id <= 0 or not new_title:
                return PluginResult(success=False, error="task_id and new_title are required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET title = ? WHERE id = ?", (new_title, task_id))
                conn.commit()
                updated = cursor.rowcount

            if updated > 0:
                return PluginResult(success=True, data={"task_id": task_id, "title": new_title, "message": f"Task #{task_id} title updated."})
            return PluginResult(success=False, error=f"Task #{task_id} not found.")

        # 7. set_task_priority
        elif action_name == "set_task_priority":
            task_id = int(parameters.get("task_id", -1))
            prio = str(parameters.get("priority", "normal")).lower()
            if task_id <= 0:
                return PluginResult(success=False, error="Valid task_id is required.")
            if prio not in ("low", "normal", "high", "urgent"):
                return PluginResult(success=False, error="Priority must be low, normal, high, or urgent.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET priority = ? WHERE id = ?", (prio, task_id))
                conn.commit()
                updated = cursor.rowcount

            if updated > 0:
                return PluginResult(success=True, data={"task_id": task_id, "priority": prio, "message": f"Task #{task_id} priority set to '{prio}'."})
            return PluginResult(success=False, error=f"Task #{task_id} not found.")

        # 8. filter_tasks_by_priority
        elif action_name == "filter_tasks_by_priority":
            prio = str(parameters.get("priority", "high")).lower()
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, priority, due_date FROM tasks WHERE priority = ? AND completed = 0", (prio,))
                rows = cursor.fetchall()

            tasks = [{"id": r[0], "title": r[1], "priority": r[2], "due_date": r[3]} for r in rows]
            return PluginResult(
                success=True,
                data={"priority": prio, "count": len(tasks), "tasks": tasks, "message": f"Found {len(tasks)} active '{prio}' priority task(s)."}
            )

        # 9. clear_completed_tasks
        elif action_name == "clear_completed_tasks":
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM tasks WHERE completed = 1")
                conn.commit()
                deleted = cursor.rowcount
            return PluginResult(success=True, data={"deleted_count": deleted, "message": f"Purged {deleted} completed task(s)."})

        # 10. set_task_due_date
        elif action_name == "set_task_due_date":
            task_id = int(parameters.get("task_id", -1))
            due = parameters.get("due_date", "").strip()
            if task_id <= 0 or not due:
                return PluginResult(success=False, error="task_id and due_date are required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (due, task_id))
                conn.commit()
                updated = cursor.rowcount

            if updated > 0:
                return PluginResult(success=True, data={"task_id": task_id, "due_date": due, "message": f"Task #{task_id} due date set to {due}."})
            return PluginResult(success=False, error=f"Task #{task_id} not found.")

        # 11. get_overdue_tasks
        elif action_name == "get_overdue_tasks":
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, priority, due_date FROM tasks WHERE completed = 0 AND due_date != '' AND due_date < ?", (today_str,))
                rows = cursor.fetchall()

            overdue = [{"id": r[0], "title": r[1], "priority": r[2], "due_date": r[3]} for r in rows]
            return PluginResult(
                success=True,
                data={"today": today_str, "count": len(overdue), "tasks": overdue, "message": f"Found {len(overdue)} overdue task(s)."}
            )

        # 12. export_tasks_to_markdown
        elif action_name == "export_tasks_to_markdown":
            out_path = parameters.get("output_path", "").strip()
            if not out_path:
                return PluginResult(success=False, error="output_path is required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, priority, due_date, completed FROM tasks ORDER BY completed ASC, id ASC")
                rows = cursor.fetchall()

            lines = ["# Jarvis Todo & Task List\n", f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
            for r in rows:
                tid, title, prio, due, comp = r
                box = "[x]" if comp else "[ ]"
                due_info = f" *(Due: {due})*" if due else ""
                lines.append(f"- {box} **#{tid}** {title} `[{prio}]`{due_info}")

            content = "\n".join(lines)
            try:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

                return PluginResult(
                    success=True,
                    data={"output_path": out_path, "total_tasks": len(rows), "size_bytes": os.path.getsize(out_path), "message": f"Exported {len(rows)} tasks to '{out_path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Markdown export failed: {e}")

        # 13. get_task_metrics
        elif action_name == "get_task_metrics":
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tasks")
                total = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1")
                done = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE completed = 0 AND due_date != '' AND due_date < ?", (today_str,))
                overdue = cursor.fetchone()[0]

            pending = total - done
            rate = round((done / total * 100.0), 1) if total > 0 else 0.0

            metrics = {
                "total_tasks": total,
                "completed": done,
                "pending": pending,
                "overdue": overdue,
                "completion_rate_percent": rate
            }
            return PluginResult(
                success=True,
                data={"metrics": metrics, "message": f"Task Productivity: {done}/{total} completed ({rate}%), {pending} pending, {overdue} overdue."}
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Tasks plugin.")
