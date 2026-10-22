# plugins/notifications/plugin.py
"""Notifications capability plugin implementation for desktop toast notifications and persistent history."""

import csv
import datetime
import json
import logging
import os
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.notifications")


class NotificationsPlugin(BasePlugin):
    """Controls desktop notifications, custom urgency alerts, and persistent history tracking."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self.db_path = os.path.join("data", "notifications.db")
        self._history: List[Dict[str, Any]] = []
        self._init_db()

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        notification_type TEXT NOT NULL DEFAULT 'info',
                        action_command TEXT DEFAULT '',
                        is_read INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
            self._sync_history_from_db()
        except Exception as e:
            logger.error("Failed initializing notifications SQLite database: %s", e)

    def _sync_history_from_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, message, notification_type, is_read, created_at FROM notifications ORDER BY id DESC LIMIT 50")
                rows = cursor.fetchall()
                self._history = [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "message": row["message"],
                        "type": row["notification_type"],
                        "is_read": bool(row["is_read"]),
                        "timestamp": row["created_at"]
                    }
                    for row in rows
                ]
        except Exception:
            pass

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="notifications",
            version="2.0.0",
            description="Windows desktop notifications, custom urgency alerts, and persistent notification history tracker.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("show_notification", "show_warning_notification", "show_error_notification", "show_actionable_notification"):
            nid = (result_data or {}).get("notification_id")
            if nid:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM notifications WHERE id = ?", (nid,))
                    found = cursor.fetchone()
                return VerificationResult(
                    verified=bool(found),
                    state=ExecutionState.SUCCESS if found else ExecutionState.FAILED,
                    check_type="database_record_exists",
                    expected=f"Notification ID {nid}",
                    actual=f"Found: {bool(found)}",
                    message="Notification persisted and delivered." if found else "Notification missing from database."
                )
        elif action_name == "export_notification_history":
            path = (result_data or {}).get("destination_path")
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=path,
                    actual=f"{os.path.getsize(path)} bytes",
                    message="Exported notification history file verified on disk."
                )
        return None

    def _send_toast(self, title: str, message: str, icon_type: str = "Info", duration_ms: int = 3000):
        try:
            safe_title = title.replace("'", "''")
            safe_msg = message.replace("'", "''")
            icon_map = {
                "Info": "[System.Drawing.SystemIcons]::Information",
                "Warning": "[System.Drawing.SystemIcons]::Warning",
                "Error": "[System.Drawing.SystemIcons]::Error",
                "Action": "[System.Drawing.SystemIcons]::Application"
            }
            icon_expr = icon_map.get(icon_type, "[System.Drawing.SystemIcons]::Information")

            tip_icon_map = {
                "Info": "[system.windows.forms.tooltipicon]::Info",
                "Warning": "[system.windows.forms.tooltipicon]::Warning",
                "Error": "[system.windows.forms.tooltipicon]::Error",
                "Action": "[system.windows.forms.tooltipicon]::Info"
            }
            tip_expr = tip_icon_map.get(icon_type, "[system.windows.forms.tooltipicon]::Info")

            ps_script = f"""
            [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
            $notify = new-object system.windows.forms.notifyicon
            $notify.icon = {icon_expr}
            $notify.visible = $true
            $notify.showballoontip({duration_ms}, '{safe_title}', '{safe_msg}', {tip_expr})
            """
            creationflags = 0x08000000 if os.name == "nt" else 0
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_script], creationflags=creationflags)
        except Exception as e:
            logger.debug("Failed to invoke PowerShell notification: %s", e)

    def _insert_notification(self, title: str, message: str, notification_type: str = "info", action_cmd: str = "") -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notifications (title, message, notification_type, action_command) VALUES (?, ?, ?, ?)",
                (title, message, notification_type, action_cmd)
            )
            conn.commit()
            nid = cursor.lastrowid
        self._sync_history_from_db()
        return nid

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. show_notification
        if action_name == "show_notification":
            title = parameters.get("title", "Jarvis Alert").strip()
            msg = parameters.get("message", "").strip()
            duration = int(parameters.get("duration_ms", 3000))

            nid = self._insert_notification(title, msg, "info")
            self._send_toast(title, msg, "Info", duration)

            return PluginResult(
                success=True,
                data={
                    "notification_id": nid,
                    "title": title,
                    "message": f"Notification '{title}: {msg}' display kar di hai, Boss."
                }
            )

        # 2. list_notifications
        elif action_name == "list_notifications":
            limit = max(1, int(parameters.get("limit", 20)))
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, message, notification_type, is_read, created_at FROM notifications ORDER BY id DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                items = [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "message": r["message"],
                        "type": r["notification_type"],
                        "is_read": bool(r["is_read"]),
                        "timestamp": r["created_at"]
                    }
                    for r in rows
                ]

            return PluginResult(
                success=True,
                data={
                    "notifications": items,
                    "count": len(items),
                    "message": f"Total {len(items)} notifications in history."
                }
            )

        # 3. clear_notifications
        elif action_name == "clear_notifications":
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM notifications")
                conn.commit()
            self._history.clear()
            return PluginResult(
                success=True,
                data={"cleared": True, "message": "Notification history clear kar di hai, Boss."}
            )

        # 4. show_warning_notification
        elif action_name == "show_warning_notification":
            title = parameters.get("title", "Jarvis Warning").strip()
            msg = parameters.get("message", "").strip()

            nid = self._insert_notification(title, msg, "warning")
            self._send_toast(title, msg, "Warning", 4000)

            return PluginResult(
                success=True,
                data={
                    "notification_id": nid,
                    "type": "warning",
                    "title": title,
                    "message": f"Warning toast '{title}' displayed successfully."
                }
            )

        # 5. show_error_notification
        elif action_name == "show_error_notification":
            title = parameters.get("title", "Jarvis System Alert").strip()
            msg = parameters.get("message", "").strip()

            nid = self._insert_notification(title, msg, "error")
            self._send_toast(title, msg, "Error", 5000)

            return PluginResult(
                success=True,
                data={
                    "notification_id": nid,
                    "type": "error",
                    "title": title,
                    "message": f"Error toast '{title}' displayed with priority."
                }
            )

        # 6. show_actionable_notification
        elif action_name == "show_actionable_notification":
            title = parameters.get("title", "Action Required").strip()
            msg = parameters.get("message", "").strip()
            action_cmd = parameters.get("action_command", "").strip()

            nid = self._insert_notification(title, msg, "action", action_cmd)
            self._send_toast(title, msg, "Action", 4000)

            return PluginResult(
                success=True,
                data={
                    "notification_id": nid,
                    "type": "actionable",
                    "action_command": action_cmd,
                    "title": title,
                    "message": f"Actionable notification '{title}' created."
                }
            )

        # 7. get_unread_notifications_count
        elif action_name == "get_unread_notifications_count":
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
                unread = cursor.fetchone()[0]

            return PluginResult(
                success=True,
                data={
                    "unread_count": unread,
                    "message": f"You have {unread} unread notification(s)."
                }
            )

        # 8. mark_notification_as_read
        elif action_name == "mark_notification_as_read":
            nid = int(parameters.get("notification_id", 0))
            with sqlite3.connect(self.db_path) as conn:
                if nid > 0:
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (nid,))
                    msg = f"Notification #{nid} marked as read."
                else:
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
                    msg = "All notifications marked as read."
                conn.commit()
            self._sync_history_from_db()

            return PluginResult(
                success=True,
                data={"marked_id": nid, "message": msg}
            )

        # 9. search_notifications
        elif action_name == "search_notifications":
            query = parameters.get("query", "").strip()
            if not query:
                return PluginResult(success=False, error="query parameter is required.")

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, message, notification_type, is_read, created_at FROM notifications WHERE title LIKE ? OR message LIKE ? ORDER BY id DESC",
                    (f"%{query}%", f"%{query}%")
                )
                rows = cursor.fetchall()
                results = [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "message": r["message"],
                        "type": r["notification_type"],
                        "is_read": bool(r["is_read"]),
                        "timestamp": r["created_at"]
                    }
                    for r in rows
                ]

            return PluginResult(
                success=True,
                data={
                    "query": query,
                    "count": len(results),
                    "notifications": results,
                    "message": f"Found {len(results)} notification(s) matching '{query}'."
                }
            )

        # 10. delete_notification_by_id
        elif action_name == "delete_notification_by_id":
            nid = int(parameters.get("notification_id", 0))
            if nid <= 0:
                return PluginResult(success=False, error="Valid notification_id is required.")

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM notifications WHERE id = ?", (nid,))
                deleted = cursor.rowcount
                conn.commit()
            self._sync_history_from_db()

            if deleted == 0:
                return PluginResult(success=False, error=f"Notification with ID {nid} not found.")

            return PluginResult(
                success=True,
                data={"deleted_id": nid, "message": f"Notification #{nid} deleted successfully."}
            )

        # 11. filter_notifications_by_type
        elif action_name == "filter_notifications_by_type":
            ntype = parameters.get("notification_type", "").strip().lower()
            if not ntype:
                return PluginResult(success=False, error="notification_type parameter is required.")

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, message, notification_type, is_read, created_at FROM notifications WHERE LOWER(notification_type) = ? ORDER BY id DESC",
                    (ntype,)
                )
                rows = cursor.fetchall()
                results = [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "message": r["message"],
                        "type": r["notification_type"],
                        "is_read": bool(r["is_read"]),
                        "timestamp": r["created_at"]
                    }
                    for r in rows
                ]

            return PluginResult(
                success=True,
                data={
                    "type": ntype,
                    "count": len(results),
                    "notifications": results,
                    "message": f"Found {len(results)} '{ntype}' notifications."
                }
            )

        # 12. export_notification_history
        elif action_name == "export_notification_history":
            dest = parameters.get("destination_path", "").strip()
            fmt = parameters.get("format", "json").strip().lower()
            if not dest:
                return PluginResult(success=False, error="destination_path parameter is required.")

            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, message, notification_type, action_command, is_read, created_at FROM notifications ORDER BY id ASC")
                rows = cursor.fetchall()
                records = [dict(r) for r in rows]

            try:
                if fmt == "csv" or dest.lower().endswith(".csv"):
                    if not dest.lower().endswith(".csv"):
                        dest += ".csv"
                    with open(dest, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=["id", "title", "message", "notification_type", "action_command", "is_read", "created_at"])
                        writer.writeheader()
                        writer.writerows(records)
                else:
                    if not dest.lower().endswith(".json"):
                        dest += ".json"
                    with open(dest, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2, default=str)

                return PluginResult(
                    success=True,
                    data={
                        "destination_path": os.path.abspath(dest),
                        "count": len(records),
                        "message": f"Exported {len(records)} notifications to '{dest}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Export failed: {e}")

        # 13. get_notification_summary_stats
        elif action_name == "get_notification_summary_stats":
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notifications")
                total = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
                unread = cursor.fetchone()[0]

                cursor.execute("SELECT notification_type, COUNT(*) FROM notifications GROUP BY notification_type")
                by_type = dict(cursor.fetchall())

            return PluginResult(
                success=True,
                data={
                    "total_count": total,
                    "unread_count": unread,
                    "read_count": total - unread,
                    "breakdown_by_type": by_type,
                    "message": f"Summary: {total} total, {unread} unread notifications."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Notifications plugin.")
