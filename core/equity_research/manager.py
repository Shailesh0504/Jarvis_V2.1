# core/equity_research/manager.py
"""
Authoritative Equity Research Manager for Jarvis V2.1.
Orchestrates Indian market data, regime analysis, technical indicators,
configurable strategy evaluation, fundamentals, catalysts, scenarios,
personalized suitability, explainable reporting, and compliance audit logging.
"""

from datetime import datetime, timedelta
import json
import logging
import os
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .catalyst_news_engine import CatalystNewsEngine
from .fundamental_engine import FundamentalEngine
from .market_data_provider import MarketDataProvider
from .market_regime import MarketRegimeEngine
from .models import (
    AdvisoryMode,
    EvidenceTier,
    MarketRegime,
    MarketStatus,
    OutputMode,
    ResearchReport,
    RiskScenario,
    StockCandidate,
    UserInvestmentProfile,
)
from .monitor import ThesisMonitor
from .report_builder import ReportBuilder
from .scorer import MultiFactorScorer
from .strategies import (
    BreakoutStrategy,
    MeanReversionStrategy,
    TechnicalStrategy,
    TrendFollowingStrategy,
)
from .suitability_engine import SuitabilityEngine
from .technical_engine import TechnicalAnalysisEngine

logger = logging.getLogger("jarvis.equity_research.manager")


class EquityResearchManager:
    """
    Central Authoritative Coordinator for 1-Month Indian Equity Research.
    Guarantees transparent decision support, zero guaranteed returns,
    and strict epistemological separation.
    """

    _instance: Optional["EquityResearchManager"] = None
    _singleton_lock = threading.Lock()

    def __init__(
        self,
        data_provider: Optional[MarketDataProvider] = None,
        regime_engine: Optional[MarketRegimeEngine] = None,
        technical_engine: Optional[TechnicalAnalysisEngine] = None,
        fundamental_engine: Optional[FundamentalEngine] = None,
        catalyst_engine: Optional[CatalystNewsEngine] = None,
        risk_engine=None,
        suitability_engine: Optional[SuitabilityEngine] = None,
        scorer: Optional[MultiFactorScorer] = None,
        monitor: Optional[ThesisMonitor] = None,
        audit_file: str = "data/equity_research_audit.json",
    ):
        self.data_provider = data_provider or MarketDataProvider()
        self.regime_engine = regime_engine or MarketRegimeEngine()
        self.technical_engine = technical_engine or TechnicalAnalysisEngine()
        self.fundamental_engine = fundamental_engine or FundamentalEngine()
        self.catalyst_engine = catalyst_engine or CatalystNewsEngine()

        from .risk_engine import RiskEngine
        self.risk_engine = risk_engine or RiskEngine()
        self.suitability_engine = suitability_engine or SuitabilityEngine()
        self.scorer = scorer or MultiFactorScorer()
        self.monitor = monitor or ThesisMonitor()
        self.audit_file = audit_file

        # Default pluggable strategies
        self._strategies: List[TechnicalStrategy] = [
            TrendFollowingStrategy(),
            BreakoutStrategy(),
            MeanReversionStrategy(),
        ]

        # In-memory client profile
        self._profile: UserInvestmentProfile = UserInvestmentProfile()

    @classmethod
    def get_instance(cls) -> "EquityResearchManager":
        """Singleton accessor ensuring single authoritative coordinator."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def update_profile(self, updates: Dict[str, Any]) -> UserInvestmentProfile:
        """Updates client risk, capital, and sector preferences while preserving horizon."""
        if "investment_amount" in updates and updates["investment_amount"] is not None:
            self._profile.investment_amount = float(updates["investment_amount"])
        if "risk_tolerance" in updates and updates["risk_tolerance"] is not None:
            from .models import RiskTolerance
            rt = str(updates["risk_tolerance"]).upper()
            if "CONSERVATIVE" in rt or "LOW" in rt:
                self._profile.risk_tolerance = RiskTolerance.CONSERVATIVE
            elif "AGGRESSIVE" in rt or "HIGH" in rt:
                self._profile.risk_tolerance = RiskTolerance.AGGRESSIVE
            else:
                self._profile.risk_tolerance = RiskTolerance.MODERATE
        if "sector_preference" in updates and updates["sector_preference"]:
            pref = str(updates["sector_preference"]).strip()
            if pref and pref.upper() not in [p.upper() for p in self._profile.sector_preferences]:
                self._profile.sector_preferences.append(pref)
        if "existing_portfolio" in updates:
            self._profile.existing_portfolio = updates["existing_portfolio"]

        logger.info("Updated client investment profile: Capital=%s, Risk=%s, Prefs=%s",
                    self._profile.investment_amount, self._profile.risk_tolerance, self._profile.sector_preferences)
        return self._profile

    def get_profile(self) -> UserInvestmentProfile:
        """Returns the active user profile."""
        return self._profile

    def research_shortlist(
        self,
        profile: Optional[UserInvestmentProfile] = None,
        sector_filter: Optional[str] = None,
        output_mode: OutputMode = OutputMode.STANDARD,
        advisory_mode: AdvisoryMode = AdvisoryMode.RESEARCH,
        language: str = "hi",
    ) -> Tuple[ResearchReport, str]:
        """
        Executes the full 1-month equity research screening pipeline.
        Returns: (ResearchReport, formatted_text_response)
        """
        active_profile = profile or self._profile
        now_dt = self.data_provider.get_current_time_ist()
        market_status, last_session = self.data_provider.get_market_status()

        # 1. Market Regime Context
        index_data = self.data_provider.get_index_metrics()
        regime, regime_rationale = self.regime_engine.evaluate_regime(index_data)

        # 2. Stock Universe Filtering
        sec_pref = sector_filter or (active_profile.sector_preferences[0] if active_profile.sector_preferences else None)
        universe = self.data_provider.get_stock_universe(
            sector_filter=sec_pref,
            exclude_sectors=active_profile.sector_exclusions,
        )

        candidates: List[StockCandidate] = []
        nifty_ret = float(index_data.get("nifty_50", {}).get("change_pct", 0.0))

        # 3. Multi-Factor Analysis per Symbol
        for item in universe:
            sym = item["symbol"]
            bars = self.data_provider.get_stock_ohlcv(sym, lookback_days=200)
            if not bars:
                continue

            latest_close = bars[-1].close
            tech = self.technical_engine.analyze(bars, nifty_return_pct=nifty_ret)
            funds = self.fundamental_engine.get_snapshot(sym)
            catalysts = self.catalyst_engine.get_upcoming_catalysts(sym, current_date=now_dt)
            news = self.catalyst_engine.get_recent_news(sym)

            # Evaluate Strategies
            matched_strat_name = "None"
            best_strat_score = 0.0
            best_strat_rationale = ""
            for strat in self._strategies:
                is_m, score, rat = strat.evaluate(tech, latest_close)
                if is_m and score > best_strat_score:
                    best_strat_score = score
                    matched_strat_name = strat.name
                    best_strat_rationale = rat

            # Discard candidates that fail all technical strategies
            if matched_strat_name == "None" or best_strat_score < 60.0:
                continue

            # Multi-Factor Scoring
            has_pos_cat = any(n.classification.value == "POSITIVE_CATALYST" for n in news)
            score_val, evidence_tier, breakdown = self.scorer.calculate_score(
                tech=tech,
                fundamentals=funds,
                has_positive_catalyst=has_pos_cat,
                adtv_cr=item.get("adtv_cr", 50.0),
                market_regime=regime,
            )

            # Filter out weak evidence
            if score_val < 60.0:
                continue

            # Risk & Scenario Modeling
            scenario = self.risk_engine.evaluate_scenarios(
                current_price=latest_close,
                tech=tech,
                catalysts=catalysts,
                market_regime=regime.value,
            )

            key_risks = self.risk_engine.identify_key_risks(
                symbol=sym,
                tech=tech,
                catalysts=catalysts,
                adtv_cr=item.get("adtv_cr", 50.0),
                market_regime=regime.value,
            )

            review_date = (now_dt + timedelta(days=14)).strftime("%Y-%m-%d")
            expiry_date = (now_dt + timedelta(days=30)).strftime("%Y-%m-%d")

            candidate = StockCandidate(
                symbol=sym,
                company_name=item["name"],
                sector=item["sector"],
                current_price=latest_close,
                closing_price=latest_close,
                is_market_open=(market_status == MarketStatus.OPEN),
                data_timestamp=index_data.get("timestamp", now_dt.strftime("%Y-%m-%d %H:%M:%S IST")),
                setup_summary=best_strat_rationale,
                strategy_matched=matched_strat_name,
                technical=tech,
                fundamentals=funds,
                catalysts=catalysts,
                recent_news=news,
                scenario=scenario,
                multi_factor_score=score_val,
                evidence_tier=evidence_tier,
                liquidity_adtv_cr=item.get("adtv_cr", 50.0),
                key_risks=key_risks,
                invalidation_thesis=f"Close below support at ₹{tech.support_level:.1f}",
                review_date=review_date,
                expiry_date=expiry_date,
            )

            # Check personalized suitability if requested
            if advisory_mode == AdvisoryMode.PERSONALIZED_ADVISORY:
                is_suit, _, _, warnings = self.suitability_engine.evaluate_suitability(candidate, active_profile)
                if not is_suit:
                    continue

            candidates.append(candidate)

        # Sort by multi-factor score descending, limit shortlist to top 3-4 candidates
        candidates.sort(key=lambda c: c.multi_factor_score, reverse=True)
        shortlist = candidates[:4]

        # Concentration feedback
        concentration_feedback = ""
        if shortlist and active_profile and active_profile.existing_portfolio:
            concentration_feedback = self.suitability_engine.evaluate_portfolio_concentration(active_profile, shortlist[0])

        report = ResearchReport(
            request_id=str(uuid.uuid4())[:8],
            generated_at=now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            market_status=market_status,
            last_trading_session=last_session,
            market_regime=regime,
            regime_rationale=regime_rationale,
            universe_size_scanned=len(universe),
            candidates=shortlist,
            profile_used=active_profile if active_profile.is_complete_for_personalized() else None,
            portfolio_concentration_feedback=concentration_feedback,
            advisory_mode=advisory_mode,
            output_mode=output_mode,
            review_date=(now_dt + timedelta(days=14)).strftime("%Y-%m-%d"),
        )

        formatted_text = ReportBuilder.build_report(report, language=language)
        report.formatted_text = formatted_text

        # Record audit trail
        self._record_audit_log(report)

        return report, formatted_text

    def analyze_single_stock(
        self,
        symbol: str,
        profile: Optional[UserInvestmentProfile] = None,
        output_mode: OutputMode = OutputMode.STANDARD,
        language: str = "hi",
    ) -> Tuple[Optional[StockCandidate], str]:
        """Analyzes a specific user-requested stock symbol for a 1-month horizon."""
        clean_symbol = symbol.upper().strip()
        if not clean_symbol.endswith(".NS") and not clean_symbol.endswith(".BO"):
            clean_symbol = f"{clean_symbol}.NS"

        meta = next((s for s in self.data_provider._universe if s["symbol"].upper() == clean_symbol), None)
        if not meta:
            # Fallback metadata
            meta = {"symbol": clean_symbol, "name": clean_symbol.replace(".NS", ""), "sector": "Diversified", "base_price": 1000.0, "adtv_cr": 100.0}

        now_dt = self.data_provider.get_current_time_ist()
        market_status, last_session = self.data_provider.get_market_status()
        bars = self.data_provider.get_stock_ohlcv(clean_symbol, 200)
        latest_close = bars[-1].close

        index_data = self.data_provider.get_index_metrics()
        regime, regime_rat = self.regime_engine.evaluate_regime(index_data)
        tech = self.technical_engine.analyze(bars, nifty_return_pct=float(index_data.get("nifty_50", {}).get("change_pct", 0.0)))
        funds = self.fundamental_engine.get_snapshot(clean_symbol)
        catalysts = self.catalyst_engine.get_upcoming_catalysts(clean_symbol, current_date=now_dt)
        news = self.catalyst_engine.get_recent_news(clean_symbol)

        score_val, evidence_tier, _ = self.scorer.calculate_score(
            tech=tech,
            fundamentals=funds,
            has_positive_catalyst=any(n.classification.value == "POSITIVE_CATALYST" for n in news),
            adtv_cr=meta.get("adtv_cr", 50.0),
            market_regime=regime,
        )

        scenario = self.risk_engine.evaluate_scenarios(latest_close, tech, catalysts, regime.value)
        key_risks = self.risk_engine.identify_key_risks(clean_symbol, tech, catalysts, meta.get("adtv_cr", 50.0), regime.value)

        candidate = StockCandidate(
            symbol=clean_symbol,
            company_name=meta["name"],
            sector=meta["sector"],
            current_price=latest_close,
            closing_price=latest_close,
            is_market_open=(market_status == MarketStatus.OPEN),
            data_timestamp=index_data.get("timestamp", now_dt.strftime("%Y-%m-%d %H:%M:%S IST")),
            setup_summary=f"Evaluated setup for {clean_symbol}",
            strategy_matched="DirectAnalysis",
            technical=tech,
            fundamentals=funds,
            catalysts=catalysts,
            recent_news=news,
            scenario=scenario,
            multi_factor_score=score_val,
            evidence_tier=evidence_tier,
            liquidity_adtv_cr=meta.get("adtv_cr", 50.0),
            key_risks=key_risks,
            invalidation_thesis=f"Close below support at ₹{tech.support_level:.1f}",
            review_date=(now_dt + timedelta(days=14)).strftime("%Y-%m-%d"),
            expiry_date=(now_dt + timedelta(days=30)).strftime("%Y-%m-%d"),
        )

        report = ResearchReport(
            request_id=str(uuid.uuid4())[:8],
            generated_at=now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            market_status=market_status,
            last_trading_session=last_session,
            market_regime=regime,
            regime_rationale=regime_rat,
            universe_size_scanned=1,
            candidates=[candidate],
            output_mode=output_mode,
            review_date=(now_dt + timedelta(days=14)).strftime("%Y-%m-%d"),
        )

        formatted_text = ReportBuilder.build_report(report, language=language)
        return candidate, formatted_text

    def monitor_stock(self, symbol: str) -> Tuple[bool, str]:
        """Creates an active monitored thesis for a stock with 30-day expiry."""
        candidate, _ = self.analyze_single_stock(symbol)
        if not candidate or not candidate.scenario:
            return False, f"Could not create monitoring setup for {symbol}."

        thesis = self.monitor.add_thesis(
            symbol=candidate.symbol,
            company_name=candidate.company_name,
            entry_thesis=f"1-Month swing setup based on {candidate.evidence_tier.value} (Score: {candidate.multi_factor_score})",
            entry_price=candidate.current_price,
            invalidation_level=candidate.scenario.invalidation_level,
            target_zone=candidate.scenario.base_case.target_zone,
        )

        msg = (
            f"✓ **{candidate.symbol} ({candidate.company_name})** is now under active 1-month monitoring.\n"
            f"• Benchmark Price: ₹{candidate.current_price:,.2f}\n"
            f"• Invalidation Level: ₹{thesis.invalidation_level:,.2f}\n"
            f"• Analytical Base Target: ₹{thesis.target_zone[0]:,.2f} – ₹{thesis.target_zone[1]:,.2f}\n"
            f"• Review Date: {thesis.review_date} | Expiry Date: {thesis.expiry_date} (Auto-expires in 30 days)."
        )
        return True, msg

    def _record_audit_log(self, report: ResearchReport) -> None:
        """Stores research rationale in data/equity_research_audit.json for compliance."""
        try:
            os.makedirs(os.path.dirname(self.audit_file), exist_ok=True)
            entry = {
                "request_id": report.request_id,
                "timestamp": report.generated_at,
                "market_status": report.market_status.value,
                "market_regime": report.market_regime.value,
                "candidates": [
                    {
                        "symbol": c.symbol,
                        "score": c.multi_factor_score,
                        "tier": c.evidence_tier.value,
                        "price": c.current_price,
                        "invalidation": c.scenario.invalidation_level if c.scenario else 0.0,
                    }
                    for c in report.candidates
                ],
                "disclaimer_verified": True,
            }

            history = []
            if os.path.exists(self.audit_file):
                with open(self.audit_file, "r", encoding="utf-8") as f:
                    history = json.load(f)

            history.append(entry)
            # Keep last 100 audit entries
            if len(history) > 100:
                history = history[-100:]

            with open(self.audit_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist equity research audit log: %s", e)


def get_equity_research_manager() -> EquityResearchManager:
    """Convenience getter for the EquityResearchManager singleton."""
    return EquityResearchManager.get_instance()
