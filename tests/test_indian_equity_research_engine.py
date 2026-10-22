# tests/test_indian_equity_research_engine.py
"""
Comprehensive test suite for Jarvis V2.1 Indian Equity 1-Month Research & Decision-Support Engine.
Validates:
- Universe screening & liquidity filtering (>= 10 Cr ADTV)
- IST Market Session & Transparent Market-Closed Status
- Technical Indicator Calculations & Strategy Plugins (Trend Following, Breakout, Mean Reversion)
- Market Regime Classification
- Fundamental & Epistemologically-Tagged Catalyst Analysis
- Scenarios & Analytical Invalidation Zones
- Suitability & Concentration Guards
- Transparent 10-Factor Scoring & Qualitative Evidence Tiers
- Multi-Tier Reports (QUICK, STANDARD, DETAILED) & SEBI Disclaimer
- Thesis Monitoring with 30-Day Auto-Expiry
- Manager Pipeline & Audit Persistence
- Goal Resolver NLP Dispatching & Slot Gating
- Contextual Suggestion Chips & Invariant Checks (No Guaranteed Returns)
"""

from datetime import datetime, timedelta
import os
import pytest

from core.equity_research.models import (
    AdvisoryMode,
    CatalystEvent,
    EpistemologicalCategory,
    EvidenceTier,
    FundamentalSnapshot,
    MarketRegime,
    MarketStatus,
    NewsClassification,
    NewsSentimentItem,
    OHLCVBar,
    OutputMode,
    RiskScenario,
    RiskTolerance,
    StockCandidate,
    TechnicalIndicators,
    UserInvestmentProfile,
    ResearchReport,
)
from core.equity_research.market_data_provider import MarketDataProvider
from core.equity_research.market_regime import MarketRegimeEngine
from core.equity_research.technical_engine import TechnicalAnalysisEngine
from core.equity_research.strategies import (
    TrendFollowingStrategy,
    BreakoutStrategy,
    MeanReversionStrategy,
)
from core.equity_research.fundamental_engine import FundamentalEngine
from core.equity_research.catalyst_news_engine import CatalystNewsEngine
from core.equity_research.risk_engine import RiskEngine
from core.equity_research.suitability_engine import SuitabilityEngine
from core.equity_research.scorer import MultiFactorScorer
from core.equity_research.report_builder import EquityReportBuilder
from core.equity_research.monitor import ThesisMonitor
from core.equity_research.manager import EquityResearchManager
from plugins.equity_research.plugin import EquityResearchPlugin
from core.semantic.goal_resolver import GoalResolver
from core.semantic.resolution import ResolutionDecision
from core.intelligence.suggestion_manager import SuggestionManager


class TestIndianEquityResearchEngine:
    """Test suite for the Indian Equity 1-Month Research Module."""

    @pytest.fixture(autouse=True)
    def setup_manager(self):
        """Resets singleton manager state before each test."""
        self.provider = MarketDataProvider()
        self.tech_engine = TechnicalAnalysisEngine()
        self.regime_engine = MarketRegimeEngine()
        self.fund_engine = FundamentalEngine()
        self.cat_engine = CatalystNewsEngine()
        self.risk_engine = RiskEngine()
        self.suit_engine = SuitabilityEngine()
        self.scorer = MultiFactorScorer()
        self.builder = EquityReportBuilder()
        self.monitor = ThesisMonitor(storage_file="data/test_monitored_theses.json")
        self.manager = EquityResearchManager(audit_file="data/test_equity_research_audit.json")
        EquityResearchManager.get_instance()._profile = UserInvestmentProfile()

    # =========================================================================
    # 1. MARKET DATA & SESSION STATUS TESTS
    # =========================================================================

    def test_universe_and_liquidity_screening(self):
        """Verifies liquid universe satisfies >= 10 Cr ADTV filter."""
        universe = self.provider.get_stock_universe()
        assert len(universe) >= 20
        for stock in universe:
            assert stock["adtv_cr"] >= 10.0, f"{stock['symbol']} ADTV {stock['adtv_cr']} Cr is below 10 Cr limit"

    def test_market_session_and_closed_status(self):
        """Tests IST market status detection and transparent closed labeling."""
        status, last_session = self.provider.get_market_status()
        assert isinstance(status, MarketStatus)
        assert last_session != ""

    def test_ohlcv_history_generation(self):
        """Verifies deterministic OHLCV historical generation."""
        bars = self.provider.get_stock_ohlcv("RELIANCE.NS", lookback_days=100)
        assert len(bars) >= 100
        for b in bars:
            assert b.high >= b.low
            assert b.high >= b.open
            assert b.high >= b.close
            assert b.low <= b.open
            assert b.low <= b.close
            assert b.volume > 0

    # =========================================================================
    # 2. TECHNICAL ANALYSIS & STRATEGIES TESTS
    # =========================================================================

    def test_technical_indicators_calculation(self):
        """Tests technical indicator mathematical engine."""
        bars = self.provider.get_stock_ohlcv("TCS.NS", lookback_days=200)
        ti = self.tech_engine.analyze(bars, nifty_return_pct=1.5)

        assert ti.ema_20 > 0
        assert ti.ema_50 > 0
        assert ti.sma_200 > 0
        assert 0 <= ti.rsi <= 100
        assert isinstance(ti.macd, float)
        assert isinstance(ti.macd_signal, float)
        assert ti.atr > 0
        assert 0 <= ti.adx <= 100
        assert ti.supertrend_direction in ("BULLISH", "BEARISH")
        assert ti.support_level <= ti.resistance_level
        assert ti.volume_ratio > 0

    def test_strategies_trend_breakout_mean_reversion(self):
        """Tests all three technical strategy evaluators."""
        bars = self.provider.get_stock_ohlcv("INFY.NS", lookback_days=200)
        ti = self.tech_engine.analyze(bars)
        price = bars[-1].close

        # 1. Trend Following
        trend_strat = TrendFollowingStrategy()
        is_m, score, rat = trend_strat.evaluate(ti, price)
        assert isinstance(is_m, bool)
        assert 0.0 <= score <= 100.0

        # 2. Breakout
        breakout_strat = BreakoutStrategy()
        is_b, b_score, b_rat = breakout_strat.evaluate(ti, price)
        assert isinstance(is_b, bool)
        assert 0.0 <= b_score <= 100.0

        # 3. Mean Reversion
        mr_strat = MeanReversionStrategy()
        is_mr, mr_score, mr_rat = mr_strat.evaluate(ti, price)
        assert isinstance(is_mr, bool)
        assert 0.0 <= mr_score <= 100.0

    # =========================================================================
    # 3. MARKET REGIME CLASSIFICATION TESTS
    # =========================================================================

    def test_market_regime_classification(self):
        """Tests multi-factor Indian market regime classifier."""
        index_data = self.provider.get_index_metrics()
        regime, rationale = self.regime_engine.evaluate_regime(index_data)
        assert regime in (
            MarketRegime.BULLISH,
            MarketRegime.BEARISH,
            MarketRegime.SIDEWAYS,
            MarketRegime.HIGH_VOLATILITY,
            MarketRegime.MIXED,
        )
        assert len(rationale) > 0

    # =========================================================================
    # 4. FUNDAMENTALS & CATALYST/NEWS EPISTEMOLOGY TESTS
    # =========================================================================

    def test_fundamental_analysis(self):
        """Tests fundamental health evaluation and debt/pledge guards."""
        fund = self.fund_engine.get_snapshot("RELIANCE.NS")
        assert fund.symbol == "RELIANCE.NS"
        assert fund.pe_ratio > 0
        assert fund.debt_to_equity >= 0
        assert 0.0 <= fund.pledged_shares_pct <= 100.0

    def test_catalyst_and_news_epistemology(self):
        """Verifies epistemological classification of corporate news and events."""
        events = self.cat_engine.get_upcoming_catalysts("RELIANCE.NS")
        assert len(events) >= 1
        assert isinstance(events[0], CatalystEvent)

        news = self.cat_engine.get_recent_news("RELIANCE.NS")
        assert len(news) >= 1
        categories = [item.category for item in news]
        assert any(c in categories for c in (
            EpistemologicalCategory.FACT,
            EpistemologicalCategory.SOURCE_REPORTED_CLAIM,
            EpistemologicalCategory.ANALYST_INTERPRETATION,
            EpistemologicalCategory.JARVIS_INFERENCE,
        ))

    # =========================================================================
    # 5. RISK SCENARIOS & ANALYTICAL INVALIDATION TESTS
    # =========================================================================

    def test_risk_scenarios_and_invalidation(self):
        """Tests 3-tier Bull/Base/Bear scenarios and invalidation levels."""
        bars = self.provider.get_stock_ohlcv("TCS.NS", lookback_days=200)
        ti = self.tech_engine.analyze(bars)
        cmp = bars[-1].close
        cats = self.cat_engine.get_upcoming_catalysts("TCS.NS")

        scenarios = self.risk_engine.evaluate_scenarios(
            current_price=cmp,
            tech=ti,
            catalysts=cats,
            market_regime="BULLISH",
        )

        assert scenarios.bull_case.target_zone[0] > cmp
        assert scenarios.base_case.target_zone[0] > cmp
        assert scenarios.bear_case.target_zone[0] < cmp
        assert scenarios.invalidation_level < cmp
        assert scenarios.risk_reward_ratio >= 1.5

    # =========================================================================
    # 6. SUITABILITY & PORTFOLIO CONCENTRATION TESTS
    # =========================================================================

    def test_suitability_and_concentration_caps(self):
        """Verifies capital allocation, max loss limits, and sector concentration."""
        profile_cons = UserInvestmentProfile(
            investment_amount=100000.0,
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            max_loss_limit_pct=3.0,
        )
        bars = self.provider.get_stock_ohlcv("TCS.NS", 200)
        tech = self.tech_engine.analyze(bars)
        candidate = StockCandidate(
            symbol="TCS.NS",
            company_name="TCS",
            sector="IT",
            current_price=4200.0,
            closing_price=4200.0,
            is_market_open=True,
            data_timestamp="2026-09-16 10:00:00 IST",
            setup_summary="Test setup",
            strategy_matched="TrendFollowing",
            technical=tech,
            fundamentals=self.fund_engine.get_snapshot("TCS.NS"),
            catalysts=[],
            recent_news=[],
            scenario=None,
            multi_factor_score=80.0,
            evidence_tier=EvidenceTier.STRONG,
            liquidity_adtv_cr=500.0,
            key_risks=[],
            invalidation_thesis="Support break",
            review_date="2026-09-30",
            expiry_date="2026-10-16",
        )

        is_suit, score, rat, warns = self.suit_engine.evaluate_suitability(candidate, profile_cons)
        assert isinstance(is_suit, bool)

        # Portfolio concentration
        profile_cons.existing_portfolio = {"INFY.NS": 0.30, "TCS.NS": 0.15}
        conc_feedback = self.suit_engine.evaluate_portfolio_concentration(profile_cons, candidate)
        assert "Concentration Notice" in conc_feedback or "sector" in conc_feedback.lower()

    # =========================================================================
    # 7. MULTI-FACTOR SCORING & EVIDENCE TIERS TESTS
    # =========================================================================

    def test_scoring_and_evidence_tier_mapping(self):
        """Tests composite research score (0-100) and qualitative evidence tiers."""
        bars = self.provider.get_stock_ohlcv("RELIANCE.NS", 200)
        tech = self.tech_engine.analyze(bars)
        funds = self.fund_engine.get_snapshot("RELIANCE.NS")
        score, tier, breakdown = self.scorer.calculate_score(
            tech=tech,
            fundamentals=funds,
            has_positive_catalyst=True,
            adtv_cr=1800.0,
            market_regime=MarketRegime.BULLISH,
        )
        assert 0.0 <= score <= 100.0
        assert tier in (EvidenceTier.STRONG, EvidenceTier.MODERATE, EvidenceTier.WEAK)
        assert len(breakdown) > 0

    # =========================================================================
    # 8. REPORT BUILDER & MANDATORY DISCLAIMER TESTS
    # =========================================================================

    def test_report_builder_modes_and_disclaimer(self):
        """Verifies QUICK, STANDARD, DETAILED modes and absence of guaranteed return claims."""
        report, formatted_std = self.manager.research_shortlist(output_mode=OutputMode.STANDARD)
        assert "1-Month Indian Equity Research" in formatted_std
        assert "Market:" in formatted_std
        assert "DECISION SUPPORT ONLY" in formatted_std

        # Quick mode
        report_q, formatted_q = self.manager.research_shortlist(output_mode=OutputMode.QUICK)
        assert len(formatted_q) < len(formatted_std)
        assert "1-Month Indian Equity Research" in formatted_q

        # Detailed mode
        report_d, formatted_d = self.manager.research_shortlist(output_mode=OutputMode.DETAILED)
        assert len(formatted_d) >= len(formatted_std)
        assert "Detailed Scenario Analysis" in formatted_d

    # =========================================================================
    # 9. THESIS MONITOR & 30-DAY AUTO-EXPIRY TESTS
    # =========================================================================

    def test_thesis_monitor_and_auto_expiry(self):
        """Tests setup monitoring, price updates, invalidation alerts, and 30-day expiry."""
        thesis = self.monitor.add_thesis(
            symbol="BHARTIARTL.NS",
            company_name="Bharti Airtel Ltd",
            entry_thesis="Breakout setup",
            entry_price=1500.0,
            invalidation_level=1450.0,
            target_zone=(1600.0, 1650.0),
        )
        assert thesis.symbol == "BHARTIARTL.NS"
        assert thesis.is_active is True

        # Check invalidation
        is_inv, alert = self.monitor.update_price_check("BHARTIARTL.NS", 1440.0)
        assert is_inv is True
        assert "INVALIDATION ALERT" in alert

        # Check auto-expiry when > 30 days
        self.monitor._theses["BHARTIARTL.NS"].is_active = True
        self.monitor._theses["BHARTIARTL.NS"].created_date = (datetime.utcnow() - timedelta(days=32)).strftime("%Y-%m-%d")
        self.monitor._theses["BHARTIARTL.NS"].expiry_date = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")
        expired_msgs = self.monitor.check_expirations()
        assert len(expired_msgs) >= 1
        assert self.monitor._theses["BHARTIARTL.NS"].is_active is False

    # =========================================================================
    # 10. END-TO-END EQUITY RESEARCH MANAGER TESTS
    # =========================================================================

    def test_manager_pipeline_and_audit(self):
        """Tests complete manager pipeline execution and audit logging."""
        profile = UserInvestmentProfile(
            investment_amount=200000.0,
            risk_tolerance=RiskTolerance.MODERATE,
            sector_preferences=["IT"],
        )
        report, text = self.manager.research_shortlist(profile=profile)
        assert isinstance(report, ResearchReport)
        assert len(report.candidates) >= 1
        top_cand = report.candidates[0]
        assert top_cand.multi_factor_score > 0
        assert top_cand.evidence_tier in (EvidenceTier.STRONG, EvidenceTier.MODERATE, EvidenceTier.WEAK)

        # Check audit log exists
        assert os.path.exists(self.manager.audit_file)

    def test_analyze_single_stock(self):
        """Tests on-demand single stock analysis."""
        candidate, text = self.manager.analyze_single_stock("RELIANCE.NS")
        assert candidate is not None
        assert candidate.symbol == "RELIANCE.NS"
        assert candidate.technical.ema_20 > 0
        assert "RELIANCE" in text

    # =========================================================================
    # 11. PLUGIN MANIFEST & EXECUTION TESTS
    # =========================================================================

    def test_equity_research_plugin(self):
        """Tests EquityResearchPlugin actions and manifest."""
        plugin = EquityResearchPlugin()
        manifest = plugin.get_manifest()
        assert manifest.name == "equity_research"
        assert len(manifest.actions) >= 5

        # Test research_shortlist action
        res = plugin.execute("research_shortlist", {"capital": 150000.0, "risk_tolerance": "MODERATE"})
        assert res.success is True
        assert res.data["candidate_count"] >= 1
        assert "report_text" in res.data

        # Test analyze_stock action
        res_stock = plugin.execute("analyze_stock", {"symbol": "TCS.NS"})
        assert res_stock.success is True
        assert res_stock.data["symbol"] == "TCS.NS"
        assert res_stock.data["score"] > 0

        # Test market_regime action
        res_regime = plugin.execute("market_regime", {})
        assert res_regime.success is True
        assert "summary_text" in res_regime.data

        # Test monitor_stock action
        res_mon = plugin.execute("monitor_stock", {"action_type": "list"})
        assert res_mon.success is True
        assert "active_theses" in res_mon.data

    # =========================================================================
    # 12. GOAL RESOLVER NLP DISPATCHING & SLOT GATING TESTS
    # =========================================================================

    def test_goal_resolver_equity_research_queries(self):
        """Tests natural language parsing of Indian equity research queries."""
        resolver = GoalResolver()

        # Query 1: Research query with explicit capital & risk
        q1 = "1 month ke liye best stock batao budget 1 lakh risk moderate"
        plan1 = resolver.resolve_utterance(q1)
        assert plan1.primary_goal == "SHORT_TERM_INVESTMENT_RESEARCH"
        assert plan1.slots.get("capital") == 100000.0
        assert plan1.slots.get("risk_tolerance") == "MODERATE"

        # Query 2: Single stock analysis
        q2 = "reliance ka 1 month technical setup kaisa hai"
        plan2 = resolver.resolve_utterance(q2)
        assert plan2.primary_goal == "ANALYZE_STOCK_SETUP"
        assert plan2.slots.get("symbol") == "RELIANCE"

        # Query 3: Market regime query
        q3 = "aaj market kaisa hai nifty trend batao"
        plan3 = resolver.resolve_utterance(q3)
        assert plan3.primary_goal == "MARKET_REGIME_QUERY"

        # Query 4: Monitor stock
        q4 = "is stock ko monitor list mein add karo TCS"
        plan4 = resolver.resolve_utterance(q4)
        assert plan4.primary_goal == "MONITOR_EQUITY_THESIS"

    def test_goal_resolver_missing_slot_clarification(self):
        """Tests clarification prompt when user asks for stock ideas without budget or risk."""
        from core.equity_research.manager import EquityResearchManager
        mgr = EquityResearchManager.get_instance()
        mgr._profile.investment_amount = None
        mgr._profile.risk_tolerance = None

        resolver = GoalResolver()
        vague_query = "mere liye stock suggest karo"
        plan = resolver.resolve_utterance(vague_query)
        assert plan.primary_goal == "SHORT_TERM_INVESTMENT_RESEARCH"
        assert plan.decision in (ResolutionDecision.CLARIFY, ResolutionDecision.ASK_PRECISE_CLARIFICATION)
        assert "budget" in plan.clarification_prompt.lower() or "capital" in plan.clarification_prompt.lower()

    def test_goal_resolver_multi_turn_profile_inheritance(self):
        """Tests slot preservation and multi-turn profile inheritance."""
        resolver = GoalResolver()

        # Turn 1: User provides profile update
        t1 = "mera budget 2 lakh hai aur moderate risk hai"
        plan1 = resolver.resolve_utterance(t1)
        assert plan1.slots.get("capital") == 200000.0
        assert plan1.slots.get("risk_tolerance") == "MODERATE"

        # Turn 2: User asks for sector-specific research without repeating capital/risk
        t2 = "IT sector mein stock suggest karo 1 month ke liye"
        plan2 = resolver.resolve_utterance(t2)
        assert plan2.primary_goal == "SHORT_TERM_INVESTMENT_RESEARCH"
        assert plan2.slots.get("sector") == "IT"
        # Capital and risk should be inherited from active profile
        assert plan2.slots.get("capital") == 200000.0
        assert plan2.slots.get("risk_tolerance") == "MODERATE"

    # =========================================================================
    # 13. SUGGESTION MANAGER CHIPS & ZERO-PERSISTENCE AUDIT INVARIANTS
    # =========================================================================

    def test_suggestion_manager_equity_research_chips(self):
        """Verifies SuggestionManager generates relevant contextual chips for equity research."""
        sm = SuggestionManager()
        chips = sm.generate_contextual_chips(
            last_user_input="1 month ke liye best stock batao",
            last_assistant_response="Yeh rahe top 3 shortlisted candidates with technical setups.",
        )
        assert len(chips) >= 3
        labels = [c.label for c in chips]
        assert "Compare Candidates" in labels
        assert "Technical Details" in labels
        assert "Risk Analysis" in labels

    def test_no_guaranteed_returns_invariant(self):
        """
        Critical Compliance & Safety Invariant:
        Verifies system output NEVER claims certainty, guaranteed returns, or 100% win rates.
        """
        forbidden_phrases = [
            "sure shot",
            "100% win",
            "zero risk",
            "can't lose",
            "fail safe profit",
            "paisa double",
            "we guarantee",
            "guaranteed profit",
        ]

        report, rep_text = self.manager.research_shortlist(output_mode=OutputMode.DETAILED)
        text_lower = rep_text.lower()

        for phrase in forbidden_phrases:
            assert phrase not in text_lower, f"Compliance Violation: '{phrase}' found in research report!"

        # Explicitly verify the disclaimer affirms that returns are NOT guaranteed
        assert "not guarantee returns" in text_lower

    # =========================================================================
    # 14. ROOT-CAUSE NATURAL-LANGUAGE INTENT & VARIATION TESTS
    # =========================================================================

    def test_natural_language_equity_research_intent_resolution(self):
        """
        Validates that all natural phrasing variations resolve to EQUITY_RESEARCH
        and FIND_OR_SUGGEST_EQUITY / SHORT_TERM_INVESTMENT_RESEARCH with high confidence.
        """
        resolver = GoalResolver()

        test_queries = [
            "mujhe koi stock suggest karo",
            "koi stock batao",
            "koi share suggest karo",
            "mujhe ek share chahiye investment ke liye",
            "kaunsa stock research karun",
            "kuch Indian stocks shortlist karo",
            "mere liye kuch shares analyze karo",
            "stock market mein kuch opportunities batao",
            "1 month ke liye koi stock dekhna hai",
            "short term ke liye shares suggest karo",
            "investment ke liye kuch stocks batao",
            "koi achha share bata sakte ho",
            "kaunsa share lena chahiye",
            "mujhe ek stock choose karne mein help karo",
            "Indian market mein koi stock batao",
            "koi share suggest kar sakte ho",
            "aaj kis stock ko dekhna chahiye",
            "investment ke liye koi stock research karo",
            "kuch stocks shortlist karo",
        ]

        for q in test_queries:
            plan = resolver.resolve_utterance(q)
            assert plan.intent == "EQUITY_RESEARCH", f"Failed for query: {q}"
            assert plan.primary_goal in ("FIND_OR_SUGGEST_EQUITY", "SHORT_TERM_INVESTMENT_RESEARCH"), f"Goal failed for {q}: {plan.primary_goal}"
            assert plan.confidence >= 0.90, f"Confidence too low for {q}: {plan.confidence}"
            assert plan.decision != ResolutionDecision.CAPABILITY_UNAVAILABLE

    def test_semantic_orchestrator_and_executor_integration(self):
        """Verifies end-to-end NLU dispatch through HinglishNLUParser and SemanticAction."""
        from brain.semantic_parser import HinglishNLUParser

        act = HinglishNLUParser.parse("mujhe koi stock suggest karo.")
        assert act is not None
        assert act.service == "equity_research"
        assert act.intent == "EQUITY_RESEARCH"
        assert act.action == "research_shortlist"
        assert act.needs_clarification is True
        assert act.clarification_prompt is not None
        assert "horizon" in act.clarification_prompt.lower() or "budget" in act.clarification_prompt.lower()

    def test_negative_queries_do_not_trigger_equity_research(self):
        """
        Ensures definitional and news queries do NOT trigger equity research.
        """
        from brain.semantic_parser import HinglishNLUParser

        negative_queries = [
            "stock kya hota hai?",
            "stock market ka matlab kya hai?",
            "what is a stock",
            "what are shares",
            "stock market mein aaj kya hua?",
            "market news",
            "mere portfolio ka review karo",
        ]

        for q in negative_queries:
            act = HinglishNLUParser.parse(q)
            # Must either be None or NOT equity_research
            assert act is None or act.service != "equity_research", f"Negative query '{q}' incorrectly matched equity research!"
            is_cand = GoalResolver._is_equity_research_candidate(q.lower(), context=None)
            assert is_cand is False, f"Negative query '{q}' was flagged as equity candidate!"

    def test_contextual_ellipsis_and_pronoun_inheritance(self):
        """
        Verifies multi-turn context ellipsis ('koi suggest karo') when equity context is active.
        """
        from core.context import ActiveTargetContext
        ctx = ActiveTargetContext()
        ctx.last_intent = "EQUITY_RESEARCH"
        ctx.last_entities = {"domain": "EQUITY", "market": "INDIA"}

        is_cand = GoalResolver._is_equity_research_candidate("koi suggest karo", context=ctx)
        assert is_cand is True

        plan = GoalResolver.resolve("koi suggest karo", context=ctx)
        assert plan.intent == "EQUITY_RESEARCH"
        assert plan.primary_goal in ("FIND_OR_SUGGEST_EQUITY", "SHORT_TERM_INVESTMENT_RESEARCH")

