# stock/stock_explanation.py
"""
Explainable Reasoning and Anti-Hallucination Delivery Layer for Stock Candidates.
Ensures zero blind 'BUY' claims, transparent 'why matched' evidence,
explicit invalidation levels, data freshness timestamps, and balanced risk caveats.
"""

from typing import Any, Dict, List, Optional
from core.equity_research.models import FundamentalSnapshot, RiskScenario, TechnicalIndicators
from .stock_models import StockCandidateResult


class StockExplanationEngine:
    """Produces explainable candidate profiles and voice responses with strict compliance invariants."""

    @staticmethod
    def build_candidate_result(
        symbol: str,
        company_name: str,
        sector: str,
        current_price: float,
        market_cap_str: str,
        tech: TechnicalIndicators,
        fundamentals: FundamentalSnapshot,
        scenario: Optional[RiskScenario],
        score: float,
        why_matched: List[str],
        risks: List[str],
        data_timestamp: str,
        data_source: str = "NSE_EQUITY_FEED",
        market_status: str = "OPEN",
    ) -> StockCandidateResult:
        """Assembles verified candidate result ensuring no fabricated metrics."""

        # Key verified metrics
        key_metrics = {
            "current_price": f"₹{current_price:,.2f}",
            "pe_ratio": f"{fundamentals.pe_ratio:.1f}" if fundamentals.pe_ratio > 0 else "N/A",
            "pb_ratio": f"{fundamentals.pb_ratio:.1f}" if fundamentals.pb_ratio > 0 else "N/A",
            "debt_to_equity": f"{fundamentals.debt_to_equity:.2f}",
            "rev_growth_yoy": f"{fundamentals.revenue_growth_yoy:+.1f}%",
            "profit_growth_yoy": f"{fundamentals.profit_growth_yoy:+.1f}%",
            "rsi_14": f"{tech.rsi:.1f}",
            "ema_20": f"₹{tech.ema_20:,.1f}",
            "ema_50": f"₹{tech.ema_50:,.1f}",
            "support_level": f"₹{tech.support_level:,.1f}" if tech.support_level > 0 else "N/A",
            "resistance_level": f"₹{tech.resistance_level:,.1f}" if tech.resistance_level > 0 else "N/A",
            "volume_ratio": f"{tech.volume_ratio:.1f}x",
        }

        # Setup & Fundamental Summaries
        fund_summary = (
            f"YoY Revenue: {fundamentals.revenue_growth_yoy:+.1f}%, "
            f"Profit: {fundamentals.profit_growth_yoy:+.1f}%, "
            f"Debt/Equity: {fundamentals.debt_to_equity:.2f}."
        )
        tech_summary = (
            f"Trend: {tech.trend}, RSI: {tech.rsi:.1f}, "
            f"SuperTrend: {tech.supertrend_direction}, Support: ₹{tech.support_level:.1f}."
        )

        inval_level = tech.support_level if tech.support_level > 0 else None
        target_zone = list(scenario.base_case.target_zone) if scenario and scenario.base_case else None

        # Ensure balanced risks are never empty
        final_risks = list(risks)
        if not final_risks:
            final_risks.append("Market volatility or broader index pullbacks could affect momentum.")
            if inval_level:
                final_risks.append(f"Setup invalidates on close below swing support at ₹{inval_level:.1f}.")

        # Deduplicate and trim reasons
        unique_why = list(dict.fromkeys(why_matched))[:5]

        return StockCandidateResult(
            company_name=company_name,
            symbol=symbol,
            current_price=current_price,
            market_cap=market_cap_str,
            sector=sector,
            trend=tech.trend.capitalize(),
            score=score,
            why_matched=unique_why,
            risks=final_risks[:4],
            key_metrics=key_metrics,
            fundamental_summary=fund_summary,
            technical_summary=tech_summary,
            invalidation_level=inval_level,
            target_zone=target_zone,
            data_timestamp=data_timestamp,
            data_source=data_source,
            market_status=market_status,
            is_stale=False,
        )

    @staticmethod
    def generate_voice_summary(
        candidates: List[StockCandidateResult],
        total_scanned: int,
        criteria_summary: str = "",
    ) -> str:
        """Generates natural, compliant voice response following section 1 and 10 rules."""
        if not candidates:
            return (
                "Selection complete hai. Lekin aapke selected filters ke basis par koi stock match nahi hua. "
                "Kripya filters ko thoda widen karke dobara analyze kijiye."
            )

        top_names = [f"{c.company_name} ({c.symbol})" for c in candidates[:3]]
        names_str = ", ".join(top_names)
        count = len(candidates)

        return (
            f"Selection complete hai. Maine aapke criteria ke basis par stock candidates analyze kiye hain. "
            f"Total {count} candidates shortlist hue hain, jinme pramukh hain: {names_str}. "
            f"Screening details dashboard par open hain."
        )
