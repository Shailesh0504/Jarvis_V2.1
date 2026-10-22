# core/knowledge/calendar/formatter.py
"""
Natural Language Response Formatter for the Festival Calendar Knowledge Engine.
Generates concise, natural Hinglish/English answers for calendar queries.
"""

from datetime import date
from typing import Optional

from .models import FestivalEntry, FestivalYearData, CalendarQueryResult, CalendarIntentType


_MONTHS_EN = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

_MONTHS_HI = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _fmt_date_en(d: date) -> str:
    """Formats date as '14 September 2026'."""
    return f"{d.day} {_MONTHS_EN[d.month]} {d.year}"


def _fmt_date_hi(d: date) -> str:
    """Formats date as '14 September 2026' (using English month names as commonly spoken in Hinglish)."""
    return f"{d.day} {_MONTHS_EN[d.month]} {d.year}"


class FestivalResponseFormatter:
    """Formats CalendarQueryResult into natural conversational responses."""

    @classmethod
    def format(
        cls,
        result: CalendarQueryResult,
        original_query: str,
        is_hindi: bool = True
    ) -> str:
        """Main entry point — returns a formatted response string."""
        if not result.found:
            return cls._format_not_found(result, is_hindi)

        intent = result.intent_type

        if intent == CalendarIntentType.FESTIVAL_DATE_QUERY:
            return cls._format_date_answer(result, is_hindi)
        elif intent == CalendarIntentType.NATIONAL_DAY_QUERY:
            return cls._format_date_answer(result, is_hindi)
        elif intent == CalendarIntentType.FESTIVAL_DEFINITION:
            return cls._format_definition(result, is_hindi)
        elif intent == CalendarIntentType.FESTIVAL_DURATION:
            return cls._format_duration(result, is_hindi)
        elif intent == CalendarIntentType.UPCOMING_FESTIVAL:
            return cls._format_upcoming(result, is_hindi)
        elif intent == CalendarIntentType.MONTH_FESTIVAL:
            return cls._format_date_answer(result, is_hindi)
        else:
            return result.answer_text or cls._format_not_found(result, is_hindi)

    # ── Individual formatters ───────────────────────────────────────────────

    @classmethod
    def _format_date_answer(cls, result: CalendarQueryResult, is_hindi: bool) -> str:
        name = result.canonical_name_en
        year = result.year
        start = result.start_date
        end = result.end_date

        if not start:
            return cls._format_not_found(result, is_hindi)

        approx_note = " (approx.)" if result.is_approximate else ""

        if is_hindi:
            if end and end != start:
                return (
                    f"{year} mein {name}{approx_note} "
                    f"{_fmt_date_hi(start)} se {_fmt_date_hi(end)} tak hai."
                )
            else:
                return f"{year} mein {name}{approx_note} {_fmt_date_hi(start)} ko hai."
        else:
            if end and end != start:
                return (
                    f"In {year}, {name} is from "
                    f"{_fmt_date_en(start)} to {_fmt_date_en(end)}{approx_note}."
                )
            else:
                return f"In {year}, {name} falls on {_fmt_date_en(start)}{approx_note}."

    @classmethod
    def _format_definition(cls, result: CalendarQueryResult, is_hindi: bool) -> str:
        """Returns the festival summary."""
        if result.answer_text:
            return result.answer_text
        return (
            f"{result.canonical_name_en} ke baare mein mujhe aur jaankari chahiye."
            if is_hindi else
            f"I need more context about {result.canonical_name_en}."
        )

    @classmethod
    def _format_duration(cls, result: CalendarQueryResult, is_hindi: bool) -> str:
        name = result.canonical_name_en
        year = result.year
        start = result.start_date
        end = result.end_date
        days = result.duration_days

        if not start:
            return cls._format_not_found(result, is_hindi)

        if is_hindi:
            if end and end != start:
                return (
                    f"{name} {days} din chalti hai — "
                    f"{year} mein {_fmt_date_hi(start)} se {_fmt_date_hi(end)} tak."
                )
            else:
                return f"{name} ek din manaya jata hai — {year} mein {_fmt_date_hi(start)} ko."
        else:
            if end and end != start:
                return (
                    f"{name} lasts {days} days — "
                    f"from {_fmt_date_en(start)} to {_fmt_date_en(end)} in {year}."
                )
            else:
                return f"{name} is a single-day celebration — {_fmt_date_en(start)} in {year}."

    @classmethod
    def _format_upcoming(cls, result: CalendarQueryResult, is_hindi: bool) -> str:
        name = result.canonical_name_en
        start = result.start_date
        if not start:
            return cls._format_not_found(result, is_hindi)

        if is_hindi:
            return f"Agla bada festival {name} hai, jo {_fmt_date_hi(start)} ko hai."
        else:
            return f"The next upcoming festival is {name}, on {_fmt_date_en(start)}."

    @classmethod
    def _format_not_found(cls, result: CalendarQueryResult, is_hindi: bool) -> str:
        if result.festival_id and result.year:
            if is_hindi:
                return (
                    f"{result.canonical_name_en or 'Is festival'} ki "
                    f"{result.year} ki exact date mere paas abhi uplabdh nahi hai, Boss. "
                    f"Kripya calendar ya Drik Panchang se confirm karein."
                )
            else:
                return (
                    f"I don't have verified date data for "
                    f"{result.canonical_name_en or 'that festival'} in {result.year}, Boss. "
                    f"Please verify with a Panchang or official calendar."
                )
        if is_hindi:
            return "Is baare mein mere paas reliable calendar jaankari uplabdh nahi hai, Boss."
        return "I don't have reliable calendar information about that, Boss."
