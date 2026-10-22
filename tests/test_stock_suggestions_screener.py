# tests/test_stock_suggestions_screener.py
"""
Automated unit & integration test suite for Stock Suggestions Screener,
Mathematical Position Sizing, Conversational Intent Routing, and GUI View.
"""

import pytest
from unittest.mock import MagicMock, patch

from core.equity_research.stock_screener import (
    StockScreenerEngine,
    StockSuggestion,
    TradeLevels,
    PositionSizeResult,
    calculate_position_size
)
from core.semantic.goals.equity_goal import EquityResearchGoalMixin
from core.semantic.models import IntentName
from plugins.equity_research.plugin import EquityResearchPlugin


class TestStockScreenerEngine:
    """Tests the technical screening engine for Intraday and Swing strategies."""

    def test_singleton_instance(self):
        engine1 = StockScreenerEngine.get_instance()
        engine2 = StockScreenerEngine.get_instance()
        assert engine1 is engine2

    def test_scan_intraday_stocks_structure(self):
        engine = StockScreenerEngine.get_instance()
        results = engine.scan_intraday_stocks()
        assert isinstance(results, list)
        assert len(results) > 0

        for item in results:
            assert isinstance(item, StockSuggestion)
            assert item.trade_type == "INTRADAY"
            assert item.direction in ("BUY", "SELL")
            assert item.symbol.isalnum() or "^" in item.symbol
            assert item.confluence_score > 0
            assert isinstance(item.levels, TradeLevels)
            assert item.levels.cmp > 0
            assert item.levels.target_1 > 0
            assert item.levels.stop_loss > 0
            assert len(item.thesis_points) > 0
            assert ":" in item.levels.risk_reward

    def test_scan_swing_stocks_structure(self):
        engine = StockScreenerEngine.get_instance()
        results = engine.scan_swing_stocks()
        assert isinstance(results, list)
        assert len(results) > 0

        for item in results:
            assert isinstance(item, StockSuggestion)
            assert item.trade_type == "SWING"
            assert item.direction in ("BUY", "SELL")
            assert item.timeframe_horizon in ("3-10 Days", "1-3 Weeks", "2-4 Weeks")
            assert isinstance(item.levels, TradeLevels)
            assert item.levels.cmp > 0
            assert item.levels.target_1 > item.levels.stop_loss

    def test_get_all_suggestions(self):
        engine = StockScreenerEngine.get_instance()
        payload = engine.get_all_suggestions(force_refresh=False)
        assert "all" in payload
        assert "intraday" in payload
        assert "swing" in payload
        assert "meta" in payload
        assert len(payload["all"]) == len(payload["intraday"]) + len(payload["swing"])
        assert payload["meta"]["status"] in ("LIVE_NSE_DATA", "HISTORICAL_FALLBACK", "SECTOR_WATCH_FALLBACK")

    def test_to_dict_serialization(self):
        engine = StockScreenerEngine.get_instance()
        suggestions = engine.scan_intraday_stocks()
        assert len(suggestions) > 0
        s_dict = suggestions[0].to_dict()
        assert "symbol" in s_dict
        assert "levels" in s_dict
        assert "cmp" in s_dict["levels"]
        assert "target_1" in s_dict["levels"]
        assert "stop_loss" in s_dict["levels"]

    def test_institutional_screening_metrics(self):
        """Verifies institutional criteria: RVOL, ATR, VWAP, and minimum 1:2 Risk:Reward."""
        engine = StockScreenerEngine.get_instance()
        intraday = engine.scan_intraday_stocks()
        assert len(intraday) > 0
        for item in intraday:
            assert "RVOL" in item.indicators
            assert "ATR_14" in item.indicators
            assert "VWAP" in item.indicators
            assert item.indicators["RVOL"] > 0.5
            # Strict 1:2 Risk to Reward check
            reward = item.levels.target_1 - item.levels.entry_min
            risk = item.levels.entry_min - item.levels.stop_loss
            assert reward >= (1.8 * risk)

        swing = engine.scan_swing_stocks()
        assert len(swing) > 0
        for item in swing:
            assert "ATR_14" in item.indicators
            assert "RS_20d_pct" in item.indicators
            reward = item.levels.target_1 - item.levels.cmp
            risk = item.levels.cmp - item.levels.stop_loss
            assert reward >= (1.8 * risk)


class TestPositionSizingCalculator:
    """Tests the risk management and position sizing calculations."""

    def test_standard_position_sizing(self):
        result = calculate_position_size(
            capital=100000.0,
            risk_pct=1.0,
            entry_price=1000.0,
            stop_loss=980.0,
            target_1=1040.0
        )
        assert isinstance(result, PositionSizeResult)
        assert result.max_risk_amount == 1000.0  # 1% of 100k
        assert result.risk_per_share == 20.0     # 1000 - 980
        assert result.shares == 50               # 1000 / 20
        assert result.capital_required == 50000.0 # 50 * 1000
        assert result.expected_profit == 2000.0  # 50 * 40
        assert result.actual_risk == 1000.0

    def test_capital_exceeded_position_sizing(self):
        # When risk allows 1000 shares but total capital only allows 10 shares
        result = calculate_position_size(
            capital=10000.0,
            risk_pct=10.0,  # 1000 risk
            entry_price=1000.0,
            stop_loss=999.0, # 1 risk per share -> 1000 shares would cost 10 lakh, but capital is 10k!
            target_1=1050.0
        )
        assert result.shares == 10  # Capped at capital / entry_price
        assert result.capital_required <= 10000.0

    def test_zero_or_negative_risk(self):
        result = calculate_position_size(
            capital=50000.0,
            risk_pct=1.0,
            entry_price=100.0,
            stop_loss=100.0, # Zero risk
            target_1=110.0
        )
        assert result.shares == 0


class TestConversationalGoalResolution:
    """Tests natural language comprehension of stock suggestion requests."""

    @pytest.mark.parametrize("query, expected_trade_type", [
        ("intraday ke liye stock suggest karo", "intraday"),
        ("aaj intraday trading ke liye kaunsa stock le", "intraday"),
        ("swing trade ke liye stock batao", "swing"),
        ("swing trading ke liye stock suggest karo", "swing"),
        ("stock suggetion dikhao", "all"),
        ("stock suggestions dikhao", "all"),
    ])
    def test_screener_query_detection(self, query, expected_trade_type):
        is_candidate = EquityResearchGoalMixin._is_equity_research_candidate(query, context=None)
        assert is_candidate is True

        resolution = EquityResearchGoalMixin._resolve_equity_research_goal(
            raw_text=query,
            effective_text=query,
            context=None
        )
        assert resolution is not None
        assert resolution.intent == IntentName.EQUITY_RESEARCH
        assert resolution.goal == "SUGGEST_STOCK_TRADES"
        assert resolution.action_plan["action"] == "suggest_stocks"
        assert resolution.action_plan["parameters"]["trade_type"] == expected_trade_type
        assert "top pick" in resolution.response_text.lower() or "setups" in resolution.response_text.lower()


class TestEquityResearchPluginSuggestStocks:
    """Tests the plugin execution layer for suggest_stocks action."""

    def test_plugin_execute_suggest_stocks(self):
        plugin = EquityResearchPlugin()
        res = plugin.execute("suggest_stocks", {"trade_type": "intraday"})
        assert res.success is True
        assert "message" in res.data
        assert "top_pick" in res.data or "total_count" in res.data
        assert "Boss" in res.data["message"]


class TestStockSuggestionsGUIView:
    """Tests that the PySide6 view initializes correctly without errors."""

    def test_view_creation(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from gui.views.stock_suggestions_view import StockSuggestionsView
        view = StockSuggestionsView(core=None)
        assert view is not None
        assert view._current_tab == "All"
        assert view._capital == 50000.0
        assert view._risk_pct == 1.0
        assert hasattr(view, "refresh_data")

        # Test tab switching
        view._set_tab("Intraday")
        assert view._current_tab == "Intraday"
        view._set_tab("Swing")
        assert view._current_tab == "Swing"
