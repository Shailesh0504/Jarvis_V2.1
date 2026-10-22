# plugins/trading_signals/__init__.py
"""
Jarvis Screen-Only Live Options Signal Engine Plugin.
Provides decision support signals (BUY/EXIT) based on visible Renko, SuperTrend,
and Donchian breakout confluence on user's dual-pane chart screen.
Strictly signal-only. No broker connectivity or execution.
"""

from .plugin import TradingSignalsPlugin

__all__ = ["TradingSignalsPlugin"]
