# core/equity_research/strategies/mean_reversion.py
"""Mean reversion strategy for pullbacks to major support in broader uptrends."""

from typing import Tuple

from .base_strategy import TechnicalStrategy
from ..models import TechnicalIndicators


class MeanReversionStrategy(TechnicalStrategy):
    """
    Identifies high-probability pullback bounces:
    Stock in larger structural uptrend (Price > SMA 200) experiencing temporary oversold
    pullback (RSI 35-46) near swing support or 50 EMA.
    """

    @property
    def name(self) -> str:
        return "MeanReversion"

    @property
    def description(self) -> str:
        return "Identifies oversold pullbacks testing major dynamic support in broader structural uptrends."

    def evaluate(self, tech: TechnicalIndicators, current_price: float) -> Tuple[bool, float, str]:
        score = 0.0
        reasons = []

        # 1. Structural bull anchor: above 200 SMA (30 pts)
        if current_price >= tech.sma_200:
            score += 30.0
            reasons.append(f"Price above long-term 200 SMA ({tech.sma_200:.1f})")

        # 2. Oversold pullback condition (30 pts)
        if 35.0 <= tech.rsi <= 48.0:
            score += 30.0
            reasons.append(f"RSI cooled off to {tech.rsi:.1f} providing low-risk entry")
        elif tech.rsi < 35.0:
            score += 20.0
            reasons.append(f"Deep oversold RSI {tech.rsi:.1f}, wait for bounce confirmation")

        # 3. Support proximity (25 pts)
        dist_to_sup = abs(current_price - tech.support_level) / max(1.0, current_price) * 100.0
        if dist_to_sup <= 2.5:
            score += 25.0
            reasons.append(f"Price hovering near strong support ({tech.support_level:.1f})")

        # 4. Asymmetric risk buffer (15 pts)
        if tech.atr_pct <= 3.5:
            score += 15.0
            reasons.append("Manageable daily volatility allows tight invalidation stop")

        matched = score >= 60.0
        rationale = "; ".join(reasons) if reasons else "No mean-reversion setup"
        return matched, min(100.0, max(0.0, score)), rationale
