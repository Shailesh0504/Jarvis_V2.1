# plugins/reminder/plugin.py
"""
Dedicated Offline Persistent Reminder Plugin for Jarvis V2.
"""

import datetime
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .database import ReminderDatabase
from .models import ReminderItem, ReminderStatus, RecurrenceType
from .permissions import PERMISSIONS_REQUIRED
from .scheduler import ReminderScheduler

logger = logging.getLogger("jarvis.plugins.reminder")


class ReminderPlugin(BasePlugin):
    """
    Dedicated Reminder Engine with SQLite persistence, non-blocking
    background scheduler, recurring schedules, and voice/GUI integration.
    """

    def __init__(self, manifest=None, config=None, db_path: Optional[str] = None, event_bus=None):
        super().__init__(manifest=manifest, config=config)
        cfg_db = config.get("db_path") if isinstance(config, dict) else None
        self.db_path = db_path or cfg_db or "data/reminders.db"
        self.event_bus = event_bus
        self.db = ReminderDatabase(db_path=self.db_path)
        self.scheduler = ReminderScheduler(
            db=self.db,
            event_bus=self.event_bus,
            on_reminder_triggered=self._on_triggered
        )
        self.scheduler.start()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="reminder",
            version="1.0.0",
            description="Offline persistent reminder engine with background scheduling, recurrence, and alerts.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _send_desktop_notification(self, title: str, message: str) -> None:
        """Native Windows Desktop balloon / toast notification."""
        if os.name != "nt":
            return
        try:
            safe_title = title.replace("'", "''")
            safe_msg = message.replace("'", "''")
            ps_script = f"""
            [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
            $notify = new-object system.windows.forms.notifyicon
            $notify.icon = [System.Drawing.SystemIcons]::Information
            $notify.visible = $true
            $notify.showballoontip(5000, '{safe_title}', '{safe_msg}', [system.windows.forms.tooltipicon]::Info)
            """
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_script], creationflags=creationflags)
        except Exception as exc:
            logger.debug("Error launching PowerShell balloon tip: %s", exc)

    def _on_triggered(self, reminder: ReminderItem) -> None:
        """Callback invoked when a reminder is due."""
        logger.info(f"ALARM: Reminder #{reminder.id} '{reminder.title}' triggered.")
        try:
            self._send_desktop_notification(
                title="⏰ Jarvis Reminder",
                message=reminder.title
            )
        except Exception as e:
            logger.debug("Desktop notification error: %s", e)

    def format_time_friendly(self, iso_str: str) -> str:
        """Formats ISO-8601 string into a human-friendly date/time."""
        try:
            dt = datetime.datetime.fromisoformat(iso_str)
            now = datetime.datetime.now().astimezone()
            if dt.date() == now.date():
                return f"aaj {dt.strftime('%I:%M %p')}"
            elif dt.date() == (now + datetime.timedelta(days=1)).date():
                return f"kal {dt.strftime('%I:%M %p')}"
            else:
                return dt.strftime('%d %b %Y, %I:%M %p')
        except Exception:
            return iso_str

    def execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        # 1. Create Reminder
        if action_name in ("create_reminder", "add_reminder"):
            title = parameters.get("title", "").strip()
            remind_time = parameters.get("remind_time", "").strip()
            recurrence = parameters.get("recurrence", RecurrenceType.NONE.value).lower().strip()
            rule = parameters.get("recurrence_rule", "").strip()

            if not title:
                return PluginResult(success=False, error="Reminder title/task is required, Boss.")
            if not remind_time:
                return PluginResult(success=False, error="Reminder time is required, Boss.")

            # Duplicate voice recognition suppression
            existing = self.db.check_duplicate(title, remind_time)
            if existing:
                time_str = self.format_time_friendly(existing.remind_time)
                return PluginResult(
                    success=True,
                    data={
                        "id": existing.id,
                        "title": existing.title,
                        "duplicate": True,
                        "message": f"Reminder #{existing.id} '{existing.title}' pehle se set hai {time_str} ke liye, Boss."
                    }
                )

            item = ReminderItem(
                title=title,
                remind_time=remind_time,
                recurrence=recurrence,
                recurrence_rule=rule,
                status=ReminderStatus.PENDING.value
            )
            r_id = self.db.add_reminder(item)
            friendly_time = self.format_time_friendly(remind_time)

            recur_note = ""
            if recurrence == RecurrenceType.DAILY.value:
                recur_note = " (Har din)"
            elif recurrence == RecurrenceType.WEEKLY.value:
                recur_note = f" (Har hafte {rule})" if rule else " (Har hafte)"

            msg = f"Reminder set kar diya hai: '{title}' {friendly_time} ke liye{recur_note}, Boss. ⏰"
            return PluginResult(
                success=True,
                data={
                    "id": r_id,
                    "title": title,
                    "remind_time": remind_time,
                    "recurrence": recurrence,
                    "message": msg
                }
            )

        # 2. List Reminders
        elif action_name == "list_reminders":
            filter_type = parameters.get("filter", "pending").lower().strip()
            all_items = self.db.get_all_reminders()

            now_dt = datetime.datetime.now().astimezone()
            today_date = now_dt.date()

            filtered: List[ReminderItem] = []
            for it in all_items:
                if filter_type == "all":
                    filtered.append(it)
                elif filter_type == "completed":
                    if it.status == ReminderStatus.COMPLETED.value:
                        filtered.append(it)
                elif filter_type == "missed":
                    if it.status == ReminderStatus.MISSED.value:
                        filtered.append(it)
                elif filter_type == "recurring":
                    if it.recurrence and it.recurrence != RecurrenceType.NONE.value and it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value):
                        filtered.append(it)
                elif filter_type == "today":
                    if it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value):
                        try:
                            dt = datetime.datetime.fromisoformat(it.remind_time)
                            if dt.date() == today_date:
                                filtered.append(it)
                        except Exception:
                            pass
                else:  # "pending"
                    if it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value):
                        filtered.append(it)

            if not filtered:
                empty_msg = f"Koi {filter_type} reminders nahi hain, Boss." if filter_type != "pending" else "Aapke koi pending reminders nahi hain, Boss."
                return PluginResult(
                    success=True,
                    data={"reminders": [], "count": 0, "message": empty_msg}
                )

            summary_items = []
            for it in filtered[:6]:
                f_time = self.format_time_friendly(it.remind_time)
                summary_items.append(f"#{it.id}: {it.title} ({f_time})")

            summary = ", ".join(summary_items)
            return PluginResult(
                success=True,
                data={
                    "reminders": [r.to_dict() for r in filtered],
                    "count": len(filtered),
                    "message": f"Aapke reminders: {summary}"
                }
            )

        # 3. Cancel / Delete Reminder
        elif action_name in ("cancel_reminder", "delete_reminder"):
            r_id = parameters.get("reminder_id", 0)
            title_kw = parameters.get("title", "").lower().strip()

            target: Optional[ReminderItem] = None
            if r_id and int(r_id) > 0:
                target = self.db.get_reminder(int(r_id))
            elif title_kw:
                # Find most relevant active reminder by keyword
                for it in self.db.get_all_reminders():
                    if it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value) and title_kw in it.title.lower():
                        target = it
                        break

            if not target:
                return PluginResult(
                    success=False,
                    error=f"Reminder #{r_id or title_kw} nahi mila, Boss."
                )

            if action_name == "delete_reminder":
                self.db.delete_reminder(target.id)
                return PluginResult(
                    success=True,
                    data={"id": target.id, "message": f"Reminder #{target.id} '{target.title}' delete kar diya hai, Boss."}
                )
            else:
                target.status = ReminderStatus.CANCELLED.value
                self.db.update_reminder(target)
                return PluginResult(
                    success=True,
                    data={"id": target.id, "message": f"Reminder #{target.id} '{target.title}' cancel kar diya hai, Boss."}
                )

        # 4. Snooze Reminder
        elif action_name == "snooze_reminder":
            r_id = parameters.get("reminder_id", 0)
            minutes = int(parameters.get("minutes", 10))

            target: Optional[ReminderItem] = None
            if r_id and int(r_id) > 0:
                target = self.db.get_reminder(int(r_id))
            else:
                # Target the latest due or pending reminder
                all_active = [it for it in self.db.get_all_reminders() if it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value, ReminderStatus.MISSED.value)]
                if all_active:
                    target = all_active[0]

            if not target:
                return PluginResult(success=False, error="Snooze karne ke liye koi active reminder nahi mila, Boss.")

            now_dt = datetime.datetime.now().astimezone()
            new_dt = now_dt + datetime.timedelta(minutes=minutes)
            target.remind_time = new_dt.isoformat()
            target.status = ReminderStatus.SNOOZED.value
            target.snooze_count += 1
            self.db.update_reminder(target)

            friendly = self.format_time_friendly(target.remind_time)
            return PluginResult(
                success=True,
                data={
                    "id": target.id,
                    "title": target.title,
                    "new_time": target.remind_time,
                    "message": f"Reminder #{target.id} '{target.title}' {minutes} minute ke liye snooze kar diya hai ({friendly}), Boss."
                }
            )

        # 5. Edit Reminder
        elif action_name == "edit_reminder":
            r_id = int(parameters.get("reminder_id", 0))
            new_time = parameters.get("new_time", "").strip()
            new_title = parameters.get("new_title", "").strip()
            new_recurrence = parameters.get("new_recurrence", parameters.get("recurrence", "")).strip().lower()

            target = self.db.get_reminder(r_id)
            if not target:
                return PluginResult(success=False, error=f"Reminder #{r_id} nahi mila, Boss.")

            if new_time:
                target.remind_time = new_time
                target.status = ReminderStatus.PENDING.value
                target.snooze_count = 0
            if new_title:
                target.title = new_title
            if new_recurrence:
                target.recurrence = new_recurrence

            self.db.update_reminder(target)
            friendly = self.format_time_friendly(target.remind_time)
            return PluginResult(
                success=True,
                data={
                    "id": target.id,
                    "title": target.title,
                    "remind_time": target.remind_time,
                    "recurrence": target.recurrence,
                    "message": f"Reminder #{target.id} update kar diya hai: '{target.title}' {friendly} ke liye, Boss."
                }
            )

        # 6. Toggle Reminders (Enable / Disable)
        elif action_name == "toggle_reminders":
            enabled = bool(parameters.get("enabled", True))
            count = self.db.set_all_enabled(enabled)
            state_str = "chalu (enabled)" if enabled else "band (disabled)"
            return PluginResult(
                success=True,
                data={
                    "enabled": enabled,
                    "updated_count": count,
                    "message": f"Saare reminders {state_str} kar diye hain, Boss."
                }
            )

        # 7. Complete Reminder
        elif action_name == "complete_reminder":
            r_id = int(parameters.get("reminder_id", 0))
            target = self.db.get_reminder(r_id)
            if not target:
                return PluginResult(success=False, error=f"Reminder #{r_id} nahi mila, Boss.")
            target.status = ReminderStatus.COMPLETED.value
            self.db.update_reminder(target)
            return PluginResult(
                success=True,
                data={
                    "id": target.id,
                    "title": target.title,
                    "status": target.status,
                    "message": f"Reminder #{target.id} '{target.title}' completed mark kar diya hai, Boss."
                }
            )

        # 8. Get Next Upcoming Reminder
        elif action_name == "get_next_upcoming":
            now_dt = datetime.datetime.now().astimezone()
            all_active = [it for it in self.db.get_all_reminders() if it.status in (ReminderStatus.PENDING.value, ReminderStatus.SNOOZED.value)]
            upcoming = []
            for it in all_active:
                try:
                    dt = datetime.datetime.fromisoformat(it.remind_time)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=now_dt.tzinfo)
                    upcoming.append((dt, it))
                except Exception:
                    pass

            if not upcoming:
                return PluginResult(success=True, data={"reminder": None, "message": "Koi upcoming reminder nahi hai, Boss."})

            upcoming.sort(key=lambda x: x[0])
            next_dt, next_item = upcoming[0]
            remaining_seconds = max(0.0, (next_dt - now_dt).total_seconds())
            remaining_minutes = round(remaining_seconds / 60.0, 1)
            remaining_hours = round(remaining_seconds / 3600.0, 2)
            friendly = self.format_time_friendly(next_item.remind_time)

            return PluginResult(
                success=True,
                data={
                    "reminder": next_item.to_dict(),
                    "minutes_remaining": remaining_minutes,
                    "hours_remaining": remaining_hours,
                    "friendly_time": friendly,
                    "message": f"Agla reminder #{next_item.id} '{next_item.title}' hai ({friendly}, lagbhag {remaining_minutes} minute bache hain)."
                }
            )

        # 9. Search Reminders
        elif action_name == "search_reminders":
            query = str(parameters.get("query", "")).strip().lower()
            if not query:
                return PluginResult(success=False, error="Search query parameter is required.")
            all_items = self.db.get_all_reminders()
            matches = [it for it in all_items if query in it.title.lower() or query in (it.recurrence_rule or "").lower()]
            return PluginResult(
                success=True,
                data={
                    "query": query,
                    "count": len(matches),
                    "reminders": [r.to_dict() for r in matches],
                    "message": f"Found {len(matches)} reminder(s) matching '{query}'."
                }
            )

        # 10. Bulk Cancel Reminders
        elif action_name == "bulk_cancel_reminders":
            status_filter = str(parameters.get("status", "pending")).strip().lower()
            all_items = self.db.get_all_reminders()
            cancelled = 0
            for it in all_items:
                if it.status.lower() == status_filter:
                    it.status = ReminderStatus.CANCELLED.value
                    self.db.update_reminder(it)
                    cancelled += 1
            return PluginResult(
                success=True,
                data={
                    "status_filter": status_filter,
                    "cancelled_count": cancelled,
                    "message": f"Cancelled {cancelled} {status_filter} reminder(s)."
                }
            )

        # 11. Export Reminders
        elif action_name == "export_reminders":
            import os
            import json
            fmt = str(parameters.get("format", "json")).strip().lower()
            out_path = str(parameters.get("output_path", "")).strip()
            if not out_path:
                out_path = os.path.join(os.getcwd(), "data", f"reminders_export.{fmt}")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            all_items = [it.to_dict() for it in self.db.get_all_reminders()]

            if fmt == "ics":
                lines = [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:-//Jarvis V2.1//Reminder Plugin//EN"
                ]
                for it in all_items:
                    lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:reminder-{it['id']}@jarvis",
                        f"SUMMARY:{it['title']}",
                        f"DESCRIPTION:Status: {it['status']}, Recurrence: {it['recurrence']}",
                        "END:VEVENT"
                    ])
                lines.append("END:VCALENDAR")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("\r\n".join(lines))
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(all_items, f, indent=2)

            return PluginResult(
                success=True,
                data={
                    "output_path": out_path,
                    "count": len(all_items),
                    "format": fmt,
                    "message": f"Exported {len(all_items)} reminder(s) to {out_path}."
                }
            )

        # 12. Import Reminders
        elif action_name == "import_reminders":
            import os
            import json
            file_path = str(parameters.get("file_path", "")).strip()
            if not file_path or not os.path.isfile(file_path):
                return PluginResult(success=False, error=f"Import file '{file_path}' does not exist.")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                imported = 0
                for d in data:
                    item = ReminderItem(
                        title=d.get("title", "Imported Reminder"),
                        remind_time=d.get("remind_time", datetime.datetime.now().astimezone().isoformat()),
                        recurrence=d.get("recurrence", "none"),
                        recurrence_rule=d.get("recurrence_rule", ""),
                        status=d.get("status", ReminderStatus.PENDING.value)
                    )
                    self.db.add_reminder(item)
                    imported += 1
                return PluginResult(
                    success=True,
                    data={"imported_count": imported, "message": f"Successfully imported {imported} reminder(s)."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error importing reminders: {e}")

        # 13. Get Reminder Stats
        elif action_name == "get_reminder_stats":
            all_items = self.db.get_all_reminders()
            total = len(all_items)
            status_counts: Dict[str, int] = {}
            for it in all_items:
                s = it.status.lower()
                status_counts[s] = status_counts.get(s, 0) + 1

            completed = status_counts.get(ReminderStatus.COMPLETED.value.lower(), 0)
            pending = status_counts.get(ReminderStatus.PENDING.value.lower(), 0)
            missed = status_counts.get(ReminderStatus.MISSED.value.lower(), 0)
            cancelled = status_counts.get(ReminderStatus.CANCELLED.value.lower(), 0)
            completion_rate = round((completed / total) * 100, 1) if total > 0 else 0.0

            return PluginResult(
                success=True,
                data={
                    "total_reminders": total,
                    "pending": pending,
                    "completed": completed,
                    "missed": missed,
                    "cancelled": cancelled,
                    "completion_rate_percent": completion_rate,
                    "status_counts": status_counts,
                    "message": f"Reminders stats: {pending} pending, {completed} completed ({completion_rate}% completion rate)."
                }
            )

        # 14. Reschedule Missed Reminders
        elif action_name == "reschedule_missed_reminders":
            mins = int(parameters.get("minutes_ahead", 60) or 60)
            now_dt = datetime.datetime.now().astimezone()
            new_dt = (now_dt + datetime.timedelta(minutes=mins)).isoformat()
            missed_items = [it for it in self.db.get_all_reminders() if it.status == ReminderStatus.MISSED.value]
            for it in missed_items:
                it.remind_time = new_dt
                it.status = ReminderStatus.PENDING.value
                self.db.update_reminder(it)
            return PluginResult(
                success=True,
                data={
                    "rescheduled_count": len(missed_items),
                    "new_time": new_dt,
                    "message": f"Rescheduled {len(missed_items)} missed reminder(s) to {mins} minutes ahead."
                }
            )

        # 15. Clear Completed Reminders
        elif action_name == "clear_completed_reminders":
            days = int(parameters.get("older_than_days", 0) or 0)
            all_items = self.db.get_all_reminders()
            purged = 0
            for it in all_items:
                if it.status in (ReminderStatus.COMPLETED.value, ReminderStatus.CANCELLED.value):
                    self.db.delete_reminder(it.id)
                    purged += 1
            return PluginResult(
                success=True,
                data={"purged_count": purged, "message": f"Purged {purged} completed/cancelled reminder(s)."}
            )

        # 16. Calculate Countdown
        elif action_name == "calculate_countdown":
            r_id = int(parameters.get("reminder_id", 0))
            target = self.db.get_reminder(r_id)
            if not target:
                return PluginResult(success=False, error=f"Reminder #{r_id} nahi mila, Boss.")
            now_dt = datetime.datetime.now().astimezone()
            try:
                dt = datetime.datetime.fromisoformat(target.remind_time)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=now_dt.tzinfo)
                diff = dt - now_dt
                is_past = diff.total_seconds() < 0
                sec = int(abs(diff.total_seconds()))
                days = sec // 86400
                hours = (sec % 86400) // 3600
                minutes = (sec % 3600) // 60
                seconds = sec % 60
                return PluginResult(
                    success=True,
                    data={
                        "reminder_id": target.id,
                        "title": target.title,
                        "is_past": is_past,
                        "days": days,
                        "hours": hours,
                        "minutes": minutes,
                        "seconds": seconds,
                        "message": f"{'Due in' if not is_past else 'Overdue by'} {days}d {hours}h {minutes}m {seconds}s."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Error parsing reminder time: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Reminder plugin.")


def format_reminder_alert(title: str, is_missed: bool = False, for_spoken: bool = True) -> str:
    """
    Formats human-like, grammatically correct natural Hinglish reminder alerts.

    Converts first-person statements and raw verb titles into polite, natural 2nd-person address:
      - 'Mujhe paani pina' -> 'Boss, aapke paani peene ka time ho gaya hai.'
      - 'paani peene' -> 'Boss, aapke paani peene ka time ho gaya hai.'
      - 'dawai leni hai' -> 'Boss, aapke dawai lene ka time ho gaya hai.'
      - 'khana khana' -> 'Boss, aapke khana khane ka time ho gaya hai.'
      - 'gym jaana' -> 'Boss, aapke gym jaane ka time ho gaya hai.'
      - 'Rohit ko call karna' -> 'Boss, aapke Rohit ko call karne ka time ho gaya hai.'
      - 'meeting' -> 'Boss, aapki meeting ka time ho gaya hai.'
      - 'sone ka time ho gaya hai' -> 'Boss, aapke sone ka time ho gaya hai.'
    """
    raw = (title or "Reminder").strip(" '\".,?!")

    # 1. Clean first-person pronouns and preambles
    t = re.sub(
        r'^(?:mujhe|humein|main|hum|mera|mere|meri|i\s+have\s+to|i\s+need\s+to|i\s+want\s+to|my)\s+',
        '', raw, flags=re.IGNORECASE
    ).strip()

    # 2. Strip redundant trailing "ka time ho gaya hai" or "time ho gaya"
    t = re.sub(
        r'\s*(?:ka\s+time\s+ho\s+gaya\s+hai|ka\s+time\s+ho\s+gaya|ka\s+time|time\s+ho\s+gaya\s+hai|time\s+ho\s+gaya)\s*$',
        '', t, flags=re.IGNORECASE
    ).strip()

    # 3. Strip trailing auxiliary verbs & reminder keywords
    t = re.sub(r'\s+(?:hai|hoga|hogi|tha|thi|the)$', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s+(?:yaad\s+dilana|yaad\s+dila\s+do|yaad\s+rakhna)$', '', t, flags=re.IGNORECASE).strip()

    if not t:
        t = "Reminder"

    if is_missed:
        if for_spoken:
            return f"Boss, aapka ek reminder miss ho gaya tha: {t}."
        return f"⏰ Missed Reminder: Aapka '{t}' reminder miss ho gaya tha, Boss."

    # 4. Grammatical inflections for Hindi verbs ending in -na / -naa -> -ne before 'ka time ho gaya hai'
    low = t.lower()
    inflected = t
    if re.search(r'\b(?:paani|pani)\s+(?:pina|peena|pine)\b', low):
        inflected = re.sub(r'\b(?:paani|pani)\s+(?:pina|peena|pine)\b', 'paani peene', low)
    else:
        words = t.split()
        if words:
            last = words[-1].lower()
            if last in ("pina", "peena", "pine"):
                words[-1] = "peene"
            elif last == "karna":
                words[-1] = "karne"
            elif last in ("jaana", "jana"):
                words[-1] = "jaane"
            elif last == "khana":
                words[-1] = "khane"
            elif last == "sona":
                words[-1] = "sone"
            elif last == "uthna":
                words[-1] = "uthne"
            elif last == "padhna":
                words[-1] = "padhne"
            elif last in ("lena", "leni"):
                words[-1] = "lene"
            elif last == "dena":
                words[-1] = "dene"
            elif last == "milna":
                words[-1] = "milne"
            elif last == "bhejna":
                words[-1] = "bhejne"
            elif last == "nikalna":
                words[-1] = "nikalne"
            elif last == "dekhna":
                words[-1] = "dekhne"
            elif last.endswith("na") and len(last) > 3:
                words[-1] = last[:-2] + "ne"
            elif last.endswith("naa") and len(last) > 4:
                words[-1] = last[:-3] + "ne"
            inflected = " ".join(words)

    # 5. Determine marker: feminine nouns use 'aapki', masculine/verbal use 'aapke'
    first_word = inflected.split()[0].lower() if inflected else ""
    fem_nouns = {"meeting", "class", "flight", "train", "dawa", "dawai", "medicine"}
    marker = "aapki" if first_word in fem_nouns else "aapke"

    if for_spoken:
        return f"Boss, {marker} {inflected} ka time ho gaya hai."
    return f"⏰ Reminder: Boss, {marker} {inflected} ka time ho gaya hai!"

