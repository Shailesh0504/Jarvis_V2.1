# stock/stock_technical.py
"""
Technical Analysis and Indicator Screening Layer for Stock Query Wizard.
Integrates with core/equity_research/technical_engine.py.
Evaluates trend alignment, breakout setups, momentum oscillators, SuperTrend, and volume confirmation.
"""

from typing import Any, Dict, List, Optional, Tuple
from core.equity_research.models import OHLCVBar, TechnicalIndicators
from core.equity_research.technical_engine import TechnicalAnalysisEngine


class StockTechnicalFilter:
    """Evaluates candidate price action and indicators against user technical preferences."""

    def __init__(self, technical_engine: Optional[TechnicalAnalysisEngine] = None):
        self.engine = technical_engine or TechnicalAnalysisEngine()

    def analyze_bars(self, bars: List[OHLCVBar], nifty_return_pct: float = 0.0) -> TechnicalIndicators:
        """Computes technical indicator snapshot from daily session bars."""
        return self.engine.analyze(bars, nifty_return_pct=nifty_return_pct)

    def evaluate(
        self,
        tech: TechnicalIndicators,
        current_price: float,
        preferences: List[str],
        horizon: str = "swing_short_term",
    ) -> Tuple[bool, float, List[str], List[str]]:
        """
        Evaluates technicals against preferences and horizon.
        Returns:
            (passes_filter, technical_score_0_to_40, matched_reasons, risk_notes)
        """
        matched_reasons: List[str] = []
        risk_notes: List[str] = []
        score = 20.0  # Base neutral technical score

        norm_prefs = [p.lower().strip().replace(" ", "_") for p in preferences]
        is_no_pref = ("no_preference" in norm_prefs or not norm_prefs)

        # 1. Base Trend Assessment
        if tech.trend == "BULLISH":
            score += 5.0
            matched_reasons.append("Constructive structural uptrend (Price > EMA 20 > EMA 50)")
        elif tech.trend == "BEARISH":
            score -= 6.0
            risk_notes.append("Bearish price trend below primary moving averages")

        # 2. Moving Average Alignment
        if current_price > tech.sma_200 > 0:
            score += 3.0
            matched_reasons.append("Trading above 200-day long-term moving average")
        elif tech.sma_200 > 0 and current_price < tech.sma_200:
            score -= 3.0
            risk_notes.append("Trading below long-term 200 SMA threshold")

        # 3. SuperTrend Indicator
        if tech.supertrend_direction == "BULLISH":
            score += 3.0
            matched_reasons.append(f"SuperTrend positive trailing support (₹{tech.supertrend_value:.1f})")
        else:
            score -= 3.0
            risk_notes.append("SuperTrend indicator currently negative/overhead")

        # 4. Momentum / RSI Checks
        if "momentum" in norm_prefs or "rsi_confirmation" in norm_prefs or is_no_pref:
            if 50.0 <= tech.rsi <= 70.0:
                score += 5.0
                matched_reasons.append(f"Bullish RSI momentum zone ({tech.rsi:.1f})")
            elif tech.rsi > 75.0:
                score -= 2.0
                risk_notes.append(f"RSI short-term overbought condition ({tech.rsi:.1f})")
            elif tech.rsi < 40.0:
                score -= 4.0
                risk_notes.append(f"Weak momentum with RSI in sub-40 zone ({tech.rsi:.1f})")

        # 5. Breakout & Volume Setup
        if "breakout" in norm_prefs or "volume_confirmation" in norm_prefs or is_no_pref:
            if tech.volume_breakout:
                score += 6.0
                matched_reasons.append(f"Volume expansion breakout ({tech.volume_ratio:.1f}x 20-day average volume)")
            elif tech.volume_ratio >= 1.2:
                score += 3.0
                matched_reasons.append(f"Above-average participation volume ({tech.volume_ratio:.1f}x 20-day SMA)")
            elif "volume_confirmation" in norm_prefs and tech.volume_ratio < 0.8:
                risk_notes.append(f"Below-average volume confirmation ({tech.volume_ratio:.1f}x)")

        # 6. Trend Following Preference
        if "trend_following" in norm_prefs or "moving_average_setup" in norm_prefs:
            if current_price > tech.ema_20 > tech.ema_50:
                score += 4.0
                matched_reasons.append("Perfect moving average alignment for trend-following")

        # 7. Pullback Setup Preference
        if "pullback" in norm_prefs:
            if tech.trend == "BULLISH" and abs(current_price - tech.ema_20) / current_price < 0.025:
                score += 5.0
                matched_reasons.append("High-probability pullback test to 20-day EMA in active uptrend")

        score = max(0.0, min(40.0, score))
        return True, score, matched_reasons, risk_notes
