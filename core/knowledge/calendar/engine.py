# core/knowledge/calendar/engine.py
"""
Festival Calendar Knowledge Engine — Main Orchestrator.
Coordinates intent classification, year inference, festival lookup,
and response formatting for all calendar/festival queries.

CRITICAL: Current year is ALWAYS derived from datetime.now() at query time.
           It is NEVER stored as a module-level constant.
"""

import logging
import threading
from datetime import datetime
from typing import Optional

from ..models import (
    KnowledgeQueryResult,
    KnowledgeSourceType,
    ConfidenceLevel,
    GKQuestionType,
    KnowledgeCategory
)
from .models import CalendarIntentType, CalendarQueryResult
from .festival_store import get_festival_store, FestivalStore
from .intent_classifier import FestivalIntentClassifier
from .year_inference import YearInferenceEngine
from .formatter import FestivalResponseFormatter

logger = logging.getLogger("jarvis.core.knowledge.calendar.engine")


def _is_hindi_or_hinglish(query: str) -> bool:
    """Lightweight Hindi/Hinglish detector — avoids false positives on English words."""
    # Use tokens that are unambiguously Hindi/Hinglish (not colliding with English words)
    hi_tokens = {
        "kab", "kya", "hai", "hain", "kaun", "kitne", "mein", "se", "ka", "ki", "ke",
        "agle", "pichle", "agla", "saal", "tyohaar", "parv",
        "batao", "bataiye", "aaj", "kal", "kaunsa", "kaunsi", "padega", "padegi",
    }
    words = set(query.lower().split())
    return bool(words.intersection(hi_tokens))


class FestivalCalendarEngine:
    """
    Authoritative Calendar & Festival Knowledge Engine.

    Query pipeline:
      1. FestivalIntentClassifier → determine intent type
      2. YearInferenceEngine → resolve target year from system clock or query
      3. FestivalStore → look up festival entry and year data
      4. FestivalResponseFormatter → produce natural language answer
      5. Return KnowledgeQueryResult compatible with the broader GK pipeline
    """

    def __init__(self, store: Optional[FestivalStore] = None):
        self.store = store or get_festival_store()

    # ── Public API ──────────────────────────────────────────────────────────

    def is_calendar_candidate(self, query: str) -> bool:
        """Returns True if the query is a festival/calendar knowledge query."""
        return FestivalIntentClassifier.is_calendar_candidate(query)

    def query(self, raw_query: str) -> KnowledgeQueryResult:
        """
        Main entry point. Returns a KnowledgeQueryResult compatible with KnowledgeRouter.
        Always derives the current year from datetime.now() — never from a hardcoded constant.
        """
        intent, conf = FestivalIntentClassifier.classify(raw_query)
        is_hi = _is_hindi_or_hinglish(raw_query)

        logger.debug(f"[CALENDAR_ENGINE] Query={raw_query!r} Intent={intent.value} Conf={conf}")

        if intent == CalendarIntentType.NOT_CALENDAR:
            return self._not_found(is_hi)

        if intent == CalendarIntentType.GENERAL_DATE_QUERY:
            # Route to TimeContext — return not-found so the router falls through
            return self._not_found(is_hi, forward_to_time_context=True)

        if intent == CalendarIntentType.UPCOMING_FESTIVAL:
            return self._handle_upcoming(raw_query, is_hi)

        if intent == CalendarIntentType.MONTH_FESTIVAL:
            return self._handle_month_festivals(raw_query, is_hi)

        # For all other intents, resolve the festival first
        festival_id = self.store.resolve_festival_id(raw_query.lower())
        if not festival_id:
            return self._not_found(is_hi)

        entry = self.store.get_festival(festival_id)
        if not entry:
            return self._not_found(is_hi)

        if intent == CalendarIntentType.FESTIVAL_DEFINITION:
            return self._handle_definition(entry, is_hi)

        # Date / Duration / National Day queries → need year
        year, is_year_inferred = YearInferenceEngine.infer_year(raw_query)
        year_data = self.store.get_year_data(festival_id, year)

        if year_data is None:
            return self._year_data_not_found(entry, year, is_hi)

        # Build CalendarQueryResult
        cal_result = CalendarQueryResult(
            found=True,
            intent_type=intent,
            festival_id=festival_id,
            canonical_name_en=entry.canonical_name_en,
            canonical_name_hi=entry.canonical_name_hi,
            year=year,
            is_year_inferred=is_year_inferred,
            start_date=year_data.start_date,
            end_date=year_data.end_date,
            duration_days=(
                (year_data.end_date - year_data.start_date).days + 1
                if year_data.end_date else 1
            ),
            source=year_data.source,
            verified_date=year_data.verified_date,
            notes=year_data.notes,
            confidence=conf,
            is_approximate=year_data.is_approximate,
        )

        answer = FestivalResponseFormatter.format(cal_result, raw_query, is_hi)
        return self._wrap_result(cal_result, answer, conf, intent)

    # ── Intent handlers ─────────────────────────────────────────────────────

    def _handle_definition(self, entry, is_hi: bool) -> KnowledgeQueryResult:
        """Returns definition/summary of a festival."""
        summary = entry.summary_hi if is_hi else entry.summary_en
        if not summary:
            summary = entry.summary_en or entry.summary_hi

        cal_result = CalendarQueryResult(
            found=True,
            intent_type=CalendarIntentType.FESTIVAL_DEFINITION,
            festival_id=entry.festival_id,
            canonical_name_en=entry.canonical_name_en,
            canonical_name_hi=entry.canonical_name_hi,
            answer_text=summary,
            confidence=0.95,
        )
        return KnowledgeQueryResult(
            found=True,
            confidence=ConfidenceLevel.HIGH,
            confidence_score=0.95,
            source_type=KnowledgeSourceType.STATIC_FACT,
            answer_text=summary,
            question_type=GKQuestionType.FESTIVAL_INFO,
            entity_id=entry.festival_id,
            entity_name=entry.canonical_name_en,
            metadata={
                "category": KnowledgeCategory.FESTIVALS,
                "festival_id": entry.festival_id,
                "region": entry.region,
            }
        )

    def _handle_upcoming(self, raw_query: str, is_hi: bool) -> KnowledgeQueryResult:
        """Returns the next upcoming festival(s) from today."""
        today = datetime.now().date()
        upcoming = self.store.get_upcoming_festivals(today, limit=3)

        if not upcoming:
            msg = (
                "Abhi koi upcoming festival ki date mere paas nahi hai, Boss."
                if is_hi else
                "I don't have upcoming festival data available right now, Boss."
            )
            return self._not_found(is_hi, custom_msg=msg)

        entry, yd = upcoming[0]
        cal_result = CalendarQueryResult(
            found=True,
            intent_type=CalendarIntentType.UPCOMING_FESTIVAL,
            festival_id=entry.festival_id,
            canonical_name_en=entry.canonical_name_en,
            canonical_name_hi=entry.canonical_name_hi,
            year=yd.start_date.year,
            is_year_inferred=True,
            start_date=yd.start_date,
            end_date=yd.end_date,
            confidence=0.93,
        )
        answer = FestivalResponseFormatter.format(cal_result, raw_query, is_hi)
        return self._wrap_result(cal_result, answer, 0.93, CalendarIntentType.UPCOMING_FESTIVAL)

    def _handle_month_festivals(self, raw_query: str, is_hi: bool) -> KnowledgeQueryResult:
        """Returns all festivals in a queried month."""
        import re
        year, _ = YearInferenceEngine.infer_year(raw_query)
        lowered = raw_query.lower()

        # Try to extract month from query
        month_names = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10,
            "november": 11, "nov": 11, "december": 12, "dec": 12,
        }
        target_month = None
        for mname, mnum in month_names.items():
            if mname in lowered:
                target_month = mnum
                break

        if target_month is None:
            target_month = datetime.now().month

        festivals = self.store.get_festivals_in_month(year, target_month)
        if not festivals:
            import calendar as cal
            month_str = cal.month_name[target_month]
            msg = (
                f"{month_str} {year} mein koi major festival nahi hai mere data mein, Boss."
                if is_hi else
                f"I don't have any festivals for {month_str} {year} in my data, Boss."
            )
            return self._not_found(is_hi, custom_msg=msg)

        import calendar as cal_mod
        month_str = cal_mod.month_name[target_month]

        if is_hi:
            lines = [f"{month_str} {year} mein yeh major festivals hain:"]
            for e, yd in festivals:
                lines.append(f"• {e.canonical_name_en}: {yd.start_date.day} {month_str}")
            answer = " ".join(lines)
        else:
            lines = [f"Major festivals in {month_str} {year}:"]
            for e, yd in festivals:
                lines.append(f"• {e.canonical_name_en}: {yd.start_date.day} {month_str}")
            answer = " ".join(lines)

        entry, yd = festivals[0]
        cal_result = CalendarQueryResult(
            found=True,
            intent_type=CalendarIntentType.MONTH_FESTIVAL,
            festival_id=entry.festival_id,
            canonical_name_en=entry.canonical_name_en,
            canonical_name_hi=entry.canonical_name_hi,
            year=year,
            is_year_inferred=True,
            start_date=yd.start_date,
            confidence=0.90,
            answer_text=answer,
        )
        return self._wrap_result(cal_result, answer, 0.90, CalendarIntentType.MONTH_FESTIVAL)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _year_data_not_found(self, entry, year: int, is_hi: bool) -> KnowledgeQueryResult:
        msg = (
            f"{entry.canonical_name_en} ki {year} ki exact date mere paas abhi uplabdh nahi hai, Boss. "
            f"Mera data 2024 se 2028 tak hai. Kripya Drik Panchang se confirm karein."
            if is_hi else
            f"I don't have verified date data for {entry.canonical_name_en} in {year}, Boss. "
            f"My data covers 2024–2028. Please verify with Drik Panchang."
        )
        return KnowledgeQueryResult(
            found=False,
            confidence=ConfidenceLevel.LOW,
            confidence_score=0.15,
            source_type=KnowledgeSourceType.UNKNOWN,
            answer_text=msg,
            question_type=GKQuestionType.FESTIVAL_DATE,
            entity_id=entry.festival_id,
            entity_name=entry.canonical_name_en,
            metadata={"festival_id": entry.festival_id, "requested_year": year}
        )

    def _not_found(
        self,
        is_hi: bool,
        forward_to_time_context: bool = False,
        custom_msg: str = ""
    ) -> KnowledgeQueryResult:
        if forward_to_time_context:
            # Signal to router to fall through to TimeContext
            return KnowledgeQueryResult(
                found=False,
                confidence=ConfidenceLevel.LOW,
                confidence_score=0.0,
                source_type=KnowledgeSourceType.UNKNOWN,
                answer_text="",
                metadata={"forward_to_time_context": True}
            )
        msg = custom_msg or (
            "Is festival ya date ke baare mein mere paas reliable jaankari nahi hai, Boss."
            if is_hi else
            "I don't have reliable calendar information about that, Boss."
        )
        return KnowledgeQueryResult(
            found=False,
            confidence=ConfidenceLevel.LOW,
            confidence_score=0.0,
            source_type=KnowledgeSourceType.UNKNOWN,
            answer_text=msg,
        )

    def _wrap_result(
        self,
        cal_result: CalendarQueryResult,
        answer: str,
        conf: float,
        intent: CalendarIntentType,
    ) -> KnowledgeQueryResult:
        """Converts CalendarQueryResult into a KnowledgeQueryResult for the main pipeline."""
        q_type_map = {
            CalendarIntentType.FESTIVAL_DATE_QUERY: GKQuestionType.FESTIVAL_DATE,
            CalendarIntentType.NATIONAL_DAY_QUERY:  GKQuestionType.FESTIVAL_DATE,
            CalendarIntentType.FESTIVAL_DEFINITION: GKQuestionType.FESTIVAL_INFO,
            CalendarIntentType.FESTIVAL_DURATION:   GKQuestionType.FESTIVAL_DATE,
            CalendarIntentType.UPCOMING_FESTIVAL:   GKQuestionType.UPCOMING_EVENT,
            CalendarIntentType.MONTH_FESTIVAL:      GKQuestionType.UPCOMING_EVENT,
        }
        return KnowledgeQueryResult(
            found=True,
            confidence=ConfidenceLevel.HIGH if conf >= 0.85 else ConfidenceLevel.MEDIUM,
            confidence_score=conf,
            source_type=KnowledgeSourceType.STATIC_FACT,
            answer_text=answer,
            question_type=q_type_map.get(intent, GKQuestionType.FESTIVAL_DATE),
            entity_id=cal_result.festival_id,
            entity_name=cal_result.canonical_name_en,
            is_time_sensitive=False,
            metadata={
                "category": KnowledgeCategory.FESTIVALS,
                "festival_id": cal_result.festival_id,
                "year": cal_result.year,
                "year_inferred": cal_result.is_year_inferred,
                "start_date": str(cal_result.start_date) if cal_result.start_date else None,
                "end_date": str(cal_result.end_date) if cal_result.end_date else None,
                "source": cal_result.source,
                "is_approximate": cal_result.is_approximate,
            }
        )


# ── Singleton ────────────────────────────────────────────────────────────────
_engine_instance: Optional[FestivalCalendarEngine] = None
_engine_lock = threading.Lock()


def get_festival_calendar_engine() -> FestivalCalendarEngine:
    """Thread-safe singleton accessor for the FestivalCalendarEngine."""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = FestivalCalendarEngine()
    return _engine_instance
