# tests/test_time_context_service.py
"""Comprehensive regression test suite for TimeContext service and natural language time/date routing."""

from datetime import datetime
import pytest
from core.time_context import TimeContext, DayPart, get_time_context


from main import create_jarvis


@pytest.fixture
def time_context():
    return TimeContext()


@pytest.fixture
def core_app():
    return create_jarvis()


def test_language_detection(time_context):
    """Verifies accurate detection of Hindi/Hinglish vs English query languages."""
    assert time_context.detect_language("time kya ho raha hai") == "hi"
    assert time_context.detect_language("abhi kitne baje hain") == "hi"
    assert time_context.detect_language("aaj ka date kya hai") == "hi"
    assert time_context.detect_language("aaj kaun sa din hai") == "hi"
    assert time_context.detect_language("kal kya date hogi") == "hi"
    assert time_context.detect_language("what time is it") == "en"
    assert time_context.detect_language("what is the date today") == "en"
    assert time_context.detect_language("what day is today") == "en"
    assert time_context.detect_language("tell me the time") == "en"


def test_day_part_boundaries(time_context):
    """Verifies deterministic day part classification across boundary hours."""
    # Morning: 05:00 - 11:59
    assert time_context.get_day_part(datetime(2026, 9, 1, 5, 0)) == DayPart.MORNING
    assert time_context.get_day_part(datetime(2026, 9, 1, 11, 59)) == DayPart.MORNING

    # Afternoon: 12:00 - 16:59
    assert time_context.get_day_part(datetime(2026, 9, 1, 12, 0)) == DayPart.AFTERNOON
    assert time_context.get_day_part(datetime(2026, 9, 1, 16, 59)) == DayPart.AFTERNOON

    # Evening: 17:00 - 20:59
    assert time_context.get_day_part(datetime(2026, 9, 1, 17, 0)) == DayPart.EVENING
    assert time_context.get_day_part(datetime(2026, 9, 1, 20, 59)) == DayPart.EVENING

    # Night: 21:00 - 04:59
    assert time_context.get_day_part(datetime(2026, 9, 1, 21, 0)) == DayPart.NIGHT
    assert time_context.get_day_part(datetime(2026, 9, 1, 0, 0)) == DayPart.NIGHT
    assert time_context.get_day_part(datetime(2026, 9, 1, 4, 59)) == DayPart.NIGHT


def test_natural_hinglish_time_formatting(time_context):
    """Verifies natural Hinglish time phrasing without robotically dumping full date."""
    # Morning query (09:15)
    ans_m = time_context.resolve_time_query("time kya ho raha hai", dt=datetime(2026, 9, 1, 9, 15))
    assert "subah ke 9:15 AM" in ans_m
    assert "Boss" in ans_m

    # Afternoon query (14:30)
    ans_a = time_context.resolve_time_query("abhi kitne baje hain", dt=datetime(2026, 9, 1, 14, 30))
    assert "dopahar ke 2:30 PM" in ans_a

    # Evening query (19:21)
    ans_e = time_context.resolve_time_query("time kya ho raha hai", dt=datetime(2026, 9, 1, 19, 21))
    assert "shaam ke 7:21 PM" in ans_e

    # Night query (23:05)
    ans_n = time_context.resolve_time_query("kya time hua", dt=datetime(2026, 9, 1, 23, 5))
    assert "raat ke 11:05 PM" in ans_n

    # Exact hour query (10:00)
    ans_h = time_context.resolve_time_query("time batao", dt=datetime(2026, 9, 1, 10, 0))
    assert "subah ke 10 baj rahe hain" in ans_h


def test_natural_english_time_formatting(time_context):
    """Verifies English queries receive natural English responses."""
    ans = time_context.resolve_time_query("what time is it", dt=datetime(2026, 9, 1, 19, 21))
    assert ans == "The current time is 7:21 PM, Boss."

    ans2 = time_context.resolve_time_query("tell me the time", dt=datetime(2026, 9, 1, 9, 0))
    assert ans2 == "The current time is 9:00 AM, Boss."


def test_date_queries(time_context):
    """Verifies date queries return clean natural date information."""
    # Hinglish
    ans_hi = time_context.resolve_time_query("aaj ka date kya hai", dt=datetime(2026, 9, 1, 12, 0))
    assert "01 September 2026" in ans_hi
    assert "Tuesday" in ans_hi

    # English
    ans_en = time_context.resolve_time_query("what is the date today", dt=datetime(2026, 9, 1, 12, 0))
    assert "Tuesday, 01 September 2026" in ans_en


def test_weekday_queries(time_context):
    """Verifies weekday questions return day name accurately."""
    # Hinglish
    ans_hi = time_context.resolve_time_query("aaj kaun sa din hai", dt=datetime(2026, 9, 1, 12, 0))
    assert "Tuesday" in ans_hi
    assert "Mangalwar" in ans_hi

    # English
    ans_en = time_context.resolve_time_query("what day is today", dt=datetime(2026, 9, 1, 12, 0))
    assert ans_en == "Today is Tuesday, Boss."


def test_relative_tomorrow_queries(time_context):
    """Verifies tomorrow's date and weekday calculations."""
    # Tuesday Sep 1 -> Tomorrow is Wednesday Sep 2
    ref_dt = datetime(2026, 9, 1, 15, 0)

    # Hinglish date
    ans_date = time_context.resolve_time_query("kal kya date hogi", dt=ref_dt)
    assert "02 September 2026" in ans_date
    assert "Wednesday" in ans_date

    # Hinglish day
    ans_day = time_context.resolve_time_query("kal kaun sa din hai", dt=ref_dt)
    assert "Wednesday" in ans_day
    assert "Budhwar" in ans_day

    # English
    ans_en_date = time_context.resolve_time_query("what date is tomorrow", dt=ref_dt)
    assert "Wednesday, 02 September 2026" in ans_en_date


def test_day_part_verification_queries(time_context):
    """Verifies day-part inquiries (is it morning or evening)."""
    ans = time_context.resolve_time_query("abhi morning hai ya evening", dt=datetime(2026, 9, 1, 19, 21))
    assert "shaam (Evening)" in ans

    ans_en = time_context.resolve_time_query("is it morning or evening", dt=datetime(2026, 9, 1, 19, 21))
    assert "currently evening" in ans_en


def test_combined_time_and_date_queries(time_context):
    """Verifies combined time + date queries."""
    ans_hi = time_context.resolve_time_query("time aur date dono batao", dt=datetime(2026, 9, 1, 19, 21))
    assert "shaam ke 7:21 PM" in ans_hi
    assert "01 September 2026" in ans_hi

    ans_en = time_context.resolve_time_query("tell me time and date", dt=datetime(2026, 9, 1, 19, 21))
    assert "7:21 PM on Tuesday, 01 September 2026" in ans_en


def test_end_to_end_jarvis_core_time_routing(core_app):
    """End-to-end integration test verifying natural conversational time replies via JarvisCore."""
    # 1. Natural Hinglish time
    resp1 = core_app.process_input("time kya ho raha hai")
    assert any(dp in resp1.lower() for dp in ["subah", "dopahar", "shaam", "raat", "ho rahe hain"])
    assert "the current time is" not in resp1.lower()

    # 2. Date query
    resp2 = core_app.process_input("aaj ka date kya hai")
    assert "2026" in resp2

    # 3. English time query
    resp3 = core_app.process_input("what time is it")
    assert any(marker in resp3.lower() for marker in ["right now", "current time", "ho rahe hain"])
    assert "boss" not in resp3.lower()

    # 4. Status check query should not be confused with time
    resp4 = core_app.process_input("kya ho raha hai")
    assert any(w in resp4 for w in ["kuch khaas nahi", "yahin", "ready hoon", "normal hai", "scene hai"])
