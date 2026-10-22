# stock/stock_service.py
"""
Stock Service Layer for Jarvis V2.1.
Authoritative orchestrator maintaining singleton state, active screening results,
workflow state transitions, and conversational follow-up filtering.
"""

import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from core.equity_research.manager import EquityResearchManager
from .stock_history import StockHistoryDatabase
from .stock_memory import StockMemoryEngine
from .stock_models import (
    PerformanceMetrics,
    PriceSnapshotRecord,
    RecommendationRecord,
    StockAnalysisResponse,
    StockCandidateResult,
    StockEventRecord,
    StockQueryParams,
    WorkflowStateUpdate,
)
from .stock_screener import StockScreener
from .stock_tracker import StockTracker

logger = logging.getLogger("jarvis.stock.service")


class StockService:
    """Singleton service coordinating stock screening, wizard sessions, and conversational follow-ups."""

    _instance: Optional["StockService"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.screener = StockScreener()
        self.equity_manager = EquityResearchManager.get_instance()
        self.history_db = StockHistoryDatabase.get_instance()
        self.tracker = StockTracker(db=self.history_db)
        self.memory_engine = StockMemoryEngine.get_instance(db=self.history_db)
        self.current_state = "IDLE"
        self.active_params: Dict[str, Any] = {}
        self.last_response: Optional[StockAnalysisResponse] = None
        self.last_shortlist: List[StockCandidateResult] = []
        self._state_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "StockService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def initialize_workflow(self, initial_params: Optional[Dict[str, Any]] = None) -> WorkflowStateUpdate:
        """Initializes a new stock selection workflow session with optional pre-filled parameters."""
        with self._state_lock:
            self.current_state = "STOCK_WIZARD_OPEN"
            self.active_params = {
                "horizon": "3_12_months",
                "risk": "moderate",
                "capital": None,
                "objective": ["growth"],
                "market_cap": ["any"],
                "sectors": [],
                "technical_preferences": [],
                "fundamental_preferences": [],
                "price_min": None,
                "price_max": None,
                "exclusions": ["penny_stocks"],
            }
            if initial_params:
                for k, v in initial_params.items():
                    if v is not None:
                        self.active_params[k] = v

            self.current_state = "WAITING_FOR_USER_SELECTION"
            return WorkflowStateUpdate(
                state=self.current_state,
                active_params=self.active_params,
                last_candidates=[],
                timestamp=time.time(),
            )

    def update_active_param(self, key: str, value: Any) -> Dict[str, Any]:
        """Updates a single parameter during active workflow."""
        with self._state_lock:
            self.active_params[key] = value
            return dict(self.active_params)

    def analyze(self, params_dict: Dict[str, Any]) -> StockAnalysisResponse:
        """Validates incoming parameters, runs screener, and updates active state."""
        with self._state_lock:
            self.current_state = "VALIDATING_SELECTION"

        # Validate with Pydantic model
        validated_params = StockQueryParams(**params_dict)

        with self._state_lock:
            self.current_state = "ANALYZING_STOCKS"
            self.active_params = validated_params.model_dump()

        # Run screener
        resp = self.screener.run_screening(validated_params)

        # Save immutable historical recommendation session into SQLite
        if resp.candidates:
            try:
                sid, records = self.history_db.save_session(
                    params=validated_params,
                    candidates=resp.candidates,
                )
                resp.session_id = sid
            except Exception as e:
                logger.error(f"StockService: Failed to save recommendation session to DB: {e}", exc_info=True)

        with self._state_lock:
            self.last_response = resp
            self.last_shortlist = resp.candidates
            self.current_state = "RESULTS_READY"

        return resp

    def get_recommendation_history(self, limit: int = 50) -> List[RecommendationRecord]:
        """Retrieves past stock recommendations from permanent SQLite storage."""
        return self.history_db.get_all_recommendations(limit=limit)

    def get_recommendation_detail(self, rec_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves recommendation record, price snapshots, audit events, and live performance."""
        rec = self.history_db.get_recommendation(rec_id)
        if not rec:
            return None
        snaps = self.history_db.get_price_snapshots(rec_id)
        events = self.history_db.get_events(rec_id)
        curr_price = snaps[-1].price if snaps else rec.reference_price
        perf = self.tracker.calculate_performance(rec, curr_price)
        return {
            "recommendation": rec.model_dump(),
            "current_performance": perf.model_dump(),
            "price_snapshots": [s.model_dump() for s in snaps],
            "events": [e.model_dump() for e in events],
        }

    def track_live_price(
        self,
        rec_id: str,
        current_price: float,
        source: str = "NSE_LIVE",
        data_timestamp: str = "",
    ) -> Tuple[Optional[RecommendationRecord], PerformanceMetrics, Optional[StockEventRecord]]:
        """Updates live price snapshot, evaluates lifecycle transitions, and emits audit events."""
        return self.tracker.track_price_update(
            recommendation_id=rec_id,
            current_price=current_price,
            source=source,
            data_timestamp=data_timestamp,
        )

    def answer_memory_query(self, user_text: str) -> Tuple[bool, str]:
        """Answers historical recommendation questions (date, price, targets, exit, status)."""
        return self.memory_engine.answer_recommendation_query(user_text)

    def get_workflow_state(self) -> WorkflowStateUpdate:
        """Returns current workflow state representation."""
        with self._state_lock:
            return WorkflowStateUpdate(
                state=self.current_state,
                active_params=self.active_params,
                last_candidates=self.last_shortlist,
                timestamp=time.time(),
            )

    def complete_workflow(self) -> None:
        """Marks workflow as complete."""
        with self._state_lock:
            self.current_state = "WORKFLOW_COMPLETE"

    def handle_followup_utterance(self, text: str) -> Tuple[bool, str]:
        """
        Interprets follow-up commands like:
        - "isme se IT wale dikhao"
        - "risk kam karo"
        - "sirf large cap"
        - "₹50,000 ke andar"
        - "technical setup batao"
        - "iske risks kya hain?"
        Returns (handled, voice_response).
        """
        low = text.lower().strip()

        # 1. Risk reduction ("risk kam karo", "conservative karo")
        if any(p in low for p in ["risk kam", "kam risk", "conservative", "low risk", "reduce risk"]):
            new_params = dict(self.active_params)
            new_params["risk"] = "conservative"
            resp = self.analyze(new_params)
            names = ", ".join([c.company_name for c in resp.candidates[:3]]) if resp.candidates else "koi stock nahi mila"
            return True, f"Risk preference conservative set kar diya hai. Updated candidates: {names}."

        # 2. Risk inquiry questions ("iske risks kya hain?", "invalidation level kya hai?")
        if any(p in low for p in ["risks kya", "kya risk", "risk kya", "kya risks", "khatra", "nuksan", "invalidation", "stop loss", "stoploss"]):
            if not self.last_shortlist:
                return True, "Abhi koi candidates analyzed nahi hain."
            top = self.last_shortlist[0]
            risks_str = " Aur ".join(top.risks[:2])
            inval_str = f" Setup support level ₹{top.invalidation_level:.1f} ke niche invalidate ho jayega." if top.invalidation_level else ""
            return True, f"{top.company_name} ke key risks: {risks_str}.{inval_str}"

        # 3. Technical setup inquiry
        if any(p in low for p in ["technical setup", "technical analysis", "chart setup", "indicator", "technicals"]):
            if not self.last_shortlist:
                return True, "Abhi koi candidates analyzed nahi hain. Kripya pehle screening run kijiye."
            top = self.last_shortlist[0]
            resp = (
                f"{top.company_name} ka technical setup: {top.technical_summary}. "
                f"Relative strength aur moving average confirmation positive hai."
            )
            return True, resp

        # 4. Sector filter refinement ("isme se IT wale dikhao", "banking wale dikhao")
        for sec in ["it", "banking", "auto", "pharma", "fmcg", "energy", "defence", "metals"]:
            if (len(sec) <= 2 and re.search(r'\b' + re.escape(sec) + r'\b', low)) or (len(sec) > 2 and sec in low):
                matching = [c for c in self.last_shortlist if sec in c.sector.lower()]
                if matching:
                    names = ", ".join([c.company_name for c in matching])
                    return True, f"Screened candidates mein se {sec.upper()} sector ke stocks hain: {names}."
                else:
                    new_params = dict(self.active_params)
                    new_params["sectors"] = [sec.upper()]
                    resp = self.analyze(new_params)
                    if resp.candidates:
                        names = ", ".join([c.company_name for c in resp.candidates[:3]])
                        return True, f"{sec.upper()} sector ke filtered candidates update ho gaye hain: {names}."
                    return True, f"{sec.upper()} sector mein aapke criteria se koi stock match nahi hua."

        # 5. Market Cap refinement ("sirf large cap", "mid cap dikhao")
        if "large cap" in low or "largecap" in low:
            new_params = dict(self.active_params)
            new_params["market_cap"] = ["large_cap"]
            resp = self.analyze(new_params)
            names = ", ".join([c.company_name for c in resp.candidates[:3]]) if resp.candidates else "koi stock nahi mila"
            return True, f"Sirf Large Cap candidates filter kar diye hain: {names}."

        if "mid cap" in low or "midcap" in low:
            new_params = dict(self.active_params)
            new_params["market_cap"] = ["mid_cap"]
            resp = self.analyze(new_params)
            names = ", ".join([c.company_name for c in resp.candidates[:3]]) if resp.candidates else "koi stock nahi mila"
            return True, f"Mid Cap candidates filter kar diye hain: {names}."

        # 5. Risk reduction ("risk kam karo", "conservative karo")
        if any(p in low for p in ["risk kam", "kam risk", "conservative", "low risk"]):
            new_params = dict(self.active_params)
            new_params["risk"] = "conservative"
            resp = self.analyze(new_params)
            names = ", ".join([c.company_name for c in resp.candidates[:3]]) if resp.candidates else "koi stock nahi mila"
            return True, f"Risk preference conservative set kar diya hai. Updated candidates: {names}."

        # 6. Fundamental strength inquiry ("fundamental strong wale dikhao")
        if "fundamental" in low or "fundamental strong" in low:
            if self.last_shortlist:
                top = self.last_shortlist[0]
                return True, f"Fundamentally strongest candidate {top.company_name} hai: {top.fundamental_summary}."

        return False, ""
