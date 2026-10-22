# stock/stock_screener.py
"""
Central Screening Pipeline Orchestrator for Stock Query Wizard.
Executes:
Parameters -> Validation -> Universe Selection -> Fundamental Filter ->
Technical Filter -> Liquidity/Quality Filter -> Risk Check -> Scoring ->
Candidate Shortlist -> Explanation Generation.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from core.equity_research.market_data_provider import MarketDataProvider
from .stock_explanation import StockExplanationEngine
from .stock_fundamental import StockFundamentalFilter
from .stock_models import StockAnalysisResponse, StockCandidateResult, StockQueryParams
from .stock_risk import StockRiskEvaluator
from .stock_scoring import StockCompositeScorer
from .stock_targets import StockTargetEngine
from .stock_technical import StockTechnicalFilter

logger = logging.getLogger("jarvis.stock.screener")


class StockScreener:
    """Executes multi-stage stock filtering and ranking according to user parameters."""

    def __init__(
        self,
        data_provider: Optional[MarketDataProvider] = None,
        fundamental_filter: Optional[StockFundamentalFilter] = None,
        technical_filter: Optional[StockTechnicalFilter] = None,
        risk_evaluator: Optional[StockRiskEvaluator] = None,
    ):
        self.data_provider = data_provider or MarketDataProvider()
        self.fundamental_filter = fundamental_filter or StockFundamentalFilter()
        self.technical_filter = technical_filter or StockTechnicalFilter()
        self.risk_evaluator = risk_evaluator or StockRiskEvaluator()
        self.scorer = StockCompositeScorer()
        self.explainer = StockExplanationEngine()

    def run_screening(self, params: StockQueryParams) -> StockAnalysisResponse:
        """Runs the end-to-end multi-dimensional screening pipeline."""
        now_dt = self.data_provider.get_current_time_ist()
        market_status, last_session = self.data_provider.get_market_status()
        timestamp_str = now_dt.strftime("%d %b %Y, %H:%M IST")

        # 1. Universe Selection
        # Resolve sector preference: if 'Any' or empty, consider all sectors
        sector_filter = None
        if params.sectors:
            valid_secs = [s for s in params.sectors if s.lower() not in ("any", "any_sector", "all")]
            if len(valid_secs) == 1:
                sector_filter = valid_secs[0]

        universe = self.data_provider.get_stock_universe(sector_filter=sector_filter)
        total_scanned = len(universe)

        index_data = self.data_provider.get_index_metrics()
        nifty_ret = float(index_data.get("nifty_50", {}).get("change_pct", 0.0))

        candidates: List[StockCandidateResult] = []

        for item in universe:
            sym = item["symbol"]
            company_name = item["name"]
            sector = item["sector"]
            adtv_cr = float(item.get("adtv_cr", 50.0))

            # Market Cap determination
            is_large_cap = adtv_cr >= 100.0 or "TCS" in sym or "RELIANCE" in sym or "HDFCBANK" in sym or "INFY" in sym or "ICICIBANK" in sym or "BHARTIARTL" in sym
            is_mid_cap = 20.0 <= adtv_cr < 100.0 and not is_large_cap
            is_small_cap = adtv_cr < 20.0

            mcap_str = "Large Cap" if is_large_cap else ("Mid Cap" if is_mid_cap else "Small Cap")

            # Check Market Cap filter
            if params.market_cap and not any(m.lower() in ("any", "all") for m in params.market_cap):
                norm_mcaps = [m.lower().replace(" ", "_") for m in params.market_cap]
                matches_mcap = False
                if "large_cap" in norm_mcaps and is_large_cap:
                    matches_mcap = True
                if "mid_cap" in norm_mcaps and is_mid_cap:
                    matches_mcap = True
                if "small_cap" in norm_mcaps and is_small_cap:
                    matches_mcap = True
                if not matches_mcap:
                    continue

            # Check Sector filter if multiple sectors requested
            if params.sectors and not any(s.lower() in ("any", "any_sector", "all") for s in params.sectors):
                norm_secs = [s.lower().strip() for s in params.sectors]
                matches_sec = False
                for s in norm_secs:
                    if s == sector.lower():
                        matches_sec = True
                        break
                    elif len(s) > 2 and s in sector.lower():
                        matches_sec = True
                        break
                    elif len(s) <= 2 and re.search(r'\b' + re.escape(s) + r'\b', sector, re.I):
                        matches_sec = True
                        break
                if not matches_sec:
                    continue

            # Retrieve price action bars
            bars = self.data_provider.get_stock_ohlcv(sym, lookback_days=200)
            if not bars:
                continue

            latest_close = bars[-1].close

            # Price range filter
            if params.price_min is not None and latest_close < params.price_min:
                continue
            if params.price_max is not None and latest_close > params.price_max:
                continue

            # Budget check: if capital is under stock price (e.g. user budget ₹1,000 but stock is ₹2,500)
            if params.capital is not None and params.capital > 0 and latest_close > params.capital:
                # Stock price exceeds total capital
                continue

            # 2. Technical Evaluation
            tech = self.technical_filter.analyze_bars(bars, nifty_return_pct=nifty_ret)
            t_pass, t_score, t_reasons, t_risks = self.technical_filter.evaluate(
                tech=tech,
                current_price=latest_close,
                preferences=params.technical_preferences,
                horizon=params.horizon,
            )
            if not t_pass:
                continue

            # 3. Fundamental Evaluation
            funds = self.fundamental_filter.get_snapshot(sym)
            f_pass, f_score, f_reasons, f_risks = self.fundamental_filter.evaluate(
                snapshot=funds,
                preferences=params.fundamental_preferences,
                exclusions=params.exclusions,
            )
            if not f_pass:
                continue

            # 4. Risk & Suitability Evaluation
            r_pass, r_score, r_reasons, r_risks = self.risk_evaluator.evaluate_suitability(
                current_price=latest_close,
                tech=tech,
                adtv_cr=adtv_cr,
                risk_preference=params.risk,
                exclusions=params.exclusions,
            )
            if not r_pass:
                continue

            # 5. Composite Scoring
            total_score, breakdown = self.scorer.calculate_score(
                tech_score=t_score,
                fund_score=f_score,
                risk_score=r_score,
                objectives=params.objective,
                sectors=params.sectors,
                candidate_sector=sector,
                horizon=params.horizon,
                is_large_cap=is_large_cap,
            )

            # Filter candidates with low composite score (< 50)
            if total_score < 50.0:
                continue

            # Scenario Modeling
            scenario = self.risk_evaluator.evaluate_scenarios(
                current_price=latest_close,
                tech=tech,
                market_regime="BULLISH",
            )

            # Build explainable result
            why_matched = t_reasons + f_reasons + r_reasons
            all_risks = t_risks + f_risks + r_risks

            cand_result = self.explainer.build_candidate_result(
                symbol=sym,
                company_name=company_name,
                sector=sector,
                current_price=latest_close,
                market_cap_str=mcap_str,
                tech=tech,
                fundamentals=funds,
                scenario=scenario,
                score=total_score,
                why_matched=why_matched,
                risks=all_risks,
                data_timestamp=timestamp_str,
                data_source="NSE_EQUITY_FEED",
                market_status=market_status.value if hasattr(market_status, "value") else str(market_status),
            )
            target_plan = StockTargetEngine.derive_target_exit_plan(
                price=latest_close,
                technical_data={
                    "atr": getattr(tech, "atr", None),
                    "high_52w": getattr(tech, "high_52w", None),
                    "ema_20": getattr(tech, "ema_20", None),
                },
                horizon=params.horizon,
                risk=params.risk,
            )
            cand_result.reference_price = target_plan.reference_price
            cand_result.target_1 = target_plan.target_1
            cand_result.target_2 = target_plan.target_2
            cand_result.target_method = target_plan.target_method
            cand_result.invalidation_price = target_plan.invalidation_price
            cand_result.invalidation_level = target_plan.invalidation_price
            cand_result.holding_period_days = target_plan.holding_period_days
            cand_result.time_exit_date = target_plan.time_exit_date

            candidates.append(cand_result)

        # Sort by composite score descending
        candidates.sort(key=lambda c: c.score, reverse=True)

        # Limit to top 6 best matching candidates for clarity
        shortlist = candidates[:6]
        voice_resp = self.explainer.generate_voice_summary(
            candidates=shortlist,
            total_scanned=total_scanned,
        )

        return StockAnalysisResponse(
            success=True,
            market_status=market_status.value if hasattr(market_status, "value") else str(market_status),
            data_timestamp=timestamp_str,
            data_source="NSE_EQUITY_FEED",
            is_market_open=(market_status.value == "OPEN") if hasattr(market_status, "value") else True,
            candidates=shortlist,
            total_scanned=total_scanned,
            total_matched=len(shortlist),
            applied_filters=params.model_dump(),
            voice_response=voice_resp,
        )
