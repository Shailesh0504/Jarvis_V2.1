# stock/stock_targets.py
"""
Stock Target and Invalidation Calculation Engine for Jarvis V2.1.
Derives mathematically sound Target 1, Target 2, setup invalidation levels,
holding periods, and time-exit dates without fabricating data.
"""

from datetime import datetime, timedelta
import logging
from typing import Any, Dict, Optional
from core.timezone_manager import get_timezone_manager

from .stock_models import TargetExitPlan

logger = logging.getLogger("jarvis.stock.targets")

IST_TZ = get_timezone_manager().get_ist_timezone()


class StockTargetEngine:
    """Calculates deterministic Target 1, Target 2, and Invalidation levels."""

    @classmethod
    def derive_target_exit_plan(
        cls,
        price: float,
        technical_data: Optional[Dict[str, Any]] = None,
        horizon: str = "swing_short_term",
        risk: str = "moderate",
        base_date: Optional[datetime] = None,
    ) -> TargetExitPlan:
        """
        Derives Target 1, Target 2, Invalidation price, and holding period.
        If reliable price data is not present (price <= 0), marks target as unavailable.
        """
        if price is None or price <= 0:
            return TargetExitPlan(
                reference_price=0.0,
                target_1=None,
                target_2=None,
                target_method="unavailable",
                invalidation_price=None,
                exit_type="unavailable",
                holding_period_days=0,
                time_exit_date=None,
                target_notes="Target unavailable because sufficient reliable data is not available.",
            )

        tech = technical_data or {}
        atr = float(tech.get("atr") or (price * 0.03))  # Fallback to realistic 3% daily ATR if not provided
        high_52w = float(tech.get("high_52w") or 0.0)
        ema_20 = float(tech.get("ema_20") or 0.0)

        # 1. Calculate Invalidation Level (Setup breakdown)
        # Conservative: tighter stop (1.2 * ATR), Aggressive: wider stop (2.0 * ATR), Moderate: 1.5 * ATR
        risk_mult = 1.2 if risk == "conservative" else (2.0 if risk == "aggressive" else 1.5)
        invalidation_delta = max(price * 0.02, atr * risk_mult)
        invalidation_price = round(price - invalidation_delta, 2)

        # Structure protection: Invalidation must not exceed 20% loss on a long setup
        if invalidation_price < round(price * 0.80, 2):
            invalidation_price = round(price * 0.80, 2)

        # Risk amount R
        r = price - invalidation_price
        if r <= 0:
            r = price * 0.04
            invalidation_price = round(price - r, 2)

        # 2. Calculate Targets
        target_1 = None
        target_2 = None
        target_method = "risk_reward"
        target_notes = ""

        # Method A: Technical Resistance (if 52W high is above price but within realistic reach)
        if high_52w > price and (high_52w - price) >= (1.5 * r):
            target_method = "technical_resistance"
            target_1 = round(price + (1.2 * r), 2)
            target_2 = round(high_52w, 2)
            target_notes = f"Target 1 derived from 1.2R swing resistance; Target 2 aligned with 52-week high resistance (₹{high_52w:.2f})."
        else:
            # Method B: Risk-Reward Multiple (1.5R and 2.5R)
            target_method = "risk_reward"
            target_1 = round(price + (1.5 * r), 2)
            target_2 = round(price + (2.5 * r), 2)
            target_notes = f"Targets derived via risk-reward asymmetry (T1: 1.5R at ₹{target_1:.2f}, T2: 2.5R at ₹{target_2:.2f}, Risk: ₹{r:.2f})."

        # 3. Holding Period & Time Exit Calculation
        norm_h = horizon.lower()
        if "intra" in norm_h:
            holding_days = 1
        elif "swing" in norm_h or "short" in norm_h or "1_3_month" in norm_h or "1_month" in norm_h:
            holding_days = 30
        elif "3_12" in norm_h or "month" in norm_h:
            holding_days = 180
        elif "year" in norm_h or "3_plus" in norm_h or "long" in norm_h:
            holding_days = 1095
        else:
            holding_days = 30

        now_dt = base_date or datetime.now(IST_TZ)
        time_exit_dt = now_dt + timedelta(days=holding_days)
        time_exit_str = time_exit_dt.strftime("%Y-%m-%d")

        return TargetExitPlan(
            reference_price=round(price, 2),
            target_1=target_1,
            target_2=target_2,
            target_method=target_method,
            invalidation_price=invalidation_price,
            exit_type="setup_invalidation",
            holding_period_days=holding_days,
            time_exit_date=time_exit_str,
            target_notes=target_notes,
        )
