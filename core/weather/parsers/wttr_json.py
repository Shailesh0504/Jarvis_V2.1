# core/weather/parsers/wttr_json.py
"""Parser for wttr.in public web JSON format (format=j1)."""

import json
import logging
import time
from typing import List, Optional

from core.weather.models import (
    DailyForecast,
    HourlyForecast,
    WeatherData,
    WeatherLocation,
)
from core.weather.parsers.base import BaseWeatherParser

logger = logging.getLogger("jarvis.weather.parsers.wttr_json")


class WttrJsonParser(BaseWeatherParser):
    """Parses JSON output from wttr.in/{city}?format=j1 into canonical WeatherData."""

    def parse(self, raw_content: bytes, location: WeatherLocation, source_name: str = "wttr.in") -> Optional[WeatherData]:
        try:
            text = raw_content.decode("utf-8", errors="replace")
            data = json.loads(text)
            if not data or not isinstance(data, dict):
                return None

            current_list = data.get("current_condition", [])
            if not current_list:
                return None

            curr = current_list[0]
            temp_c = float(curr.get("temp_C", 0.0))
            temp_f = float(curr.get("temp_F", round(temp_c * 9 / 5 + 32, 1)))
            feels_c = float(curr.get("FeelsLikeC", temp_c))
            feels_f = float(curr.get("FeelsLikeF", round(feels_c * 9 / 5 + 32, 1)))

            # Weather condition description
            desc_list = curr.get("weatherDesc", [])
            condition_desc = desc_list[0].get("value", "Clear").strip() if desc_list else "Clear"

            # Humidity & Wind
            humidity = int(curr.get("humidity", 0)) if curr.get("humidity") else None
            wind_kmh = float(curr.get("windspeedKmph", 0.0)) if curr.get("windspeedKmph") else None
            wind_dir = curr.get("winddir16Point")

            # Precipitation & Visibility & Pressure
            precip_mm = float(curr.get("precipMM", 0.0)) if curr.get("precipMM") else None
            visibility = float(curr.get("visibility", 0.0)) if curr.get("visibility") else None
            pressure = float(curr.get("pressure", 0.0)) if curr.get("pressure") else None
            uv = float(curr.get("uvIndex", 0.0)) if curr.get("uvIndex") else None
            obs_time = curr.get("observation_time")

            # Parse daily forecasts (today, tomorrow, day after tomorrow)
            daily_forecasts: List[DailyForecast] = []
            weather_days = data.get("weather", [])
            current_precip_prob = None

            for i, day in enumerate(weather_days):
                date_str = day.get("date", "")
                max_c = float(day.get("maxtempC", temp_c))
                min_c = float(day.get("mintempC", temp_c))

                # Extract hourly slots
                hourly_list: List[HourlyForecast] = []
                day_rain_probs: List[int] = []

                for hr in day.get("hourly", []):
                    hr_time = hr.get("time", "0")
                    hour_num = int(hr_time) // 100
                    time_fmt = f"{hour_num:02d}:00"
                    hr_temp = float(hr.get("tempC", 0.0))
                    hr_desc_list = hr.get("weatherDesc", [])
                    hr_cond = hr_desc_list[0].get("value", "").strip() if hr_desc_list else "Clear"
                    hr_rain = int(hr.get("chanceofrain", 0)) if hr.get("chanceofrain") else 0
                    day_rain_probs.append(hr_rain)

                    hourly_list.append(HourlyForecast(
                        time_str=time_fmt,
                        hour=hour_num,
                        temperature_c=hr_temp,
                        condition=hr_cond,
                        rain_probability=hr_rain,
                        humidity=int(hr.get("humidity", 0)) if hr.get("humidity") else None,
                        wind_speed_kmh=float(hr.get("windspeedKmph", 0.0)) if hr.get("windspeedKmph") else None
                    ))

                # Overall day rain probability is max of hourly rain chances
                day_rain_prob = max(day_rain_probs) if day_rain_probs else 0
                if i == 0:
                    current_precip_prob = day_rain_prob

                # Condition for the day (midday or first hourly condition)
                day_cond = hourly_list[4].condition if len(hourly_list) > 4 else condition_desc

                from datetime import datetime
                try:
                    day_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    day_name = day_obj.strftime("%A")
                except Exception:
                    day_name = "Unknown"

                daily_forecasts.append(DailyForecast(
                    date_str=date_str,
                    day_name=day_name,
                    max_temp_c=max_c,
                    min_temp_c=min_c,
                    condition=day_cond,
                    rain_probability=day_rain_prob,
                    precipitation_mm=None,
                    hourly=hourly_list
                ))

            # Extract location info if present
            nearest = data.get("nearest_area", [])
            resolved_loc_name = location.name
            country = location.country
            if nearest and isinstance(nearest, list):
                area_obj = nearest[0]
                area_names = area_obj.get("areaName", [])
                country_names = area_obj.get("country", [])
                if area_names and isinstance(area_names, list):
                    resolved_loc_name = area_names[0].get("value", location.name)
                if country_names and isinstance(country_names, list):
                    country = country_names[0].get("value", location.country)

            loc = WeatherLocation(
                name=resolved_loc_name,
                country=country,
                state=location.state,
                latitude=location.latitude,
                longitude=location.longitude,
                is_default=location.is_default,
                resolution_source=location.resolution_source
            )

            return WeatherData(
                location=loc,
                observed_at=obs_time,
                retrieved_at=time.time(),
                temperature_c=temp_c,
                temperature_f=temp_f,
                feels_like_c=feels_c,
                feels_like_f=feels_f,
                condition=condition_desc,
                humidity=humidity,
                wind_speed_kmh=wind_kmh,
                wind_direction=wind_dir,
                precipitation_mm=precip_mm,
                precipitation_probability=current_precip_prob,
                visibility_km=visibility,
                pressure_mb=pressure,
                uv_index=uv,
                daily_forecasts=daily_forecasts,
                alerts=[],
                source_name=source_name,
                confidence_score=1.0
            )
        except Exception as e:
            logger.error("Error parsing wttr.in JSON data: %s", e)
            return None
