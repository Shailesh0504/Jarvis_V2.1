# plugins/reminder/scheduler.py
"""
Background Reminder Scheduler for evaluating due reminders and triggering notifications.
"""

import datetime
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .database import ReminderDatabase
from .models import ReminderItem, ReminderStatus, RecurrenceType

logger = logging.getLogger("jarvis.plugins.reminder.scheduler")


class ReminderScheduler:
    """
    Non-blocking background scheduler evaluating due reminders,
    recalculating recurring schedules, and firing event bus / voice alerts.
    """

    def __init__(
        self,
        db: ReminderDatabase,
        event_bus: Optional[Any] = None,
        on_reminder_triggered: Optional[Callable[[ReminderItem], None]] = None,
        poll_interval: float = 2.0
    ):
        self.db = db
        self.event_bus = event_bus
        self.on_reminder_triggered = on_reminder_triggered
        self.poll_interval = poll_interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._missed_handled = False

    def start(self) -> None:
        """Starts the background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="JarvisReminderScheduler", daemon=True)
        self._thread.start()
        logger.info("ReminderScheduler background worker started.")

    def stop(self) -> None:
        """Stops the scheduler gracefully."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("ReminderScheduler background worker stopped.")

    def _run_loop(self) -> None:
        # Check missed reminders on startup once
        if not self._missed_handled:
            self._handle_missed_reminders()
            self._missed_handled = True

        while self._running:
            try:
                self._check_due_reminders()
            except Exception as e:
                logger.error(f"Error in ReminderScheduler loop: {e}", exc_info=True)

            # Sleep in increments for responsive shutdown
            slept = 0.0
            while self._running and slept < self.poll_interval:
                time.sleep(0.2)
                slept += 0.2

    def _handle_missed_reminders(self) -> None:
        """Checks for reminders scheduled in the past that were missed while Jarvis was offline."""
        now_iso = datetime.datetime.now().astimezone().isoformat()
        missed = self.db.get_missed_reminders(now_iso)
        if missed:
            logger.warning(f"Found {len(missed)} missed reminders after startup.")
            for item in missed:
                item.status = ReminderStatus.MISSED.value
                self.db.update_reminder(item)
                self._trigger_notification(item, is_missed=True)

    def _check_due_reminders(self) -> None:
        """Finds and triggers all reminders currently due."""
        now_dt = datetime.datetime.now().astimezone()
        now_iso = now_dt.isoformat()
        due_items = self.db.get_due_reminders(now_iso)

        for item in due_items:
            self._trigger_notification(item, is_missed=False)
            self._handle_post_trigger(item, now_dt)

    def _handle_post_trigger(self, item: ReminderItem, now_dt: datetime.datetime) -> None:
        """Handles completion or recalculating next run time for recurring reminders."""
        if item.recurrence and item.recurrence != RecurrenceType.NONE.value:
            next_time = self.calculate_next_recurrence(item.remind_time, item.recurrence, item.recurrence_rule, now_dt)
            if next_time:
                item.remind_time = next_time.isoformat()
                item.status = ReminderStatus.PENDING.value
                item.snooze_count = 0
                self.db.update_reminder(item)
                logger.info(f"Recurring reminder '{item.title}' rescheduled to {item.remind_time}")
                return

        # Single one-time reminder
        item.status = ReminderStatus.COMPLETED.value
        self.db.update_reminder(item)

    @classmethod
    def calculate_next_recurrence(
        cls,
        current_time_str: str,
        recurrence: str,
        recurrence_rule: str,
        base_dt: Optional[datetime.datetime] = None
    ) -> Optional[datetime.datetime]:
        """Calculates next timezone-aware datetime for recurrence rules."""
        if not base_dt:
            base_dt = datetime.datetime.now().astimezone()

        try:
            cur_dt = datetime.datetime.fromisoformat(current_time_str)
        except Exception:
            cur_dt = base_dt

        target = cur_dt
        if recurrence == RecurrenceType.DAILY.value:
            target = cur_dt + datetime.timedelta(days=1)
            while target <= base_dt:
                target += datetime.timedelta(days=1)
        elif recurrence == RecurrenceType.WEEKLY.value:
            target = cur_dt + datetime.timedelta(days=7)
            while target <= base_dt:
                target += datetime.timedelta(days=7)
        elif recurrence == RecurrenceType.WEEKDAYS.value:
            target = cur_dt + datetime.timedelta(days=1)
            while target.weekday() >= 5 or target <= base_dt:  # 5=Sat, 6=Sun
                target += datetime.timedelta(days=1)
        elif recurrence == RecurrenceType.MONTHLY.value:
            # Add roughly 30 days or next month same day
            target = cur_dt + datetime.timedelta(days=30)
            while target <= base_dt:
                target += datetime.timedelta(days=30)
        else:
            target = cur_dt + datetime.timedelta(days=1)

        return target

    def _trigger_notification(self, item: ReminderItem, is_missed: bool = False) -> None:
        """Emits event bus notifications and calls trigger callbacks."""
        msg = f"Reminder: {item.title}" if not is_missed else f"Missed Reminder: {item.title}"
        logger.info(f"Triggering reminder #{item.id}: '{item.title}' (missed={is_missed})")

        bus = self.event_bus
        if not bus:
            try:
                from core.event_bus import EventBus
                bus = EventBus.get_default()
            except Exception:
                bus = None

        if bus:
            try:
                from core.event_bus import Event, EventTopics
                topic = getattr(EventTopics, "REMINDER_TRIGGERED", "reminder.triggered")
                bus.publish(Event(
                    topic=topic,
                    data={
                        "id": item.id,
                        "title": item.title,
                        "remind_time": item.remind_time,
                        "recurrence": item.recurrence,
                        "is_missed": is_missed,
                        "message": msg
                    },
                    source="plugin.reminder"
                ))
            except Exception as err:
                logger.error(f"EventBus publish error: {err}")

        if self.on_reminder_triggered:
            try:
                self.on_reminder_triggered(item)
            except Exception as e:
                logger.error(f"Error in on_reminder_triggered callback: {e}")
