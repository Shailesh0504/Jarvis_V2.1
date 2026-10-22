# core/equity_research/strategies/breakout.py
"""Breakout strategy with volume confirmation for 1-month swing setups."""

from typing import Tuple

from .base_strategy import TechnicalStrategy
from ..models import TechnicalIndicators


class BreakoutStrategy(TechnicalStrategy):
    """
    Identifies resistance breakouts backed by volume expansion:
    Price challenging or breaking swing resistance with volume > 1.4x 20-SMA volume,
    ADX > 22 (trend building), and healthy ATR.
    """

    @property
    def name(self) -> str:
        return "Breakout"

    @property
    def description(self) -> str:
        return "Identifies horizontal or swing resistance breakouts with volume surge and ADX expansion."

    def evaluate(self, tech: TechnicalIndicators, current_price: float) -> Tuple[bool, float, str]:
        score = 0.0
        reasons = []

        # 1. Proximity to resistance or breakout (35 pts)
        dist_to_res = (tech.resistance_level - current_price) / max(1.0, current_price) * 100.0
        if current_price >= tech.resistance_level:
            score += 35.0
            reasons.append(f"Price broke above key swing resistance ({tech.resistance_level:.1f})")
        elif -1.5 <= dist_to_res <= 1.5:
            score += 25.0
            reasons.append(f"Price testing breakout resistance zone ({tech.resistance_level:.1f})")

        # 2. Volume expansion confirmation (30 pts)
        if tech.volume_breakout and tech.volume_ratio >= 1.5:
            score += 30.0
            reasons.append(f"Strong volume expansion ({tech.volume_ratio:.1f}x 20-day average)")
        elif tech.volume_ratio >= 1.2:
            score += 15.0
            reasons.append(f"Improving volume ({tech.volume_ratio:.1f}x average)")
        else:
            reasons.append("Breakout lacks strong volume surge")

        # 3. ADX trend strength (20 pts)
        if tech.adx >= 25.0:
            score += 20.0
            reasons.append(f"ADX at {tech.adx:.1f} signals strong trend emergence")
        elif tech.adx >= 20.0:
            score += 10.0
            reasons.append(f"ADX at {tech.adx:.1f} building momentum")

        # 4. Moving average support (15 pts)
        if current_price > tech.ema_20:
            score += 15.0
            reasons.append("Breakout supported by 20 EMA floor")

        matched = score >= 60.0
        rationale = "; ".join(reasons) if reasons else "No breakout setup detected"
        return matched, min(100.0, max(0.0, score)), rationale
