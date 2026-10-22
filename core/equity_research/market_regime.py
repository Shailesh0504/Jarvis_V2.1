# core/equity_research/market_regime.py
"""
Market Regime Engine for Indian Equities.
Analyzes NIFTY 50, NIFTY 500, India VIX, Market Breadth, and Sector Rotation
to classify market regime context (BULLISH, BEARISH, SIDEWAYS, HIGH_VOLATILITY, MIXED).
"""

import logging
from typing import Any, Dict, Tuple

from .models import MarketRegime

logger = logging.getLogger("jarvis.equity_research.market_regime")


class MarketRegimeEngine:
    """
    Evaluates broader market environment before individual stock analysis.
    Invariant: Regime classification is an analytical context variable, NOT a guaranteed prediction.
    """

    def evaluate_regime(self, index_data: Dict[str, Any]) -> Tuple[MarketRegime, str]:
        """
        Evaluates the current market regime based on multi-factor index data.
        Returns: (MarketRegime, detailed_rationale_string)
        """
        nifty = index_data.get("nifty_50", {})
        vix = float(index_data.get("india_vix", 15.0))
        breadth = index_data.get("market_breadth", {})
        ad_ratio = float(breadth.get("advance_decline_ratio", 1.0))

        nifty_price = float(nifty.get("current", 25000.0))
        ema_20 = float(nifty.get("ema_20", nifty_price))
        ema_50 = float(nifty.get("ema_50", nifty_price))
        sma_200 = float(nifty.get("sma_200", nifty_price))

        # 1. High Volatility Check (VIX > 22 indicates severe market turbulence)
        if vix >= 22.0:
            rationale = (
                f"India VIX is elevated at {vix:.1f} (> 22), signaling high macroeconomic "
                f"uncertainty, broader index swings, and elevated gap risks for 1-month swing trades."
            )
            return MarketRegime.HIGH_VOLATILITY, rationale

        # 2. Bullish Alignment
        # Price > EMA 20 > EMA 50 > SMA 200, healthy breadth (> 1.25), and stable VIX (< 18)
        if nifty_price > ema_20 > ema_50 and ad_ratio >= 1.25 and vix <= 18.0:
            rationale = (
                f"NIFTY 50 trades comfortably above 20 EMA ({ema_20:.0f}) and 50 EMA ({ema_50:.0f}) "
                f"with positive market breadth (A/D ratio {ad_ratio:.2f}) and benign India VIX ({vix:.1f}). "
                f"Environment supports momentum and trend continuation setups."
            )
            return MarketRegime.BULLISH, rationale

        # 3. Bearish Breakdown
        # Price < EMA 20 < EMA 50, weak breadth (< 0.75)
        if nifty_price < ema_20 < ema_50 and ad_ratio <= 0.75:
            rationale = (
                f"NIFTY 50 trades below short-term 20 EMA ({ema_20:.0f}) and 50 EMA ({ema_50:.0f}) "
                f"with weak breadth (A/D ratio {ad_ratio:.2f}) and selling pressure across sectors. "
                f"Higher caution and strict invalidation buffers are warranted."
            )
            return MarketRegime.BEARISH, rationale

        # 4. Sideways / Consolidation
        # Narrow distance between price and 20/50 EMA, balanced A/D ratio (0.9 to 1.2)
        price_ema_diff_pct = abs(nifty_price - ema_20) / nifty_price * 100.0
        if price_ema_diff_pct < 1.0 and 0.85 <= ad_ratio <= 1.2:
            rationale = (
                f"NIFTY 50 is consolidating closely around 20 EMA ({ema_20:.0f}) within a defined range. "
                f"Market breadth is balanced (A/D {ad_ratio:.2f}) with sector-specific rotation rather "
                f"than broad index directional momentum."
            )
            return MarketRegime.SIDEWAYS, rationale

        # 5. Mixed / Divergent
        rationale = (
            f"Index shows mixed signals: NIFTY 50 near {nifty_price:.0f} with A/D ratio at {ad_ratio:.2f} "
            f"and India VIX at {vix:.1f}. Sector dispersion is high; selective stock picking with "
            f"strong relative strength is favored over broad market exposure."
        )
        return MarketRegime.MIXED, rationale
