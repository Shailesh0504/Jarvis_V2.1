# core/weather/response_generator.py
"""Conversational response generator adhering to DIRECT ANSWER -> useful detail -> STOP."""

import logging
import re
from typing import Optional

from core.weather.models import (
    DailyForecast,
    TemperatureUnit,
    WeatherData,
    WeatherForecastPeriod,
    WeatherIntent,
    WeatherQuery,
)
from core.weather.normalizer import WeatherNormalizer

logger = logging.getLogger("jarvis.weather.response_generator")


class WeatherResponseGenerator:
    """Generates concise, human-like, spoken weather responses in Hinglish and English."""

    @classmethod
    def generate_response(cls, data: WeatherData, query: WeatherQuery) -> str:
        """Constructs target natural response based on intent, date period, and units."""
        lang = query.language or "hi"
        loc_name = data.location.name
        unit = query.unit

        # 1. Umbrella Query ("aaj umbrella lena chahiye?")
        if query.is_umbrella_query:
            return cls._format_umbrella_response(data, query, loc_name, lang)

        # 2. Rain Forecast ("kal baarish hogi?", "aaj baarish hogi?")
        if query.intent == WeatherIntent.RAIN_FORECAST:
            return cls._format_rain_response(data, query, loc_name, lang)

        # 3. Specific attribute queries (Temperature, Humidity, Wind, Feels-like)
        if query.intent == WeatherIntent.TEMPERATURE:
            return cls._format_temperature_response(data, query, loc_name, unit, lang)

        if query.intent == WeatherIntent.HUMIDITY:
            return cls._format_humidity_response(data, loc_name, lang)

        if query.intent == WeatherIntent.WIND:
            return cls._format_wind_response(data, loc_name, lang)

        if query.intent == WeatherIntent.FEELS_LIKE:
            return cls._format_feels_like_response(data, loc_name, unit, lang)

        # 4. Multi-day or Weekend Forecast
        if query.target_period in (WeatherForecastPeriod.MULTI_DAY, WeatherForecastPeriod.THIS_WEEKEND):
            return cls._format_multi_day_response(data, query, loc_name, unit, lang)

        # 5. Tomorrow / Day after tomorrow Forecast
        if query.target_period in (WeatherForecastPeriod.TOMORROW, WeatherForecastPeriod.DAY_AFTER_TOMORROW):
            return cls._format_future_day_response(data, query, loc_name, unit, lang)

        # 6. Default Current Weather / Today's Weather
        return cls._format_current_weather_response(data, loc_name, unit, lang)

    @classmethod
    def _format_temp_val(cls, temp_c: float, unit: TemperatureUnit) -> str:
        if unit == TemperatureUnit.FAHRENHEIT:
            f = WeatherNormalizer.celsius_to_fahrenheit(temp_c)
            return f"{round(f)}°F"
        return f"{round(temp_c)}°C"

    @classmethod
    def _format_current_weather_response(
        cls, data: WeatherData, loc_name: str, unit: TemperatureUnit, lang: str
    ) -> str:
        temp_str = cls._format_temp_val(data.temperature_c, unit)
        cond_hi = WeatherNormalizer.get_hindi_condition(data.condition)

        if lang == "en":
            resp = f"In {loc_name}, it's currently {temp_str} with {data.condition.lower()} skies."
            if data.feels_like_c and abs(data.feels_like_c - data.temperature_c) >= 2:
                resp += f" Feels like {cls._format_temp_val(data.feels_like_c, unit)}."
        else:
            resp = f"Aaj {loc_name} mein {temp_str} hai aur {cond_hi}."
            if data.feels_like_c and abs(data.feels_like_c - data.temperature_c) >= 2:
                resp += f" Feels-like temperature {cls._format_temp_val(data.feels_like_c, unit)} hai."

        if data.alerts:
            alert_text = data.alerts[0]
            resp += f" Note: {alert_text}."
        return resp

    @classmethod
    def _format_rain_response(
        cls, data: WeatherData, query: WeatherQuery, loc_name: str, lang: str
    ) -> str:
        target_forecast = cls._find_forecast_for_period(data, query.target_period)
        rain_prob = target_forecast.rain_probability if target_forecast else data.precipitation_probability
        period_name = cls._get_period_name(query.target_period, lang)

        if rain_prob is None:
            rain_prob = 0

        chance_str = WeatherNormalizer.format_rain_chance(rain_prob, language=lang)
        if lang == "en":
            return f"{period_name.capitalize()} in {loc_name}, {chance_str}."
        else:
            return f"{period_name.capitalize()} {loc_name} mein {chance_str}."

    @classmethod
    def _format_umbrella_response(
        cls, data: WeatherData, query: WeatherQuery, loc_name: str, lang: str
    ) -> str:
        target_forecast = cls._find_forecast_for_period(data, query.target_period)
        rain_prob = target_forecast.rain_probability if target_forecast else (data.precipitation_probability or 0)
        period_name = cls._get_period_name(query.target_period, lang)

        if rain_prob >= 50:
            if lang == "en":
                return f"Yes, there's a {rain_prob}% chance of rain {period_name} in {loc_name}. Carrying an umbrella is recommended."
            return f"Haan, {period_name} {loc_name} mein {rain_prob}% baarish ke chances hain, umbrella saath rakhna theek rahega."
        else:
            if lang == "en":
                return f"No need, rain probability {period_name} in {loc_name} is only {rain_prob}%."
            return f"Umbrella ki zaroorat nahi lagti, {period_name} {loc_name} mein baarish ke chances sirf {rain_prob}% hain."

    @classmethod
    def _format_temperature_response(
        cls, data: WeatherData, query: WeatherQuery, loc_name: str, unit: TemperatureUnit, lang: str
    ) -> str:
        temp_str = cls._format_temp_val(data.temperature_c, unit)
        if unit == TemperatureUnit.FAHRENHEIT:
            dual_str = f"{round(data.temperature_f)}°F ({round(data.temperature_c)}°C)"
        else:
            dual_str = temp_str

        raw_low = (getattr(query, "raw_query", "") or "").lower()
        is_hot_comfort = bool(re.search(r"\b(?:bahut\s+garmi|bohot\s+garmi|garmi\s+lag\s+rahi|it'?s\s+(?:so\s+)?hot)\b", raw_low))
        is_cold_comfort = bool(re.search(r"\b(?:bahut\s+thand|bohot\s+thand|thand\s+lag\s+rahi|it'?s\s+(?:so\s+)?cold)\b", raw_low))

        if is_hot_comfort:
            if lang == "en":
                return f"Yes, it really feels hot! The temperature in {loc_name} is {dual_str}. Would you like me to remind you for AC or cold water?"
            return f"Haan, kaafi garmi lag rahi hai! {loc_name} mein temperature abhi {dual_str} hai. Kya main fan ya AC ke liye remind karun?"
        elif is_cold_comfort:
            if lang == "en":
                return f"Yes, it feels quite cold! The temperature in {loc_name} is {dual_str}. Should I turn on the heater or prepare a warm reminder?"
            return f"Haan, sach mein thand lag rahi hai! {loc_name} mein temperature abhi {dual_str} hai. Kya main heater ke liye remind karun?"

        if lang == "en":
            return f"The temperature in {loc_name} is {dual_str}."
        return f"Abhi {loc_name} mein temperature {dual_str} hai."

    @classmethod
    def _format_humidity_response(cls, data: WeatherData, loc_name: str, lang: str) -> str:
        hum = data.humidity if data.humidity is not None else 65
        if lang == "en":
            return f"Current humidity in {loc_name} is {hum}%."
        return f"Abhi {loc_name} mein humidity {hum}% hai."

    @classmethod
    def _format_wind_response(cls, data: WeatherData, loc_name: str, lang: str) -> str:
        wind = data.wind_speed_kmh if data.wind_speed_kmh is not None else 12.0
        if lang == "en":
            return f"Wind speed in {loc_name} is around {round(wind)} km/h."
        return f"Abhi {loc_name} mein wind speed lagbhag {round(wind)} km/h hai."

    @classmethod
    def _format_feels_like_response(
        cls, data: WeatherData, loc_name: str, unit: TemperatureUnit, lang: str
    ) -> str:
        feels_val = data.feels_like_c if data.feels_like_c is not None else data.temperature_c
        feels_str = cls._format_temp_val(feels_val, unit)
        curr_str = cls._format_temp_val(data.temperature_c, unit)

        if lang == "en":
            return f"In {loc_name}, it feels like {feels_str} (actual {curr_str})."
        return f"Abhi {loc_name} mein temperature {curr_str} hai aur feels-like {feels_str} hai."

    @classmethod
    def _format_future_day_response(
        cls, data: WeatherData, query: WeatherQuery, loc_name: str, unit: TemperatureUnit, lang: str
    ) -> str:
        day_fc = cls._find_forecast_for_period(data, query.target_period)
        period_name = cls._get_period_name(query.target_period, lang)

        if not day_fc:
            return cls._format_current_weather_response(data, loc_name, unit, lang)

        max_t = cls._format_temp_val(day_fc.max_temp_c, unit)
        min_t = cls._format_temp_val(day_fc.min_temp_c, unit)
        cond_hi = WeatherNormalizer.get_hindi_condition(day_fc.condition)

        if lang == "en":
            resp = f"{period_name.capitalize()} in {loc_name}, temperature will be around {max_t} (low {min_t}) with {day_fc.condition.lower()} skies."
            if day_fc.rain_probability and day_fc.rain_probability > 0:
                resp += f" Chance of rain is {day_fc.rain_probability}%."
        else:
            resp = f"{period_name.capitalize()} {loc_name} mein temperature lagbhag {max_t} rahega (min {min_t}) aur {cond_hi}."
            if day_fc.rain_probability and day_fc.rain_probability > 0:
                resp += f" Baarish ki possibility {day_fc.rain_probability}% hai."
        return resp

    @classmethod
    def _format_multi_day_response(
        cls, data: WeatherData, query: WeatherQuery, loc_name: str, unit: TemperatureUnit, lang: str
    ) -> str:
        if not data.daily_forecasts:
            return cls._format_current_weather_response(data, loc_name, unit, lang)

        count = min(query.target_days_count, len(data.daily_forecasts))
        parts = []
        for i in range(count):
            df = data.daily_forecasts[i]
            max_t = cls._format_temp_val(df.max_temp_c, unit)
            cond = WeatherNormalizer.get_hindi_condition(df.condition) if lang == "hi" else df.condition
            parts.append(f"{df.day_name}: {max_t} ({cond})")

        joined = ", ".join(parts)
        if lang == "en":
            return f"Weather forecast for {loc_name}: {joined}."
        return f"{loc_name} ka forecast: {joined}."

    @classmethod
    def _find_forecast_for_period(
        cls, data: WeatherData, period: WeatherForecastPeriod
    ) -> Optional[DailyForecast]:
        if not data.daily_forecasts:
            return None
        if period in (WeatherForecastPeriod.CURRENT, WeatherForecastPeriod.TODAY):
            return data.daily_forecasts[0]
        if period == WeatherForecastPeriod.TOMORROW:
            return data.daily_forecasts[1] if len(data.daily_forecasts) > 1 else data.daily_forecasts[0]
        if period == WeatherForecastPeriod.DAY_AFTER_TOMORROW:
            return data.daily_forecasts[2] if len(data.daily_forecasts) > 2 else data.daily_forecasts[-1]
        return data.daily_forecasts[0]

    @classmethod
    def _get_period_name(cls, period: WeatherForecastPeriod, lang: str) -> str:
        if period == WeatherForecastPeriod.TOMORROW:
            return "kal" if lang == "hi" else "tomorrow"
        if period == WeatherForecastPeriod.DAY_AFTER_TOMORROW:
            return "parso" if lang == "hi" else "day after tomorrow"
        if period == WeatherForecastPeriod.THIS_WEEKEND:
            return "is weekend" if lang == "hi" else "this weekend"
        return "aaj" if lang == "hi" else "today"
