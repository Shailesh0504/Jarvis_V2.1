# core/equity_research/strategies/__init__.py
"""Pluggable strategies package for 1-month equity research."""

from .base_strategy import TechnicalStrategy
from .trend_following import TrendFollowingStrategy
from .breakout import BreakoutStrategy
from .mean_reversion import MeanReversionStrategy

__all__ = [
    "TechnicalStrategy",
    "TrendFollowingStrategy",
    "BreakoutStrategy",
    "MeanReversionStrategy",
]
