# plugins/trading_signals/models/data_feed_types.py
"""
DataFeedState and FrameConfidence Models.
Orthogonal to the SignalState trading lifecycle.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class DataFeedState(str, Enum):
    """
    State of visual chart observation and sensor data quality.
    Orthogonal to PositionState: changing DataFeedState never corrupts SignalState.
    """
    LIVE_AND_VALID = "LIVE_AND_VALID"
    WINDOW_OCCLUDED_OR_HIDDEN = "WINDOW_OCCLUDED_OR_HIDDEN"
    INDICATOR_DISCREPANCY = "INDICATOR_DISCREPANCY"    # OCR and geometry disagree beyond tolerance
    LOW_CONFIDENCE = "LOW_CONFIDENCE"                  # Confidence below minimum threshold
    CHART_RENDER_UNSTABLE = "CHART_RENDER_UNSTABLE"    # Chart panning, scrolling, or redrawing
    DATA_STALE = "DATA_STALE"                          # Loop latency or frame staleness > 1.5s
    CONFIG_MISMATCH = "CONFIG_MISMATCH"                # Chart settings do not match expected strategy


@dataclass
class FrameConfidence:
    """
    Measurable component-wise visual confidence scores [0.0, 1.0].
    """
    index_price_conf: float = 1.0
    option_price_conf: float = 1.0
    index_supertrend_conf: float = 1.0
    option_supertrend_conf: float = 1.0
    ema_conf: float = 1.0
    donchian_conf: float = 1.0
    contract_text_conf: float = 1.0
    layout_conf: float = 1.0
    ocr_confidence: Optional[float] = None
    color_segmentation_confidence: Optional[float] = None
    contour_confidence: Optional[float] = None
    scale_calibration_confidence: Optional[float] = None
    window_visibility_confidence: Optional[float] = None

    @property
    def composite_confidence(self) -> float:
        """Conservative minimum confidence across all measurable components."""
        scores = [
            self.index_price_conf,
            self.option_price_conf,
            self.index_supertrend_conf,
            self.option_supertrend_conf,
            self.ema_conf,
            self.donchian_conf,
            self.contract_text_conf,
            self.layout_conf
        ]
        for extra in (
            self.ocr_confidence,
            self.color_segmentation_confidence,
            self.contour_confidence,
            self.scale_calibration_confidence,
            self.window_visibility_confidence
        ):
            if extra is not None:
                scores.append(extra)
        return min(scores)

    def is_acceptable(self, min_threshold: float = 0.85) -> bool:
        """True only if every required component meets or exceeds the threshold."""
        return self.composite_confidence >= min_threshold
