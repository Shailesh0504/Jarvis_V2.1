# core/weather/weather_engine.py
"""Authoritative orchestrator for the Jarvis API-Free Live Weather Engine."""

import logging
import re
from typing import Optional

from core.connectivity import ConnectivityManager
from core.weather.cache import WeatherCache
from core.weather.confidence import WeatherConfidenceEvaluator
from core.weather.date_resolver import WeatherDateResolver
from core.weather.fetcher import WeatherFetcher
from core.weather.freshness import WeatherFreshnessValidator
from core.weather.location_resolver import WeatherLocationResolver
from core.weather.models import (
    TemperatureUnit,
    WeatherData,
    WeatherEngineResult,
    WeatherForecastPeriod,
    WeatherIntent,
    WeatherLocation,
    WeatherQuery,
)
from core.weather.parsers import get_parser
from core.weather.response_generator import WeatherResponseGenerator
from core.weather.source_manager import WeatherSourceManager

logger = logging.getLogger("jarvis.weather.engine")


class WeatherEngine:
    """Orchestrates API-free weather retrieval, fallback chain, caching, and response generation."""

    def __init__(
        self,
        source_manager: Optional[WeatherSourceManager] = None,
        location_resolver: Optional[WeatherLocationResolver] = None,
        fetcher: Optional[WeatherFetcher] = None,
        cache: Optional[WeatherCache] = None,
        connectivity_manager: Optional[ConnectivityManager] = None,
    ):
        self.sources = source_manager or WeatherSourceManager()
        self.location_resolver = location_resolver or WeatherLocationResolver(default_city=self.sources.default_location)
        self.connectivity = connectivity_manager or ConnectivityManager()
        self.fetcher = fetcher or WeatherFetcher(connectivity_manager=self.connectivity)
        self.cache = cache or WeatherCache(current_ttl_seconds=600.0, forecast_ttl_seconds=1800.0)

    def is_online(self) -> bool:
        """Returns True if internet access is active."""
        return self.connectivity.is_online

    @staticmethod
    def is_weather_query(text: str) -> bool:
        """Detects whether raw or normalized text is inquiring about weather or related conditions."""
        if not text:
            return False
        lowered = text.lower().strip()

        # Guard 1: System maintenance / file / folder / disk cleanup commands containing "temp"
        system_cleanup_keywords = {
            "file", "files", "folder", "folders", "dir", "dirs", "directory", "directories",
            "clean", "clear", "delete", "remove", "empty", "saaf", "khali", "hatao", "hata",
            "mitao", "format", "purge", "flush", "junk", "cache", "recycle", "bin", "trash",
            "disk", "storage", "drive", "space", "memory"
        }
        has_cleanup_keyword = any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in system_cleanup_keywords)
        has_explicit_weather = any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in ["weather", "mausam", "mousam", "forecast"])

        # If cleanup terms are present and no explicit "weather"/"mausam" word is present, reject weather
        if has_cleanup_keyword and not has_explicit_weather:
            return False

        # Guard 2: Media / playback requests containing "rain" (e.g. "play rain sounds", "rain sound", "rain song")
        media_keywords = {"play", "song", "music", "gaana", "gana", "sound", "sounds", "track", "audio", "video", "movie", "game", "chalao", "bajaao", "bajao"}
        has_media_keyword = any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in media_keywords)
        if has_media_keyword and not has_explicit_weather:
            return False

        # Guard 3: "temp" without "temperature" must be an actual temperature question cue
        # (e.g. "temp kya hai", "aaj ka temp", "delhi ka temp", "current temp", "what is the temp")
        # and NOT an abbreviation for temporary/template
        if re.search(r"\btemp\b", lowered) and not re.search(r"\btemperature\b", lowered) and not has_explicit_weather:
            temp_inquiry_cues = {
                "what", "kya", "kitna", "kitni", "batao", "bata", "bataiye", "check",
                "celsius", "fahrenheit", "degree", "degrees", "hot", "cold", "garmi", "sardi", "thand",
                "aaj", "today", "abhi", "now", "current", "outside", "bahar", "delhi", "mumbai"
            }
            if not any(re.search(rf"\b{re.escape(c)}\b", lowered) for c in temp_inquiry_cues):
                return False

        weather_keywords = [
            "weather", "mausam", "mousam", "baarish", "rain", "temperature", "temp",
            "garmi", "sardi", "thand", "humidity", "nami", "wind", "hawa",
            "forecast", "umbrella", "chhatri", "chhate", "raincoat", "dhoop",
            "cloudy", "sunny", "fog", "kohra"
        ]
        return any(re.search(rf"\b{re.escape(kw)}\b", lowered) for kw in weather_keywords)

    def parse_query(self, raw_text: str) -> WeatherQuery:
        """Transforms natural user utterance into a structured WeatherQuery."""
        lowered = raw_text.lower().strip()

        # 1. Intent Determination
        is_umbrella = any(w in lowered for w in ["umbrella", "chhatri", "chhate", "raincoat"])
        if is_umbrella:
            intent = WeatherIntent.RAIN_FORECAST
        elif any(w in lowered for w in ["baarish", "rain", "boondabaandi", "shower", "baraf", "snow"]):
            intent = WeatherIntent.RAIN_FORECAST
        elif "temperature" in lowered or ("temp" in lowered and not any(w in lowered for w in ["file", "files", "folder", "clean", "clear", "delete", "remove", "saaf"])) or any(w in lowered for w in ["garmi", "sardi", "thand"]):
            intent = WeatherIntent.TEMPERATURE
        elif any(w in lowered for w in ["humidity", "nami"]):
            intent = WeatherIntent.HUMIDITY
        elif any(w in lowered for w in ["wind", "hawa", "aandhi", "toofan"]):
            intent = WeatherIntent.WIND
        elif any(w in lowered for w in ["feels like", "feel like", "lag kaisa"]):
            intent = WeatherIntent.FEELS_LIKE
        elif any(w in lowered for w in ["alert", "warning", "chetawani"]):
            intent = WeatherIntent.WEATHER_ALERT
        elif any(w in lowered for w in ["forecast", "agle kuch din", "is hafte", "weekly"]):
            intent = WeatherIntent.WEATHER_FORECAST
        else:
            intent = WeatherIntent.CURRENT_WEATHER

        # 2. Temperature Unit
        unit = TemperatureUnit.FAHRENHEIT if "fahrenheit" in lowered else TemperatureUnit.CELSIUS

        # 3. Language
        hindi_cues = ["kaisa", "hai", "aaj", "kal", "mein", "me", "ka", "ki", "ke", "batao", "hogi", "hoga", "chahiye", "rahega", "parso", "kitni"]
        is_hindi = any(w in lowered for w in hindi_cues)
        lang = "hi" if is_hindi else "en"

        # 4. Period & Date
        period, target_date, days_count = WeatherDateResolver.resolve_period_and_date(raw_text)

        # 5. Location Extraction (if explicit)
        explicit_loc = self.location_resolver._extract_explicit_city(lowered)

        return WeatherQuery(
            raw_query=raw_text,
            intent=intent,
            location=explicit_loc,
            target_period=period,
            target_date=target_date,
            target_days_count=days_count,
            unit=unit,
            language=lang,
            is_umbrella_query=is_umbrella
        )

    def process_weather_request(self, raw_text: str) -> WeatherEngineResult:
        """End-to-end convenience method parsing raw input and returning structured WeatherEngineResult."""
        query = self.parse_query(raw_text)
        return self.get_weather(query)

    def get_weather(self, query: WeatherQuery) -> WeatherEngineResult:
        """Executes full weather pipeline for a structured WeatherQuery."""
        # 1. Location Resolution
        location_name = query.location
        loc_obj: Optional[WeatherLocation] = None

        if location_name:
            lat, lon = self.location_resolver.get_city_coordinates(location_name)
            loc_obj = WeatherLocation(
                name=location_name.title(),
                latitude=lat,
                longitude=lon,
                is_default=False,
                resolution_source="explicit"
            )
            self.location_resolver.update_conversation_location(loc_obj.name)
        else:
            loc_obj, needs_clarify, clarify_prompt = self.location_resolver.resolve_location(query.raw_query)
            if needs_clarify or not loc_obj:
                return WeatherEngineResult(
                    success=False,
                    query=query,
                    formatted_response=clarify_prompt or "Main kis city ka weather check karun?",
                    needs_clarification=True,
                    clarification_prompt=clarify_prompt
                )

        # 2. Date & Period Resolution
        if query.target_period == WeatherForecastPeriod.CURRENT:
            period, target_date, days_count = WeatherDateResolver.resolve_period_and_date(query.raw_query)
            query.target_period = period
            if target_date and not query.target_date:
                query.target_date = target_date
            if days_count > 1:
                query.target_days_count = days_count

        is_forecast_request = query.target_period not in (WeatherForecastPeriod.CURRENT, WeatherForecastPeriod.TODAY)

        # 3. Offline Safety Check (Rule 32)
        if not self.is_online():
            logger.info("WeatherEngine: System is offline. Refusing to invent weather.")
            offline_msg = (
                "Abhi live weather data access nahi ho pa raha, isliye main current weather verify nahi kar sakta."
                if query.language == "hi" else
                "Live weather data is currently unreachable, so I cannot verify current conditions."
            )
            return WeatherEngineResult(
                success=False,
                query=query,
                formatted_response=offline_msg,
                is_offline=True,
                error="offline"
            )

        # 4. Cache Check
        cached_data = self.cache.get(loc_obj.name, is_forecast=is_forecast_request)
        if cached_data is not None:
            is_fresh, _ = WeatherFreshnessValidator.is_fresh(cached_data, is_forecast=is_forecast_request)
            if is_fresh:
                logger.debug("WeatherEngine: Returning cached data for %s", loc_obj.name)
                resp_text = WeatherResponseGenerator.generate_response(cached_data, query)
                return WeatherEngineResult(
                    success=True,
                    query=query,
                    data=cached_data,
                    formatted_response=resp_text,
                    source_name=cached_data.source_name,
                    from_cache=True
                )

        # 5. Multi-Source Fallback Retrieval
        enabled_sources = self.sources.get_enabled_sources(requires_forecast=is_forecast_request)
        if not enabled_sources:
            enabled_sources = self.sources.get_enabled_sources()

        for src_cfg in enabled_sources:
            try:
                target_url = self.fetcher.build_url(src_cfg.url_pattern, loc_obj)
                raw_bytes = self.fetcher.fetch_single_url(target_url)
                if not raw_bytes:
                    logger.debug("Source %s returned empty response, trying next fallback...", src_cfg.name)
                    continue

                parser = get_parser(src_cfg.parser_type)
                if not parser:
                    continue

                parsed_data = parser.parse(raw_bytes, loc_obj, source_name=src_cfg.name)
                if not parsed_data:
                    continue

                # Freshness and Confidence check
                is_fresh, _ = WeatherFreshnessValidator.is_fresh(parsed_data, is_forecast=is_forecast_request)
                conf_score = WeatherConfidenceEvaluator.evaluate(parsed_data, query)

                if conf_score < 0.4:
                    logger.warning("Source %s returned low confidence (%.2f), trying fallback...", src_cfg.name, conf_score)
                    continue

                parsed_data.confidence_score = conf_score

                # Cache and update memory
                self.cache.put(loc_obj.name, parsed_data, is_forecast=is_forecast_request)
                self.location_resolver.update_conversation_location(loc_obj.name)

                resp_text = WeatherResponseGenerator.generate_response(parsed_data, query)
                return WeatherEngineResult(
                    success=True,
                    query=query,
                    data=parsed_data,
                    formatted_response=resp_text,
                    source_name=src_cfg.name,
                    from_cache=False
                )
            except Exception as e:
                logger.error("Exception in weather source %s: %s", src_cfg.name, e)

        # 6. All sources failed
        fail_msg = (
            "Abhi live weather sources access nahi ho pa rahe hain, isliye main weather verify nahi kar sakta."
            if query.language == "hi" else
            "Public weather services are currently unreachable, so I cannot verify weather conditions right now."
        )
        return WeatherEngineResult(
            success=False,
            query=query,
            formatted_response=fail_msg,
            error="all_sources_unreachable"
        )


# Global singleton
_global_weather_engine: Optional[WeatherEngine] = None


def get_weather_engine() -> WeatherEngine:
    """Returns global singleton WeatherEngine instance."""
    global _global_weather_engine
    if _global_weather_engine is None:
        _global_weather_engine = WeatherEngine()
    return _global_weather_engine
