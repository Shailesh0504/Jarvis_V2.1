# core/time_context.py
"""
Centralized TimeContext & Dynamic Day-Part Detection Subsystem for Jarvis V2.
Discovers local OS timezone, computes day-part boundaries, generates dynamic
time-aware greetings, resolves natural time/date queries, and unifies time parsing.
"""

from dataclasses import dataclass, field
from datetime import datetime, date, time as dt_time, timedelta
from enum import Enum
import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.time_context")


class DayPart(str, Enum):
    MORNING = "morning"        # 05:00 - 11:59 ("subah")
    AFTERNOON = "afternoon"    # 12:00 - 16:59 ("dopahar")
    EVENING = "evening"        # 17:00 - 20:59 ("shaam")
    NIGHT = "night"            # 21:00 - 04:59 ("raat", crosses midnight)


@dataclass
class DayPartConfig:
    """Configurable hour boundaries for day parts (24-hour clock)."""
    morning_start: int = 5      # 05:00
    afternoon_start: int = 12   # 12:00
    evening_start: int = 17     # 17:00
    night_start: int = 21       # 21:00


class TimeContext:
    """
    Centralized TimeContext service for Jarvis V2.
    Provides OS timezone awareness, day-part classification, dynamic greetings,
    and natural Hinglish time/date query resolution.
    """

    def __init__(
        self,
        config: Optional[DayPartConfig] = None,
        custom_timezone: Optional[str] = None
    ):
        self.config = config or DayPartConfig()
        self.custom_timezone = custom_timezone
        self._tz = self._discover_timezone()

    def _discover_timezone(self):
        """Discovers and caches local OS timezone or configured timezone via TimezoneManager."""
        try:
            from core.timezone_manager import TimezoneManager
            return TimezoneManager.get_instance().get_timezone(self.custom_timezone)
        except Exception:
            pass
        return None

    def now(self, dt: Optional[datetime] = None) -> datetime:
        """Returns the current local datetime (or converted datetime if timezone configured)."""
        if dt is not None:
            return dt
        if self._tz:
            return datetime.now(self._tz)
        return datetime.now().astimezone()

    def get_day_part(self, dt: Optional[datetime] = None) -> DayPart:
        """
        Classifies current datetime into DayPart using configurable boundaries:
        - Morning:   05:00 to 11:59:59
        - Afternoon: 12:00 to 16:59:59
        - Evening:   17:00 to 20:59:59
        - Night:     21:00 to 04:59:59 (crosses midnight)
        """
        current_dt = self.now(dt)
        hour = current_dt.hour
        minute = current_dt.minute

        # Total minutes from midnight for boundary precision
        total_mins = hour * 60 + minute

        m_start = self.config.morning_start * 60     # 300 mins (05:00)
        a_start = self.config.afternoon_start * 60   # 720 mins (12:00)
        e_start = self.config.evening_start * 60     # 1020 mins (17:00)
        n_start = self.config.night_start * 60       # 1260 mins (21:00)

        if m_start <= total_mins < a_start:
            return DayPart.MORNING
        elif a_start <= total_mins < e_start:
            return DayPart.AFTERNOON
        elif e_start <= total_mins < n_start:
            return DayPart.EVENING
        else:
            return DayPart.NIGHT

    def get_day_part_name_hi(self, dt: Optional[datetime] = None) -> str:
        """Returns natural Hindi term for day part (subah, dopahar, shaam, raat)."""
        dp = self.get_day_part(dt)
        mapping = {
            DayPart.MORNING: "subah",
            DayPart.AFTERNOON: "dopahar",
            DayPart.EVENING: "shaam",
            DayPart.NIGHT: "raat"
        }
        return mapping[dp]

    def get_day_part_name_en(self, dt: Optional[datetime] = None) -> str:
        """Returns English term for day part (morning, afternoon, evening, night)."""
        return self.get_day_part(dt).value

    def get_greeting(
        self,
        user_said: Optional[str] = None,
        dt: Optional[datetime] = None,
        tone: str = "natural"
    ) -> str:
        """
        Generates a dynamic, time-accurate, and non-repeating Hinglish greeting.
        If the user gave an explicit day-part greeting that mismatches the actual time
        (e.g., 'Good morning' at 17:00), Jarvis politely acknowledges the real time.
        """
        current_dt = self.now(dt)
        day_part = self.get_day_part(current_dt)
        time_12h = current_dt.strftime("%I:%M %p").lstrip("0")
        day_name = current_dt.strftime("%A")
        user_lower = (user_said or "").strip().lower()

        # Check for user day-part mismatch
        mismatches = {
            "good morning": DayPart.MORNING,
            "morning jarvis": DayPart.MORNING,
            "shubh prabhat": DayPart.MORNING,
            "good afternoon": DayPart.AFTERNOON,
            "good evening": DayPart.EVENING,
            "shubh sandhya": DayPart.EVENING,
            "good night": DayPart.NIGHT,
            "shubh ratri": DayPart.NIGHT,
        }

        user_specified_dp = None
        for k, v in mismatches.items():
            if k in user_lower:
                user_specified_dp = v
                break

        # Handle user mismatch politely
        if user_specified_dp and user_specified_dp != day_part:
            hi_part = self.get_day_part_name_hi(current_dt)
            if day_part == DayPart.AFTERNOON:
                return f"Good afternoon Boss! (Vaise abhi dopahar ke {time_12h} baj rahe hain 😄) Bataiye kya help chahiye?"
            elif day_part == DayPart.EVENING:
                return f"Good evening Boss! (Vaise abhi shaam ke {time_12h} ho rahe hain 😄) Aaj ka kya plan hai?"
            elif day_part == DayPart.NIGHT:
                return f"Good evening / night Boss! (Abhi raat ke {time_12h} ho rahe hain) Boliye aage kya karna hai."
            elif day_part == DayPart.MORNING:
                return f"Good morning Boss! (Abhi subah ke {time_12h} hain) Bataiye aaj kya start karein?"

        # Dynamic greetings by DayPart
        greetings_pool: Dict[DayPart, List[str]] = {
            DayPart.MORNING: [
                "Good morning Boss! ☀️ Aaj ka kya plan hai?",
                "Good morning! Ek shandaar subah hai, bataiye aaj kya kaam karna hai?",
                "Shubh prabhat Boss! Main ready hoon, boliye kya help karun?",
                f"Good morning Boss! Aaj {day_name} hai, bataiye kya start karein?",
                "Morning Boss! Sab systems operational hain, boliye aage kya karna hai."
            ],
            DayPart.AFTERNOON: [
                "Good afternoon Boss! Aaj ka din kaisa chal raha hai?",
                "Good afternoon! Bataiye aage kya help chahiye?",
                f"Good afternoon Boss! Dopahar ke {time_12h} ho rahe hain, boliye kya task hai?",
                "Afternoon Boss! Main active hoon, bataiye kya karna hai.",
                "Good afternoon Boss! Sab ready hai, boliye kya chal raha hai?"
            ],
            DayPart.EVENING: [
                "Good evening Boss! 🌆 Aaj shaam ka kya plan hai?",
                "Good evening! Bataiye aaj shaam kya help karun?",
                f"Good evening Boss! Shaam ke {time_12h} ho rahe hain, boliye kya kaam hai.",
                "Evening Boss! Main active hoon, bataiye aage kya karna hai.",
                "Good evening Boss! Kaam kaisa chal raha hai? Boliye kya help chahiye."
            ],
            DayPart.NIGHT: [
                "Good night Boss! 🌙 Aaj ka din kaisa raha?",
                f"Raat ke {time_12h} ho rahe hain Boss! Bataiye kya help chahiye, ya main standby par rahoon?",
                "Good evening Boss! Kafi raat ho gayi hai, boliye kya zaroori task hai.",
                "Namaste Boss! Raat ke samay bhi main aapke commands ke liye fully active hoon.",
                "Good night Boss! Araam kijiye, main yahan active standby par hoon."
            ]
        }

        choices = greetings_pool.get(day_part, ["Hello Boss! Boliye kya help chahiye?"])
        return random.choice(choices)

    def get_time_summary(self, dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Provides a complete structured snapshot of the current time context."""
        current_dt = self.now(dt)
        day_part = self.get_day_part(current_dt)
        day_part_hi = self.get_day_part_name_hi(current_dt)

        hour_12 = current_dt.strftime("%I").lstrip("0")
        minute = current_dt.strftime("%M")
        ampm = current_dt.strftime("%p")

        # Natural Hindi time phrasing: "dopahar ke 4 bajkar 15 minute"
        if current_dt.minute == 0:
            time_hi = f"{day_part_hi} ke {hour_12} baje"
        else:
            time_hi = f"{day_part_hi} ke {hour_12} bajkar {minute} minute"

        return {
            "datetime": current_dt,
            "iso": current_dt.isoformat(),
            "time_12h": f"{hour_12}:{minute} {ampm}",
            "time_24h": current_dt.strftime("%H:%M"),
            "time_hi": time_hi,
            "date_str": current_dt.strftime("%d %B %Y"),
            "date_full": current_dt.strftime("%A, %d %B %Y"),
            "day_name": current_dt.strftime("%A"),
            "day_part": day_part.value,
            "day_part_hi": day_part_hi,
            "timezone": str(current_dt.tzinfo or "Local OS")
        }

    def detect_language(self, text: str) -> str:
        """Detects whether query is in English ('en') or Hindi/Hinglish ('hi')."""
        if not text:
            return "hi"
        low = text.lower()
        hindi_markers = [
            "kya", "hai", "hain", "ho raha", "hua", "batao", "bataiye", "kitne", "kitna",
            "baje", "samay", "aaj", "kal", "tarikh", "din", "subah", "dopahar", "shaam",
            "raat", "hoga", "hogi", "dono", "kaunsa", "kaun sa", "abhi"
        ]
        if any(re.search(r'\b' + re.escape(w) + r'\b', low) for w in hindi_markers):
            return "hi"
        return "en"

    def resolve_time_query(self, query: str, dt: Optional[datetime] = None) -> Optional[str]:
        """
        Resolves natural questions about time, date, day-part, day of week, or month.
        Generates clean, human-like Hinglish or English responses matching the query language.
        """
        if not query:
            return None

        q_lower = query.strip().lower()
        summary = self.get_time_summary(dt)
        curr_dt = summary["datetime"]
        time_12h = summary["time_12h"]
        day_name = summary["day_name"]
        date_str = summary["date_str"]
        date_full = summary["date_full"]
        day_part_hi = summary["day_part_hi"]
        day_part_en = summary["day_part"].capitalize()

        hour_12 = curr_dt.strftime("%I").lstrip("0")
        minute = curr_dt.strftime("%M")
        ampm = curr_dt.strftime("%p")

        lang = self.detect_language(query)

        # Hindi weekday names
        day_names_hi = {
            "Monday": "Somwar", "Tuesday": "Mangalwar", "Wednesday": "Budhwar",
            "Thursday": "Guruwar", "Friday": "Shukrawar", "Saturday": "Shaniwar",
            "Sunday": "Raviwar"
        }
        day_hi = day_names_hi.get(day_name, day_name)

        # 1. Combined Time and Date Queries ("time aur date dono batao", "tell me time and date")
        is_both = (
            any(w in q_lower for w in ["time aur date", "date aur time", "time and date", "date and time", "time aur tarikh", "dono batao"]) or
            ("time" in q_lower and ("date" in q_lower or "tarikh" in q_lower))
        )
        is_both_action = any(re.search(rf"\b{re.escape(c)}\b", q_lower) for c in ["set", "change", "update", "remind", "schedule", "alarm", "event", "fix", "badlo"])
        if is_both and not is_both_action:
            if lang == "en":
                return f"It is {time_12h} on {date_full}, Boss."
            return f"Abhi {day_part_hi} ke {hour_12}:{minute} {ampm} ho rahe hain aur aaj {day_name}, {date_str} hai, Boss."

        # 2. Relative Day (Tomorrow / Kal) Queries ("kal kya date hogi", "kal kaun sa din hai", "what date is tomorrow")
        if any(w in q_lower for w in ["kal", "tomorrow"]):
            # Guard: Must be an actual inquiry about tomorrow's date or weekday.
            # Exclude action directives / reminders / events (e.g. "kal subah 8 baje papa ko call", "kal meeting hai", "kal alarm lagao").
            action_or_event_cues = [
                "call", "remind", "reminder", "alarm", "meeting", "bhejo", "bhejna", "karo", "karna", "kardo",
                "khol", "kholo", "open", "play", "chalao", "jana", "jaana", "aana", "uthana", "doctor",
                "appointment", "task", "note", "karein", "chalna", "jayenge", "aayenge", "schedule"
            ]
            has_action_cue = any(re.search(rf"\b{re.escape(c)}\b", q_lower) for c in action_or_event_cues)

            is_tom_query = (
                any(p in q_lower for p in [
                    "kal kya date", "kal kya din", "kal kaun sa din", "kal kaunsa din", "kal konsa din",
                    "kal kon sa din", "kal ki date", "kal ka date", "kal ki tarikh", "kal ka din",
                    "kal date kya", "kal din kya", "kal tarikh kya",
                    "what date is tomorrow", "what day is tomorrow", "what is tomorrow's date",
                    "what is tomorrows date", "date tomorrow", "day tomorrow", "tomorrow date",
                    "tomorrow day", "tomorrow's date", "tomorrow's day", "tomorrow kya hai",
                    "tomorrow kaunsa din", "tomorrow konsa din"
                ])
                or (
                    any(w in q_lower for w in ["date", "tarikh", "din", "day"])
                    and any(w in q_lower for w in ["kya", "kaun", "konsa", "kon sa", "what", "which", "batao", "bataiye", "hogi", "hoga"])
                )
            )

            if is_tom_query and not has_action_cue:
                tomorrow_dt = curr_dt + timedelta(days=1)
                tom_day = tomorrow_dt.strftime("%A")
                tom_date = tomorrow_dt.strftime("%d %B %Y")
                tom_day_hi = day_names_hi.get(tom_day, tom_day)

                # Check if asking specifically for weekday
                if any(w in q_lower for w in ["din", "day"]):
                    if lang == "en":
                        return f"Tomorrow will be {tom_day}, Boss."
                    return f"Kal {tom_day} ({tom_day_hi}) hoga, Boss."

                # Date query for tomorrow
                if lang == "en":
                    return f"Tomorrow will be {tom_day}, {tom_date}, Boss."
                return f"Kal {tom_date} hogi, Boss ({tom_day})."

        # 3. Day of Week Queries ("aaj kaunsa din hai", "aaj konsa din hai", "what day is today", "what day is it")
        is_day_query = any(w in q_lower for w in [
            "kaunsa din", "kaun sa din", "konsa din", "kon sa din", "aaj kya din", "kya din hai",
            "aaj din kya", "what day is today", "what day is it", "what day is it today",
            "which day is today", "today day", "today's day", "what is today", "what day",
            "which day", "aaj konsa day", "konsa day", "kaunsa day"
        ])
        if is_day_query:
            if lang == "en":
                return f"Today is {day_name}, Boss."
            return f"Aaj {day_name} ({day_hi}) hai, Boss."

        # 4. Date Queries ("aaj date kya hai", "what is date today", "what is the date today", "aaj ki tarikh")
        is_date_query = any(w in q_lower for w in [
            "what is date today", "what is date", "what is the date", "what is the date today",
            "what is today's date", "what date is today", "what date is it", "what date",
            "today date", "today's date", "date today", "current date", "date kya hai",
            "aaj date", "aaj ki date", "aaj ka date", "aaj tarikh kya hai", "aaj ki tarikh",
            "aaj tarikh", "kaunsi tarikh", "konsi tarikh", "date batao", "date please",
            "tarikh batao", "tarikh kya hai"
        ])
        if is_date_query:
            if lang == "en":
                return f"Today is {date_full}, Boss."
            return f"Aaj {date_str} hai, Boss ({day_name})."

        # 5. Day-Part Verification Queries ("abhi morning hai ya afternoon", "abhi subah hai ya dopahar")
        is_daypart_query = any(w in q_lower for w in [
            "morning hai ya", "afternoon hai ya", "evening hai ya", "night hai ya",
            "subah hai ya", "dopahar hai ya", "shaam hai ya", "raat hai ya",
            "abhi subah hai", "abhi dopahar hai", "abhi shaam hai", "abhi raat hai",
            "is it morning or", "is it afternoon or", "is it evening or", "is it night or"
        ])
        if is_daypart_query:
            if lang == "en":
                return f"It's currently {day_part_en.lower()} ({time_12h}), Boss."
            return f"Abhi {day_part_hi} ({day_part_en}) ka samay hai Boss, lagbhag {time_12h} ho rahe hain."

        # 6. Month Queries ("abhi kaunsa month chal raha hai", "which month is it")
        if any(w in q_lower for w in ["kaunsa month", "kaun sa mahina", "current month", "which month"]):
            month_name = curr_dt.strftime("%B")
            if lang == "en":
                return f"It is currently {month_name}, Boss."
            return f"Abhi {month_name} chal raha hai Boss."

        # 7. Year Queries ("kaunsa year hai", "current year", "which year")
        if any(w in q_lower for w in ["kaunsa saal", "kaun sa year", "current year", "which year"]):
            year_name = curr_dt.strftime("%Y")
            if lang == "en":
                return f"The current year is {year_name}, Boss."
            return f"Abhi {year_name} chal raha hai Boss."

        # 8. Time Queries ("time kya ho raha hai", "kya time ho raha hai", "kitne baje hain", "what time is it")
        is_time_query = (
            any(w in q_lower for w in [
                "kitne baje", "kitna time", "kya time", "what time", "current time",
                "time kya", "time batao", "time bataiye", "time bata", "samay kya", "kya samay",
                "kitna baj", "kitne baj", "what is the time", "what's the time",
                "tell me the time", "time please", "time now"
            ]) or
            (re.search(r'\b(?:time|samay|clock)\b', q_lower) and any(w in q_lower for w in ["kya", "kitna", "kitne", "batao", "bataiye", "bata", "tell", "what", "current", "now"]))
        )
        if is_time_query:
            if lang == "en":
                return f"The current time is {time_12h}, Boss."
            # Natural Hinglish time response using day-part
            if curr_dt.minute == 0:
                return f"Abhi {day_part_hi} ke {hour_12} baj rahe hain ({time_12h}), Boss."
            return f"Abhi {day_part_hi} ke {hour_12}:{minute} {ampm} ho rahe hain, Boss."

        return None

    def resolve_relative_time(
        self,
        phrase: str,
        base_dt: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        Interprets natural Hindi/English relative time phrases for reminders & schedulers:
        - "aaj subah" -> today at morning_start (09:00 default reference)
        - "aaj dopahar" -> today at 14:00
        - "aaj shaam" / "shaam ko" -> today at 18:00
        - "aaj raat" / "raat ko" -> today at 21:00
        - "kal subah" -> tomorrow at 09:00
        - "kal shaam" -> tomorrow at 18:00
        - "kal subah 8 baje" -> tomorrow at 08:00
        - "aaj shaam 7 baje" -> today at 19:00
        - "raat ko 10 baje" -> today at 22:00
        """
        if not phrase:
            return None

        p_lower = phrase.strip().lower()
        now = self.now(base_dt)

        target_date = now.date()
        if "kal" in p_lower or "tomorrow" in p_lower:
            target_date = now.date() + timedelta(days=1)
        elif "parso" in p_lower or "day after tomorrow" in p_lower:
            target_date = now.date() + timedelta(days=2)

        # Check for explicit hour mention (e.g. "8 baje", "7:30 baje", "10 pm", "10 baje")
        hour_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(?:baje|am|pm|o\'clock)?', p_lower)
        target_hour = None
        target_minute = 0

        if hour_match:
            try:
                num = int(hour_match.group(1))
                if 1 <= num <= 24:
                    target_hour = num
                if hour_match.group(2):
                    target_minute = int(hour_match.group(2))
            except Exception:
                pass

        # Interpret day-part context for 12-hour ambiguity
        is_subah = any(w in p_lower for w in ["subah", "morning", "am"])
        is_dopahar = any(w in p_lower for w in ["dopahar", "afternoon", "noon"])
        is_shaam = any(w in p_lower for w in ["shaam", "evening"])
        is_raat = any(w in p_lower for w in ["raat", "night", "pm"])

        if target_hour is not None:
            # If 12-hour format is used with day-part qualifiers
            if target_hour <= 12:
                if (is_shaam or is_raat or is_dopahar) and target_hour < 12:
                    target_hour += 12
                elif is_subah and target_hour == 12:
                    target_hour = 0
            return datetime.combine(target_date, dt_time(target_hour, target_minute))

        # Default day-part baseline targets
        if is_subah:
            return datetime.combine(target_date, dt_time(9, 0))
        elif is_dopahar:
            return datetime.combine(target_date, dt_time(14, 0))
        elif is_shaam:
            return datetime.combine(target_date, dt_time(18, 0))
        elif is_raat:
            return datetime.combine(target_date, dt_time(21, 0))

        return None


# Global singleton instance
_time_context_instance: Optional[TimeContext] = None


def get_time_context() -> TimeContext:
    """Returns the global TimeContext service singleton."""
    global _time_context_instance
    if _time_context_instance is None:
        _time_context_instance = TimeContext()
    return _time_context_instance
