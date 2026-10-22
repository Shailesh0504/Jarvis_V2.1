# gui/island/home_context.py
"""Home greeting context: session/start/context-based, never per-second.

Single owner of *which* greeting the Home card shows. The card renders;
this module decides. Rules (per product spec):
- Time-of-day greeting recomputes ONLY on day-part rollover within a session.
- Contextual greetings (first startup / welcome back / task done) lock in and
  persist until a newer context event replaces them — never on a timer, never
  on show/expand.
- No Qt dependency: fully unit-testable.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.gui.home_context")

LONG_IDLE_SEC = 15 * 60  # "long idle" threshold for Welcome back


class HomeKind:
    TIME = "time"
    FIRST_STARTUP = "first_startup"
    WELCOME_BACK = "welcome_back"
    TASK_DONE = "task_done"

    ALL = (TIME, FIRST_STARTUP, WELCOME_BACK, TASK_DONE)


def _daypart_fallback(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def resolve_time_greeting(now: Optional[datetime] = None) -> Tuple[str, str, str]:
    """Returns (title, subtitle, daypart) for the current time of day.

    Tone mirrors the existing Home card. `now` is injectable for tests.
    """
    try:
        from core.time_context import get_time_context, DayPart
        tc = get_time_context()
        moment = now or tc.now()
        dp = tc.get_day_part(moment)
        dp_value = dp.value if hasattr(dp, "value") else str(dp)
        clock = moment.strftime("%A") + " \u2022 " + moment.strftime("%I:%M %p")
        if dp == DayPart.MORNING:
            return ("Good Morning, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        if dp == DayPart.AFTERNOON:
            return ("Good Afternoon, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        if dp == DayPart.EVENING:
            return ("Good Evening, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        return ("Working Late, Boss?",
                "\u25cf JARVIS is online and ready", dp_value)
    except Exception:
        moment = now or datetime.now()
        dp_value = _daypart_fallback(moment.hour)
        clock = moment.strftime("%A") + " \u2022 " + moment.strftime("%I:%M %p")
        if dp_value == "morning":
            return ("Good Morning, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        if dp_value == "afternoon":
            return ("Good Afternoon, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        if dp_value == "evening":
            return ("Good Evening, Boss",
                    "\u25cf JARVIS is online and ready", dp_value)
        return ("Working Late, Boss?",
                "\u25cf JARVIS is online and ready", dp_value)


def resolve_context_greeting(kind: str, detail: str = "") -> Tuple[str, str]:
    """Returns (title, subtitle) for a locked contextual greeting."""
    if kind == HomeKind.FIRST_STARTUP:
        return ("Good to see you, Boss.",
                "All systems ready \u2022 Say 'Jarvis' or type below")
    if kind == HomeKind.WELCOME_BACK:
        away = detail.strip() or "a while"
        return ("Welcome back, Boss.",
                f"Away for {away} \u2022 What shall we do?")
    if kind == HomeKind.TASK_DONE:
        return ("All done, Boss.",
                f"{detail.strip()} \u2022 Anything else, Boss?" if detail.strip()
                else "\u25cf Task completed")
    title, sub, _ = resolve_time_greeting()
    return (title, sub)


def describe_idle(seconds: float) -> str:
    """Human away-duration: '20m', '2h 14m', '3d'."""
    try:
        seconds = max(0, int(seconds))
    except Exception:
        return "a while"
    if seconds < 90:
        return "a moment"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        rem = minutes % 60
        return f"{hours}h {rem}m" if rem else f"{hours}h"
    return f"{hours // 24}d"


def _default_storage_path() -> str:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(data_dir, "jarvis_home.json")


class HomeStore:
    """Persists first-seen + last-active timestamps (data/jarvis_home.json)."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or _default_storage_path()

    def load(self) -> dict:
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                return {"first_seen": data.get("first_seen"),
                        "last_active": data.get("last_active")}
        except Exception as e:
            logger.debug(f"[HOME] load failed: {e}")
        return {"first_seen": None, "last_active": None}

    def save(self, first_seen, last_active) -> None:
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"first_seen": first_seen, "last_active": last_active},
                          f, indent=2)
        except Exception as e:
            logger.debug(f"[HOME] save failed: {e}")

    def is_first_startup(self) -> bool:
        """True only when no home state was ever recorded."""
        return self.load().get("first_seen") is None

    def mark_active(self, timestamp: Optional[float] = None) -> None:
        """Records now as both first-seen (if new) and last-active."""
        now_ts = float(timestamp if timestamp is not None else time.time())
        state = self.load()
        first_seen = state.get("first_seen") or now_ts
        self.save(first_seen, now_ts)

    def idle_seconds(self, now: Optional[float] = None) -> Optional[float]:
        """Seconds since last activity, or None if never recorded."""
        state = self.load()
        last_active = state.get("last_active")
        if last_active is None:
            return None
        try:
            return max(0.0, float(now if now is not None else time.time()) - float(last_active))
        except Exception:
            return None
