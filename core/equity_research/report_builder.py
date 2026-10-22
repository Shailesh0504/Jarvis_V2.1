# core/equity_research/report_builder.py
"""
Research Report Builder for 1-Month Indian Equity Setups.
Formats transparent, human-readable research outputs across QUICK, STANDARD, and DETAILED modes.
Strictly adheres to:
- Explanation-first structure (Why considered -> Invalidation -> Key risks)
- No guaranteed returns or certainty claims
- Data timestamp & Market status transparency
- SEBI / Advisory compliance disclaimers
"""

import logging
from typing import List, Optional

from .models import (
    MarketStatus,
    OutputMode,
    ResearchReport,
    StockCandidate,
)

logger = logging.getLogger("jarvis.equity_research.report_builder")


class ReportBuilder:
    """
    Generates structured, explainable research reports for Indian equities.
    """

    @classmethod
    def build_report(
        cls,
        report: ResearchReport,
        language: str = "hi",
    ) -> str:
        """Renders the research report according to selected output mode and language."""
        if report.output_mode == OutputMode.QUICK:
            return cls._build_quick_report(report, language)
        elif report.output_mode == OutputMode.DETAILED:
            return cls._build_detailed_report(report, language)
        else:
            return cls._build_standard_report(report, language)

    @classmethod
    def _build_standard_report(cls, report: ResearchReport, language: str) -> str:
        lines = []

        # Header & Market Context
        is_closed = report.market_status == MarketStatus.CLOSED
        status_tag = f"Market: CLOSED (Data reflects session: {report.last_trading_session})" if is_closed else "Market: LIVE / OPEN"

        lines.append("📊 **1-Month Indian Equity Research (Decision Support)**")
        lines.append(f"• {status_tag} | Timestamp: {report.generated_at}")
        lines.append(f"• **Market Regime**: {report.market_regime.value}")
        lines.append(f"  _{report.regime_rationale}_")
        lines.append("")

        if not report.candidates:
            lines.append("⚠️ **No Suitable Candidates Found**")
            lines.append("Current market regime, liquidity constraints, or risk parameters do not present a high-confidence setup meeting our 1-month risk-to-reward criteria.")
            lines.append("Review scheduled for next market session.")
            lines.append("")
            lines.append(f"_{report.disclaimer}_")
            return "\n".join(lines)

        lines.append(f"🔎 **Shortlisted Candidates (1-Month Horizon | Scanned: {report.universe_size_scanned} stocks):**\n")

        for idx, c in enumerate(report.candidates, 1):
            price_label = f"Closing Price: ₹{c.closing_price:,.2f}" if is_closed else f"Current Price: ₹{c.current_price:,.2f}"

            lines.append(f"### {idx}. {c.company_name} (`{c.symbol}`)")
            lines.append(f"• **Sector**: {c.sector} | **{price_label}**")
            lines.append(f"• **Evidence Tier**: {c.evidence_tier.value} (Score: {c.multi_factor_score}/100) | Strategy: `{c.strategy_matched}`")
            lines.append("")
            lines.append("  **Why It Is Being Considered:**")
            lines.append(f"  - **Trend**: {c.technical.trend} (Price vs 20 EMA: ₹{c.technical.ema_20:.1f}, 50 EMA: ₹{c.technical.ema_50:.1f})")
            lines.append(f"  - **Momentum**: RSI {c.technical.rsi:.1f} with MACD hist {c.technical.macd_hist:+.2f}")
            lines.append(f"  - **Volume**: {c.technical.volume_trend} ({c.technical.volume_ratio:.1f}x 20-day average{' - Breakout Confirmed' if c.technical.volume_breakout else ''})")
            lines.append(f"  - **Relative Strength**: {c.technical.relative_strength_nifty:+.1f}% vs NIFTY 50 over 1 month")

            if c.catalysts:
                cat = c.catalysts[0]
                lines.append(f"  - **Upcoming Catalyst**: {cat.event_type} on {cat.event_date} ({cat.description})")

            if c.scenario:
                sc = c.scenario
                lines.append("")
                lines.append("  **Analytical Levels (Risk Management Coordinates, NOT Guaranteed Prices):**")
                lines.append(f"  - Entry Zone: ₹{sc.entry_zone[0]:,.1f} – ₹{sc.entry_zone[1]:,.1f}")
                lines.append(f"  - Invalidation Stop: ₹{sc.invalidation_level:,.1f}")
                lines.append(f"  - Base Target Zone (1-Month): ₹{sc.base_case.target_zone[0]:,.1f} – ₹{sc.base_case.target_zone[1]:,.1f} (R:R ~{sc.reward_to_risk_ratio}:1)")

            lines.append("")
            lines.append("  **What Can Invalidate The Thesis:**")
            lines.append(f"  - Daily close below support floor ₹{c.technical.support_level:.1f}")
            lines.append("  - Reversal of relative strength vs broader market")
            lines.append("  - Adverse catalyst outcome or macro regime shift")

            lines.append("")
            lines.append("  **Key Risks:**")
            for r in c.key_risks[:2]:
                lines.append(f"  - {r}")
            lines.append(f"  - Horizon: Review scheduled before {c.review_date} (Expiry: {c.expiry_date})")
            lines.append("-" * 40)

        if report.portfolio_concentration_feedback:
            lines.append(f"📌 **Portfolio Concentration Check**: {report.portfolio_concentration_feedback}\n")

        lines.append(f"⚖️ *{report.disclaimer}*")
        return "\n".join(lines)

    @classmethod
    def _build_quick_report(cls, report: ResearchReport, language: str) -> str:
        lines = []
        is_closed = report.market_status == MarketStatus.CLOSED
        status_tag = f"Market CLOSED ({report.last_trading_session})" if is_closed else "Market LIVE"

        lines.append("⚡ **1-Month Indian Equity Research Shortlist**")
        lines.append(f"Regime: {report.market_regime.value} | {status_tag}\n")

        if not report.candidates:
            lines.append("No suitable candidates meeting 1-month risk-reward criteria at this time.")
            return "\n".join(lines)

        for idx, c in enumerate(report.candidates, 1):
            sc = c.scenario
            price = c.closing_price if is_closed else c.current_price
            inval = f" | Invalidation: ₹{sc.invalidation_level:.1f}" if sc else ""
            lines.append(f"{idx}. **{c.symbol}** ({c.company_name}) — ₹{price:,.1f}")
            lines.append(f"   • Thesis: {c.evidence_tier.value} | RSI {c.technical.rsi:.0f} | RS {c.technical.relative_strength_nifty:+.1f}% vs Nifty{inval}")
            if c.key_risks:
                lines.append(f"   • Top Risk: {c.key_risks[0]}")
            lines.append("")

        lines.append(f"_{report.disclaimer}_")
        return "\n".join(lines)

    @classmethod
    def _build_detailed_report(cls, report: ResearchReport, language: str) -> str:
        # Detailed extends Standard with Scenarios and Fundamentals
        std = cls._build_standard_report(report, language)
        extra = []
        extra.append("\n### 🔬 Detailed Scenario Analysis & Fundamentals:")
        for c in report.candidates:
            extra.append(f"**{c.symbol} Scenario Breakdown:**")
            if c.scenario:
                sc = c.scenario
                extra.append(f"  • Bull Case: ₹{sc.bull_case.target_zone[0]:,.1f} – ₹{sc.bull_case.target_zone[1]:,.1f} ({sc.bull_case.conditions})")
                extra.append(f"  • Base Case: ₹{sc.base_case.target_zone[0]:,.1f} – ₹{sc.base_case.target_zone[1]:,.1f} ({sc.base_case.conditions})")
                extra.append(f"  • Bear Case: ₹{sc.bear_case.target_zone[0]:,.1f} – ₹{sc.bear_case.target_zone[1]:,.1f} ({sc.bear_case.conditions})")
            f = c.fundamentals
            extra.append(f"  • Fundamental Context: Revenue Growth: {f.revenue_growth_yoy:.1f}%, Profit Growth: {f.profit_growth_yoy:.1f}%, P/E: {f.pe_ratio:.1f}, Debt/Eq: {f.debt_to_equity:.2f}, Pledged: {f.pledged_shares_pct}%\n")

        return std + "\n".join(extra)


EquityReportBuilder = ReportBuilder
