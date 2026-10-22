# core/equity_research/models.py
"""
Data models and contracts for the Indian Equity 1-Month Research & Decision-Support Engine.
Enforces typed structures for market data, regimes, indicators, fundamentals, catalysts,
scenarios, user profiles, and transparent evidence scoring.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Tuple


class MarketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    POST_CLOSE = "POST_CLOSE"


class MarketRegime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    MIXED = "MIXED"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class EvidenceTier(str, Enum):
    STRONG_EVIDENCE = "STRONG EVIDENCE"
    MODERATE_EVIDENCE = "MODERATE EVIDENCE"
    WEAK_EVIDENCE = "WEAK/MIXED EVIDENCE"
    STRONG = "STRONG EVIDENCE"
    MODERATE = "MODERATE EVIDENCE"
    WEAK = "WEAK/MIXED EVIDENCE"


class NewsClassification(str, Enum):
    POSITIVE_CATALYST = "POSITIVE_CATALYST"
    NEGATIVE_CATALYST = "NEGATIVE_CATALYST"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


class EpistemologicalCategory(str, Enum):
    FACT = "FACT"
    SOURCE_REPORTED_CLAIM = "SOURCE_REPORTED_CLAIM"
    ANALYST_INTERPRETATION = "ANALYST_INTERPRETATION"
    JARVIS_INFERENCE = "JARVIS_INFERENCE"


class OutputMode(str, Enum):
    QUICK = "QUICK"
    STANDARD = "STANDARD"
    DETAILED = "DETAILED"


class AdvisoryMode(str, Enum):
    EDUCATION = "EDUCATION"
    RESEARCH = "RESEARCH"
    PERSONALIZED_ADVISORY = "PERSONALIZED_ADVISORY"


@dataclass
class OHLCVBar:
    """Represents a single session bar for Indian equity instruments."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    delivery_pct: Optional[float] = None


@dataclass
class UserInvestmentProfile:
    """Captures client risk, financial capacity, and preferences for suitability gating."""
    investment_amount: Optional[float] = None          # e.g., 200000.0 (2 Lakh INR)
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    risk_capacity: str = "MODERATE"                    # HIGH, MODERATE, LOW
    investment_horizon: str = "1_MONTH"                # Explicitly 1 month
    liquidity_requirement: str = "NORMAL"              # HIGH, NORMAL, LOW
    existing_portfolio: List[Dict[str, Any]] = field(default_factory=list) # [{symbol, sector, allocation_pct}]
    sector_preferences: List[str] = field(default_factory=list)
    sector_exclusions: List[str] = field(default_factory=list)
    maximum_acceptable_loss_pct: float = 7.0           # 7% max drawdown tolerance for 1-month
    trading_experience: str = "INTERMEDIATE"           # BEGINNER, INTERMEDIATE, EXPERIENCED
    # Compatibility aliases
    total_capital: Optional[float] = None
    max_loss_limit_pct: Optional[float] = None
    max_loss_tolerance_pct: Optional[float] = None
    strategy_preference: str = "any"
    sector_preference: Optional[str] = None

    def __post_init__(self):
        if self.total_capital is not None and self.investment_amount is None:
            self.investment_amount = self.total_capital
        elif self.investment_amount is not None and self.total_capital is None:
            self.total_capital = self.investment_amount

        if self.max_loss_limit_pct is not None:
            self.maximum_acceptable_loss_pct = self.max_loss_limit_pct
        elif self.max_loss_tolerance_pct is not None:
            self.maximum_acceptable_loss_pct = self.max_loss_tolerance_pct

        if self.sector_preference and self.sector_preference not in self.sector_preferences:
            self.sector_preferences.append(self.sector_preference)

    def is_complete_for_personalized(self) -> bool:
        """Determines if sufficient profile data exists before giving personalized recommendations."""
        return self.investment_amount is not None and self.investment_amount > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize profile to dictionary."""
        return {
            "investment_amount": self.investment_amount,
            "risk_tolerance": self.risk_tolerance.value if hasattr(self.risk_tolerance, "value") else str(self.risk_tolerance),
            "risk_capacity": self.risk_capacity,
            "investment_horizon": self.investment_horizon,
            "liquidity_requirement": self.liquidity_requirement,
            "existing_portfolio": self.existing_portfolio,
            "sector_preferences": self.sector_preferences,
            "sector_exclusions": self.sector_exclusions,
            "maximum_acceptable_loss_pct": self.maximum_acceptable_loss_pct,
            "trading_experience": self.trading_experience,
        }


@dataclass
class TechnicalIndicators:
    """1-Month specific technical indicator snapshot."""
    trend: str = "NEUTRAL"                             # BULLISH, BEARISH, SIDEWAYS
    ema_20: float = 0.0
    ema_50: float = 0.0
    sma_200: float = 0.0
    rsi: float = 50.0                                  # 14-period daily RSI
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    atr: float = 0.0                                   # 14-period daily ATR (absolute volatility)
    atr_pct: float = 0.0                               # ATR as percentage of price
    adx: float = 0.0                                   # 14-period ADX trend strength
    supertrend_direction: str = "BULLISH"              # BULLISH / BEARISH
    supertrend_value: float = 0.0
    support_level: float = 0.0                         # Dynamic swing support
    resistance_level: float = 0.0                      # Dynamic swing resistance
    volume_trend: str = "STABLE"                       # EXPANDING, CONTRACTING, STABLE
    volume_breakout: bool = False                      # Current vol > 1.5x 20-day SMA volume
    volume_ratio: float = 1.0                          # Current vol / 20-day SMA vol
    relative_strength_nifty: float = 0.0               # Outperformance vs NIFTY 50 over 20-40 days
    recent_swing_high: float = 0.0
    recent_swing_low: float = 0.0


@dataclass
class FundamentalSnapshot:
    """Supporting fundamental context for 1-month swing candidates."""
    symbol: str = ""
    revenue_growth_yoy: float = 0.0                    # % YoY
    profit_growth_yoy: float = 0.0                     # % YoY
    operating_margin: float = 0.0                      # %
    debt_to_equity: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    promoter_holding_pct: float = 0.0
    pledged_shares_pct: float = 0.0                    # Risk flag if > 20%
    data_freshness_quarter: str = "Q3-FY25"


@dataclass
class CatalystEvent:
    """Upcoming corporate or macro event relevant to the 1-month timeframe."""
    event_type: str                                    # EARNINGS, CORPORATE_ACTION, POLICY, ORDER_WIN, MACRO
    event_date: str                                    # YYYY-MM-DD
    description: str = ""
    expected_relevance: str = "MEDIUM"                 # HIGH, MEDIUM, LOW
    uncertainty: str = "MEDIUM"                        # HIGH, MODERATE, LOW


@dataclass
class NewsSentimentItem:
    """Verified news headline with strict epistemological categorization."""
    headline: str
    source: str
    timestamp: str
    classification: NewsClassification
    category: EpistemologicalCategory
    summary: str = ""


@dataclass
class ScenarioCase:
    """Describes scenario triggers, analytical targets, and invalidation rules."""
    conditions: str
    target_zone: Tuple[float, float]                   # (low, high)
    direction: str
    invalidation_level: float
    key_evidence: List[str] = field(default_factory=list)


@dataclass
class RiskScenario:
    """Three-tier scenario modeling for 1-month holding horizon."""
    bull_case: ScenarioCase
    base_case: ScenarioCase
    bear_case: ScenarioCase
    reward_to_risk_ratio: float = 2.0
    invalidation_level: float = 0.0
    entry_zone: Tuple[float, float] = (0.0, 0.0)

    @property
    def risk_reward_ratio(self) -> float:
        return self.reward_to_risk_ratio


@dataclass
class StockCandidate:
    """Comprehensive candidate research profile."""
    symbol: str                                        # e.g., "RELIANCE.NS"
    company_name: str                                  # e.g., "Reliance Industries Ltd"
    sector: str                                        # e.g., "Energy"
    current_price: float
    closing_price: float
    is_market_open: bool
    data_timestamp: str
    data_source: str = "NSE_EQUITY_FEED"
    is_stale_data: bool = False
    setup_summary: str = ""
    strategy_matched: str = "TrendFollowing"
    technical: TechnicalIndicators = field(default_factory=TechnicalIndicators)
    fundamentals: FundamentalSnapshot = field(default_factory=FundamentalSnapshot)
    catalysts: List[CatalystEvent] = field(default_factory=list)
    recent_news: List[NewsSentimentItem] = field(default_factory=list)
    scenario: Optional[RiskScenario] = None
    multi_factor_score: float = 0.0                    # 0 to 100
    evidence_tier: EvidenceTier = EvidenceTier.MODERATE_EVIDENCE
    holding_horizon: str = "1_MONTH (approx 20-22 trading days)"
    liquidity_adtv_cr: float = 0.0                     # 20-day Average Daily Traded Value in Crores INR
    liquidity_grade: str = "HIGH"                      # HIGH (> 50 Cr), MODERATE (10-50 Cr), LOW (< 10 Cr)
    key_risks: List[str] = field(default_factory=list)
    invalidation_thesis: str = ""
    review_date: str = ""
    expiry_date: str = ""


@dataclass
class MonitoredThesis:
    """Active thesis saved when user asks to monitor a specific stock setup."""
    symbol: str
    company_name: str
    entry_thesis: str
    entry_price_benchmark: float
    invalidation_level: float
    target_zone: Tuple[float, float]
    created_date: str
    review_date: str
    expiry_date: str                                   # Exactly 30 calendar days from creation
    is_active: bool = True
    invalidation_triggered: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Returns dictionary representation of monitored thesis."""
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "entry_thesis": self.entry_thesis,
            "entry_price_benchmark": self.entry_price_benchmark,
            "invalidation_level": self.invalidation_level,
            "target_zone": list(self.target_zone),
            "created_date": self.created_date,
            "review_date": self.review_date,
            "expiry_date": self.expiry_date,
            "is_active": self.is_active,
            "invalidation_triggered": self.invalidation_triggered,
            "notes": self.notes,
        }


@dataclass
class ResearchReport:
    """Formal research deliverable returned to user."""
    request_id: str
    generated_at: str
    market_status: MarketStatus
    last_trading_session: str
    market_regime: MarketRegime
    regime_rationale: str
    universe_size_scanned: int
    candidates: List[StockCandidate]
    profile_used: Optional[UserInvestmentProfile] = None
    portfolio_concentration_feedback: str = ""
    data_limitations: List[str] = field(default_factory=list)
    advisory_mode: AdvisoryMode = AdvisoryMode.RESEARCH
    output_mode: OutputMode = OutputMode.STANDARD
    formatted_text: str = ""
    review_date: str = ""
    disclaimer: str = (
        "DECISION SUPPORT ONLY: This research report provides analytical evaluation based on "
        "historical price action, publicly disclosed corporate data, and market regime context. "
        "It does NOT guarantee returns, predict certainty, or constitute financial/investment tips. "
        "Equities carry capital risk. Past performance does not guarantee future results."
    )
