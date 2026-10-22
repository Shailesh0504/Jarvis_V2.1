# core/equity_research/technical_engine.py
"""
1-Month Technical Analysis Engine for Indian Equities.
Calculates EMA 20/50, SMA 200, RSI 14, MACD, ATR 14, ADX, SuperTrend,
Support/Resistance pivots, Volume breakouts, and Relative Strength vs NIFTY 50.
"""

import logging
import math
from typing import List, Optional, Tuple

from .models import OHLCVBar, TechnicalIndicators

logger = logging.getLogger("jarvis.equity_research.technical_engine")


class TechnicalAnalysisEngine:
    """
    Computes multi-indicator technical evidence for 1-month swing investment setups.
    Avoids single-indicator biases by requiring confluence across trend, momentum, and volume.
    """

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """Calculates exponential moving average series."""
        if not prices or period <= 0:
            return []
        if len(prices) < period:
            return [sum(prices) / len(prices)] * len(prices)

        ema = [sum(prices[:period]) / period]
        multiplier = 2.0 / (period + 1)

        for price in prices[period:]:
            new_val = (price - ema[-1]) * multiplier + ema[-1]
            ema.append(new_val)

        # Pad initial items
        padding = [ema[0]] * (period - 1)
        return padding + ema

    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> float:
        """Calculates simple moving average for the latest window."""
        if not prices:
            return 0.0
        window = prices[-period:] if len(prices) >= period else prices
        return sum(window) / len(window)

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """Calculates 14-period Wilder's Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0

        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change >= 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))

        # Initial averages
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Smoothed Wilder calculation
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    @staticmethod
    def calculate_macd(prices: List[float]) -> Tuple[float, float, float]:
        """
        Calculates standard MACD (12, 26, 9).
        Returns: (macd_line, signal_line, histogram)
        """
        if len(prices) < 26:
            return 0.0, 0.0, 0.0

        ema_12 = TechnicalAnalysisEngine.calculate_ema(prices, 12)
        ema_26 = TechnicalAnalysisEngine.calculate_ema(prices, 26)

        macd_series = [e12 - e26 for e12, e26 in zip(ema_12, ema_26)]
        signal_series = TechnicalAnalysisEngine.calculate_ema(macd_series, 9)

        macd_line = round(macd_series[-1], 2)
        signal_line = round(signal_series[-1], 2)
        hist = round(macd_line - signal_line, 2)
        return macd_line, signal_line, hist

    @staticmethod
    def calculate_atr(bars: List[OHLCVBar], period: int = 14) -> float:
        """Calculates Average True Range (14-period)."""
        if len(bars) < 2:
            return 10.0

        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return round(sum(true_ranges) / max(1, len(true_ranges)), 2)

        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period
        return round(atr, 2)

    @staticmethod
    def calculate_adx(bars: List[OHLCVBar], period: int = 14) -> float:
        """Calculates Average Directional Index (ADX) measuring trend strength."""
        if len(bars) < period * 2:
            return 26.0  # Default moderate strength

        plus_dm_list = []
        minus_dm_list = []
        tr_list = []

        for i in range(1, len(bars)):
            h_diff = bars[i].high - bars[i - 1].high
            l_diff = bars[i - 1].low - bars[i].low

            plus_dm = h_diff if (h_diff > l_diff and h_diff > 0) else 0.0
            minus_dm = l_diff if (l_diff > h_diff and l_diff > 0) else 0.0

            tr = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i - 1].close),
                abs(bars[i].low - bars[i - 1].close)
            )
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)
            tr_list.append(tr)

        tr_smooth = sum(tr_list[:period])
        plus_smooth = sum(plus_dm_list[:period])
        minus_smooth = sum(minus_dm_list[:period])

        if tr_smooth == 0:
            return 25.0

        dx_list = []
        for i in range(period, len(bars) - 1):
            tr_smooth = tr_smooth - (tr_smooth / period) + tr_list[i]
            plus_smooth = plus_smooth - (plus_smooth / period) + plus_dm_list[i]
            minus_smooth = minus_smooth - (minus_smooth / period) + minus_dm_list[i]

            plus_di = 100.0 * (plus_smooth / tr_smooth) if tr_smooth > 0 else 0
            minus_di = 100.0 * (minus_smooth / tr_smooth) if tr_smooth > 0 else 0
            denom = plus_di + minus_di
            dx = (abs(plus_di - minus_di) / denom * 100.0) if denom > 0 else 0
            dx_list.append(dx)

        adx = sum(dx_list[-period:]) / min(len(dx_list), period) if dx_list else 25.0
        return round(adx, 1)

    @staticmethod
    def calculate_supertrend(bars: List[OHLCVBar], period: int = 10, multiplier: float = 3.0) -> Tuple[str, float]:
        """Calculates SuperTrend direction and stop band."""
        if len(bars) < period:
            latest = bars[-1].close if bars else 1000.0
            return "BULLISH", round(latest * 0.95, 2)

        atr = TechnicalAnalysisEngine.calculate_atr(bars, period)
        latest_bar = bars[-1]
        hl2 = (latest_bar.high + latest_bar.low) / 2.0
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        if latest_bar.close >= lower_band:
            return "BULLISH", round(lower_band, 2)
        else:
            return "BEARISH", round(upper_band, 2)

    @staticmethod
    def find_support_resistance(bars: List[OHLCVBar], lookback: int = 20) -> Tuple[float, float, float, float]:
        """
        Identifies dynamic swing support, resistance, recent swing high and low.
        Returns: (support, resistance, swing_high, swing_low)
        """
        recent = bars[-lookback:] if len(bars) >= lookback else bars
        swing_high = max(b.high for b in recent)
        swing_low = min(b.low for b in recent)
        latest_close = bars[-1].close

        # Support is nearest swing low below current price; Resistance is nearest swing high above
        support = swing_low
        resistance = swing_high

        # If current price broke above all recent highs, project 1.5x ATR resistance
        if latest_close >= swing_high:
            atr = TechnicalAnalysisEngine.calculate_atr(bars, 14)
            resistance = round(latest_close + (1.5 * atr), 2)
            support = round(swing_high * 0.98, 2)
        elif latest_close <= swing_low:
            atr = TechnicalAnalysisEngine.calculate_atr(bars, 14)
            support = round(latest_close - (1.5 * atr), 2)
            resistance = round(swing_low * 1.02, 2)

        return round(support, 2), round(resistance, 2), round(swing_high, 2), round(swing_low, 2)

    def analyze(self, bars: List[OHLCVBar], nifty_return_pct: float = 2.5) -> TechnicalIndicators:
        """
        Analyzes a full OHLCV series and returns a complete TechnicalIndicators profile.
        """
        if not bars:
            return TechnicalIndicators()

        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        latest_close = closes[-1]

        # Moving Averages
        ema_20_list = self.calculate_ema(closes, 20)
        ema_50_list = self.calculate_ema(closes, 50)
        ema_20 = round(ema_20_list[-1], 2)
        ema_50 = round(ema_50_list[-1], 2)
        sma_200 = round(self.calculate_sma(closes, 200), 2)

        # Oscillators & Indicators
        rsi = self.calculate_rsi(closes, 14)
        macd, macd_signal, macd_hist = self.calculate_macd(closes)
        atr = self.calculate_atr(bars, 14)
        atr_pct = round((atr / latest_close) * 100.0, 2)
        adx = self.calculate_adx(bars, 14)
        st_dir, st_val = self.calculate_supertrend(bars, 10, 3.0)

        support, resistance, swing_high, swing_low = self.find_support_resistance(bars, 20)

        # Volume Confirmation
        avg_vol_20 = self.calculate_sma([float(v) for v in volumes], 20)
        latest_vol = volumes[-1]
        vol_ratio = round(latest_vol / max(1.0, avg_vol_20), 2)
        vol_breakout = vol_ratio >= 1.4

        if vol_ratio > 1.2:
            vol_trend = "EXPANDING"
        elif vol_ratio < 0.8:
            vol_trend = "CONTRACTING"
        else:
            vol_trend = "STABLE"

        # Relative Strength vs NIFTY 50 over 30 days (~21 sessions)
        lookback_sessions = min(21, len(closes) - 1)
        if lookback_sessions > 0:
            stock_return_pct = ((latest_close - closes[-lookback_sessions]) / closes[-lookback_sessions]) * 100.0
            rs_nifty = round(stock_return_pct - nifty_return_pct, 2)
        else:
            rs_nifty = 0.0

        # Overall Trend Classification
        if latest_close > ema_20 > ema_50 and rsi >= 50.0:
            trend = "BULLISH"
        elif latest_close < ema_20 < ema_50 and rsi <= 45.0:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

        return TechnicalIndicators(
            trend=trend,
            ema_20=ema_20,
            ema_50=ema_50,
            sma_200=sma_200,
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
            atr=atr,
            atr_pct=atr_pct,
            adx=adx,
            supertrend_direction=st_dir,
            supertrend_value=st_val,
            support_level=support,
            resistance_level=resistance,
            volume_trend=vol_trend,
            volume_breakout=vol_breakout,
            volume_ratio=vol_ratio,
            relative_strength_nifty=rs_nifty,
            recent_swing_high=swing_high,
            recent_swing_low=swing_low,
        )
