# core/knowledge/calendar/intent_classifier.py
"""
Festival & Calendar Intent Classifier for the Jarvis Calendar Knowledge Engine.
Determines the type of calendar/festival query before dispatching to the engine.
"""

import re
from typing import Tuple

from .models import CalendarIntentType
from .festival_store import get_festival_store


# ── Token banks ───────────────────────────────────────────────────────────────

_DATE_QUESTION_TOKENS = [
    # Hindi/Hinglish date-query markers
    "kab hai", "kab padega", "kab padegi", "kab aayega", "kab aayegi",
    "kab manaya", "kab manai", "kab tha", "kab thi", "kab hoga", "kab hogi",
    "kab se", "kab tak", "kis date", "kaunsi date", "kis tarikh",
    "date kya hai", "tarikh kya hai",
    # English equivalents
    "when is", "what date is", "on which date", "which date",
    "when does", "when will", "when was",
]

_DEFINITION_QUESTION_TOKENS = [
    "kya hai", "kya hota hai", "kya hoti hai", "kya hote hain",
    "kya hain", "kya h", "what is", "what are",
    "ke baare mein batao", "ke bare mein batao", "baare mein batao",
    "about", "explain", "samjhao", "samjhaiye",
    "describe", "tell me about",
]

_DURATION_QUESTION_TOKENS = [
    "kitne din", "kitne dino", "kitna din", "how many days",
    "kab se kab tak", "kab shuru", "kab khatam", "kab samapat",
    "start to end", "start date", "end date", "visarjan",
    "kitne time", "how long",
]

_UPCOMING_FESTIVAL_TOKENS = [
    "agla festival", "agla tyohaar", "agle festival", "agle tyohaar",
    "next festival", "next tyohaar", "upcoming festival", "upcoming tyohaar",
    "abhi agla", "abhi kaunsa festival", "kaunsa festival aane wala",
    "next major festival", "nearest festival",
]

_MONTH_FESTIVAL_TOKENS = [
    "is month", "is mahine", "is mahine mein", "is month mein",
    "this month", "current month",
    "january mein", "february mein", "march mein", "april mein",
    "may mein", "june mein", "july mein", "august mein",
    "september mein", "october mein", "november mein", "december mein",
    "jan mein", "feb mein", "mar mein", "apr mein",
    "aug mein", "sep mein", "oct mein", "nov mein", "dec mein",
    "in january", "in february", "in march", "in april", "in may",
    "in june", "in july", "in august", "in september",
    "in october", "in november", "in december",
]

_NATIONAL_DAY_TOKENS = [
    "republic day", "gantantra diwas",
    "independence day", "swatantrata diwas", "azaadi ka din",
    "gandhi jayanti",
    "teachers day", "teachers' day", "shikshak diwas",
    "childrens day", "children's day", "bal diwas",
    "constitution day", "samvidhan diwas",
    "national science day", "rashtriya vigyan diwas",
]

_GENERAL_DATE_TOKENS = [
    "aaj kya date", "aaj ki date", "aaj ka date", "today's date",
    "what date is today", "what is today's date", "what is the date",
    "aaj kaun sa din", "aaj kaunsa din", "what day is today",
    "kal kya date", "kal kya hogi", "tomorrow's date",
    "current date", "today date", "aaj tarikh",
]


class FestivalIntentClassifier:
    """
    Classifies a query into a CalendarIntentType.
    Also detects which festival is being asked about via the FestivalStore alias index.
    """

    @classmethod
    def classify(cls, query: str) -> Tuple[CalendarIntentType, float]:
        """
        Returns (CalendarIntentType, confidence).
        confidence is 0.0 if NOT_CALENDAR, otherwise 0.85–0.97.
        """
        lowered = query.strip().lower()
        store = get_festival_store()

        # 1. General date queries ("aaj kya date hai?") — route to TimeContext
        if any(tok in lowered for tok in _GENERAL_DATE_TOKENS):
            return CalendarIntentType.GENERAL_DATE_QUERY, 0.95

        # 2. Upcoming festival queries
        if any(tok in lowered for tok in _UPCOMING_FESTIVAL_TOKENS):
            return CalendarIntentType.UPCOMING_FESTIVAL, 0.95

        # 3. Month-based festival queries
        if any(tok in lowered for tok in _MONTH_FESTIVAL_TOKENS):
            # Only classify as month-festival if a festival keyword is also present,
            # or the phrasing is specifically about festivals in a month
            if any(tok in lowered for tok in ["festival", "tyohaar", "parv", "holiday", "chhutti"]):
                return CalendarIntentType.MONTH_FESTIVAL, 0.92

        # 4. Check if the query references a known festival
        festival_id = store.resolve_festival_id(lowered)
        is_national_day = any(tok in lowered for tok in _NATIONAL_DAY_TOKENS)

        # Exclude action commands — if the query has action verbs, it's not a knowledge query
        _action_verbs = [
            "laga do", "set karo", "yaad dilao", "remind", "create reminder",
            "reminder banao", "schedule", "book", "cancel",
        ]
        if any(av in lowered for av in _action_verbs):
            return CalendarIntentType.NOT_CALENDAR, 0.0

        if festival_id or is_national_day:
            # Sub-classify: duration > definition > date (priority order)
            if any(tok in lowered for tok in _DURATION_QUESTION_TOKENS):
                return CalendarIntentType.FESTIVAL_DURATION, 0.93

            if any(tok in lowered for tok in _DEFINITION_QUESTION_TOKENS):
                return CalendarIntentType.FESTIVAL_DEFINITION, 0.92

            if any(tok in lowered for tok in _DATE_QUESTION_TOKENS):
                if is_national_day:
                    return CalendarIntentType.NATIONAL_DAY_QUERY, 0.95
                return CalendarIntentType.FESTIVAL_DATE_QUERY, 0.95

            # Even without explicit question words, "Ganpati kab?" or "Diwali 2026?" is a date query
            # Check for bare festival name + year or bare festival name with no other context
            has_year = bool(re.search(r'\b20[2-9]\d\b', lowered))
            if has_year:
                return CalendarIntentType.FESTIVAL_DATE_QUERY, 0.90

            # Bare festival name alone → date query (most natural intent)
            tokens_in_query = set(re.findall(r'\b\w+\b', lowered))
            question_words = {"kya", "what", "how", "kyun", "why", "explain", "baare", "about",
                              "samjhao", "describe", "bataiye"}
            if question_words.intersection(tokens_in_query):
                return CalendarIntentType.FESTIVAL_DEFINITION, 0.87

            # Default for known festival: date query
            if is_national_day:
                return CalendarIntentType.NATIONAL_DAY_QUERY, 0.88
            return CalendarIntentType.FESTIVAL_DATE_QUERY, 0.88

        return CalendarIntentType.NOT_CALENDAR, 0.0

    @classmethod
    def is_calendar_candidate(cls, query: str) -> bool:
        """Quick check: does this query involve calendar/festival knowledge?"""
        intent, conf = cls.classify(query)
        return intent != CalendarIntentType.NOT_CALENDAR
