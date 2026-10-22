# core/equity_research/monitor.py
"""
1-Month Thesis Monitoring Engine for Indian Equities.
Tracks active setups, detects invalidations, and enforces strict 30-calendar-day thesis expiry.
"""

from datetime import datetime, timedelta
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from .models import MonitoredThesis

logger = logging.getLogger("jarvis.equity_research.monitor")


class ThesisMonitor:
    """
    Manages active monitored theses for user-selected stocks.
    Guarantees that 1-month ideas expire automatically and are never kept open indefinitely.
    """

    def __init__(self, storage_file: str = "data/equity_monitored_theses.json"):
        self.storage_file = storage_file
        self._theses: Dict[str, MonitoredThesis] = {}
        self._load()

    def add_thesis(
        self,
        symbol: str,
        company_name: str,
        entry_thesis: str,
        entry_price: float,
        invalidation_level: float,
        target_zone: Tuple[float, float],
    ) -> MonitoredThesis:
        """Adds a new monitored thesis with an explicit 30-day expiry date."""
        now = datetime.utcnow()
        clean_symbol = symbol.upper().strip()
        created_str = now.strftime("%Y-%m-%d")
        review_str = (now + timedelta(days=14)).strftime("%Y-%m-%d")
        expiry_str = (now + timedelta(days=30)).strftime("%Y-%m-%d")

        thesis = MonitoredThesis(
            symbol=clean_symbol,
            company_name=company_name,
            entry_thesis=entry_thesis,
            entry_price_benchmark=entry_price,
            invalidation_level=invalidation_level,
            target_zone=target_zone,
            created_date=created_str,
            review_date=review_str,
            expiry_date=expiry_str,
            is_active=True,
            invalidation_triggered=False,
            notes=[f"Thesis created on {created_str} at benchmark price ₹{entry_price:,.2f}."],
        )

        self._theses[clean_symbol] = thesis
        self._save()
        logger.info("Added 1-month monitored thesis for %s (Expiry: %s)", clean_symbol, expiry_str)
        return thesis

    def get_thesis(self, symbol: str) -> Optional[MonitoredThesis]:
        """Retrieves monitored thesis for a given stock symbol."""
        clean_symbol = symbol.upper().strip()
        self.check_expirations()
        return self._theses.get(clean_symbol)

    def list_active_theses(self) -> List[MonitoredThesis]:
        """Returns all currently active monitored theses."""
        self.check_expirations()
        return [t for t in self._theses.values() if t.is_active]

    def check_expirations(self, current_date: Optional[datetime] = None) -> List[str]:
        """Checks and marks theses that have surpassed their 30-day horizon as EXPIRED."""
        now = current_date or datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        expired_symbols = []

        for symbol, thesis in self._theses.items():
            if thesis.is_active and today_str >= thesis.expiry_date:
                thesis.is_active = False
                thesis.notes.append(f"Thesis expired automatically on {today_str} after 30-day investment window.")
                expired_symbols.append(symbol)

        if expired_symbols:
            self._save()
            logger.info("Expired %d active theses: %s", len(expired_symbols), expired_symbols)

        return expired_symbols

    def check_invalidation(self, symbol: str, current_price: float) -> Tuple[bool, str]:
        """Checks if current price has violated the invalidation stop level."""
        thesis = self.get_thesis(symbol)
        if not thesis or not thesis.is_active:
            return False, "No active monitored thesis found."

        if current_price <= thesis.invalidation_level:
            thesis.is_active = False
            thesis.invalidation_triggered = True
            msg = (
                f"🚨 THESIS INVALIDATION ALERT: {symbol} has dropped to ₹{current_price:,.2f}, "
                f"violating the analytical stop level of ₹{thesis.invalidation_level:,.2f}. "
                f"The 1-month swing setup is formally invalidated."
            )
            thesis.notes.append(msg)
            self._save()
            return True, msg

        return False, f"{symbol} price (₹{current_price:,.2f}) remains above invalidation level (₹{thesis.invalidation_level:,.2f})."

    # Alias for price check
    update_price_check = check_invalidation

    def _save(self) -> None:
        """Persists monitored theses to JSON."""
        try:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            data = {}
            for sym, t in self._theses.items():
                data[sym] = {
                    "symbol": t.symbol,
                    "company_name": t.company_name,
                    "entry_thesis": t.entry_thesis,
                    "entry_price_benchmark": t.entry_price_benchmark,
                    "invalidation_level": t.invalidation_level,
                    "target_zone": list(t.target_zone),
                    "created_date": t.created_date,
                    "review_date": t.review_date,
                    "expiry_date": t.expiry_date,
                    "is_active": t.is_active,
                    "invalidation_triggered": t.invalidation_triggered,
                    "notes": t.notes,
                }
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist monitored theses: %s", e)

    def _load(self) -> None:
        """Loads monitored theses from JSON."""
        if not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sym, d in data.items():
                self._theses[sym] = MonitoredThesis(
                    symbol=d["symbol"],
                    company_name=d["company_name"],
                    entry_thesis=d["entry_thesis"],
                    entry_price_benchmark=d["entry_price_benchmark"],
                    invalidation_level=d["invalidation_level"],
                    target_zone=tuple(d.get("target_zone", (0.0, 0.0))),
                    created_date=d["created_date"],
                    review_date=d["review_date"],
                    expiry_date=d["expiry_date"],
                    is_active=d.get("is_active", True),
                    invalidation_triggered=d.get("invalidation_triggered", False),
                    notes=d.get("notes", []),
                )
        except Exception as e:
            logger.warning("Could not load monitored theses: %s", e)
