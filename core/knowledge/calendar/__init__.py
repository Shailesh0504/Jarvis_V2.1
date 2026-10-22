# core/knowledge/calendar/__init__.py
"""
Jarvis Calendar & Festival Knowledge Sub-System.
Provides year-aware festival date resolution, definition answers,
upcoming festival discovery, and national day queries for Indian festivals.

Current year is ALWAYS derived from datetime.now() at runtime — never hardcoded.
"""

from .models import (
    FestivalDateType,
    FestivalCategory,
    CalendarIntentType,
    FestivalYearData,
    FestivalEntry,
    CalendarQueryResult
)
from .festival_store import FestivalStore, get_festival_store
from .year_inference import YearInferenceEngine
from .intent_classifier import FestivalIntentClassifier
from .formatter import FestivalResponseFormatter
from .engine import FestivalCalendarEngine, get_festival_calendar_engine

__all__ = [
    "FestivalDateType",
    "FestivalCategory",
    "CalendarIntentType",
    "FestivalYearData",
    "FestivalEntry",
    "CalendarQueryResult",
    "FestivalStore",
    "get_festival_store",
    "YearInferenceEngine",
    "FestivalIntentClassifier",
    "FestivalResponseFormatter",
    "FestivalCalendarEngine",
    "get_festival_calendar_engine",
]
