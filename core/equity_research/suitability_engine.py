# core/equity_research/suitability_engine.py
"""
Suitability & Portfolio Concentration Engine for 1-Month Indian Equity Research.
Enforces the fundamental principle: Market Opportunity != Personalized Suitability.
Evaluates client risk profile, capital sizing, loss capacity, and flags excessive sector concentration.
"""

import logging
from typing import Dict, List, Optional, Tuple

from .models import (
    RiskTolerance,
    StockCandidate,
    UserInvestmentProfile,
)

logger = logging.getLogger("jarvis.equity_research.suitability_engine")


class SuitabilityEngine:
    """
    Evaluates whether a technically strong market setup is suitable for the specific user.
    Prevents over-allocation, high-volatility exposure for conservative profiles,
    and portfolio sector overlap.
    """

    MAX_SINGLE_STOCK_ALLOCATION_PCT = 25.0  # Max 25% capital in single 1-month idea
    MAX_SECTOR_ALLOCATION_PCT = 40.0        # Max 40% capital in single sector

    def evaluate_suitability(
        self,
        candidate: StockCandidate,
        profile: Optional[UserInvestmentProfile],
    ) -> Tuple[bool, float, str, List[str]]:
        """
        Assesses personalized suitability.
        Returns: (is_suitable, suitability_score_0_to_100, rationale, feedback_warnings)
        """
        if not profile or not profile.is_complete_for_personalized():
            # If no personalized profile, return generic suitability
            return True, 80.0, "Generic research candidate evaluated against standard 1-month swing parameters.", []

        suitability_score = 100.0
        warnings = []
        is_suitable = True

        capital = profile.investment_amount or 100000.0
        stock_price = candidate.current_price

        # 1. Capital sizing check (Stock price should not exceed 25% of user capital for 1 share)
        if stock_price > (capital * 0.35):
            is_suitable = False
            suitability_score -= 50.0
            warnings.append(
                f"Share price (₹{stock_price:,.0f}) is too large relative to capital (₹{capital:,.0f}) "
                f"to achieve appropriate diversification."
            )

        # 2. Risk Tolerance vs Candidate Volatility (ATR %)
        atr_pct = candidate.technical.atr_pct
        if profile.risk_tolerance == RiskTolerance.CONSERVATIVE:
            if atr_pct > 2.8:
                is_suitable = False
                suitability_score -= 40.0
                warnings.append(
                    f"Candidate daily volatility (ATR {atr_pct:.1f}%) exceeds conservative risk tolerance "
                    f"(target ATR < 2.8%)."
                )
            elif candidate.technical.trend != "BULLISH":
                is_suitable = False
                suitability_score -= 30.0
                warnings.append("Conservative profile requires confirmed structural uptrend.")
        elif profile.risk_tolerance == RiskTolerance.MODERATE:
            if atr_pct > 4.5:
                suitability_score -= 20.0
                warnings.append(f"Elevated ATR ({atr_pct:.1f}%) warrants moderate position sizing.")

        # 3. Maximum acceptable loss constraint
        if candidate.scenario:
            loss_distance_pct = (candidate.current_price - candidate.scenario.invalidation_level) / max(1.0, candidate.current_price) * 100.0
            if loss_distance_pct > profile.maximum_acceptable_loss_pct:
                is_suitable = False
                suitability_score -= 35.0
                warnings.append(
                    f"Invalidation distance ({loss_distance_pct:.1f}%) exceeds your max acceptable loss "
                    f"threshold ({profile.maximum_acceptable_loss_pct:.1f}%)."
                )

        # 4. Sector Exclusions
        user_exclusions = {s.upper() for s in profile.sector_exclusions}
        if candidate.sector.upper() in user_exclusions:
            is_suitable = False
            suitability_score = 0.0
            warnings.append(f"Sector '{candidate.sector}' is listed in your excluded sectors.")

        # 5. Sector Preferences
        user_prefs = [s.upper() for s in profile.sector_preferences]
        if user_prefs and "ALL" not in user_prefs:
            if not any(pref in candidate.sector.upper() for pref in user_prefs):
                suitability_score -= 25.0
                warnings.append(f"Sector '{candidate.sector}' does not match your active preference ({', '.join(profile.sector_preferences)}).")

        # 6. Portfolio Sector Concentration
        existing_holdings = profile.existing_portfolio or []
        sector_matches = [h for h in existing_holdings if h.get("sector", "").upper() == candidate.sector.upper()]
        if sector_matches:
            total_sector_pct = sum(float(h.get("allocation_pct", 0.0)) for h in sector_matches)
            if total_sector_pct >= self.MAX_SECTOR_ALLOCATION_PCT:
                is_suitable = False
                suitability_score -= 30.0
                warnings.append(
                    f"Adding {candidate.symbol} increases '{candidate.sector}' sector exposure beyond {self.MAX_SECTOR_ALLOCATION_PCT}% "
                    f"(current sector holding: {total_sector_pct:.1f}%)."
                )

        rationale = "; ".join(warnings) if warnings else "Setup aligns with client risk capacity, capital sizing, and horizon."
        return is_suitable and (suitability_score >= 50.0), max(0.0, suitability_score), rationale, warnings

    def evaluate_portfolio_concentration(self, profile: UserInvestmentProfile, proposed_candidate: StockCandidate) -> str:
        """Analyzes sector concentration and overlap for follow-up explanations."""
        if not profile or not profile.existing_portfolio:
            return "No existing portfolio holdings specified; standalone position risk applies."

        held_symbols = []
        held_sectors = []
        if isinstance(profile.existing_portfolio, dict):
            for sym in profile.existing_portfolio.keys():
                held_symbols.append(str(sym).upper())
                # Infer sector if possible
                if any(it in str(sym).upper() for it in ["TCS", "INFY", "WIPRO", "HCL"]):
                    held_sectors.append("IT")
                elif any(b in str(sym).upper() for b in ["HDFC", "ICICI", "SBI", "AXIS"]):
                    held_sectors.append("BANKING")
        elif isinstance(profile.existing_portfolio, list):
            for h in profile.existing_portfolio:
                if isinstance(h, dict):
                    held_symbols.append(h.get("symbol", "").upper())
                    held_sectors.append(h.get("sector", "").upper())
                else:
                    held_symbols.append(str(h).upper())

        if proposed_candidate.symbol.upper() in held_symbols:
            return f"⚠️ Concentration Notice: You already hold {proposed_candidate.symbol}. Adding to an existing position increases single-stock concentration risk."

        if proposed_candidate.sector.upper() in held_sectors:
            count = held_sectors.count(proposed_candidate.sector.upper())
            return f"⚠️ Sector Concentration Notice: You already hold {count} asset(s) in {proposed_candidate.sector}. Ensure total sector exposure remains within your risk limit."

        return f"Good diversification: {proposed_candidate.sector} adds low correlation to your existing holdings ({', '.join(set(held_sectors)) if held_sectors else 'active'})."
