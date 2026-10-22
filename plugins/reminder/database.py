# plugins/reminder/database.py
"""
Persistent SQLite database manager for the Reminder Plugin.
"""

import datetime
import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from .models import ReminderItem, ReminderStatus, RecurrenceType

logger = logging.getLogger("jarvis.plugins.reminder.db")


class ReminderDatabase:
    """Thread-safe SQLite storage for reminders."""

    def __init__(self, db_path: str = "data/reminders.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes the database schema and indexes."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        remind_time TEXT NOT NULL,
                        recurrence TEXT DEFAULT 'none',
                        recurrence_rule TEXT DEFAULT '',
                        status TEXT DEFAULT 'pending',
                        snooze_count INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        notification_type TEXT DEFAULT 'gui_voice',
                        enabled INTEGER DEFAULT 1
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reminders_status_time 
                    ON reminders (status, remind_time, enabled)
                """)
                conn.commit()
            finally:
                conn.close()

    def add_reminder(self, reminder: ReminderItem) -> int:
        """Inserts a new reminder item and returns its database ID."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO reminders (
                        title, remind_time, recurrence, recurrence_rule,
                        status, snooze_count, created_at, notification_type, enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reminder.title,
                    reminder.remind_time,
                    reminder.recurrence,
                    reminder.recurrence_rule,
                    reminder.status,
                    reminder.snooze_count,
                    reminder.created_at or datetime.datetime.now().astimezone().isoformat(),
                    reminder.notification_type,
                    1 if reminder.enabled else 0
                ))
                conn.commit()
                reminder.id = cursor.lastrowid
                return reminder.id
            finally:
                conn.close()

    def check_duplicate(self, title: str, remind_time: str, window_seconds: int = 10) -> Optional[ReminderItem]:
        """Checks if an identical reminder exists within a small time window to prevent voice double-triggers."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM reminders
                    WHERE LOWER(title) = LOWER(?) AND remind_time = ? AND status IN ('pending', 'snoozed')
                    ORDER BY id DESC LIMIT 1
                """, (title.strip(), remind_time.strip()))
                row = cursor.fetchone()
                if row:
                    return ReminderItem.from_row(dict(row))
                return None
            finally:
                conn.close()

    def get_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
                row = cursor.fetchone()
                return ReminderItem.from_row(dict(row)) if row else None
            finally:
                conn.close()

    def get_all_reminders(self, status_filter: Optional[str] = None) -> List[ReminderItem]:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if status_filter and status_filter != "all":
                    cursor.execute("SELECT * FROM reminders WHERE status = ? ORDER BY remind_time ASC", (status_filter,))
                else:
                    cursor.execute("SELECT * FROM reminders ORDER BY remind_time ASC")
                rows = cursor.fetchall()
                return [ReminderItem.from_row(dict(r)) for r in rows]
            finally:
                conn.close()

    def get_due_reminders(self, current_iso: str) -> List[ReminderItem]:
        """Fetches active reminders that are due on or before current_iso."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM reminders
                    WHERE enabled = 1 
                      AND status IN ('pending', 'snoozed') 
                      AND remind_time <= ?
                    ORDER BY remind_time ASC
                """, (current_iso,))
                rows = cursor.fetchall()
                return [ReminderItem.from_row(dict(r)) for r in rows]
            finally:
                conn.close()

    def get_missed_reminders(self, startup_iso: str) -> List[ReminderItem]:
        """Finds reminders whose scheduled time passed while Jarvis was offline."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM reminders
                    WHERE enabled = 1 
                      AND status IN ('pending', 'snoozed') 
                      AND remind_time < ?
                    ORDER BY remind_time ASC
                """, (startup_iso,))
                rows = cursor.fetchall()
                return [ReminderItem.from_row(dict(r)) for r in rows]
            finally:
                conn.close()

    def update_reminder(self, reminder: ReminderItem) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE reminders SET
                        title = ?,
                        remind_time = ?,
                        recurrence = ?,
                        recurrence_rule = ?,
                        status = ?,
                        snooze_count = ?,
                        enabled = ?
                    WHERE id = ?
                """, (
                    reminder.title,
                    reminder.remind_time,
                    reminder.recurrence,
                    reminder.recurrence_rule,
                    reminder.status,
                    reminder.snooze_count,
                    1 if reminder.enabled else 0,
                    reminder.id
                ))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def delete_reminder(self, reminder_id: int) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def set_all_enabled(self, enabled: bool) -> int:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("UPDATE reminders SET enabled = ? WHERE status IN ('pending', 'snoozed')", (1 if enabled else 0,))
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()
