# core/weather/date_resolver.py
"""Dynamic temporal and date resolver for weather queries (runtime-clock aware)."""

from datetime import datetime, timedelta
import re
from typing import Optional, Tuple

from core.weather.models import WeatherForecastPeriod


class WeatherDateResolver:
    """Resolves relative date and time expressions dynamically using runtime system clock."""

    @classmethod
    def resolve_period_and_date(
        cls,
        text: str,
        now_dt: Optional[datetime] = None
    ) -> Tuple[WeatherForecastPeriod, Optional[str], int]:
        """
        Extracts temporal period, target ISO date string (YYYY-MM-DD), and count of days.
        Returns:
            (period, target_date_iso, days_count)
        """
        now = now_dt or datetime.now()
        lowered = text.lower()

        # 1. Day after tomorrow / Parso (+2 days)
        if any(w in lowered for w in ["parso", "day after tomorrow"]):
            target_dt = now + timedelta(days=2)
            return (WeatherForecastPeriod.DAY_AFTER_TOMORROW, target_dt.strftime("%Y-%m-%d"), 1)

        # 2. Tomorrow / Kal (+1 day)
        # Note: Avoid false match if phrase says "kal kitni baarish hui thi" (past),
        # but for weather forecasts "kal" is predominantly tomorrow.
        if any(w in lowered for w in ["kal", "tomorrow", "agle din", "next day"]):
            target_dt = now + timedelta(days=1)
            return (WeatherForecastPeriod.TOMORROW, target_dt.strftime("%Y-%m-%d"), 1)

        # 3. Tonight / This evening / Aaj raat
        if any(w in lowered for w in ["aaj raat", "tonight", "this evening", "aaj sham", "sham ko", "raat ko"]):
            return (WeatherForecastPeriod.TONIGHT, now.strftime("%Y-%m-%d"), 1)

        # 4. Weekend / This weekend
        if any(w in lowered for w in ["this weekend", "weekend", "hafte ke aakhri", "shaniwar itwar", "saturday sunday"]):
            # Find next Saturday (weekday 5 where Monday is 0)
            days_ahead = (5 - now.weekday()) % 7
            if days_ahead == 0 and now.weekday() == 5:
                # Today is Saturday
                target_dt = now
            else:
                target_dt = now + timedelta(days=days_ahead if days_ahead > 0 else 7)
            return (WeatherForecastPeriod.THIS_WEEKEND, target_dt.strftime("%Y-%m-%d"), 2)

        # 5. Multi-day forecasts ("next 3 days", "3 din ka", "next 7 days", "hafte ka")
        m_days = re.search(r"\b(?:next\s+)?(\d+)\s*(?:days?|din)\b", lowered)
        if m_days:
            num = int(m_days.group(1))
            num = max(1, min(num, 7))
            return (WeatherForecastPeriod.MULTI_DAY, now.strftime("%Y-%m-%d"), num)

        if any(w in lowered for w in ["next week", "is week", "this week", "agle hafte", "pure hafte", "weekly forecast"]):
            return (WeatherForecastPeriod.MULTI_DAY, now.strftime("%Y-%m-%d"), 7)

        # 6. Hourly / Next few hours
        if any(w in lowered for w in ["hourly", "har ghante", "next few hours", "agle kuch ghante", "ghante ka"]):
            return (WeatherForecastPeriod.HOURLY, now.strftime("%Y-%m-%d"), 1)

        # 7. Today / Aaj / Abhi / Current
        if any(w in lowered for w in ["aaj", "today", "abhi", "right now", "current", "is samay", "ab"]):
            return (WeatherForecastPeriod.CURRENT, now.strftime("%Y-%m-%d"), 1)

        # Default fallback to CURRENT
        return (WeatherForecastPeriod.CURRENT, now.strftime("%Y-%m-%d"), 1)
