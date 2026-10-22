# core/weather/normalizer.py
"""Weather condition multilingual normalization and unit conversions."""

from typing import Dict, Optional, Tuple

CONDITION_HI_MAP: Dict[str, str] = {
    "sunny": "dhoop khili hai",
    "clear": "mausam saaf hai",
    "partly cloudy": "halke baadal hain",
    "cloudy": "baadal chhaye hue hain",
    "overcast": "ghane baadal hain",
    "mist": "dhund hai",
    "fog": "kohra hai",
    "freezing fog": "thanda kohra hai",
    "patchy rain possible": "halki baarish ki sambhavna hai",
    "patchy light drizzle": "halki boondabaandi ho sakti hai",
    "light drizzle": "halki boondabaandi hai",
    "light rain": "halki baarish hai",
    "moderate rain": "madhyam baarish hai",
    "heavy rain": "tez baarish hai",
    "torrential rain shower": "bhaari baarish hai",
    "thundery outbreaks possible": "bijli aur toofan ki sambhavna hai",
    "thunderstorm": "toofan aur garaj ke saath baarish hai",
    "patchy snow possible": "halki barafbaari ki sambhavna hai",
    "light snow": "halki barafbaari hai",
    "heavy snow": "bhaari barafbaari hai",
    "haze": "haze aur dhund hai",
}


class WeatherNormalizer:
    """Normalizes weather conditions, multilingual terms, and unit representations."""

    @staticmethod
    def celsius_to_fahrenheit(c: float) -> float:
        """Converts Celsius to Fahrenheit."""
        return round((c * 9.0 / 5.0) + 32.0, 1)

    @staticmethod
    def fahrenheit_to_celsius(f: float) -> float:
        """Converts Fahrenheit to Celsius."""
        return round((f - 32.0) * 5.0 / 9.0, 1)

    @staticmethod
    def get_hindi_condition(condition_en: str) -> str:
        """Translates English weather description into natural Hindi/Hinglish."""
        if not condition_en:
            return "saaf mausam"
        lowered = condition_en.lower().strip()

        # Direct match
        if lowered in CONDITION_HI_MAP:
            return CONDITION_HI_MAP[lowered]

        # Substring heuristics
        if "thunder" in lowered or "storm" in lowered:
            return "garaj aur toofan"
        if "heavy rain" in lowered or "torrential" in lowered:
            return "tez baarish"
        if "rain" in lowered or "drizzle" in lowered or "shower" in lowered:
            return "baarish"
        if "snow" in lowered or "blizzard" in lowered:
            return "barafbaari"
        if "cloud" in lowered or "overcast" in lowered:
            return "baadal"
        if "clear" in lowered or "sunny" in lowered:
            return "saaf mausam"
        if "fog" in lowered or "mist" in lowered or "haze" in lowered:
            return "kohra"

        return condition_en

    @staticmethod
    def format_rain_chance(probability: Optional[int], language: str = "hi") -> str:
        """Formats rain probability into natural non-absolute Hinglish or English."""
        if probability is None:
            return "baarish ke chances abhi clear nahi hain" if language == "hi" else "rain probability is currently not available"

        if probability >= 80:
            return f"baarish ke bohot high chances hain ({probability}%)" if language == "hi" else f"very high chance of rain ({probability}%)"
        elif probability >= 60:
            return f"baarish ki achhi sambhavna hai ({probability}%)" if language == "hi" else f"good chance of rain ({probability}%)"
        elif probability >= 40:
            return f"baarish ki lagbhag {probability}% possibility hai" if language == "hi" else f"around {probability}% chance of rain"
        elif probability >= 20:
            return f"halki baarish ke 20-30% chances hain" if language == "hi" else f"slight chance of rain ({probability}%)"
        elif probability > 0:
            return f"baarish ke chances bohot kam hain ({probability}%)" if language == "hi" else f"low chance of rain ({probability}%)"
        else:
            return "baarish ke koi chances nahi hain (0%)" if language == "hi" else "no rain expected (0%)"
