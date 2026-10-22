# tests/test_stock_wizard_engine.py
"""
Unit and API integration tests for Stock Query Wizard and Screener Engine.
Verifies Pydantic model validation, screener pipeline, multi-factor scoring,
risk exclusions, explanations, and local HTTP REST endpoints.
"""

import json
import pytest
from stock.stock_models import StockQueryParams, StockAnalysisResponse, StockCandidateResult
from stock.stock_screener import StockScreener
from stock.stock_service import StockService
from stock.stock_router import StockWebServer


class TestStockWizardModelsAndValidation:
    """Validates schema rules and guards against malformed input."""

    def test_valid_parameters_instantiation(self):
        params = StockQueryParams(
            horizon="swing_short_term",
            risk="moderate",
            capital=100000.0,
            objective=["growth", "momentum"],
            market_cap=["large_cap"],
            sectors=["IT", "Banking & Finance"],
            price_min=50.0,
            price_max=5000.0,
            exclusions=["penny_stocks", "high_debt"],
        )
        assert params.horizon == "swing_short_term"
        assert params.risk == "moderate"
        assert params.capital == 100000.0
        assert params.price_min == 50.0
        assert params.price_max == 5000.0

    def test_horizon_is_required(self):
        with pytest.raises(Exception):
            StockQueryParams(horizon="", risk="moderate")

    def test_risk_is_required(self):
        with pytest.raises(Exception):
            StockQueryParams(horizon="3_12_months", risk="")

    def test_negative_capital_rejected(self):
        with pytest.raises(ValueError):
            StockQueryParams(horizon="3_12_months", risk="moderate", capital=-5000.0)

    def test_min_price_exceeding_max_price_rejected(self):
        with pytest.raises(ValueError):
            StockQueryParams(horizon="3_12_months", risk="moderate", price_min=5000.0, price_max=1000.0)

    def test_horizon_normalization(self):
        p1 = StockQueryParams(horizon="1 month", risk="low")
        assert p1.horizon == "swing_short_term"
        assert p1.risk == "conservative"

        p2 = StockQueryParams(horizon="long term", risk="high")
        assert p2.horizon == "3_plus_years"
        assert p2.risk == "aggressive"


class TestStockScreenerPipeline:
    """Verifies end-to-end multi-dimensional screening, scoring, and explanations."""

    def test_screener_produces_valid_candidates(self):
        screener = StockScreener()
        params = StockQueryParams(
            horizon="3_12_months",
            risk="moderate",
            capital=200000.0,
            objective=["growth"],
            market_cap=["large_cap", "mid_cap"],
            sectors=["Any"],
            exclusions=["penny_stocks"],
        )
        res = screener.run_screening(params)
        assert res.success is True
        assert res.total_scanned > 0
        assert len(res.candidates) > 0
        assert res.voice_response != ""

        # Check candidate structure
        top = res.candidates[0]
        assert top.company_name != ""
        assert top.symbol.endswith(".NS") or top.symbol != ""
        assert top.current_price > 0
        assert top.score >= 50.0
        assert len(top.why_matched) > 0
        assert len(top.risks) > 0
        assert top.invalidation_level is not None or top.support_level != "N/A"

    def test_screener_respects_sector_filter(self):
        screener = StockScreener()
        params = StockQueryParams(
            horizon="swing_short_term",
            risk="moderate",
            sectors=["IT"],
        )
        res = screener.run_screening(params)
        assert res.success is True
        for cand in res.candidates:
            assert "IT" in cand.sector or "Technology" in cand.sector

    def test_screener_respects_market_cap_filter(self):
        screener = StockScreener()
        params = StockQueryParams(
            horizon="1_3_months",
            risk="conservative",
            market_cap=["large_cap"],
        )
        res = screener.run_screening(params)
        assert res.success is True
        for cand in res.candidates:
            assert cand.market_cap == "Large Cap"

    def test_screener_respects_price_filter(self):
        screener = StockScreener()
        params = StockQueryParams(
            horizon="3_12_months",
            risk="moderate",
            price_min=500.0,
            price_max=2000.0,
        )
        res = screener.run_screening(params)
        assert res.success is True
        for cand in res.candidates:
            assert 500.0 <= cand.current_price <= 2000.0

    def test_no_guaranteed_return_claim_in_response(self):
        screener = StockScreener()
        params = StockQueryParams(horizon="3_12_months", risk="aggressive")
        res = screener.run_screening(params)
        assert "guaranteed" not in res.voice_response.lower()
        assert "pakka return" not in res.voice_response.lower()
        assert "buy" not in res.voice_response.lower()
        assert "decision support only" in res.disclaimer.lower()


class TestStockWebServerAndAPI:
    """Verifies local HTTP server lifecycle and REST endpoints."""

    @classmethod
    def setup_class(cls):
        cls.server = StockWebServer.get_instance(port=8765)
        cls.url = cls.server.start()

    def test_server_status_endpoint(self):
        import urllib.request
        status_url = f"{self.url.replace('/wizard', '')}/api/stocks/status"
        req = urllib.request.Request(status_url)
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))
            assert "market_status" in data
            assert "timestamp" in data

    def test_server_analyze_endpoint_success(self):
        import urllib.request
        analyze_url = f"{self.url.replace('/wizard', '')}/api/stocks/analyze"
        payload = json.dumps({
            "horizon": "3_12_months",
            "risk": "moderate",
            "capital": 100000.0,
            "objective": ["growth"],
            "market_cap": ["large_cap"],
            "sectors": ["Any"],
        }).encode("utf-8")

        req = urllib.request.Request(analyze_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))
            assert data["success"] is True
            assert "candidates" in data
            assert len(data["candidates"]) > 0

    def test_server_analyze_endpoint_validation_error(self):
        import urllib.request
        import urllib.error
        analyze_url = f"{self.url.replace('/wizard', '')}/api/stocks/analyze"
        # Missing horizon and risk
        payload = json.dumps({"capital": -100}).encode("utf-8")

        req = urllib.request.Request(analyze_url, data=payload, headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req, timeout=5)
        assert exc_info.value.code == 422
