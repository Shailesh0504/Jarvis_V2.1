# core/weather/confidence.py
"""Confidence and data completeness evaluator for retrieved weather data."""

from core.weather.models import WeatherData, WeatherForecastPeriod, WeatherQuery


class WeatherConfidenceEvaluator:
    """Computes confidence score based on data completeness and source reliability."""

    @staticmethod
    def evaluate(data: WeatherData, query: WeatherQuery) -> float:
        """Calculates confidence score (0.0 to 1.0)."""
        score = 1.0

        # Location check
        if not data.location or not data.location.name:
            score -= 0.40

        # Current temperature check
        if data.temperature_c is None:
            score -= 0.30

        # Weather condition check
        if not data.condition or data.condition.lower() == "unknown":
            score -= 0.20

        # Forecast completeness if forecast requested
        if query.target_period not in (WeatherForecastPeriod.CURRENT, WeatherForecastPeriod.TODAY):
            if not data.daily_forecasts:
                score -= 0.35
            elif query.target_days_count > 1 and len(data.daily_forecasts) < query.target_days_count:
                score -= 0.15

        # Rain inquiry completeness
        if query.is_umbrella_query or "rain" in query.raw_query.lower() or "baarish" in query.raw_query.lower():
            if data.precipitation_probability is None and not any(d.rain_probability is not None for d in data.daily_forecasts):
                score -= 0.15

        return max(0.0, min(score, 1.0))
