# stock/stock_scoring.py
"""
Multi-Factor Composite Scoring Engine for Stock Query Wizard.
Combines technical alignment (0-40), fundamental health (0-30),
risk suitability (0-20), and user objective/sector fit (0-10) into a transparent 0-100 score.
"""

from typing import Any, Dict, List, Optional, Tuple


class StockCompositeScorer:
    """Calculates multi-factor candidate scores and ranks shortlists."""

    @staticmethod
    def calculate_score(
        tech_score: float,
        fund_score: float,
        risk_score: float,
        objectives: List[str],
        sectors: List[str],
        candidate_sector: str,
        horizon: str,
        is_large_cap: bool,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculates composite score from component scores plus alignment bonus.
        Returns:
            (total_score_0_to_100, breakdown_dict)
        """
        # Component weights: Tech (max 40), Fund (max 30), Risk (max 20), Objective/Fit (max 10)
        fit_score = 5.0  # Base fit

        norm_objs = [o.lower().strip().replace(" ", "_") for o in objectives]
        norm_sectors = [s.lower().strip() for s in sectors]

        # Sector alignment bonus
        if norm_sectors and not any(s in ("any", "any_sector", "all") for s in norm_sectors):
            if candidate_sector.lower() in norm_sectors:
                fit_score += 3.0

        # Objective alignment bonus
        if "dividend_income" in norm_objs and is_large_cap:
            fit_score += 2.0
        if "growth" in norm_objs or "capital_growth" in norm_objs:
            fit_score += 2.0
        if "momentum" in norm_objs or "breakout" in norm_objs:
            fit_score += 2.0
        if "long_term_compounder" in norm_objs or "compounder" in norm_objs:
            fit_score += 2.0

        fit_score = min(10.0, fit_score)
        total = tech_score + fund_score + risk_score + fit_score
        total_clamped = round(max(0.0, min(100.0, total)), 1)

        breakdown = {
            "technical": round(tech_score, 1),
            "fundamental": round(fund_score, 1),
            "risk_fit": round(risk_score, 1),
            "objective_alignment": round(fit_score, 1),
            "composite": total_clamped,
        }
        return total_clamped, breakdown
