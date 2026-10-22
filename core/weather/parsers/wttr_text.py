# core/weather/parsers/wttr_text.py
"""Parser for lightweight wttr.in plain-text formatted responses."""

import logging
import re
import time
from typing import Optional

from core.weather.models import WeatherData, WeatherLocation
from core.weather.parsers.base import BaseWeatherParser

logger = logging.getLogger("jarvis.weather.parsers.wttr_text")


class WttrTextParser(BaseWeatherParser):
    """Parses pipe-delimited plain-text response: %t|%f|%h|%w|%p|%C."""

    def parse(self, raw_content: bytes, location: WeatherLocation, source_name: str = "wttr.in-text") -> Optional[WeatherData]:
        try:
            text = raw_content.decode("utf-8", errors="replace").strip()
            parts = text.split("|")
            if len(parts) < 3:
                return None

            # 1. Temp (%t: e.g. "+31°C", "31°C")
            temp_match = re.search(r"([+-]?\d+(?:\.\d+)?)", parts[0])
            temp_c = float(temp_match.group(1)) if temp_match else 0.0
            temp_f = round(temp_c * 9 / 5 + 32, 1)

            # 2. Feels like (%f: e.g. "+34°C")
            feels_match = re.search(r"([+-]?\d+(?:\.\d+)?)", parts[1]) if len(parts) > 1 else None
            feels_c = float(feels_match.group(1)) if feels_match else temp_c
            feels_f = round(feels_c * 9 / 5 + 32, 1)

            # 3. Humidity (%h: e.g. "65%")
            hum_match = re.search(r"(\d+)", parts[2]) if len(parts) > 2 else None
            humidity = int(hum_match.group(1)) if hum_match else None

            # 4. Wind (%w: e.g. "12km/h" or "↖12km/h")
            wind_kmh = None
            if len(parts) > 3:
                wind_match = re.search(r"(\d+(?:\.\d+)?)", parts[3])
                if wind_match:
                    wind_kmh = float(wind_match.group(1))

            # 5. Precip (%p: e.g. "0.0mm")
            precip_mm = None
            if len(parts) > 4:
                precip_match = re.search(r"(\d+(?:\.\d+)?)", parts[4])
                if precip_match:
                    precip_mm = float(precip_match.group(1))

            # 6. Condition (%C: e.g. "Partly cloudy")
            cond = parts[5].strip() if len(parts) > 5 else "Clear"

            return WeatherData(
                location=location,
                retrieved_at=time.time(),
                temperature_c=temp_c,
                temperature_f=temp_f,
                feels_like_c=feels_c,
                feels_like_f=feels_f,
                condition=cond,
                humidity=humidity,
                wind_speed_kmh=wind_kmh,
                precipitation_mm=precip_mm,
                daily_forecasts=[],
                alerts=[],
                source_name=source_name,
                confidence_score=0.85
            )
        except Exception as e:
            logger.error("Error parsing plain text weather data: %s", e)
            return None
