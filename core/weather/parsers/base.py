# core/weather/parsers/base.py
"""Base interface for modular weather source parsers."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.weather.models import WeatherData, WeatherLocation


class BaseWeatherParser(ABC):
    """Abstract parser translating raw public web bytes or text into normalized WeatherData."""

    @abstractmethod
    def parse(self, raw_content: bytes, location: WeatherLocation, source_name: str = "") -> Optional[WeatherData]:
        """Parses raw downloaded content into structured WeatherData."""
        pass
