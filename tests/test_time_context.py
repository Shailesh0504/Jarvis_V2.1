# tests/test_time_context.py
"""Unit tests for Centralized TimeContext & Dynamic Day-Part Greeting Subsystem."""

from datetime import datetime, timedelta
import pytest
from core.time_context import TimeContext, DayPart, DayPartConfig, get_time_context


def test_day_part_boundaries():
    """
    Verify strict day-part boundary classifications:
    - 04:59 -> NIGHT
    - 05:00 -> MORNING
    - 11:59 -> MORNING
    - 12:00 -> AFTERNOON
    - 16:59 -> AFTERNOON
    - 17:00 -> EVENING
    - 20:59 -> EVENING
    - 21:00 -> NIGHT
    - 00:00 (Midnight) -> NIGHT
    """
    tc = TimeContext()
    base_date = datetime(2026, 9, 1)

    # 1. Pre-dawn (04:59) -> NIGHT
    dt_0459 = base_date.replace(hour=4, minute=59)
    assert tc.get_day_part(dt_0459) == DayPart.NIGHT
    assert tc.get_day_part_name_hi(dt_0459) == "raat"

    # 2. Morning start (05:00) -> MORNING
    dt_0500 = base_date.replace(hour=5, minute=0)
    assert tc.get_day_part(dt_0500) == DayPart.MORNING
    assert tc.get_day_part_name_hi(dt_0500) == "subah"

    # 3. Morning end (11:59) -> MORNING
    dt_1159 = base_date.replace(hour=11, minute=59)
    assert tc.get_day_part(dt_1159) == DayPart.MORNING

    # 4. Afternoon start (12:00) -> AFTERNOON
    dt_1200 = base_date.replace(hour=12, minute=0)
    assert tc.get_day_part(dt_1200) == DayPart.AFTERNOON
    assert tc.get_day_part_name_hi(dt_1200) == "dopahar"

    # 5. Afternoon end (16:59) -> AFTERNOON
    dt_1659 = base_date.replace(hour=16, minute=59)
    assert tc.get_day_part(dt_1659) == DayPart.AFTERNOON

    # 6. Evening start (17:00) -> EVENING
    dt_1700 = base_date.replace(hour=17, minute=0)
    assert tc.get_day_part(dt_1700) == DayPart.EVENING
    assert tc.get_day_part_name_hi(dt_1700) == "shaam"

    # 7. Evening end (20:59) -> EVENING
    dt_2059 = base_date.replace(hour=20, minute=59)
    assert tc.get_day_part(dt_2059) == DayPart.EVENING

    # 8. Night start (21:00) -> NIGHT
    dt_2100 = base_date.replace(hour=21, minute=0)
    assert tc.get_day_part(dt_2100) == DayPart.NIGHT
    assert tc.get_day_part_name_hi(dt_2100) == "raat"

    # 9. Midnight (00:00) -> NIGHT
    dt_0000 = base_date.replace(hour=0, minute=0)
    assert tc.get_day_part(dt_0000) == DayPart.NIGHT


def test_dynamic_greetings_by_day_part():
    """Verify greeting changes appropriately according to time of day."""
    tc = TimeContext()
    base_date = datetime(2026, 9, 1)

    # Morning (09:00)
    dt_morning = base_date.replace(hour=9, minute=0)
    g_morning = tc.get_greeting(dt=dt_morning)
    assert any(w in g_morning.lower() for w in ["morning", "subah", "prabhat"])
    assert "good afternoon" not in g_morning.lower()
    assert "good night" not in g_morning.lower()

    # Afternoon (14:30)
    dt_afternoon = base_date.replace(hour=14, minute=30)
    g_afternoon = tc.get_greeting(dt=dt_afternoon)
    assert "afternoon" in g_afternoon.lower()
    assert "good morning" not in g_afternoon.lower()

    # Evening (18:45)
    dt_evening = base_date.replace(hour=18, minute=45)
    g_evening = tc.get_greeting(dt=dt_evening)
    assert "evening" in g_evening.lower()
    assert "good morning" not in g_evening.lower()

    # Night (23:15)
    dt_night = base_date.replace(hour=23, minute=15)
    g_night = tc.get_greeting(dt=dt_night)
    assert any(w in g_night.lower() for w in ["night", "raat", "evening", "namaste"])
    assert "good morning" not in g_night.lower()


def test_user_greeting_mismatch_correction():
    """Verify polite contextual acknowledgement when user says 'Good morning' in evening."""
    tc = TimeContext()
    base_date = datetime(2026, 9, 1)

    # User says 'Good morning' at 17:30 (Evening)
    dt_evening = base_date.replace(hour=17, minute=30)
    resp = tc.get_greeting(user_said="Good morning Jarvis", dt=dt_evening)

    assert "good evening" in resp.lower()
    assert "shaam" in resp.lower() or "5:30" in resp.lower()


def test_time_and_date_queries():
    """Verify resolution of natural time, date, and day questions."""
    tc = TimeContext()
    test_dt = datetime(2026, 9, 1, 16, 14)  # Tuesday, 1 September 2026 at 16:14

    # 1. Time query
    res_time = tc.resolve_time_query("kya time hua hai", dt=test_dt)
    assert res_time is not None
    assert "4:14" in res_time or "16:14" in res_time or "4 bajkar 14 minute" in res_time

    # 2. Date query
    res_date = tc.resolve_time_query("aaj date kya hai", dt=test_dt)
    assert res_date is not None
    assert "1 September 2026" in res_date or "September" in res_date

    # 3. Day query
    res_day = tc.resolve_time_query("aaj kaunsa din hai", dt=test_dt)
    assert res_day is not None
    assert "Tuesday" in res_day

    # 4. Day-part verification query
    res_dp = tc.resolve_time_query("abhi subah hai ya dopahar?", dt=test_dt)
    assert res_dp is not None
    assert "Afternoon" in res_dp or "Dopahar" in res_dp


def test_relative_time_resolution():
    """Verify natural relative time parsing for reminders."""
    tc = TimeContext()
    base_dt = datetime(2026, 9, 1, 10, 0)

    # 'kal subah 8 baje'
    res_tomorrow_8am = tc.resolve_relative_time("kal subah 8 baje", base_dt=base_dt)
    assert res_tomorrow_8am is not None
    assert res_tomorrow_8am.date() == (base_dt.date() + timedelta(days=1))
    assert res_tomorrow_8am.hour == 8
    assert res_tomorrow_8am.minute == 0

    # 'aaj shaam 7 baje'
    res_today_7pm = tc.resolve_relative_time("aaj shaam 7 baje", base_dt=base_dt)
    assert res_today_7pm is not None
    assert res_today_7pm.date() == base_dt.date()
    assert res_today_7pm.hour == 19
    assert res_today_7pm.minute == 0

    # 'raat ko 10 baje'
    res_tonight_10pm = tc.resolve_relative_time("raat ko 10 baje", base_dt=base_dt)
    assert res_tonight_10pm is not None
    assert res_tonight_10pm.hour == 22


def test_custom_configurable_boundaries():
    """Verify custom day-part boundaries can be configured."""
    custom_cfg = DayPartConfig(
        morning_start=6,     # 06:00
        afternoon_start=13,  # 13:00
        evening_start=18,    # 18:00
        night_start=22       # 22:00
    )
    tc = TimeContext(config=custom_cfg)
    base_date = datetime(2026, 9, 1)

    # 05:30 -> NIGHT with custom boundary (morning starts at 6)
    dt_0530 = base_date.replace(hour=5, minute=30)
    assert tc.get_day_part(dt_0530) == DayPart.NIGHT

    # 12:30 -> MORNING with custom boundary (afternoon starts at 13)
    dt_1230 = base_date.replace(hour=12, minute=30)
    assert tc.get_day_part(dt_1230) == DayPart.MORNING
