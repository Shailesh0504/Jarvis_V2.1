# core/weather/parsers/open_meteo.py
"""Parser for Open-Meteo public web weather forecast responses."""

from datetime import datetime
import json
import logging
import time
from typing import List, Optional

from core.weather.models import (
    DailyForecast,
    WeatherData,
    WeatherLocation,
)
from core.weather.parsers.base import BaseWeatherParser

logger = logging.getLogger("jarvis.weather.parsers.open_meteo")

WMO_CODE_MAP = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}


class OpenMeteoParser(BaseWeatherParser):
    """Parses Open-Meteo public web response into canonical WeatherData."""

    def parse(self, raw_content: bytes, location: WeatherLocation, source_name: str = "Open-Meteo") -> Optional[WeatherData]:
        try:
            text = raw_content.decode("utf-8", errors="replace")
            data = json.loads(text)
            if not data or not isinstance(data, dict):
                return None

            curr = data.get("current", {})
            temp_c = float(curr.get("temperature_2m", 0.0))
            temp_f = round(temp_c * 9 / 5 + 32, 1)
            feels_c = float(curr.get("apparent_temperature", temp_c))
            feels_f = round(feels_c * 9 / 5 + 32, 1)

            wmo_code = curr.get("weather_code", 0)
            condition_desc = WMO_CODE_MAP.get(wmo_code, "Partly cloudy")

            humidity = int(curr.get("relative_humidity_2m", 0)) if "relative_humidity_2m" in curr else None
            wind_kmh = float(curr.get("wind_speed_10m", 0.0)) if "wind_speed_10m" in curr else None
            precip_mm = float(curr.get("precipitation", 0.0)) if "precipitation" in curr else None

            # Daily forecasts
            daily = data.get("daily", {})
            daily_forecasts: List[DailyForecast] = []
            dates = daily.get("time", [])
            codes = daily.get("weather_code", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            precip_probs = daily.get("precipitation_probability_max", [])

            for i in range(len(dates)):
                d_str = dates[i]
                d_code = codes[i] if i < len(codes) else 0
                d_cond = WMO_CODE_MAP.get(d_code, "Partly cloudy")
                d_max = float(max_temps[i]) if i < len(max_temps) else temp_c
                d_min = float(min_temps[i]) if i < len(min_temps) else temp_c
                d_prob = int(precip_probs[i]) if i < len(precip_probs) and precip_probs[i] is not None else 0

                try:
                    day_obj = datetime.strptime(d_str, "%Y-%m-%d")
                    day_name = day_obj.strftime("%A")
                except Exception:
                    day_name = "Unknown"

                daily_forecasts.append(DailyForecast(
                    date_str=d_str,
                    day_name=day_name,
                    max_temp_c=d_max,
                    min_temp_c=d_min,
                    condition=d_cond,
                    rain_probability=d_prob,
                    precipitation_mm=None,
                    hourly=[]
                ))

            curr_prob = daily_forecasts[0].rain_probability if daily_forecasts else None

            return WeatherData(
                location=location,
                observed_at=curr.get("time"),
                retrieved_at=time.time(),
                temperature_c=temp_c,
                temperature_f=temp_f,
                feels_like_c=feels_c,
                feels_like_f=feels_f,
                condition=condition_desc,
                humidity=humidity,
                wind_speed_kmh=wind_kmh,
                precipitation_mm=precip_mm,
                precipitation_probability=curr_prob,
                daily_forecasts=daily_forecasts,
                alerts=[],
                source_name=source_name,
                confidence_score=0.95
            )
        except Exception as e:
            logger.error("Error parsing Open-Meteo response: %s", e)
            return None
