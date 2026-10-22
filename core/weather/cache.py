# core/weather/cache.py
"""Short-lived thread-safe cache for weather observations and forecasts."""

import threading
import time
from typing import Dict, Optional, Tuple

from core.weather.models import WeatherData


class WeatherCache:
    """In-memory cache with independent TTLs for current conditions and multi-day forecasts."""

    def __init__(self, current_ttl_seconds: float = 600.0, forecast_ttl_seconds: float = 1800.0):
        self.current_ttl = current_ttl_seconds
        self.forecast_ttl = forecast_ttl_seconds
        self._cache: Dict[str, Tuple[WeatherData, float]] = {}  # key -> (data, cached_at)
        self._lock = threading.Lock()

    def _make_key(self, location_name: str, is_forecast: bool) -> str:
        return f"{location_name.strip().lower()}:{'forecast' if is_forecast else 'current'}"

    def get(self, location_name: str, is_forecast: bool = False) -> Optional[WeatherData]:
        """Returns cached WeatherData if present and unexpired."""
        key = self._make_key(location_name, is_forecast)
        ttl = self.forecast_ttl if is_forecast else self.current_ttl

        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None

            data, cached_at = entry
            if (time.time() - cached_at) > ttl:
                # Expired
                del self._cache[key]
                return None

            return data

    def put(self, location_name: str, data: WeatherData, is_forecast: bool = False) -> None:
        """Stores WeatherData into the cache."""
        key = self._make_key(location_name, is_forecast)
        with self._lock:
            self._cache[key] = (data, time.time())

    def clear(self) -> None:
        """Clears all cached weather entries."""
        with self._lock:
            self._cache.clear()
