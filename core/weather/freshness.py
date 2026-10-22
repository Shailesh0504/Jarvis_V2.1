# core/weather/freshness.py
"""Freshness validator for live weather observations and forecasts."""

import time
from typing import Optional, Tuple

from core.weather.models import WeatherData

# Max age for live current weather (3 hours)
MAX_CURRENT_WEATHER_AGE_SECONDS = 3 * 3600

# Max age for multi-day forecasts (12 hours)
MAX_FORECAST_AGE_SECONDS = 12 * 3600


class WeatherFreshnessValidator:
    """Validates that retrieved weather information is fresh and suitable for live presentation."""

    @staticmethod
    def is_fresh(data: WeatherData, is_forecast: bool = False, max_age_seconds: Optional[float] = None) -> Tuple[bool, float]:
        """
        Evaluates data freshness.
        Returns:
            (is_fresh, age_seconds)
        """
        limit = max_age_seconds or (MAX_FORECAST_AGE_SECONDS if is_forecast else MAX_CURRENT_WEATHER_AGE_SECONDS)
        now = time.time()
        age = now - data.retrieved_at

        if age < 0:
            # Future timestamp or clock drift
            return True, 0.0

        return age <= limit, age
