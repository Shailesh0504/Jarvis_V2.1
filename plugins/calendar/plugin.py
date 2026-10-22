# plugins/calendar/plugin.py
"""Calendar capability plugin implementation for managing events, meetings, schedules, and iCalendar exports."""

import datetime
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.calendar")


class CalendarPlugin(BasePlugin):
    """Controls persistent calendar events, appointments, conflict checks, and agenda."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.db_path = os.path.join("data", "calendar.db")
        self._init_db()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="calendar",
            version="2.0.0",
            description="Persistent calendar events, meetings scheduler, conflict detection, and .ics export manager.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _init_db(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS calendar_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        duration_minutes INTEGER DEFAULT 60,
                        description TEXT DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize calendar database: %s", e)

    def _get_conn(self) -> sqlite3.Connection:
        self._init_db()
        return sqlite3.connect(self.db_path)

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "export_events_ics":
            out_path = parameters.get("output_path")
            if out_path and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=out_path,
                    actual=f"{os.path.getsize(out_path)} bytes",
                    message="iCalendar .ics export verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=out_path,
                actual=None,
                error="Exported ICS file missing or empty."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. init_persistent_storage
        if action_name == "init_persistent_storage":
            self._init_db()
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM calendar_events")
                count = cursor.fetchone()[0]
            return PluginResult(
                success=True,
                data={"db_path": self.db_path, "total_events": count, "message": f"Calendar database verified at '{self.db_path}' ({count} events stored)."}
            )

        # 2. add_event
        elif action_name == "add_event":
            title = parameters.get("title", "Meeting").strip()
            start = parameters.get("start_time", "").strip()
            duration = int(parameters.get("duration_minutes", 60))
            notes = parameters.get("description", "").strip()

            if not title:
                return PluginResult(success=False, error="Meeting title is required.")
            if not start:
                start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

            now_str = datetime.datetime.now().isoformat()
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO calendar_events (title, start_time, duration_minutes, description, created_at) VALUES (?, ?, ?, ?, ?)",
                    (title, start, duration, notes, now_str)
                )
                conn.commit()
                event_id = cursor.lastrowid

            event = {
                "id": event_id,
                "title": title,
                "start_time": start,
                "duration_minutes": duration,
                "description": notes,
                "created_at": now_str
            }
            return PluginResult(
                success=True,
                data={"event": event, "message": f"Event #{event_id} '{title}' scheduled for {start} ({duration} mins)."}
            )

        # 3. list_events
        elif action_name == "list_events":
            limit = int(parameters.get("limit", 10))
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, start_time, duration_minutes, description, created_at FROM calendar_events ORDER BY start_time ASC LIMIT ?", (limit,))
                rows = cursor.fetchall()

            events = [{
                "id": r[0], "title": r[1], "start_time": r[2], "duration_minutes": r[3], "description": r[4], "created_at": r[5]
            } for r in rows]

            summary = ", ".join([f"{e['title']} ({e['start_time']})" for e in events])
            return PluginResult(
                success=True,
                data={
                    "events": events,
                    "count": len(events),
                    "message": f"Upcoming events ({len(events)}): {summary}" if events else "Calendar schedule is clear."
                }
            )

        # 4. get_today_agenda
        elif action_name == "get_today_agenda":
            today_prefix = datetime.date.today().strftime("%Y-%m-%d")
            today_label = datetime.date.today().strftime("%A, %d %B %Y")
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, start_time, duration_minutes, description FROM calendar_events WHERE start_time LIKE ? ORDER BY start_time ASC", (f"{today_prefix}%",))
                rows = cursor.fetchall()

            agenda = [{
                "id": r[0], "title": r[1], "start_time": r[2], "duration_minutes": r[3], "description": r[4]
            } for r in rows]

            summary = ", ".join([f"{e['title']} at {e['start_time']}" for e in agenda])
            return PluginResult(
                success=True,
                data={
                    "date": today_label,
                    "agenda": agenda,
                    "count": len(agenda),
                    "message": f"Today's agenda ({today_label}): {summary}" if agenda else f"Schedule for {today_label} is completely free, Boss."
                }
            )

        # 5. delete_event
        elif action_name == "delete_event":
            event_id = int(parameters.get("event_id", -1))
            title = parameters.get("title", "").strip()

            with self._get_conn() as conn:
                cursor = conn.cursor()
                if event_id > 0:
                    cursor.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
                elif title:
                    cursor.execute("DELETE FROM calendar_events WHERE title LIKE ?", (f"%{title}%",))
                else:
                    return PluginResult(success=False, error="event_id or title is required to delete event.")
                conn.commit()
                deleted = cursor.rowcount

            if deleted > 0:
                return PluginResult(success=True, data={"deleted_count": deleted, "message": f"Deleted {deleted} event(s)."})
            return PluginResult(success=False, error="No matching event found to delete.")

        # 6. update_event
        elif action_name == "update_event":
            event_id = int(parameters.get("event_id", -1))
            if event_id <= 0:
                return PluginResult(success=False, error="Valid event_id is required.")

            new_title = parameters.get("title", "").strip()
            new_start = parameters.get("start_time", "").strip()
            new_dur = int(parameters.get("duration_minutes", -1))

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, start_time, duration_minutes FROM calendar_events WHERE id = ?", (event_id,))
                row = cursor.fetchone()
                if not row:
                    return PluginResult(success=False, error=f"Event #{event_id} not found.")

                title_to_set = new_title or row[1]
                start_to_set = new_start or row[2]
                dur_to_set = new_dur if new_dur > 0 else row[3]

                cursor.execute(
                    "UPDATE calendar_events SET title = ?, start_time = ?, duration_minutes = ? WHERE id = ?",
                    (title_to_set, start_to_set, dur_to_set, event_id)
                )
                conn.commit()

            return PluginResult(
                success=True,
                data={"event_id": event_id, "title": title_to_set, "start_time": start_to_set, "duration_minutes": dur_to_set, "message": f"Event #{event_id} updated."}
            )

        # 7. get_upcoming_events
        elif action_name == "get_upcoming_events":
            days = max(1, int(parameters.get("days", 7)))
            today = datetime.date.today()
            end_date = today + datetime.timedelta(days=days)
            today_str = today.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d 23:59:59")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, start_time, duration_minutes FROM calendar_events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
                    (today_str, end_str)
                )
                rows = cursor.fetchall()

            events = [{"id": r[0], "title": r[1], "start_time": r[2], "duration_minutes": r[3]} for r in rows]
            return PluginResult(
                success=True,
                data={"days": days, "count": len(events), "events": events, "message": f"Found {len(events)} event(s) in next {days} days."}
            )

        # 8. search_events
        elif action_name == "search_events":
            query = parameters.get("query", "").strip()
            if not query:
                return PluginResult(success=False, error="Search query is required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, start_time, duration_minutes, description FROM calendar_events WHERE title LIKE ? OR description LIKE ? ORDER BY start_time ASC",
                    (f"%{query}%", f"%{query}%")
                )
                rows = cursor.fetchall()

            matches = [{"id": r[0], "title": r[1], "start_time": r[2], "duration_minutes": r[3], "description": r[4]} for r in rows]
            return PluginResult(
                success=True,
                data={"query": query, "count": len(matches), "matches": matches, "message": f"Found {len(matches)} event(s) matching '{query}'."}
            )

        # 9. clear_past_events
        elif action_name == "clear_past_events":
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM calendar_events WHERE start_time < ?", (today_str,))
                conn.commit()
                deleted = cursor.rowcount

            return PluginResult(
                success=True,
                data={"deleted_count": deleted, "message": f"Cleared {deleted} past event(s) older than {today_str}."}
            )

        # 10. export_events_ics
        elif action_name == "export_events_ics":
            out_path = parameters.get("output_path", "").strip()
            if not out_path:
                return PluginResult(success=False, error="output_path is required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, start_time, duration_minutes, description FROM calendar_events ORDER BY start_time ASC")
                rows = cursor.fetchall()

            lines = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Jarvis Assistant//EN"
            ]

            for r in rows:
                eid, title, start, dur, desc = r
                clean_start = start.replace("-", "").replace(":", "").replace(" ", "T")
                if len(clean_start) == 8:
                    clean_start = f"{clean_start}T090000"
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:jarvis-event-{eid}@assistant.local",
                    f"SUMMARY:{title}",
                    f"DESCRIPTION:{desc or ''}",
                    f"DTSTART:{clean_start}",
                    "END:VEVENT"
                ])

            lines.append("END:VCALENDAR")
            ics_content = "\r\n".join(lines)

            try:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(ics_content)

                return PluginResult(
                    success=True,
                    data={"output_path": out_path, "events_exported": len(rows), "size_bytes": os.path.getsize(out_path), "message": f"Exported {len(rows)} event(s) to '{out_path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"ICS export failed: {e}")

        # 11. import_events_ics
        elif action_name == "import_events_ics":
            file_path = parameters.get("file_path", "").strip()
            if not file_path or not os.path.isfile(file_path):
                return PluginResult(success=False, error=f"ICS file not found: '{file_path}'")

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                imported = 0
                events = content.split("BEGIN:VEVENT")
                now_str = datetime.datetime.now().isoformat()

                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    for block in events[1:]:
                        title = "Imported Event"
                        start = datetime.datetime.now().strftime("%Y-%m-%d 10:00")
                        for line in block.splitlines():
                            if line.startswith("SUMMARY:"):
                                title = line.replace("SUMMARY:", "").strip()
                            elif line.startswith("DTSTART:"):
                                raw_dt = line.replace("DTSTART:", "").strip()
                                if len(raw_dt) >= 8:
                                    start = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:8]} 10:00"

                        cursor.execute(
                            "INSERT INTO calendar_events (title, start_time, duration_minutes, description, created_at) VALUES (?, ?, ?, ?, ?)",
                            (title, start, 60, "Imported from ICS", now_str)
                        )
                        imported += 1
                    conn.commit()

                return PluginResult(
                    success=True,
                    data={"imported_count": imported, "message": f"Successfully imported {imported} event(s) from '{os.path.basename(file_path)}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"ICS import failed: {e}")

        # 12. check_conflict
        elif action_name == "check_conflict":
            start = parameters.get("start_time", "").strip()
            if not start:
                return PluginResult(success=False, error="start_time is required.")

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, start_time FROM calendar_events WHERE start_time LIKE ?", (f"%{start[:10]}%",))
                rows = cursor.fetchall()

            conflicts = [{"id": r[0], "title": r[1], "start_time": r[2]} for r in rows if r[2] == start]
            has_conflict = len(conflicts) > 0
            return PluginResult(
                success=True,
                data={
                    "start_time": start,
                    "has_conflict": has_conflict,
                    "conflicts": conflicts,
                    "message": f"Slot '{start}' has {len(conflicts)} conflict(s)." if has_conflict else f"Time slot '{start}' is completely free."
                }
            )

        # 13. get_weekly_agenda
        elif action_name == "get_weekly_agenda":
            today = datetime.date.today()
            start_week = today - datetime.timedelta(days=today.weekday())
            end_week = start_week + datetime.timedelta(days=6)

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, title, start_time, duration_minutes FROM calendar_events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
                    (start_week.strftime("%Y-%m-%d"), end_week.strftime("%Y-%m-%d 23:59:59"))
                )
                rows = cursor.fetchall()

            events = [{"id": r[0], "title": r[1], "start_time": r[2], "duration_minutes": r[3]} for r in rows]
            return PluginResult(
                success=True,
                data={
                    "week_start": str(start_week),
                    "week_end": str(end_week),
                    "count": len(events),
                    "events": events,
                    "message": f"Weekly agenda ({start_week} to {end_week}): {len(events)} meeting(s) scheduled."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Calendar plugin.")
