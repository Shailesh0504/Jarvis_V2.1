# core/equity_research/__init__.py
"""
Indian Equity 1-Month Investment Research & Decision-Support Engine Package.
"""

from .models import (
    AdvisoryMode,
    EvidenceTier,
    MarketRegime,
    MarketStatus,
    OutputMode,
    ResearchReport,
    StockCandidate,
    UserInvestmentProfile,
)
from .manager import EquityResearchManager, get_equity_research_manager

__all__ = [
    "EquityResearchManager",
    "get_equity_research_manager",
    "MarketStatus",
    "MarketRegime",
    "EvidenceTier",
    "OutputMode",
    "AdvisoryMode",
    "UserInvestmentProfile",
    "StockCandidate",
    "ResearchReport",
]
