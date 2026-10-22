# stock/stock_fundamental.py
"""
Fundamental Analysis and Screening Layer for Stock Query Wizard.
Integrates with core/equity_research/fundamental_engine.py.
Evaluates revenue growth, profitability, balance sheet strength, valuation ratios, and exclusions.
"""

from typing import Any, Dict, List, Optional, Tuple
from core.equity_research.fundamental_engine import FundamentalEngine
from core.equity_research.models import FundamentalSnapshot


class StockFundamentalFilter:
    """Evaluates candidate fundamentals against user fundamental preferences and exclusions."""

    def __init__(self, fundamental_engine: Optional[FundamentalEngine] = None):
        self.engine = fundamental_engine or FundamentalEngine()

    def get_snapshot(self, symbol: str) -> FundamentalSnapshot:
        """Retrieves verified fundamental snapshot for an Indian equity symbol."""
        return self.engine.get_snapshot(symbol)

    def evaluate(
        self,
        snapshot: FundamentalSnapshot,
        preferences: List[str],
        exclusions: List[str],
    ) -> Tuple[bool, float, List[str], List[str]]:
        """
        Evaluates snapshot against preferences and exclusions.
        Returns:
            (passes_filter, fundamental_score_0_to_30, matched_reasons, risk_notes)
        """
        matched_reasons: List[str] = []
        risk_notes: List[str] = []
        score = 15.0  # Base neutral fundamental score

        # 1. Check Exclusions
        norm_exclusions = [e.lower().strip().replace(" ", "_") for e in exclusions]
        if "exclude_loss_making" in norm_exclusions or "loss_making" in norm_exclusions:
            if snapshot.profit_growth_yoy < -10.0:
                return False, 0.0, [], ["Excluded: Significant profit decline or negative earnings"]

        if "exclude_high_debt" in norm_exclusions or "high_debt" in norm_exclusions:
            if snapshot.debt_to_equity > 1.5:
                return False, 0.0, [], [f"Excluded: High debt-to-equity ratio ({snapshot.debt_to_equity:.2f} > 1.5)"]

        # 2. Score Fundamental Preferences
        norm_prefs = [p.lower().strip().replace(" ", "_") for p in preferences]
        if "no_preference" in norm_prefs or not norm_prefs:
            # Neutral baseline assessment
            if snapshot.revenue_growth_yoy > 10.0:
                score += 4.0
                matched_reasons.append(f"Healthy YoY revenue growth ({snapshot.revenue_growth_yoy:.1f}%)")
            if snapshot.profit_growth_yoy > 12.0:
                score += 4.0
                matched_reasons.append(f"Strong YoY profit growth ({snapshot.profit_growth_yoy:.1f}%)")
            if snapshot.debt_to_equity < 0.6:
                score += 3.0
                matched_reasons.append(f"Prudent leverage (Debt/Equity {snapshot.debt_to_equity:.2f})")
            return True, min(30.0, score), matched_reasons, risk_notes

        # Specific user preference checks
        if "revenue_growth" in norm_prefs:
            if snapshot.revenue_growth_yoy >= 12.0:
                score += 5.0
                matched_reasons.append(f"Strong top-line expansion ({snapshot.revenue_growth_yoy:.1f}% YoY)")
            elif snapshot.revenue_growth_yoy >= 5.0:
                score += 2.5
                matched_reasons.append(f"Moderate revenue growth ({snapshot.revenue_growth_yoy:.1f}% YoY)")
            else:
                score -= 2.0
                risk_notes.append(f"Subdued revenue growth ({snapshot.revenue_growth_yoy:.1f}% YoY)")

        if "profit_growth" in norm_prefs or "eps_growth" in norm_prefs:
            if snapshot.profit_growth_yoy >= 15.0:
                score += 5.0
                matched_reasons.append(f"Robust net profit growth ({snapshot.profit_growth_yoy:.1f}% YoY)")
            elif snapshot.profit_growth_yoy >= 8.0:
                score += 3.0
                matched_reasons.append(f"Steady profit growth ({snapshot.profit_growth_yoy:.1f}% YoY)")
            else:
                score -= 2.0
                risk_notes.append("Profit growth below 8% YoY benchmark")

        if "low_debt" in norm_prefs:
            if snapshot.debt_to_equity <= 0.4:
                score += 5.0
                matched_reasons.append(f"Low leverage structure (Debt/Equity {snapshot.debt_to_equity:.2f})")
            elif snapshot.debt_to_equity <= 0.8:
                score += 2.0
                matched_reasons.append(f"Manageable debt (Debt/Equity {snapshot.debt_to_equity:.2f})")
            else:
                score -= 3.0
                risk_notes.append(f"Elevated debt-to-equity ({snapshot.debt_to_equity:.2f})")

        if "valuation" in norm_prefs:
            if 0 < snapshot.pe_ratio <= 28.0:
                score += 4.0
                matched_reasons.append(f"Favorable earnings multiple (P/E {snapshot.pe_ratio:.1f})")
            elif snapshot.pe_ratio > 50.0:
                risk_notes.append(f"Elevated valuation multiple (P/E {snapshot.pe_ratio:.1f})")

        # Promoter pledge check (Risk invariant)
        if snapshot.pledged_shares_pct > 20.0:
            score -= 5.0
            risk_notes.append(f"High promoter pledge warning ({snapshot.pledged_shares_pct:.1f}%)")

        score = max(0.0, min(30.0, score))
        return True, score, matched_reasons, risk_notes
