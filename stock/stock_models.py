# stock/stock_models.py
"""
Pydantic data models and schemas for the Stock Query Wizard and Screening Pipeline.
Enforces strict input validation, horizon/risk requirements, and structured responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class StockQueryParams(BaseModel):
    """User-specified parameters collected from the Stock Query Wizard or Voice NLU."""
    horizon: str = Field(..., description="Investment horizon (e.g., intraday, swing_short_term, 1_3_months, 3_12_months, 1_3_years, 3_plus_years)")
    risk: str = Field(..., description="Risk preference: conservative, moderate, aggressive")
    capital: Optional[float] = Field(default=None, description="Investment capital in INR")
    objective: List[str] = Field(default_factory=list, description="Objectives: capital_growth, dividend_income, momentum, value, growth, breakout, compounder, balanced")
    market_cap: List[str] = Field(default_factory=list, description="Market segments: large_cap, mid_cap, small_cap, any")
    sectors: List[str] = Field(default_factory=list, description="Sector preferences (empty or 'Any' for all sectors)")
    technical_preferences: List[str] = Field(default_factory=list, description="Technical preferences (momentum, trend, breakout, pullback, moving_average, supertrend, rsi, volume)")
    fundamental_preferences: List[str] = Field(default_factory=list, description="Fundamental preferences (revenue_growth, profit_growth, eps_growth, roe, roce, low_debt, cash_flow, dividend, valuation)")
    price_min: Optional[float] = Field(default=None, description="Minimum stock price in INR")
    price_max: Optional[float] = Field(default=None, description="Maximum stock price in INR")
    exclusions: List[str] = Field(default_factory=list, description="Exclusions (penny_stocks, volatile, loss_making, high_debt, low_liquidity)")

    @field_validator("horizon")
    @classmethod
    def validate_horizon(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Investment horizon is required.")
        norm = v.lower().strip().replace(" ", "_").replace("-", "_").replace("+", "_plus")
        valid_horizons = {
            "intraday", "swing", "short_term", "swing_short_term",
            "1_3_months", "1_month", "3_12_months", "1_3_years", "3_plus_years", "long_term"
        }
        # Map common variations
        if norm in ("1_month", "short_term", "swing"):
            return "swing_short_term"
        if norm in ("long_term", "3_years", "3plus_years"):
            return "3_plus_years"
        if norm in valid_horizons:
            return norm
        return norm

    @field_validator("risk")
    @classmethod
    def validate_risk(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Risk preference is required.")
        norm = v.lower().strip()
        if norm in ("conservative", "low", "kam"):
            return "conservative"
        if norm in ("aggressive", "high", "zyada", "jyada"):
            return "aggressive"
        return "moderate"

    @field_validator("capital")
    @classmethod
    def validate_capital(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Capital amount cannot be negative.")
        return v

    @model_validator(mode="after")
    def validate_price_range(self) -> "StockQueryParams":
        if self.price_min is not None and self.price_min < 0:
            raise ValueError("Minimum price cannot be negative.")
        if self.price_max is not None and self.price_max < 0:
            raise ValueError("Maximum price cannot be negative.")
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("Minimum price cannot exceed maximum price.")
        return self


class StockCandidateResult(BaseModel):
    """Structured candidate profile returned for UI display and explainable voice responses."""
    company_name: str
    symbol: str
    current_price: float
    reference_price: Optional[float] = None
    market_cap: str  # Large Cap, Mid Cap, Small Cap
    sector: str
    trend: str  # Bullish, Neutral, Bearish
    score: float  # 0 to 100
    why_matched: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    key_metrics: Dict[str, Any] = Field(default_factory=dict)
    fundamental_summary: str = ""
    technical_summary: str = ""
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_method: str = "risk_reward"
    invalidation_price: Optional[float] = None
    invalidation_level: Optional[float] = None  # Alias for backward-compatibility
    target_zone: Optional[List[float]] = None
    holding_period_days: int = 30
    time_exit_date: Optional[str] = None
    data_timestamp: str = ""
    data_source: str = "NSE_EQUITY_FEED"
    market_status: str = "OPEN"
    is_stale: bool = False


class TargetExitPlan(BaseModel):
    """Predefined mathematical target and exit/invalidation derivation."""
    reference_price: float
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_method: str = "risk_reward"  # technical_resistance, risk_reward, strategy_engine
    invalidation_price: Optional[float] = None
    exit_type: str = "setup_invalidation"
    holding_period_days: int = 30
    time_exit_date: Optional[str] = None
    target_notes: str = ""


class PerformanceMetrics(BaseModel):
    """Real-time performance calculation comparing live market price vs. immutable snapshot."""
    reference_price: float
    current_price: float
    absolute_change: float
    percentage_change: float
    target_1_distance: Optional[float] = None
    target_2_distance: Optional[float] = None
    invalidation_distance: Optional[float] = None
    tracking_status: str = "ACTIVE"


class PriceSnapshotRecord(BaseModel):
    """Historical tracking point in stock_price_snapshots table."""
    id: Optional[str] = None
    recommendation_id: str
    symbol: str
    price: float
    timestamp: float
    source: str = "NSE_EQUITY_FEED"
    data_timestamp: str = ""


class StockEventRecord(BaseModel):
    """Audit trail event record in stock_events table."""
    id: Optional[str] = None
    recommendation_id: str
    symbol: str
    event_type: str  # RECOMMENDED, PRICE_UPDATED, TARGET_1_HIT, TARGET_2_HIT, INVALIDATION_HIT, TIME_EXIT, USER_CLOSED, DATA_ERROR
    old_status: str
    new_status: str
    price: float
    trigger_detail: str = ""
    timestamp: float


class RecommendationRecord(BaseModel):
    """Immutable historical recommendation record stored in stock_recommendations table."""
    id: str
    session_id: str
    user_id: str = "default_user"
    symbol: str
    company_name: str
    exchange: str = "NSE"
    recommendation_date: str  # YYYY-MM-DD in Asia/Kolkata
    recommendation_time: str  # HH:MM:SS
    timezone: str = "Asia/Kolkata"
    reference_price: float  # IMMUTABLE SNAPSHOT
    current_price_at_analysis: float
    target_1: Optional[float] = None  # IMMUTABLE SNAPSHOT
    target_2: Optional[float] = None  # IMMUTABLE SNAPSHOT
    target_method: str = "risk_reward"
    exit_price: Optional[float] = None
    invalidation_price: Optional[float] = None  # IMMUTABLE SNAPSHOT
    exit_type: str = "setup_invalidation"
    maximum_holding_period_days: int = 30
    time_exit_date: Optional[str] = None
    recommendation_type: str = "SWING_LONG"
    investment_horizon: str = "swing_short_term"
    risk_profile: str = "moderate"
    sector: str = ""
    market_cap: str = ""
    technical_reason: str = ""
    fundamental_reason: str = ""
    risk_reason: str = ""
    selection_criteria_json: str = "{}"
    data_source: str = "NSE_EQUITY_FEED"
    data_timestamp: str = ""
    analysis_version: str = "v2.1"
    strategy_version: str = "v1.0-multi-factor-equity"
    status: str = "ACTIVE"  # ACTIVE, TARGET_1_REACHED, TARGET_2_REACHED, INVALIDATED, TIME_EXIT, CLOSED, EXPIRED, DATA_UNAVAILABLE
    created_at: float
    updated_at: float


class StockAnalysisResponse(BaseModel):
    """Full API response returned from POST /api/stocks/analyze."""
    success: bool
    market_status: str
    data_timestamp: str
    data_source: str = "NSE_EQUITY_FEED"
    is_market_open: bool = True
    session_id: Optional[str] = None
    candidates: List[StockCandidateResult] = Field(default_factory=list)
    total_scanned: int = 0
    total_matched: int = 0
    applied_filters: Dict[str, Any] = Field(default_factory=dict)
    voice_response: str = ""
    disclaimer: str = (
        "DECISION SUPPORT ONLY: This research screening provides analytical evaluation based on "
        "historical price action, publicly disclosed corporate data, and market regime context. "
        "It does NOT guarantee returns, predict certainty, or constitute financial/investment tips. "
        "Equities carry capital risk. Past performance does not guarantee future results."
    )
    error: Optional[str] = None


class WorkflowStateUpdate(BaseModel):
    """Payload representing current state of STOCK_SELECTION_WORKFLOW."""
    state: str  # IDLE, STOCK_WIZARD_OPEN, WAITING_FOR_USER_SELECTION, ANALYZING_STOCKS, RESULTS_READY, etc.
    active_params: Dict[str, Any] = Field(default_factory=dict)
    last_candidates: List[StockCandidateResult] = Field(default_factory=list)
    active_query: str = ""
    timestamp: float = 0.0
