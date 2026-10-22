# core/weather/parsers/__init__.py
"""Weather parser registry and factory."""

from typing import Dict, Optional, Type

from core.weather.parsers.base import BaseWeatherParser
from core.weather.parsers.open_meteo import OpenMeteoParser
from core.weather.parsers.wttr_json import WttrJsonParser
from core.weather.parsers.wttr_text import WttrTextParser

_PARSER_REGISTRY: Dict[str, Type[BaseWeatherParser]] = {
    "wttr_json": WttrJsonParser,
    "open_meteo": OpenMeteoParser,
    "wttr_text": WttrTextParser,
}


def get_parser(parser_type: str) -> Optional[BaseWeatherParser]:
    """Returns an instantiated parser instance for the given parser type."""
    cls = _PARSER_REGISTRY.get(parser_type.lower())
    if cls:
        return cls()
    return None
