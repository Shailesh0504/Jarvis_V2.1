# core/equity_research/scorer.py
"""
Multi-Factor Research Scorer for 1-Month Indian Equity Setups.
Evaluates 11 transparent dimensions:
1. Trend (15%)
2. Momentum (15%)
3. Volume Confirmation (10%)
4. Relative Strength vs NIFTY (15%)
5. Volatility / Risk buffer (10%)
6. Liquidity (10%)
7. Support / Resistance Structure (10%)
8. Catalyst Quality (5%)
9. Fundamental Context (5%)
10. Market-Regime Alignment (5%)
Maps to transparent evidence tiers:
- STRONG EVIDENCE (>= 75)
- MODERATE EVIDENCE (60 - 74)
- WEAK/MIXED EVIDENCE (< 60)
"""

import logging
from typing import Dict, Tuple

from .models import (
    EvidenceTier,
    FundamentalSnapshot,
    MarketRegime,
    TechnicalIndicators,
)

logger = logging.getLogger("jarvis.equity_research.scorer")


class MultiFactorScorer:
    """
    Transparent multi-factor research scoring engine without fake decimal precision.
    """

    def calculate_score(
        self,
        tech: TechnicalIndicators,
        fundamentals: FundamentalSnapshot,
        has_positive_catalyst: bool,
        adtv_cr: float,
        market_regime: MarketRegime,
        is_stale_data: bool = False,
    ) -> Tuple[float, EvidenceTier, Dict[str, float]]:
        """
        Computes the multi-factor research score and assigns the qualitative evidence tier.
        Returns: (final_score, evidence_tier, component_breakdown)
        """
        breakdown: Dict[str, float] = {}

        # 1. Trend Structure (Max 15)
        trend_score = 0.0
        if tech.trend == "BULLISH":
            trend_score = 15.0
        elif tech.trend == "SIDEWAYS":
            trend_score = 8.0
        else:
            trend_score = 2.0
        breakdown["trend"] = trend_score

        # 2. Momentum (Max 15)
        mom_score = 0.0
        if 52.0 <= tech.rsi <= 68.0:
            mom_score = 15.0
        elif 45.0 <= tech.rsi < 52.0 or 68.0 < tech.rsi <= 74.0:
            mom_score = 10.0
        elif tech.rsi > 74.0:
            mom_score = 5.0  # Overbought penalty
        else:
            mom_score = 3.0
        breakdown["momentum"] = mom_score

        # 3. Volume Confirmation (Max 10)
        vol_score = 0.0
        if tech.volume_breakout:
            vol_score = 10.0
        elif tech.volume_ratio >= 1.2:
            vol_score = 8.0
        elif tech.volume_ratio >= 0.9:
            vol_score = 5.0
        else:
            vol_score = 2.0
        breakdown["volume"] = vol_score

        # 4. Relative Strength vs NIFTY 50 (Max 15)
        rs_score = 0.0
        if tech.relative_strength_nifty >= 3.0:
            rs_score = 15.0
        elif tech.relative_strength_nifty >= 1.0:
            rs_score = 11.0
        elif tech.relative_strength_nifty >= -1.0:
            rs_score = 7.0
        else:
            rs_score = 2.0
        breakdown["relative_strength"] = rs_score

        # 5. Volatility / ATR Risk Buffer (Max 10)
        volat_score = 0.0
        if 1.5 <= tech.atr_pct <= 3.2:
            volat_score = 10.0  # Ideal swing volatility
        elif tech.atr_pct < 1.5:
            volat_score = 7.0   # Very slow
        elif tech.atr_pct <= 4.5:
            volat_score = 5.0   # Moderately high
        else:
            volat_score = 2.0   # Excessive gap/whipsaw risk
        breakdown["volatility"] = volat_score

        # 6. Liquidity (Max 10)
        liq_score = 0.0
        if adtv_cr >= 100.0:
            liq_score = 10.0
        elif adtv_cr >= 30.0:
            liq_score = 8.0
        elif adtv_cr >= 10.0:
            liq_score = 5.0
        else:
            liq_score = 0.0
        breakdown["liquidity"] = liq_score

        # 7. Support / Resistance Pivots (Max 10)
        sr_score = 0.0
        if tech.supertrend_direction == "BULLISH" and tech.macd_hist > 0:
            sr_score = 10.0
        elif tech.supertrend_direction == "BULLISH" or tech.macd_hist > 0:
            sr_score = 6.0
        else:
            sr_score = 2.0
        breakdown["support_resistance"] = sr_score

        # 8. Catalyst Quality (Max 5)
        cat_score = 5.0 if has_positive_catalyst else 2.5
        breakdown["catalyst"] = cat_score

        # 9. Fundamental Context (Max 5)
        fund_score = 5.0
        if fundamentals.pledged_shares_pct > 15.0:
            fund_score -= 3.0
        if fundamentals.debt_to_equity > 1.8:
            fund_score -= 1.5
        breakdown["fundamentals"] = max(0.0, fund_score)

        # 10. Market Regime Alignment (Max 5)
        regime_score = 0.0
        if market_regime == MarketRegime.BULLISH:
            regime_score = 5.0
        elif market_regime in (MarketRegime.SIDEWAYS, MarketRegime.MIXED):
            regime_score = 3.5
        else:
            regime_score = 1.0
        breakdown["market_regime"] = regime_score

        # Total Raw Score (0 to 100)
        raw_total = sum(breakdown.values())

        # Data Freshness Penalty (if stale, cap score)
        if is_stale_data:
            raw_total *= 0.5

        final_score = round(raw_total, 1)

        # Evidence Tier Assignment
        if final_score >= 75.0:
            tier = EvidenceTier.STRONG_EVIDENCE
        elif final_score >= 60.0:
            tier = EvidenceTier.MODERATE_EVIDENCE
        else:
            tier = EvidenceTier.WEAK_EVIDENCE

        return final_score, tier, breakdown
