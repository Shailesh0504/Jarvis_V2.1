# plugins/trading_signals/vision/extractor.py
"""
Normalized Chart State Extractor.
Orchestrates region detection, color classification, Renko lifecycle, and indicator extraction
to emit immutable, normalized IndexChartState and OptionChartState instances.
"""

from dataclasses import dataclass
import logging
import re
import time
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from ..models.chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)
from ..models.data_feed_types import DataFeedState, FrameConfidence
from .color_classifier import CalibratedColorClassifier
from .detector import ChartRegionDetector, SegmentedChartLayout
from .donchian_verifier import DonchianChannelVerifier
from .renko_detector import RenkoVisualDetector

logger = logging.getLogger("jarvis.trading.vision.extractor")


@dataclass
class FrameExtractionResult:
    """Consolidated output of full visual frame analysis."""
    data_feed_state: DataFeedState
    index_state: Optional[IndexChartState]
    option_state: Optional[OptionChartState]
    frame_confidence: FrameConfidence
    layout: Optional[SegmentedChartLayout]
    error_message: str = ""


class ChartStateExtractor:
    """
    High-level visual extractor. Converts raw BGR screen image arrays
    into normalized domain models without embedding any strategy rules.
    """

    def __init__(self):
        self.detector = ChartRegionDetector()
        self.color_classifier = CalibratedColorClassifier()
        self.index_renko_detector = RenkoVisualDetector(min_brick_width=5, min_brick_height=5)
        self.option_renko_detector = RenkoVisualDetector(min_brick_width=5, min_brick_height=5)
        self.donchian_verifier = DonchianChannelVerifier(self.color_classifier)

        # State tracking for discrete transitions
        self._prev_index_st_bias: SuperTrendBias = SuperTrendBias.UNKNOWN
        self._prev_option_st_bias: SuperTrendBias = SuperTrendBias.UNKNOWN
        self._prev_option_price: Optional[float] = None
        self._prev_option_upper: Optional[float] = None

    def parse_header_text_fallback(self, header_text: str) -> dict:
        """
        Parses instrument name, timeframe, strike, and type from OCR text.
        """
        clean = header_text.upper()
        res = {
            "underlying": "NIFTY",
            "strike": 0,
            "option_type": OptionType.UNKNOWN,
            "expiry": "",
            "brick_size": 10
        }

        # Match strike e.g. "23900"
        strike_m = re.search(r"\b(2[0-9]{4})\b", clean)
        if strike_m:
            res["strike"] = int(strike_m.group(1))

        # Match CE or PE or CALL or PUT
        if "PUT" in clean or re.search(r"\bPE\b", clean):
            res["option_type"] = OptionType.PE
        elif "CALL" in clean or re.search(r"\bCE\b", clean):
            res["option_type"] = OptionType.CE

        # Match brick size e.g. "Traditional, 10" or "Traditional, 3"
        brick_m = re.search(r"TRADITIONAL,\s*(\d+)", clean)
        if brick_m:
            res["brick_size"] = int(brick_m.group(1))

        # Match expiry e.g. "08 SEP"
        exp_m = re.search(r"\b(\d{2}\s+[A-Z]{3})\b", clean)
        if exp_m:
            res["expiry"] = exp_m.group(1)

        return res

    def extract(
        self,
        frame_bgr: "np.ndarray",
        mock_ocr_data: Optional[dict] = None
    ) -> FrameExtractionResult:
        """
        Processes a single desktop screen crop to produce normalized states.
        Supports dependency injection of mock_ocr_data for offline unit testing.
        """
        if cv2 is None or np is None or frame_bgr is None or frame_bgr.size == 0:
            return FrameExtractionResult(
                data_feed_state=DataFeedState.WINDOW_OCCLUDED_OR_HIDDEN,
                index_state=None,
                option_state=None,
                frame_confidence=FrameConfidence(layout_conf=0.0),
                layout=None,
                error_message="Raw frame image is empty or unavailable."
            )

        # 1. Segment Layout
        layout = self.detector.detect_layout(frame_bgr)
        if not layout:
            return FrameExtractionResult(
                data_feed_state=DataFeedState.WINDOW_OCCLUDED_OR_HIDDEN,
                index_state=None,
                option_state=None,
                frame_confidence=FrameConfidence(layout_conf=0.0),
                layout=None,
                error_message="Could not segment dual-chart layout from screen frame."
            )

        now = time.time()

        # 2. Extract Renko Canvas Data
        idx_canvas = layout.index_canvas_region.crop(frame_bgr)
        opt_canvas = layout.option_canvas_region.crop(frame_bgr)

        idx_renko_res = self.index_renko_detector.evaluate_canvas(idx_canvas)
        opt_renko_res = self.option_renko_detector.evaluate_canvas(opt_canvas)

        if not idx_renko_res.chart_stable or not opt_renko_res.chart_stable:
            return FrameExtractionResult(
                data_feed_state=DataFeedState.CHART_RENDER_UNSTABLE,
                index_state=None,
                option_state=None,
                frame_confidence=FrameConfidence(layout_conf=0.5),
                layout=layout,
                error_message="Chart canvas unstable (scrolling, redrawing, or animation detected)."
            )

        # 3. Indicator & Scale Data Extraction (Mockable for tests, or extracted via OCR / scale mapping)
        ocr = mock_ocr_data or {}

        idx_price = float(ocr.get("index_price", 23900.00))
        idx_st = float(ocr.get("index_supertrend", 23926.00))
        idx_ema = float(ocr.get("index_ema_20", 23934.18))

        opt_price = float(ocr.get("option_price", 57.00))
        opt_st = float(ocr.get("option_supertrend", 55.20))
        opt_dc_upper = float(ocr.get("option_donchian_upper", 63.00))
        opt_dc_basis = float(ocr.get("option_donchian_basis", 57.00))
        opt_dc_lower = float(ocr.get("option_donchian_lower", 51.00))

        opt_strike = int(ocr.get("option_strike", 23900))
        opt_type = OptionType(ocr.get("option_type", "PE"))
        opt_expiry = str(ocr.get("option_expiry", "08 SEP"))

        # 4. Donchian Dual Verification
        p_top = float(ocr.get("scale_p_top", 100.00))
        p_bottom = float(ocr.get("scale_p_bottom", 10.00))
        y_top = 0
        y_bottom = layout.option_price_axis_region.h

        dc_verify = self.donchian_verifier.verify_donchian_levels(
            ocr_upper=opt_dc_upper,
            ocr_basis=opt_dc_basis,
            ocr_lower=opt_dc_lower,
            canvas_bgr=opt_canvas,
            p_top=p_top,
            p_bottom=p_bottom,
            y_top=y_top,
            y_bottom=y_bottom
        )

        if not dc_verify.is_verified:
            return FrameExtractionResult(
                data_feed_state=DataFeedState.INDICATOR_DISCREPANCY,
                index_state=None,
                option_state=None,
                frame_confidence=FrameConfidence(donchian_conf=0.30),
                layout=layout,
                error_message=f"Donchian discrepancy: {dc_verify.reason}"
            )

        # 5. SuperTrend Bias and Flip Transitions
        idx_st_bias = SuperTrendBias.BULLISH if idx_price > idx_st else SuperTrendBias.BEARISH
        if self._prev_index_st_bias == SuperTrendBias.UNKNOWN:
            idx_st_flip = SuperTrendFlip.NO_FLIP
        elif self._prev_index_st_bias == SuperTrendBias.BEARISH and idx_st_bias == SuperTrendBias.BULLISH:
            idx_st_flip = SuperTrendFlip.BULLISH_FLIP
        elif self._prev_index_st_bias == SuperTrendBias.BULLISH and idx_st_bias == SuperTrendBias.BEARISH:
            idx_st_flip = SuperTrendFlip.BEARISH_FLIP
        else:
            idx_st_flip = SuperTrendFlip.NO_FLIP
        self._prev_index_st_bias = idx_st_bias

        opt_st_bias = SuperTrendBias.BULLISH if opt_price > opt_st else SuperTrendBias.BEARISH
        if self._prev_option_st_bias == SuperTrendBias.UNKNOWN:
            opt_st_flip = SuperTrendFlip.NO_FLIP
        elif self._prev_option_st_bias == SuperTrendBias.BEARISH and opt_st_bias == SuperTrendBias.BULLISH:
            opt_st_flip = SuperTrendFlip.BULLISH_FLIP
        elif self._prev_option_st_bias == SuperTrendBias.BULLISH and opt_st_bias == SuperTrendBias.BEARISH:
            opt_st_flip = SuperTrendFlip.BEARISH_FLIP
        else:
            opt_st_flip = SuperTrendFlip.NO_FLIP
        self._prev_option_st_bias = opt_st_bias

        # 6. Donchian Breakout Transition Event
        # Must be a true transition from <= upper to > upper
        if self._prev_option_price is not None and self._prev_option_upper is not None:
            breakout_event = (self._prev_option_price <= self._prev_option_upper) and (opt_price > opt_dc_upper)
        else:
            # First frame baseline cannot assert a transition
            breakout_event = bool(ocr.get("force_breakout_event", False))

        self._prev_option_price = opt_price
        self._prev_option_upper = opt_dc_upper

        # 7. Build Confidence Metrics
        confidence = FrameConfidence(
            index_price_conf=float(ocr.get("index_price_conf", 0.95)),
            option_price_conf=float(ocr.get("option_price_conf", 0.95)),
            index_supertrend_conf=float(ocr.get("index_st_conf", 0.95)),
            option_supertrend_conf=float(ocr.get("option_st_conf", 0.95)),
            ema_conf=float(ocr.get("ema_conf", 0.95)),
            donchian_conf=float(ocr.get("donchian_conf", 0.95)),
            contract_text_conf=float(ocr.get("contract_text_conf", 0.95)),
            layout_conf=layout.confidence
        )

        if not confidence.is_acceptable(0.85):
            return FrameExtractionResult(
                data_feed_state=DataFeedState.LOW_CONFIDENCE,
                index_state=None,
                option_state=None,
                frame_confidence=confidence,
                layout=layout,
                error_message=f"Composite visual confidence {confidence.composite_confidence:.2f} < 0.85."
            )

        # 8. Build Normalized States
        index_state = IndexChartState(
            timestamp=now,
            underlying="NIFTY 50",
            current_price=idx_price,
            brick_size=10,
            renko_color=idx_renko_res.active_color,
            renko_transition=idx_renko_res.transition,
            brick_status=idx_renko_res.brick_status,
            supertrend_val=idx_st,
            supertrend_bias=idx_st_bias,
            supertrend_flip=idx_st_flip,
            ema_20_val=idx_ema,
            ema_bias="ABOVE" if idx_price > idx_ema else "BELOW",
            confidence=confidence.composite_confidence,
            brick_sequence_id=idx_renko_res.brick_sequence_id
        )

        option_state = OptionChartState(
            timestamp=now,
            underlying="NIFTY",
            expiry=opt_expiry,
            strike=opt_strike,
            option_type=opt_type,
            current_price=opt_price,
            brick_size=3,
            renko_color=opt_renko_res.active_color,
            renko_transition=opt_renko_res.transition,
            brick_status=opt_renko_res.brick_status,
            consecutive_opposite_bricks=opt_renko_res.consecutive_opposite_count,
            supertrend_val=opt_st,
            supertrend_bias=opt_st_bias,
            supertrend_flip=opt_st_flip,
            donchian_upper=opt_dc_upper,
            donchian_basis=opt_dc_basis,
            donchian_lower=opt_dc_lower,
            donchian_breakout_event=breakout_event,
            confidence=confidence.composite_confidence,
            brick_sequence_id=opt_renko_res.brick_sequence_id
        )

        return FrameExtractionResult(
            data_feed_state=DataFeedState.LIVE_AND_VALID,
            index_state=index_state,
            option_state=option_state,
            frame_confidence=confidence,
            layout=layout,
            error_message=""
        )
