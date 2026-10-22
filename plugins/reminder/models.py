# plugins/reminder/models.py
"""
Data models and Enums for the Reminder Plugin.
"""

from dataclasses import dataclass, field
import datetime
from enum import Enum
import time
from typing import Any, Dict, Optional


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"


class RecurrenceType(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    WEEKDAYS = "weekdays"
    CUSTOM = "custom"


@dataclass
class ReminderItem:
    """Represents a scheduled reminder item with full lifecycle state."""
    id: Optional[int] = None
    title: str = ""
    remind_time: str = ""  # ISO-8601 string with timezone
    recurrence: str = RecurrenceType.NONE.value
    recurrence_rule: str = ""  # e.g., "monday", "every_day", "10:00"
    status: str = ReminderStatus.PENDING.value
    snooze_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.datetime.now().astimezone().isoformat())
    notification_type: str = "gui_voice"
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "remind_time": self.remind_time,
            "recurrence": self.recurrence,
            "recurrence_rule": self.recurrence_rule,
            "status": self.status,
            "snooze_count": self.snooze_count,
            "created_at": self.created_at,
            "notification_type": self.notification_type,
            "enabled": self.enabled
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "ReminderItem":
        return cls(
            id=row.get("id"),
            title=row.get("title", ""),
            remind_time=row.get("remind_time", ""),
            recurrence=row.get("recurrence", RecurrenceType.NONE.value),
            recurrence_rule=row.get("recurrence_rule", ""),
            status=row.get("status", ReminderStatus.PENDING.value),
            snooze_count=row.get("snooze_count", 0),
            created_at=row.get("created_at", ""),
            notification_type=row.get("notification_type", "gui_voice"),
            enabled=bool(row.get("enabled", 1))
        )
