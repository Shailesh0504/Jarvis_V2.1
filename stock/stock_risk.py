# stock/stock_risk.py
"""
Risk Suitability, Volatility Gating, and Scenario Invalidation Layer.
Integrates with core/equity_research/risk_engine.py.
Enforces client risk tolerance alignment, exclusion gates, and dynamic stop-loss levels.
"""

from typing import Any, Dict, List, Optional, Tuple
from core.equity_research.models import CatalystEvent, RiskScenario, TechnicalIndicators
from core.equity_research.risk_engine import RiskEngine


class StockRiskEvaluator:
    """Evaluates suitability vs risk preferences, exclusions, and stop-loss levels."""

    def __init__(self, risk_engine: Optional[RiskEngine] = None):
        self.engine = risk_engine or RiskEngine()

    def evaluate_scenarios(
        self,
        current_price: float,
        tech: TechnicalIndicators,
        catalysts: Optional[List[CatalystEvent]] = None,
        market_regime: str = "BULLISH",
    ) -> RiskScenario:
        """Calculates bull, base, bear target cases and dynamic invalidation level."""
        return self.engine.evaluate_scenarios(
            current_price=current_price,
            tech=tech,
            catalysts=catalysts or [],
            market_regime=market_regime,
        )

    def evaluate_suitability(
        self,
        current_price: float,
        tech: TechnicalIndicators,
        adtv_cr: float,
        risk_preference: str,
        exclusions: List[str],
    ) -> Tuple[bool, float, List[str], List[str]]:
        """
        Evaluates risk suitability and exclusions.
        Returns:
            (passes_suitability, risk_fit_score_0_to_20, why_reasons, risk_warnings)
        """
        why_reasons: List[str] = []
        risk_warnings: List[str] = []
        score = 12.0  # Base risk score

        norm_exclusions = [e.lower().strip().replace(" ", "_") for e in exclusions]
        risk_pref = risk_preference.lower().strip()

        # 1. Penny Stock Exclusion (< ₹20)
        if "exclude_penny_stocks" in norm_exclusions or "penny_stocks" in norm_exclusions:
            if current_price < 20.0:
                return False, 0.0, [], [f"Excluded penny stock (Price ₹{current_price:.2f} < ₹20.00)"]

        # 2. Low Liquidity Exclusion (< ₹5 Cr ADTV)
        if "exclude_low_liquidity_stocks" in norm_exclusions or "low_liquidity" in norm_exclusions:
            if adtv_cr < 5.0:
                return False, 0.0, [], [f"Excluded low liquidity counter (ADTV ₹{adtv_cr:.1f} Cr < ₹5 Cr)"]

        # 3. High Volatility Check (ATR% > 4.5%)
        is_high_vol = tech.atr_pct > 4.5
        if "exclude_highly_volatile_stocks" in norm_exclusions or "volatile" in norm_exclusions:
            if is_high_vol:
                return False, 0.0, [], [f"Excluded highly volatile instrument (Daily ATR {tech.atr_pct:.1f}% > 4.5%)"]

        # 4. Risk Preference Suitability Matching
        if risk_pref == "conservative":
            if tech.atr_pct <= 2.2 and adtv_cr >= 50.0:
                score += 8.0
                why_reasons.append("Low daily volatility and institutional tier liquidity (Conservative fit)")
            elif tech.atr_pct <= 3.0:
                score += 4.0
                why_reasons.append("Controlled volatility profile")
            else:
                score -= 6.0
                risk_warnings.append(f"Elevated price fluctuation for conservative profile (ATR {tech.atr_pct:.1f}%)")

        elif risk_pref == "aggressive":
            if tech.atr_pct >= 2.5 or tech.volume_breakout:
                score += 8.0
                why_reasons.append("High beta momentum and breakout activity (Aggressive fit)")
            else:
                score += 4.0
                why_reasons.append("Stable price action suitable for aggressive sizing")

        else:  # Moderate (default)
            if tech.atr_pct <= 3.5:
                score += 7.0
                why_reasons.append("Balanced risk/reward profile matching moderate preference")
            else:
                score -= 3.0
                risk_warnings.append(f"Above-average daily swings (ATR {tech.atr_pct:.1f}%)")

        # Invalidation level support note
        if tech.support_level > 0:
            why_reasons.append(f"Defined technical invalidation anchor at ₹{tech.support_level:.1f}")

        score = max(0.0, min(20.0, score))
        return True, score, why_reasons, risk_warnings
