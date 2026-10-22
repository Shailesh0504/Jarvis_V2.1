# core/equity_research/strategies/base_strategy.py
"""Abstract base class for pluggable technical strategies in 1-month equity research."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple

from ..models import TechnicalIndicators


class TechnicalStrategy(ABC):
    """Base interface ensuring strategies are isolated and pluggable without hardcoding."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, tech: TechnicalIndicators, current_price: float) -> Tuple[bool, float, str]:
        """
        Evaluates whether indicators match this strategy.
        Returns: (is_matched, strategy_score_0_to_100, rationale)
        """
        pass
