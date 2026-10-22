# stock/stock_tracker.py
"""
Stock Recommendation Lifecycle Tracker and Performance Monitor for Jarvis V2.1.
Evaluates current market price against immutable historical snapshots to derive
dynamic lifecycle states, distance metrics, and audit event transitions.
"""

from datetime import datetime
import logging
from typing import Dict, List, Optional, Tuple
from core.timezone_manager import get_timezone_manager

from .stock_history import StockHistoryDatabase
from .stock_models import PerformanceMetrics, RecommendationRecord, StockEventRecord

logger = logging.getLogger("jarvis.stock.tracker")

IST_TZ = get_timezone_manager().get_ist_timezone()


class StockTracker:
    """Evaluates dynamic tracking states, metrics, and emits audit events."""

    def __init__(self, db: Optional[StockHistoryDatabase] = None):
        self.db = db or StockHistoryDatabase.get_instance()

    def evaluate_status(
        self,
        rec: RecommendationRecord,
        current_price: float,
        current_date_str: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """
        Determines (persisted_status, tracking_label, event_type).
        Does NOT alter historical snapshot values.
        """
        if current_price is None or current_price <= 0:
            return "DATA_UNAVAILABLE", "Data Unavailable", ""

        # 1. Invalidation Check (Setup breakdown)
        if rec.invalidation_price is not None and current_price <= rec.invalidation_price:
            return "INVALIDATED", "Invalidation Level Breached", "INVALIDATION_HIT"

        # 2. Target 2 Check (Objective 2 reached)
        if rec.target_2 is not None and current_price >= rec.target_2:
            return "TARGET_2_REACHED", "Target 2 Reached", "TARGET_2_HIT"

        # 3. Target 1 Check (Objective 1 reached)
        if rec.target_1 is not None and current_price >= rec.target_1:
            return "TARGET_1_REACHED", "Target 1 Reached", "TARGET_1_HIT"

        # 4. Time Exit Check (Holding window passed)
        today = current_date_str or datetime.now(IST_TZ).strftime("%Y-%m-%d")
        if rec.time_exit_date and today > rec.time_exit_date:
            return "TIME_EXIT", "Time Exit Window Reached", "TIME_EXIT"

        # 5. Approaching Target 1 Check (within 2% below Target 1)
        if rec.target_1 is not None:
            dist = rec.target_1 - current_price
            if 0 < dist <= (0.02 * rec.target_1):
                return "ACTIVE", "Approaching Target 1", "PRICE_UPDATED"

        return "ACTIVE", "Active Setup", "PRICE_UPDATED"

    def calculate_performance(
        self,
        rec: RecommendationRecord,
        current_price: float,
    ) -> PerformanceMetrics:
        """
        Calculates performance change and distance to key levels using immutable reference price.
        """
        ref = rec.reference_price
        abs_change = round(current_price - ref, 2)
        pct_change = round((abs_change / ref) * 100.0, 2) if ref > 0 else 0.0

        t1_dist = round(rec.target_1 - current_price, 2) if rec.target_1 is not None else None
        t2_dist = round(rec.target_2 - current_price, 2) if rec.target_2 is not None else None
        inv_dist = round(current_price - rec.invalidation_price, 2) if rec.invalidation_price is not None else None

        _, tracking_label, _ = self.evaluate_status(rec, current_price)

        return PerformanceMetrics(
            reference_price=ref,
            current_price=round(current_price, 2),
            absolute_change=abs_change,
            percentage_change=pct_change,
            target_1_distance=t1_dist,
            target_2_distance=t2_dist,
            invalidation_distance=inv_dist,
            tracking_status=tracking_label,
        )

    def track_price_update(
        self,
        recommendation_id: str,
        current_price: float,
        source: str = "NSE_LIVE",
        data_timestamp: str = "",
        timestamp: Optional[float] = None,
    ) -> Tuple[Optional[RecommendationRecord], PerformanceMetrics, Optional[StockEventRecord]]:
        """
        Updates live tracking for a recommendation:
        1. Records price snapshot.
        2. Evaluates state transition.
        3. Updates status in DB if changed.
        4. Logs audit event.
        5. Returns updated record and calculated performance metrics.
        """
        rec = self.db.get_recommendation(recommendation_id)
        if not rec:
            raise ValueError(f"Recommendation with ID '{recommendation_id}' not found.")

        # Save price snapshot
        self.db.record_price_snapshot(
            recommendation_id=rec.id,
            symbol=rec.symbol,
            price=current_price,
            source=source,
            data_timestamp=data_timestamp,
            timestamp=timestamp,
        )

        # Evaluate lifecycle
        new_status, tracking_label, event_type = self.evaluate_status(rec, current_price)
        old_status = rec.status
        event_record = None

        if new_status != old_status:
            self.db.update_status(rec.id, new_status)
            event_record = self.db.record_event(
                recommendation_id=rec.id,
                symbol=rec.symbol,
                event_type=event_type,
                old_status=old_status,
                new_status=new_status,
                price=current_price,
                trigger_detail=f"Price ₹{current_price:.2f} triggered transition to {new_status} ({tracking_label})",
                timestamp=timestamp,
            )
            rec.status = new_status

        perf = self.calculate_performance(rec, current_price)
        return rec, perf, event_record
