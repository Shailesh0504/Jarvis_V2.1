# core/weather/models.py
"""Canonical data models, enums, and structured payloads for Jarvis Weather Engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class WeatherIntent(str, Enum):
    CURRENT_WEATHER = "CURRENT_WEATHER"
    WEATHER_FORECAST = "WEATHER_FORECAST"
    RAIN_FORECAST = "RAIN_FORECAST"
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    WIND = "WIND"
    FEELS_LIKE = "FEELS_LIKE"
    WEATHER_ALERT = "WEATHER_ALERT"
    WEATHER_COMPARISON = "WEATHER_COMPARISON"
    LOCATION_WEATHER = "LOCATION_WEATHER"
    HOURLY_FORECAST = "HOURLY_FORECAST"
    DAILY_FORECAST = "DAILY_FORECAST"


class WeatherForecastPeriod(str, Enum):
    CURRENT = "CURRENT"
    HOURLY = "HOURLY"
    TODAY = "TODAY"
    TONIGHT = "TONIGHT"
    TOMORROW = "TOMORROW"
    DAY_AFTER_TOMORROW = "DAY_AFTER_TOMORROW"
    THIS_WEEKEND = "THIS_WEEKEND"
    NEXT_WEEK = "NEXT_WEEK"
    MULTI_DAY = "MULTI_DAY"


class TemperatureUnit(str, Enum):
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"


@dataclass
class WeatherLocation:
    name: str
    country: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_default: bool = False
    resolution_source: str = "explicit"  # "explicit", "conversation_context", "default_config"


@dataclass
class HourlyForecast:
    time_str: str
    hour: int
    temperature_c: float
    condition: str
    rain_probability: Optional[int] = None
    humidity: Optional[int] = None
    wind_speed_kmh: Optional[float] = None


@dataclass
class DailyForecast:
    date_str: str  # YYYY-MM-DD
    day_name: str  # e.g. "Monday"
    max_temp_c: float
    min_temp_c: float
    condition: str
    condition_hi: Optional[str] = None
    rain_probability: Optional[int] = None
    precipitation_mm: Optional[float] = None
    hourly: List[HourlyForecast] = field(default_factory=list)


@dataclass
class WeatherData:
    location: WeatherLocation
    observed_at: Optional[str] = None
    retrieved_at: float = 0.0
    temperature_c: float = 0.0
    temperature_f: float = 0.0
    feels_like_c: Optional[float] = None
    feels_like_f: Optional[float] = None
    condition: str = "Unknown"
    condition_hi: Optional[str] = None
    humidity: Optional[int] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction: Optional[str] = None
    precipitation_mm: Optional[float] = None
    precipitation_probability: Optional[int] = None
    visibility_km: Optional[float] = None
    pressure_mb: Optional[float] = None
    uv_index: Optional[float] = None
    daily_forecasts: List[DailyForecast] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    source_name: str = ""
    confidence_score: float = 1.0


@dataclass
class WeatherQuery:
    raw_query: str
    intent: WeatherIntent = WeatherIntent.CURRENT_WEATHER
    location: Optional[str] = None
    target_period: WeatherForecastPeriod = WeatherForecastPeriod.CURRENT
    target_date: Optional[str] = None  # YYYY-MM-DD
    target_days_count: int = 1
    unit: TemperatureUnit = TemperatureUnit.CELSIUS
    language: str = "hi"
    is_umbrella_query: bool = False


@dataclass
class WeatherEngineResult:
    success: bool
    query: WeatherQuery
    data: Optional[WeatherData] = None
    formatted_response: str = ""
    source_name: Optional[str] = None
    from_cache: bool = False
    is_offline: bool = False
    needs_clarification: bool = False
    clarification_prompt: Optional[str] = None
    error: Optional[str] = None
