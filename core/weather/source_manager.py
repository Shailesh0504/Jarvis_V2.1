# core/weather/source_manager.py
"""Weather Source Manager loading, filtering, and prioritizing public web sources."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("jarvis.weather.sources")

DEFAULT_SOURCES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "weather_sources.json"


@dataclass
class WeatherSourceConfig:
    id: str
    name: str
    source_type: str
    url_pattern: str
    parser_type: str
    priority: int = 1
    timeout_seconds: float = 3.5
    enabled: bool = True
    supports_forecast: bool = True
    supports_hourly: bool = False


class WeatherSourceManager:
    """Manages public weather source configurations without hardcoding URLs in core logic."""

    def __init__(self, sources_path: Optional[Path] = None):
        self.sources_path = sources_path or DEFAULT_SOURCES_PATH
        self._sources: List[WeatherSourceConfig] = []
        self.default_location: str = "Delhi"
        self.reload()

    def reload(self) -> None:
        """Loads or reloads sources from JSON configuration file."""
        self._sources.clear()
        if not self.sources_path.exists():
            logger.warning("Weather sources config not found at: %s. Using default fallbacks.", self.sources_path)
            self._load_fallback_sources()
            return

        try:
            with open(self.sources_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.default_location = data.get("default_location", "Delhi")
            for item in data.get("sources", []):
                src = WeatherSourceConfig(
                    id=item.get("id", ""),
                    name=item.get("name", "Unknown"),
                    source_type=item.get("source_type", "wttr_json"),
                    url_pattern=item.get("url_pattern", ""),
                    parser_type=item.get("parser_type", "wttr_json"),
                    priority=int(item.get("priority", 1)),
                    timeout_seconds=float(item.get("timeout_seconds", 3.5)),
                    enabled=bool(item.get("enabled", True)),
                    supports_forecast=bool(item.get("supports_forecast", True)),
                    supports_hourly=bool(item.get("supports_hourly", False)),
                )
                if src.url_pattern:
                    self._sources.append(src)
            # Sort by priority (ascending)
            self._sources.sort(key=lambda s: s.priority)
            logger.info("Loaded %d weather sources from %s", len(self._sources), self.sources_path)
        except Exception as e:
            logger.error("Error reading weather sources from %s: %s", self.sources_path, e)
            self._load_fallback_sources()

    def _load_fallback_sources(self) -> None:
        """Loads built-in public sources if configuration file is absent."""
        self._sources = [
            WeatherSourceConfig(
                id="wttr_in_json",
                name="wttr.in Web Service",
                source_type="wttr_json",
                url_pattern="https://wttr.in/{location}?format=j1",
                parser_type="wttr_json",
                priority=1,
                timeout_seconds=3.5,
                enabled=True,
                supports_forecast=True,
                supports_hourly=True,
            ),
            WeatherSourceConfig(
                id="open_meteo_public",
                name="Open-Meteo Public Web",
                source_type="open_meteo",
                url_pattern="https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto",
                parser_type="open_meteo",
                priority=2,
                timeout_seconds=3.5,
                enabled=True,
                supports_forecast=True,
                supports_hourly=False,
            ),
            WeatherSourceConfig(
                id="wttr_in_text",
                name="wttr.in Plain Text Web",
                source_type="wttr_text",
                url_pattern="https://wttr.in/{location}?format=%t|%f|%h|%w|%p|%C",
                parser_type="wttr_text",
                priority=3,
                timeout_seconds=3.0,
                enabled=True,
                supports_forecast=False,
                supports_hourly=False,
            ),
        ]

    def get_enabled_sources(self, requires_forecast: bool = False) -> List[WeatherSourceConfig]:
        """Returns sorted enabled sources, optionally filtering for forecast support."""
        sources = [s for s in self._sources if s.enabled]
        if requires_forecast:
            sources = [s for s in sources if s.supports_forecast]
        return sources
