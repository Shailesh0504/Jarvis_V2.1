# core/equity_research/strategies/trend_following.py
"""Trend-following strategy for 1-month swing momentum."""

from typing import Tuple

from .base_strategy import TechnicalStrategy
from ..models import TechnicalIndicators


class TrendFollowingStrategy(TechnicalStrategy):
    """
    Looks for established upward trend persistence:
    Price > EMA 20 > EMA 50, RSI between 52 and 68 (momentum without extreme overbought),
    positive MACD histogram, and positive Relative Strength vs NIFTY 50.
    """

    @property
    def name(self) -> str:
        return "TrendFollowing"

    @property
    def description(self) -> str:
        return "Captures established multi-week uptrends with EMA 20/50 alignment and positive relative strength."

    def evaluate(self, tech: TechnicalIndicators, current_price: float) -> Tuple[bool, float, str]:
        score = 0.0
        reasons = []

        # 1. Moving average alignment (30 pts)
        if current_price > tech.ema_20 > tech.ema_50:
            score += 30.0
            reasons.append("Price > 20 EMA > 50 EMA bullish alignment")
        elif current_price > tech.ema_20:
            score += 15.0
            reasons.append("Price holding above 20 EMA")

        # 2. RSI momentum zone (25 pts)
        if 52.0 <= tech.rsi <= 68.0:
            score += 25.0
            reasons.append(f"RSI {tech.rsi} in sweet spot for swing continuation")
        elif 48.0 <= tech.rsi < 52.0:
            score += 12.0
            reasons.append(f"RSI {tech.rsi} stabilizing at median")
        elif tech.rsi > 75.0:
            score -= 10.0
            reasons.append(f"RSI {tech.rsi} overbought, entry risk elevated")

        # 3. MACD confirmation (20 pts)
        if tech.macd > tech.macd_signal and tech.macd_hist > 0:
            score += 20.0
            reasons.append("MACD bullish crossover active")

        # 4. SuperTrend alignment (15 pts)
        if tech.supertrend_direction == "BULLISH":
            score += 15.0
            reasons.append(f"SuperTrend bullish support at {tech.supertrend_value:.1f}")

        # 5. Relative strength vs Nifty (10 pts)
        if tech.relative_strength_nifty > 1.0:
            score += 10.0
            reasons.append(f"Outperforming NIFTY 50 by {tech.relative_strength_nifty:.1f}%")

        matched = score >= 60.0
        rationale = "; ".join(reasons) if reasons else "No trend confluence"
        return matched, min(100.0, max(0.0, score)), rationale
