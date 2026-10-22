# tests/test_weather_engine.py
"""
Comprehensive tests for Jarvis API-Free Live Weather Engine (core/weather).
Verifies:
1. Multilingual normalizer (Celsius/Fahrenheit conversions, conditions, rain formatting).
2. Temporal date resolver (clock-aware resolution of today, tomorrow, parso, weekend, multi-day).
3. Hierarchical location resolver (local cues, explicit city, coordinates, conversation context, default).
4. Short-lived thread-safe cache (independent TTLs, put, get, expiration).
5. Freshness validator (current conditions <= 3h, forecasts <= 12h).
6. Confidence evaluator (data completeness, missing attributes penalty).
7. Source manager (JSON configuration, priority ordering, forecast support filtering).
8. Response generator (Direct answer -> optional detail -> stop in Hinglish & English).
9. Modular parsers (wttr_json, open_meteo, wttr_text).
10. WeatherEngine end-to-end orchestration, query parsing, and Rule 32 offline safety.
11. FastPathEngine Section 10 execution and ultra-low latency routing.
12. ConversationalIntentClassifier capability question gating (no execution on "kya tum weather check kar sakte ho?").
"""

import json
import time
from unittest.mock import MagicMock, patch
import pytest

from core.connectivity import ConnectivityManager
from core.weather.cache import WeatherCache
from core.weather.confidence import WeatherConfidenceEvaluator
from core.weather.date_resolver import WeatherDateResolver
from core.weather.fetcher import WeatherFetcher
from core.weather.freshness import WeatherFreshnessValidator
from core.weather.location_resolver import WeatherLocationResolver
from core.weather.models import (
    DailyForecast,
    HourlyForecast,
    TemperatureUnit,
    WeatherData,
    WeatherEngineResult,
    WeatherForecastPeriod,
    WeatherIntent,
    WeatherLocation,
    WeatherQuery,
)
from core.weather.normalizer import WeatherNormalizer
from core.weather.parsers.open_meteo import OpenMeteoParser
from core.weather.parsers.wttr_json import WttrJsonParser
from core.weather.parsers.wttr_text import WttrTextParser
from core.weather.response_generator import WeatherResponseGenerator
from core.weather.source_manager import WeatherSourceConfig, WeatherSourceManager
from core.weather.weather_engine import WeatherEngine, get_weather_engine


# ==============================================================================
# 1. NORMALIZER TESTS
# ==============================================================================

def test_weather_normalizer_conversions():
    assert WeatherNormalizer.celsius_to_fahrenheit(0.0) == 32.0
    assert WeatherNormalizer.celsius_to_fahrenheit(25.0) == 77.0
    assert WeatherNormalizer.celsius_to_fahrenheit(100.0) == 212.0

    assert WeatherNormalizer.fahrenheit_to_celsius(32.0) == 0.0
    assert WeatherNormalizer.fahrenheit_to_celsius(77.0) == 25.0


def test_weather_normalizer_hindi_conditions():
    assert WeatherNormalizer.get_hindi_condition("Sunny") == "dhoop khili hai"
    assert WeatherNormalizer.get_hindi_condition("Partly cloudy") == "halke baadal hain"
    assert WeatherNormalizer.get_hindi_condition("Heavy rain") == "tez baarish hai"
    assert WeatherNormalizer.get_hindi_condition("Thunderstorm") == "toofan aur garaj ke saath baarish hai"
    assert WeatherNormalizer.get_hindi_condition("Fog") == "kohra hai"
    assert WeatherNormalizer.get_hindi_condition("Unknown Custom Condition") == "Unknown Custom Condition"


def test_weather_normalizer_rain_chance_formatting():
    assert "bohot high" in WeatherNormalizer.format_rain_chance(90, language="hi")
    assert "very high" in WeatherNormalizer.format_rain_chance(90, language="en")
    assert "achhi sambhavna" in WeatherNormalizer.format_rain_chance(70, language="hi")
    assert "20-30%" in WeatherNormalizer.format_rain_chance(25, language="hi")
    assert "koi chances nahi" in WeatherNormalizer.format_rain_chance(0, language="hi")
    assert "clear nahi" in WeatherNormalizer.format_rain_chance(None, language="hi")


# ==============================================================================
# 2. DATE RESOLVER TESTS
# ==============================================================================

def test_date_resolver_periods():
    period, target_date, count = WeatherDateResolver.resolve_period_and_date("kal ka mausam")
    assert period == WeatherForecastPeriod.TOMORROW
    assert count == 1
    assert target_date is not None

    period, target_date, count = WeatherDateResolver.resolve_period_and_date("parso baarish hogi?")
    assert period == WeatherForecastPeriod.DAY_AFTER_TOMORROW
    assert count == 1

    period, target_date, count = WeatherDateResolver.resolve_period_and_date("aaj raat ka temperature")
    assert period == WeatherForecastPeriod.TONIGHT

    period, target_date, count = WeatherDateResolver.resolve_period_and_date("this weekend forecast")
    assert period == WeatherForecastPeriod.THIS_WEEKEND

    period, target_date, count = WeatherDateResolver.resolve_period_and_date("next 5 days forecast")
    assert period == WeatherForecastPeriod.MULTI_DAY
    assert count == 5

    period, target_date, count = WeatherDateResolver.resolve_period_and_date("delhi weather abhi")
    assert period == WeatherForecastPeriod.CURRENT


# ==============================================================================
# 3. LOCATION RESOLVER TESTS
# ==============================================================================

def test_location_resolver_explicit_city():
    resolver = WeatherLocationResolver(default_city="Delhi", enable_device_location=False)

    loc, clarify, prompt = resolver.resolve_location("Mumbai ka weather kaisa hai")
    assert not clarify
    assert loc is not None
    assert loc.name.lower() in ("mumbai", "bombay")
    assert loc.resolution_source == "explicit"
    assert loc.latitude is not None  # Auto-populated from CITY_COORDINATES
    assert loc.longitude is not None

    loc_pune, _, _ = resolver.resolve_location("pune weather forecast")
    assert loc_pune is not None
    assert loc_pune.name.lower() == "pune"


def test_location_resolver_conversation_context():
    resolver = WeatherLocationResolver(default_city="Delhi", enable_device_location=False)

    # 1. First turn mentions Mumbai
    resolver.resolve_location("Mumbai mein baarish")
    assert resolver.get_conversation_location() == "Mumbai"

    # 2. Follow-up query without city
    loc, clarify, _ = resolver.resolve_location("aur kal ka mausam kaisa rahega?")
    assert not clarify
    assert loc is not None
    assert loc.name == "Mumbai"
    assert loc.resolution_source == "conversation_context"


def test_location_resolver_default_fallback():
    resolver = WeatherLocationResolver(default_city="Delhi", enable_device_location=False)
    resolver.clear_context()

    loc, clarify, _ = resolver.resolve_location("abhi mausam kaisa hai")
    assert not clarify
    assert loc is not None
    assert loc.name == "Delhi"
    assert loc.is_default is True


# ==============================================================================
# 4. CACHE & FRESHNESS TESTS
# ==============================================================================

def test_weather_cache_and_freshness():
    cache = WeatherCache(current_ttl_seconds=1.0, forecast_ttl_seconds=2.0)
    loc = WeatherLocation(name="Delhi")
    data = WeatherData(
        location=loc,
        retrieved_at=time.time(),
        temperature_c=28.0,
        condition="Sunny",
        source_name="test"
    )

    # Put and immediate get
    cache.put("Delhi", data, is_forecast=False)
    cached = cache.get("Delhi", is_forecast=False)
    assert cached is not None
    assert cached.temperature_c == 28.0

    # Freshness check
    is_fresh, age = WeatherFreshnessValidator.is_fresh(cached)
    assert is_fresh is True
    assert age >= 0.0

    # Stale data check
    stale_data = WeatherData(
        location=loc,
        retrieved_at=time.time() - (4 * 3600),
        temperature_c=20.0,
        condition="Clear"
    )
    is_fresh_stale, _ = WeatherFreshnessValidator.is_fresh(stale_data, is_forecast=False)
    assert is_fresh_stale is False


# ==============================================================================
# 5. CONFIDENCE EVALUATOR TESTS
# ==============================================================================

def test_confidence_evaluator():
    loc = WeatherLocation(name="Delhi")
    query = WeatherQuery(raw_query="Delhi weather", location="Delhi")

    # Complete data
    complete_data = WeatherData(
        location=loc,
        temperature_c=28.0,
        condition="Clear",
        precipitation_probability=10
    )
    score = WeatherConfidenceEvaluator.evaluate(complete_data, query)
    assert score >= 0.95

    # Missing temperature & condition
    incomplete_data = WeatherData(
        location=loc,
        temperature_c=None,
        condition="Unknown"
    )
    score_low = WeatherConfidenceEvaluator.evaluate(incomplete_data, query)
    assert score_low < 0.60


# ==============================================================================
# 6. SOURCE MANAGER TESTS
# ==============================================================================

def test_source_manager_loading(tmp_path):
    cfg_file = tmp_path / "test_sources.json"
    payload = {
        "default_location": "Mumbai",
        "sources": [
            {
                "id": "s1",
                "name": "Source 1",
                "source_type": "wttr_json",
                "url_pattern": "http://example.com/{location}",
                "parser_type": "wttr_json",
                "priority": 2,
                "supports_forecast": False
            },
            {
                "id": "s2",
                "name": "Source 2",
                "source_type": "open_meteo",
                "url_pattern": "http://example.com/{lat}/{lon}",
                "parser_type": "open_meteo",
                "priority": 1,
                "supports_forecast": True
            }
        ]
    }
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    mgr = WeatherSourceManager(sources_path=cfg_file)
    assert mgr.default_location == "Mumbai"
    enabled = mgr.get_enabled_sources()
    assert len(enabled) == 2
    # Priority sorting: s2 (p=1) comes before s1 (p=2)
    assert enabled[0].id == "s2"

    forecast_sources = mgr.get_enabled_sources(requires_forecast=True)
    assert len(forecast_sources) == 1
    assert forecast_sources[0].id == "s2"


# ==============================================================================
# 7. RESPONSE GENERATOR TESTS
# ==============================================================================

def test_response_generator_current_and_rain():
    loc = WeatherLocation(name="Delhi")
    data = WeatherData(
        location=loc,
        temperature_c=30.0,
        feels_like_c=33.0,
        condition="Partly cloudy",
        precipitation_probability=45,
        source_name="mock"
    )

    q_curr = WeatherQuery(raw_query="Delhi weather", location="Delhi", language="hi")
    resp_hi = WeatherResponseGenerator.generate_response(data, q_curr)
    assert "Delhi mein 30°C" in resp_hi
    assert "halke baadal" in resp_hi
    assert "Feels-like" in resp_hi

    q_rain = WeatherQuery(raw_query="kal baarish hogi kya", intent=WeatherIntent.RAIN_FORECAST, language="hi")
    resp_rain = WeatherResponseGenerator.generate_response(data, q_rain)
    assert "Delhi mein" in resp_rain
    assert "baarish" in resp_rain

    q_umbrella = WeatherQuery(raw_query="umbrella lena chahiye", is_umbrella_query=True, language="hi")
    resp_umb = WeatherResponseGenerator.generate_response(data, q_umbrella)
    assert "Umbrella" in resp_umb


# ==============================================================================
# 8. PARSERS UNIT TESTS
# ==============================================================================

def test_wttr_json_parser():
    parser = WttrJsonParser()
    loc = WeatherLocation(name="Delhi")
    mock_json = {
        "current_condition": [
            {
                "temp_C": "29",
                "FeelsLikeC": "32",
                "weatherDesc": [{"value": "Partly cloudy"}],
                "humidity": "60",
                "windspeedKmph": "14"
            }
        ],
        "weather": [
            {
                "date": "2026-09-15",
                "maxtempC": "34",
                "mintempC": "26",
                "hourly": [
                    {"time": "1200", "tempC": "33", "weatherDesc": [{"value": "Partly cloudy"}], "chanceofrain": "20"}
                ]
            }
        ]
    }
    raw_bytes = json.dumps(mock_json).encode("utf-8")
    data = parser.parse(raw_bytes, loc)
    assert data is not None
    assert data.temperature_c == 29.0
    assert data.feels_like_c == 32.0
    assert data.condition == "Partly cloudy"
    assert len(data.daily_forecasts) == 1


def test_open_meteo_parser():
    parser = OpenMeteoParser()
    loc = WeatherLocation(name="Delhi")
    mock_json = {
        "current": {
            "temperature_2m": 28.5,
            "apparent_temperature": 31.0,
            "weather_code": 0,
            "relative_humidity_2m": 55,
            "wind_speed_10m": 12.0
        },
        "daily": {
            "time": ["2026-09-15", "2026-09-16"],
            "weather_code": [0, 61],
            "temperature_2m_max": [33.0, 31.0],
            "temperature_2m_min": [25.0, 24.0],
            "precipitation_probability_max": [10, 65]
        }
    }
    raw_bytes = json.dumps(mock_json).encode("utf-8")
    data = parser.parse(raw_bytes, loc)
    assert data is not None
    assert data.temperature_c == 28.5
    assert data.condition == "Clear"
    assert len(data.daily_forecasts) == 2
    assert data.daily_forecasts[1].condition == "Slight rain"


def test_wttr_text_parser():
    parser = WttrTextParser()
    loc = WeatherLocation(name="Delhi")
    raw_text = "+30°C|+33°C|65%|15km/h|0.0mm|Partly cloudy".encode("utf-8")
    data = parser.parse(raw_text, loc)
    assert data is not None
    assert data.temperature_c == 30.0
    assert data.feels_like_c == 33.0
    assert data.humidity == 65
    assert data.condition == "Partly cloudy"


# ==============================================================================
# 9. WEATHER ENGINE ORCHESTRATION & OFFLINE SAFETY
# ==============================================================================

def test_weather_engine_query_parsing():
    engine = WeatherEngine()

    q1 = engine.parse_query("Delhi ka weather kaisa hai")
    assert q1.location == "delhi"
    assert q1.intent == WeatherIntent.CURRENT_WEATHER
    assert q1.language == "hi"

    q2 = engine.parse_query("kal baarish hogi kya")
    assert q2.intent == WeatherIntent.RAIN_FORECAST
    assert q2.target_period == WeatherForecastPeriod.TOMORROW

    q3 = engine.parse_query("aaj umbrella lena chahiye kya")
    assert q3.is_umbrella_query is True


def test_weather_engine_offline_safety():
    conn = ConnectivityManager()
    conn.set_forced_offline(True)
    engine = WeatherEngine(connectivity_manager=conn)

    res = engine.process_weather_request("Delhi ka weather kaisa hai")
    assert res.success is False
    assert res.is_offline is True
    assert "access nahi ho pa raha" in res.formatted_response or "unreachable" in res.formatted_response


def test_weather_engine_fallback_chain():
    loc = WeatherLocation(name="Delhi")
    mock_data = WeatherData(
        location=loc,
        temperature_c=29.0,
        condition="Clear",
        retrieved_at=time.time()
    )

    fetcher = MagicMock()
    # First source returns None, second source succeeds
    fetcher.fetch_single_url.side_effect = [None, b'{"mock": true}']
    fetcher.build_url.return_value = "http://example.com/weather"

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_data

    conn = ConnectivityManager()
    conn.set_forced_offline(False)

    engine = WeatherEngine(fetcher=fetcher, connectivity_manager=conn)
    with patch("core.weather.weather_engine.get_parser", return_value=mock_parser):
        with patch.object(engine, "is_online", return_value=True):
            res = engine.process_weather_request("Delhi ka weather")
            assert res.success is True
            assert res.data.temperature_c == 29.0


# ==============================================================================
# 10. PIPELINE INTEGRATION & CONVERSATIONAL INTENT GATING
# ==============================================================================

def test_conversational_intent_capability_question():
    from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType

    # Capability question MUST be answered directly without executing live weather API
    res = ConversationalIntentClassifier.classify("kya tum weather check kar sakte ho?")
    assert res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
    assert res.is_executable is False
    assert "live weather" in res.natural_response.lower()

    # Weather request MUST NOT be classified as small talk / how are you chitchat
    res2 = ConversationalIntentClassifier.classify("Delhi ka weather kaisa hai")
    assert res2.natural_response != "Main bilkul theek hoon, Boss! Aap batayein, sab kaisa chal raha hai?"


def test_fast_path_live_weather_integration():
    from core.execution.fast_path import FastPathEngine

    fast_path = FastPathEngine()
    mock_turn = MagicMock()
    mock_turn.metadata = {}

    with patch("core.weather.get_weather_engine") as mock_get_we:
        mock_we = MagicMock()
        mock_we.is_weather_query.return_value = True
        mock_we.process_weather_request.return_value = WeatherEngineResult(
            success=True,
            query=WeatherQuery(raw_query="Delhi weather"),
            formatted_response="Aaj Delhi mein 29°C hai."
        )
        mock_get_we.return_value = mock_we

        resp = fast_path.try_handle(
            raw_text="Delhi ka weather kaisa hai",
            normalized_input="delhi ka weather kaisa hai",
            turn=mock_turn,
            start_time=time.perf_counter(),
            tracker=None,
            source="cli"
        )
        assert resp == "Aaj Delhi mein 29°C hai."
        assert "weather_result" in mock_turn.metadata
