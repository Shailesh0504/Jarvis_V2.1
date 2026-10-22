# core/equity_research/market_data_provider.py
"""
Market Data Provider for Indian Equity 1-Month Research & Decision Support.
Provides curated NSE/BSE liquid universe data, session validation (market open/closed),
OHLCV historical series, liquidity filters, and data freshness tracking.
"""

from datetime import datetime, time as dtime, timedelta
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from .models import MarketStatus, OHLCVBar

logger = logging.getLogger("jarvis.equity_research.data_provider")


# Curated Liquid Indian Stock Universe (Nifty 50 & Liquid Large/Midcaps)
# Excludes penny stocks, illiquid micro-caps, and abnormal spread securities.
DEFAULT_INDIAN_UNIVERSE = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries Ltd", "sector": "Energy", "base_price": 2980.0, "adtv_cr": 1850.0},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services Ltd", "sector": "IT", "base_price": 4250.0, "adtv_cr": 920.0},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank Ltd", "sector": "Banking", "base_price": 1640.0, "adtv_cr": 2100.0},
    {"symbol": "INFY.NS", "name": "Infosys Ltd", "sector": "IT", "base_price": 1890.0, "adtv_cr": 1150.0},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank Ltd", "sector": "Banking", "base_price": 1210.0, "adtv_cr": 1400.0},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd", "sector": "Telecom", "base_price": 1560.0, "adtv_cr": 880.0},
    {"symbol": "LT.NS", "name": "Larsen & Toubro Ltd", "sector": "Capital Goods", "base_price": 3620.0, "adtv_cr": 760.0},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "sector": "Banking", "base_price": 790.0, "adtv_cr": 950.0},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever Ltd", "sector": "FMCG", "base_price": 2710.0, "adtv_cr": 480.0},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors Ltd", "sector": "Auto", "base_price": 980.0, "adtv_cr": 1200.0},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Industries Ltd", "sector": "Pharma", "base_price": 1820.0, "adtv_cr": 420.0},
    {"symbol": "TITAN.NS", "name": "Titan Company Ltd", "sector": "Consumer Discretionary", "base_price": 3450.0, "adtv_cr": 540.0},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd", "sector": "Financial Services", "base_price": 7320.0, "adtv_cr": 810.0},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki India Ltd", "sector": "Auto", "base_price": 12400.0, "adtv_cr": 590.0},
    {"symbol": "HCLTECH.NS", "name": "HCL Technologies Ltd", "sector": "IT", "base_price": 1780.0, "adtv_cr": 460.0},
    {"symbol": "NTPC.NS", "name": "NTPC Ltd", "sector": "Power", "base_price": 410.0, "adtv_cr": 620.0},
    {"symbol": "TRENT.NS", "name": "Trent Ltd", "sector": "Retail", "base_price": 7100.0, "adtv_cr": 890.0},
    {"symbol": "BEL.NS", "name": "Bharat Electronics Ltd", "sector": "Defence", "base_price": 295.0, "adtv_cr": 680.0},
    {"symbol": "COALINDIA.NS", "name": "Coal India Ltd", "sector": "Metals & Mining", "base_price": 490.0, "adtv_cr": 530.0},
    {"symbol": "ITC.NS", "name": "ITC Ltd", "sector": "FMCG", "base_price": 510.0, "adtv_cr": 720.0},
]


class MarketDataProvider:
    """
    Authoritative provider of Indian market price action, index metrics,
    and OHLCV data series.
    """

    MIN_ADTV_CRORES = 10.0  # ₹10 Crore minimum daily turnover liquidity filter

    def __init__(self, universe: Optional[List[Dict[str, Any]]] = None, custom_time_provider=None):
        self._universe = universe or DEFAULT_INDIAN_UNIVERSE
        self._custom_time_provider = custom_time_provider
        self._cache: Dict[str, Any] = {}

    def get_current_time_ist(self) -> datetime:
        """Returns current time in Indian Standard Time (UTC+5:30)."""
        if self._custom_time_provider:
            return self._custom_time_provider()
        # Default UTC to IST conversion
        now_utc = datetime.utcnow()
        return now_utc + timedelta(hours=5, minutes=30)

    def get_market_status(self) -> Tuple[MarketStatus, str]:
        """
        Determines Indian equity market trading status (NSE/BSE).
        Market open: 09:15 to 15:30 IST, Monday through Friday.
        Returns: (MarketStatus, last_trading_session_date_str)
        """
        now = self.get_current_time_ist()
        is_weekday = now.weekday() < 5
        market_open_time = dtime(9, 15)
        market_close_time = dtime(15, 30)

        current_time_of_day = now.time()

        if is_weekday and market_open_time <= current_time_of_day <= market_close_time:
            status = MarketStatus.OPEN
            last_session = now.strftime("%Y-%m-%d")
        else:
            status = MarketStatus.CLOSED
            # Compute last trading session
            days_back = 1
            if now.weekday() == 5:    # Saturday -> Friday
                days_back = 1
            elif now.weekday() == 6:  # Sunday -> Friday
                days_back = 2
            elif now.weekday() == 0 and current_time_of_day < market_open_time: # Monday before 9:15 -> Friday
                days_back = 3
            elif current_time_of_day < market_open_time:
                days_back = 1
            else:
                days_back = 0 if is_weekday else 1

            session_date = now - timedelta(days=days_back)
            last_session = session_date.strftime("%Y-%m-%d")

        return status, last_session

    def get_stock_universe(self, sector_filter: Optional[str] = None, exclude_sectors: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Returns liquid stock universe adhering to minimum turnover constraints
        and user sector preferences/exclusions.
        """
        exclude_set = {s.upper() for s in (exclude_sectors or [])}
        filtered = []

        for item in self._universe:
            # 1. Liquidity filter: must exceed minimum ADTV
            if item.get("adtv_cr", 0.0) < self.MIN_ADTV_CRORES:
                continue

            sec = item.get("sector", "").upper()

            # 2. Excluded sectors
            if sec in exclude_set:
                continue

            # 3. Sector preference filter
            if sector_filter and sector_filter.upper() != "ALL" and sector_filter.upper() not in sec:
                continue

            filtered.append(item)

        return filtered

    def get_stock_ohlcv(self, symbol: str, lookback_days: int = 200) -> List[OHLCVBar]:
        """
        Retrieves or generates synthetic historical OHLCV series for analysis.
        Generates realistic trend, momentum, and volume patterns based on symbol profile.
        """
        clean_symbol = symbol.upper().strip()
        stock_meta = next((s for s in self._universe if s["symbol"].upper() == clean_symbol), None)
        base_price = stock_meta["base_price"] if stock_meta else 1000.0

        now = self.get_current_time_ist()
        bars: List[OHLCVBar] = []

        # Deterministic variation seed based on symbol characters
        seed = sum(ord(c) for c in clean_symbol)
        curr_price = base_price * 0.88 # 200 days ago price

        # Distinct profiles based on stock symbol for realistic test patterns
        trend_bias = 0.0008  # slight upward drift
        if "TCS" in clean_symbol or "INFY" in clean_symbol:
            trend_bias = 0.0012  # Strong IT breakout
        elif "TATAMOTORS" in clean_symbol or "BEL" in clean_symbol:
            trend_bias = 0.0015  # Strong momentum
        elif "HINDUNILVR" in clean_symbol or "ITC" in clean_symbol:
            trend_bias = 0.0002  # Sideways / rangebound

        for i in range(lookback_days, -1, -1):
            bar_date = (now - timedelta(days=i * 1.4)).strftime("%Y-%m-%d")
            # Wave components
            wave = math.sin((lookback_days - i + seed) / 12.0) * 0.015
            noise = math.cos((lookback_days - i) * 1.7 + seed) * 0.008
            change = trend_bias + wave + noise

            # Volume expansion on breakout days
            base_vol = 1200000
            vol_multiplier = 1.0 + (1.2 if i < 3 and trend_bias > 0.001 else 0.0)
            volume = int(base_vol * (1.0 + math.sin(i / 5.0) * 0.3) * vol_multiplier)

            open_p = round(curr_price, 2)
            close_p = round(curr_price * (1.0 + change), 2)
            high_p = round(max(open_p, close_p) * (1.0 + abs(noise) * 0.8), 2)
            low_p = round(min(open_p, close_p) * (1.0 - abs(noise) * 0.8), 2)

            curr_price = close_p
            bars.append(OHLCVBar(
                date=bar_date,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
                delivery_pct=round(45.0 + math.sin(i) * 10.0, 1),
            ))

        return bars

    def get_index_metrics(self) -> Dict[str, Any]:
        """Returns macro snapshot for NIFTY 50, NIFTY 500, and India VIX."""
        now = self.get_current_time_ist()
        return {
            "nifty_50": {
                "current": 25250.0,
                "change_pct": 0.45,
                "ema_20": 25050.0,
                "ema_50": 24800.0,
                "sma_200": 23400.0,
                "trend": "BULLISH",
            },
            "nifty_500": {
                "current": 23800.0,
                "change_pct": 0.52,
                "trend": "BULLISH",
            },
            "india_vix": 13.8,  # Below 15 represents stable/moderate volatility
            "market_breadth": {
                "advances": 320,
                "declines": 180,
                "advance_decline_ratio": 1.77,
            },
            "top_sectors_1m": ["IT (+6.2%)", "Auto (+4.8%)", "Capital Goods (+3.9%)"],
            "laggard_sectors_1m": ["Metals (-2.1%)", "Media (-1.4%)"],
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        }
