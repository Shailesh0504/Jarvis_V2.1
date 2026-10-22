# tests/test_stock_recommendation_memory.py
"""
Comprehensive automated tests for Jarvis Stock Recommendation Memory & Tracking System.
Verifies target derivation, immutable SQLite persistence, lifecycle state transitions,
performance calculations, and natural-language memory retrieval.
"""

from datetime import datetime
import os
import tempfile
import pytest

from stock.stock_history import StockHistoryDatabase
from stock.stock_memory import StockMemoryEngine
from stock.stock_models import (
    RecommendationRecord,
    StockCandidateResult,
    StockQueryParams,
)
from stock.stock_targets import StockTargetEngine
from stock.stock_tracker import StockTracker


@pytest.fixture
def temp_history_db():
    """Provides an isolated SQLite database instance for clean test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = StockHistoryDatabase(db_path=path)
    yield db
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


class TestStockTargetsEngine:
    """Validates Target 1, Target 2, Invalidation, and Holding Period derivation."""

    def test_target_derivation_risk_reward(self):
        """Tests mathematical derivation of T1, T2, Invalidation via Risk-Reward."""
        plan = StockTargetEngine.derive_target_exit_plan(
            price=420.0,
            technical_data={"atr": 10.0},
            horizon="swing_short_term",
            risk="moderate",
        )
        assert plan.reference_price == 420.0
        assert plan.invalidation_price is not None
        assert plan.invalidation_price < 420.0
        assert plan.target_1 is not None
        assert plan.target_1 > 420.0
        assert plan.target_2 is not None
        assert plan.target_2 > plan.target_1
        assert plan.holding_period_days == 30
        assert plan.time_exit_date is not None

    def test_target_derivation_technical_resistance(self):
        """Tests target alignment when 52W high acts as technical resistance."""
        plan = StockTargetEngine.derive_target_exit_plan(
            price=420.0,
            technical_data={"atr": 10.0, "high_52w": 480.0},
            horizon="3_12_months",
            risk="moderate",
        )
        assert plan.reference_price == 420.0
        assert plan.target_2 == 480.0
        assert plan.target_method == "technical_resistance"
        assert plan.holding_period_days == 180

    def test_target_derivation_insufficient_data(self):
        """Verifies strict refusal to fabricate targets when price is zero or negative."""
        plan = StockTargetEngine.derive_target_exit_plan(price=0.0)
        assert plan.target_1 is None
        assert plan.target_2 is None
        assert plan.invalidation_price is None
        assert "sufficient reliable data is not available" in plan.target_notes.lower()


class TestStockHistoryPersistence:
    """Verifies SQLite storage and immutable historical snapshot preservation."""

    def test_save_and_retrieve_recommendation(self, temp_history_db):
        """Ensures sessions and candidate records are stored and fetched accurately."""
        params = StockQueryParams(horizon="3_12_months", risk="moderate")
        cand = StockCandidateResult(
            company_name="ABC Ltd",
            symbol="ABC.NS",
            current_price=420.0,
            reference_price=420.0,
            market_cap="Large Cap",
            sector="IT",
            trend="Bullish",
            score=88.5,
            target_1=450.0,
            target_2=480.0,
            invalidation_price=395.0,
            holding_period_days=30,
            time_exit_date="2026-10-18",
            technical_summary="Strong 20 EMA breakout with volume surge",
            fundamental_summary="High profit margin and zero debt",
        )

        sid, recs = temp_history_db.save_session(params, [cand])
        assert sid is not None
        assert len(recs) == 1
        rec = recs[0]
        assert rec.reference_price == 420.0
        assert rec.target_1 == 450.0
        assert rec.target_2 == 480.0
        assert rec.invalidation_price == 395.0

        # Retrieve from DB
        fetched = temp_history_db.get_recommendation(rec.id)
        assert fetched is not None
        assert fetched.symbol == "ABC.NS"
        assert fetched.reference_price == 420.0
        assert fetched.target_1 == 450.0

    def test_immutability_of_reference_price_during_updates(self, temp_history_db):
        """Critical check: Live price updates must NEVER overwrite reference_price or targets."""
        params = StockQueryParams(horizon="3_12_months", risk="moderate")
        cand = StockCandidateResult(
            company_name="ABC Ltd",
            symbol="ABC.NS",
            current_price=420.0,
            reference_price=420.0,
            market_cap="Large Cap",
            sector="IT",
            trend="Bullish",
            score=85.0,
            target_1=450.0,
            target_2=480.0,
            invalidation_price=395.0,
        )

        _, recs = temp_history_db.save_session(params, [cand])
        rec = recs[0]

        tracker = StockTracker(db=temp_history_db)

        # Update price to 447
        updated_rec, perf, _ = tracker.track_price_update(rec.id, current_price=447.0)
        assert updated_rec.reference_price == 420.0
        assert updated_rec.target_1 == 450.0
        assert updated_rec.target_2 == 480.0
        assert updated_rec.invalidation_price == 395.0
        assert perf.current_price == 447.0
        assert perf.absolute_change == 27.0
        assert perf.percentage_change == 6.43

        # Update price to 480
        updated_rec2, perf2, _ = tracker.track_price_update(rec.id, current_price=480.0)
        assert updated_rec2.reference_price == 420.0

        # Confirm from DB directly
        db_rec = temp_history_db.get_recommendation(rec.id)
        assert db_rec.reference_price == 420.0


class TestLifecycleStateMachine:
    """Tests the exact scenario from Section 26 of the requirement specification."""

    def test_section_26_lifecycle_simulation(self, temp_history_db):
        """
        Simulation from Section 26:
        Recommendation: ABC at Ref ₹420, T1 ₹450, T2 ₹480, Invalidation ₹395
        Simulate:
          447 -> ACTIVE / Approaching Target 1
          452 -> TARGET_1_REACHED
          485 -> TARGET_2_REACHED
          390 -> INVALIDATED
        Verify reference price remains 420 in every case.
        """
        params = StockQueryParams(horizon="3_12_months", risk="moderate")
        cand = StockCandidateResult(
            company_name="ABC Ltd",
            symbol="ABC.NS",
            current_price=420.0,
            reference_price=420.0,
            market_cap="Large Cap",
            sector="IT",
            trend="Bullish",
            score=90.0,
            target_1=450.0,
            target_2=480.0,
            invalidation_price=395.0,
            holding_period_days=30,
            time_exit_date="2026-10-18",
        )
        _, recs = temp_history_db.save_session(params, [cand])
        rec = recs[0]
        tracker = StockTracker(db=temp_history_db)

        # 1. Price = 447 (within 2% of T1 450 -> dist = 3 <= 9)
        rec1, perf1, _ = tracker.track_price_update(rec.id, current_price=447.0)
        assert rec1.status == "ACTIVE"
        assert perf1.tracking_status == "Approaching Target 1"
        assert rec1.reference_price == 420.0

        # 2. Price = 452 (Target 1 breached)
        rec2, perf2, evt2 = tracker.track_price_update(rec.id, current_price=452.0)
        assert rec2.status == "TARGET_1_REACHED"
        assert perf2.tracking_status == "Target 1 Reached"
        assert evt2.event_type == "TARGET_1_HIT"
        assert rec2.reference_price == 420.0

        # 3. Price = 485 (Target 2 breached)
        rec3, perf3, evt3 = tracker.track_price_update(rec.id, current_price=485.0)
        assert rec3.status == "TARGET_2_REACHED"
        assert perf3.tracking_status == "Target 2 Reached"
        assert evt3.event_type == "TARGET_2_HIT"
        assert rec3.reference_price == 420.0

        # 4. Price = 390 (Invalidation breached)
        rec4, perf4, evt4 = tracker.track_price_update(rec.id, current_price=390.0)
        assert rec4.status == "INVALIDATED"
        assert perf4.tracking_status == "Invalidation Level Breached"
        assert evt4.event_type == "INVALIDATION_HIT"
        assert rec4.reference_price == 420.0


class TestStockMemoryAndNLPQueries:
    """Validates natural language question answering, date resolution, and turn N+1 context."""

    def test_date_resolution(self):
        """Tests parsing of relative and absolute date expressions."""
        mem = StockMemoryEngine()
        ref_dt = datetime(2026, 9, 18, 10, 30)

        # aaj
        assert mem.resolve_date_expression("aaj kya stock bataya", ref_date=ref_dt) == "2026-09-18"
        # kal
        assert mem.resolve_date_expression("kal wala stock", ref_date=ref_dt) == "2026-09-17"
        # 18 September
        assert mem.resolve_date_expression("18 September ko kya suggest kiya", ref_date=ref_dt) == "2026-09-18"
        # 18/09/2026
        assert mem.resolve_date_expression("18/09/2026 wala", ref_date=ref_dt) == "2026-09-18"

    def test_conversational_memory_queries(self, temp_history_db):
        """Tests historical questions from Section 11 & 12 of requirements."""
        mem = StockMemoryEngine(db=temp_history_db)

        # Seed database with recommendation from 18 Sep 2026
        rec = RecommendationRecord(
            id="REC-ABC-20260918",
            session_id="SESS-001",
            symbol="ABC.NS",
            company_name="ABC Ltd",
            recommendation_date="2026-09-18",
            recommendation_time="10:30:00",
            reference_price=420.0,
            current_price_at_analysis=420.0,
            target_1=450.0,
            target_2=480.0,
            invalidation_price=395.0,
            maximum_holding_period_days=30,
            status="ACTIVE",
            created_at=1789800000.0,
            updated_at=1789800000.0,
        )
        with temp_history_db._lock:
            with temp_history_db._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO stock_recommendations (
                        id, session_id, user_id, symbol, company_name, exchange,
                        recommendation_date, recommendation_time, timezone, reference_price,
                        current_price_at_analysis, target_1, target_2, target_method, exit_price,
                        invalidation_price, exit_type, maximum_holding_period_days, time_exit_date,
                        recommendation_type, investment_horizon, risk_profile, sector, market_cap,
                        technical_reason, fundamental_reason, risk_reason, selection_criteria_json,
                        data_source, data_timestamp, analysis_version, strategy_version, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.id, rec.session_id, rec.user_id, rec.symbol, rec.company_name, rec.exchange,
                        rec.recommendation_date, rec.recommendation_time, rec.timezone, rec.reference_price,
                        rec.current_price_at_analysis, rec.target_1, rec.target_2, rec.target_method, rec.exit_price,
                        rec.invalidation_price, rec.exit_type, rec.maximum_holding_period_days, rec.time_exit_date,
                        rec.recommendation_type, rec.investment_horizon, rec.risk_profile, rec.sector, rec.market_cap,
                        rec.technical_reason, rec.fundamental_reason, rec.risk_reason, rec.selection_criteria_json,
                        rec.data_source, rec.data_timestamp, rec.analysis_version, rec.strategy_version, rec.status,
                        rec.created_at, rec.updated_at
                    ),
                )
                conn.commit()

        # Query 1: Latest recommendation
        h1, resp1 = mem.answer_recommendation_query("Jarvis tumne mujhe kaunsa stock suggest kiya tha?")
        assert h1 is True
        assert "ABC Ltd" in resp1
        assert "420" in resp1
        assert "450" in resp1
        assert "395" in resp1

        # Query 2: Date specific query
        h2, resp2 = mem.answer_recommendation_query("18 September ko tumne kya stock bataya tha?")
        assert h2 is True
        assert "ABC Ltd" in resp2

        # Query 3: Turn N+1 Contextual Follow-up: "us time price kya tha?"
        h3, resp3 = mem.answer_recommendation_query("us time price kya tha?")
        assert h3 is True
        assert "420.00" in resp3

        # Query 4: Turn N+1 Contextual Follow-up: "target kya diya tha?"
        h4, resp4 = mem.answer_recommendation_query("target kya diya tha?")
        assert h4 is True
        assert "450.00" in resp4
        assert "480.00" in resp4

        # Query 5: Turn N+1 Contextual Follow-up: "exit kab karna tha?"
        h5, resp5 = mem.answer_recommendation_query("exit kab karna tha?")
        assert h5 is True
        assert "395.00" in resp5
        assert "30 days" in resp5

        # Query 6: Specific stock query
        h6, resp6 = mem.answer_recommendation_query("ABC ka target kya hai?")
        assert h6 is True
        assert "450.00" in resp6
        assert "480.00" in resp6

        # Query 7: Specific stock price query
        h7, resp7 = mem.answer_recommendation_query("ABC kitne pe suggest kiya tha?")
        assert h7 is True
        assert "420.00" in resp7

        # Query 8: Status inquiry
        h8, resp8 = mem.answer_recommendation_query("abhi uska status kya hai?")
        assert h8 is True
        assert "Active Setup" in resp8
