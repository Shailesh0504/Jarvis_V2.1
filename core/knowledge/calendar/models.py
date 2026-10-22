# core/knowledge/calendar/models.py
"""
Data models for the Jarvis Calendar & Festival Knowledge Engine.
Defines festival entries, year-specific date data, query classification,
and calendar query results — all year-aware with runtime clock resolution.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional


class FestivalDateType(str, Enum):
    """How a festival's date is determined."""
    GREGORIAN_FIXED   = "GREGORIAN_FIXED"   # Same date every year (Christmas, Independence Day)
    LUNAR_COMPUTED    = "LUNAR_COMPUTED"     # Varies by lunar/Hindu calendar (Diwali, Holi, etc.)
    SOLAR_COMPUTED    = "SOLAR_COMPUTED"     # Based on solar position (Makar Sankranti ~14 Jan)
    ISLAMIC_LUNAR     = "ISLAMIC_LUNAR"      # Islamic lunar calendar (Eid)


class FestivalCategory(str, Enum):
    HINDU_FESTIVAL    = "HINDU_FESTIVAL"
    NATIONAL_DAY      = "NATIONAL_DAY"
    ISLAMIC_FESTIVAL  = "ISLAMIC_FESTIVAL"
    CHRISTIAN_FESTIVAL = "CHRISTIAN_FESTIVAL"
    SIKH_FESTIVAL     = "SIKH_FESTIVAL"
    JAIN_FESTIVAL     = "JAIN_FESTIVAL"
    BUDDHIST_FESTIVAL = "BUDDHIST_FESTIVAL"
    REGIONAL_FESTIVAL = "REGIONAL_FESTIVAL"
    HARVEST_FESTIVAL  = "HARVEST_FESTIVAL"


class CalendarIntentType(str, Enum):
    FESTIVAL_DATE_QUERY    = "FESTIVAL_DATE_QUERY"     # "Ganpati kab hai?"
    FESTIVAL_DEFINITION    = "FESTIVAL_DEFINITION"     # "Ganpati kya hai?"
    FESTIVAL_DURATION      = "FESTIVAL_DURATION"       # "Ganpati kitne din chalega?"
    UPCOMING_FESTIVAL      = "UPCOMING_FESTIVAL"       # "Agla festival kaunsa hai?"
    MONTH_FESTIVAL         = "MONTH_FESTIVAL"          # "Is month kaun sa festival hai?"
    NATIONAL_DAY_QUERY     = "NATIONAL_DAY_QUERY"      # "Republic Day kab hai?"
    GENERAL_DATE_QUERY     = "GENERAL_DATE_QUERY"      # "Aaj date kya hai?" → route to TimeContext
    NOT_CALENDAR           = "NOT_CALENDAR"            # Not a calendar/festival query


@dataclass
class FestivalYearData:
    """Date information for a festival in a specific year."""
    year: int
    start_date: date                    # Start date of the festival
    end_date: Optional[date] = None     # End date (None if single-day)
    source: str = "Hindu Panchang"      # Source of the date computation
    verified_date: str = ""             # When this data was verified (ISO date string)
    notes: str = ""                     # Regional notes, e.g. "Maharashtra main 10 din"
    is_approximate: bool = False        # True for Islamic/approximated dates


@dataclass
class FestivalEntry:
    """
    Canonical festival definition with multi-year date registry.
    Dates are pre-verified from authoritative calendar sources; never hardcoded
    assumptions — look up by year from dates_by_year.
    """
    festival_id: str                            # e.g. "ganesh_chaturthi"
    canonical_name_en: str                      # "Ganesh Chaturthi"
    canonical_name_hi: str                      # "गणेश चतुर्थी / Ganesh Chaturthi"
    aliases: List[str] = field(default_factory=list)    # All recognized aliases
    date_type: FestivalDateType = FestivalDateType.LUNAR_COMPUTED
    category: FestivalCategory = FestivalCategory.HINDU_FESTIVAL
    calendar_system: str = "Hindu Lunar"
    region: str = "Pan-India"
    typical_duration_days: int = 1
    summary_en: str = ""
    summary_hi: str = ""
    # Pre-computed, verified dates indexed by year
    dates_by_year: Dict[int, FestivalYearData] = field(default_factory=dict)


@dataclass
class CalendarQueryResult:
    """Structured result from the Festival Calendar Engine."""
    found: bool
    intent_type: CalendarIntentType = CalendarIntentType.NOT_CALENDAR
    festival_id: Optional[str] = None
    canonical_name_en: str = ""
    canonical_name_hi: str = ""
    year: Optional[int] = None
    is_year_inferred: bool = True       # True when year came from system clock, not user
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_days: int = 1
    answer_text: str = ""
    source: str = ""
    verified_date: str = ""
    notes: str = ""
    confidence: float = 0.0
    is_approximate: bool = False
