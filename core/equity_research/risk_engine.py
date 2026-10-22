# core/equity_research/risk_engine.py
"""
Risk & Scenario Engine for 1-Month Indian Equity Research.
Models Bull, Base, and Bear scenarios, calculates analytical entry/invalidation zones,
evaluates gap risk, volatility risk, event risk, and checks capital liquidity capacity.
"""

import logging
from typing import List, Tuple

from .models import (
    CatalystEvent,
    RiskScenario,
    ScenarioCase,
    TechnicalIndicators,
)

logger = logging.getLogger("jarvis.equity_research.risk_engine")


class RiskEngine:
    """
    Computes analytical risk buffers, scenarios, and invalidation rules.
    Invariant: Analytical levels are risk-management coordinates, NEVER guaranteed price predictions.
    """

    def evaluate_scenarios(
        self,
        current_price: float,
        tech: TechnicalIndicators,
        catalysts: List[CatalystEvent],
        market_regime: str = "BULLISH",
    ) -> RiskScenario:
        """
        Builds Bull, Base, and Bear case scenarios with analytical invalidation boundaries.
        """
        atr = tech.atr if tech.atr > 0 else (current_price * 0.02)

        # Invalidation Stop: Placed just below swing support or 1.5x ATR below entry
        invalidation_level = round(min(tech.support_level * 0.99, current_price - (1.5 * atr)), 2)
        risk_distance = max(1.0, current_price - invalidation_level)

        # Entry Zone: Pullback tolerance buffer
        entry_low = round(max(tech.support_level, current_price - (0.5 * atr)), 2)
        entry_high = round(current_price * 1.005, 2)

        # 1. Base Case (1-Month swing target: 1.5x to 2.0x risk)
        base_target_low = round(current_price + (1.5 * risk_distance), 2)
        base_target_high = round(current_price + (2.2 * risk_distance), 2)
        base_case = ScenarioCase(
            conditions="Market regime remains stable and stock sustains above 20 EMA",
            target_zone=(base_target_low, base_target_high),
            direction="UPWARD_STEADY",
            invalidation_level=invalidation_level,
            key_evidence=[
                f"Holding above key support at {tech.support_level:.1f}",
                f"RSI {tech.rsi:.1f} sustaining in bullish momentum band",
                "Healthy volume participation supporting consolidation",
            ],
        )

        # 2. Bull Case (Breakout surge: 2.5x to 3.5x risk)
        bull_target_low = round(current_price + (2.5 * risk_distance), 2)
        bull_target_high = round(current_price + (3.8 * risk_distance), 2)
        bull_case = ScenarioCase(
            conditions="Upcoming catalyst exceeds expectations or sector momentum experiences sharp breakout",
            target_zone=(bull_target_low, bull_target_high),
            direction="STRONG_BREAKOUT",
            invalidation_level=invalidation_level,
            key_evidence=[
                f"Breakout above horizontal resistance at {tech.resistance_level:.1f}",
                f"Volume surge ({tech.volume_ratio:.1f}x 20-day SMA)",
                "Positive institutional relative strength vs NIFTY benchmark",
            ],
        )

        # 3. Bear Case (Thesis invalidation breakdown)
        bear_target_low = round(invalidation_level - (1.0 * risk_distance), 2)
        bear_target_high = round(invalidation_level, 2)
        bear_case = ScenarioCase(
            conditions=f"Breakdown below support zone {invalidation_level:.1f} on heavy volume or adverse macro shock",
            target_zone=(bear_target_low, bear_target_high),
            direction="DOWNSIDE_INVALIDATION",
            invalidation_level=invalidation_level,
            key_evidence=[
                f"Decisive close below support floor ({tech.support_level:.1f})",
                "Loss of short-term 20 EMA trend anchor",
                "Risk of stop-loss cascading across swing participants",
            ],
        )

        reward_to_risk = round((base_target_low - current_price) / max(0.1, risk_distance), 2)

        return RiskScenario(
            bull_case=bull_case,
            base_case=base_case,
            bear_case=bear_case,
            reward_to_risk_ratio=reward_to_risk,
            invalidation_level=invalidation_level,
            entry_zone=(entry_low, entry_high),
        )

    def identify_key_risks(
        self,
        symbol: str,
        tech: TechnicalIndicators,
        catalysts: List[CatalystEvent],
        adtv_cr: float,
        market_regime: str,
    ) -> List[str]:
        """Catalogs specific operational, volatility, and event risks for the 1-month setup."""
        risks = []

        # 1. Near Resistance Risk
        if tech.resistance_level > 0:
            pct_to_res = (tech.resistance_level - tech.support_level) / max(1.0, tech.support_level) * 100.0
            if (tech.resistance_level - tech.recent_swing_high) <= 0:
                risks.append(f"Immediate resistance nearby at {tech.resistance_level:.1f}; failure to clear could stall momentum")

        # 2. Upcoming High-Impact Event
        for cat in catalysts:
            if cat.expected_relevance == "HIGH" and cat.uncertainty == "HIGH":
                risks.append(f"Upcoming {cat.event_type} on {cat.event_date} creates binary event volatility risk")

        # 3. Liquidity Risk
        if adtv_cr < 25.0:
            risks.append(f"Moderate daily turnover (₹{adtv_cr:.1f} Cr); gap risk on open and slippage on large execution")

        # 4. Market Regime Discordance
        if market_regime in ("BEARISH", "HIGH_VOLATILITY"):
            risks.append(f"Headwind from {market_regime} market regime may drag individual stock performance")

        # 5. Volatility Drag
        if tech.atr_pct > 3.5:
            risks.append(f"High daily volatility (ATR {tech.atr_pct:.1f}% of price) requires wider invalidation tolerance")

        if not risks:
            risks.append("Normal market pullback risk; invalidation triggered if support floor breaks")

        return risks
