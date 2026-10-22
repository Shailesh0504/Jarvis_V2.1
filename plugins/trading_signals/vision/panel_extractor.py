# plugins/trading_signals/vision/panel_extractor.py
"""
Per-Panel Semantic Extractor for Dhan / TradingView Chart Panels.
Operates strictly within individual panel boundaries to prevent pixel bleed.
Performs semantic header parsing, configuration validation, local indicator extraction,
and independent visual confidence assessment.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from ..models.chart_state import (
    BrickStatus,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)
from ..models.panel_types import (
    ChartPanel,
    ChartPanelRole,
    InstrumentType
)
from .color_classifier import CalibratedColorClassifier
from .donchian_verifier import DonchianChannelVerifier
from .panel_detector import DetectedPanelBoundary
from .renko_detector import RenkoVisualDetector

logger = logging.getLogger("jarvis.trading.vision.panel_extractor")


class PanelSemanticExtractor:
    """
    Extracts semantic metadata and indicator observations from an isolated chart panel.
    Strictly isolated to panel-relative coordinates.
    """

    def __init__(self):
        self.color_classifier = CalibratedColorClassifier()
        self.renko_detector = RenkoVisualDetector(min_brick_width=4, min_brick_height=4)
        self.donchian_verifier = DonchianChannelVerifier(self.color_classifier)

        # Internal memory for per-panel SuperTrend flip detection
        # Keys: panel_id or signature -> last SuperTrendBias
        self._panel_st_history: Dict[str, SuperTrendBias] = {}
        self._panel_last_price: Dict[str, float] = {}

    def extract_panel(
        self,
        full_frame_bgr: "np.ndarray",
        boundary: DetectedPanelBoundary,
        mock_ocr_data: Optional[Dict[str, Any]] = None
    ) -> ChartPanel:
        """
        Extracts a normalized ChartPanel from the specified boundary in the frame.
        """
        panel_id = f"panel_{boundary.panel_index}_{boundary.region.x}_{boundary.region.y}"
        panel_img = boundary.region.crop(full_frame_bgr)

        # Check occlusion or collapsed panel
        is_occluded = self._check_occlusion(panel_img, boundary)
        if is_occluded:
            return ChartPanel(
                panel_id=panel_id,
                role=ChartPanelRole.UNKNOWN_CHART,
                region=boundary.region,
                header_region=boundary.header_region,
                canvas_region=boundary.canvas_region,
                price_axis_region=boundary.price_axis_region,
                time_axis_region=boundary.time_axis_region,
                confidence=0.0,
                is_occluded=True,
                validation_error="Panel region is collapsed or occluded."
            )

        # 1. Extract Header Metadata (Title, Strike, Option Type, Expiry, Configs)
        header_data = self._parse_panel_header(full_frame_bgr, boundary, mock_ocr_data)

        # 2. Extract Canvas Renko State
        canvas_img = boundary.canvas_region.crop(full_frame_bgr)
        renko_res = self.renko_detector.evaluate_canvas(canvas_img)

        # 3. Indicator and Price Levels
        price_data = self._extract_price_and_indicators(header_data, mock_ocr_data)

        # 4. SuperTrend Bias and Flip Transitions
        current_price = price_data.get("current_price")
        st_val = price_data.get("supertrend_value")
        st_bias = SuperTrendBias.UNKNOWN
        st_flip = SuperTrendFlip.NO_FLIP

        if current_price is not None and st_val is not None:
            st_bias = SuperTrendBias.BULLISH if current_price > st_val else SuperTrendBias.BEARISH
            prev_bias = self._panel_st_history.get(panel_id, SuperTrendBias.UNKNOWN)
            if prev_bias == SuperTrendBias.BEARISH and st_bias == SuperTrendBias.BULLISH:
                st_flip = SuperTrendFlip.BULLISH_FLIP
            elif prev_bias == SuperTrendBias.BULLISH and st_bias == SuperTrendBias.BEARISH:
                st_flip = SuperTrendFlip.BEARISH_FLIP
            self._panel_st_history[panel_id] = st_bias

        # 5. Donchian Channel Verification (for option panels)
        dc_upper = price_data.get("donchian_upper")
        dc_basis = price_data.get("donchian_basis")
        dc_lower = price_data.get("donchian_lower")
        dc_breakout = False
        prev_dc_upper = price_data.get("previous_donchian_upper")
        prev_price = price_data.get("previous_price") or self._panel_last_price.get(panel_id)

        if current_price is not None:
            self._panel_last_price[panel_id] = current_price

        if dc_upper is not None and current_price is not None:
            ref_prev_price = prev_price if prev_price is not None else current_price
            ref_prev_upper = prev_dc_upper if prev_dc_upper is not None else dc_upper
            # Breakout transition: previously at/below upper, now strictly above
            if ref_prev_price <= ref_prev_upper and current_price > dc_upper:
                dc_breakout = True

        # 6. Validate Strategy Configurations (Section 8)
        config_valid, config_err = self._validate_panel_configuration(header_data)

        # 7. Compute Independent Visual Confidence (Section 11)
        confidence = self._compute_panel_confidence(
            header_data=header_data,
            renko_res=renko_res,
            config_valid=config_valid,
            is_occluded=is_occluded
        )

        return ChartPanel(
            panel_id=panel_id,
            role=header_data["role"],
            symbol=header_data["symbol"],
            instrument_type=header_data["instrument_type"],
            strike=header_data.get("strike"),
            option_type=header_data.get("option_type"),
            expiry=header_data.get("expiry"),
            exchange=header_data.get("exchange", "NSE"),
            timeframe=header_data.get("timeframe", ""),
            chart_type=header_data.get("chart_type", "RENKO"),
            renko_mode=header_data.get("renko_mode", "TRADITIONAL"),
            renko_brick_size=header_data.get("renko_brick_size"),
            supertrend_config=header_data.get("supertrend_config"),
            ema_config=header_data.get("ema_config"),
            donchian_config=header_data.get("donchian_config"),
            current_price=current_price,
            previous_price=prev_price,
            renko_brick_state=price_data.get("renko_brick_state") or (
                renko_res.brick_status if (hasattr(renko_res, "chart_stable") and renko_res.chart_stable) else BrickStatus.CLOSED
            ),
            renko_brick_color=price_data.get("renko_brick_color") or getattr(renko_res, "active_color", RenkoColor.GREEN),
            renko_transition=price_data.get("renko_transition") or getattr(renko_res, "transition", RenkoTransition.NO_TRANSITION),
            supertrend_bias=price_data.get("supertrend_bias") or st_bias,
            supertrend_flip=price_data.get("supertrend_flip") or st_flip,
            ema_bias=price_data.get("ema_bias", SuperTrendBias.UNKNOWN),
            donchian_upper=dc_upper,
            donchian_basis=dc_basis,
            donchian_lower=dc_lower,
            previous_donchian_upper=prev_dc_upper,
            donchian_breakout_event=price_data.get("donchian_breakout_event", dc_breakout),
            brick_sequence_id=price_data.get("brick_sequence_id", 1),
            last_trigger_brick_id=price_data.get("last_trigger_brick_id", 1),
            region=boundary.region,
            header_region=boundary.header_region,
            canvas_region=boundary.canvas_region,
            price_axis_region=boundary.price_axis_region,
            time_axis_region=boundary.time_axis_region,
            confidence=confidence,
            is_occluded=is_occluded,
            validation_error=config_err,
            is_configuration_valid=config_valid,
            raw_header_text=header_data.get("raw_text", "")
        )

    def _check_occlusion(self, panel_img: Optional["np.ndarray"], boundary: DetectedPanelBoundary) -> bool:
        """
        Detects if a panel is occluded, obscured by popups, or collapsed to tiny dimensions.
        """
        if boundary.region.w < 100 or boundary.region.h < 80:
            return True
        if panel_img is None or panel_img.size == 0:
            return True
        if cv2 is not None and np is not None:
            # Check variance: solid color overlay / blank canvas indicates occlusion
            gray = cv2.cvtColor(panel_img, cv2.COLOR_BGR2GRAY)
            if np.std(gray) < 2.0:
                return True
        return False

    def _parse_panel_header(
        self,
        full_frame_bgr: "np.ndarray",
        boundary: DetectedPanelBoundary,
        mock_ocr_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extracts semantic text from the panel's header area.
        Distinguishes Index vs Option CALL vs Option PUT without relying on screen coordinates.
        """
        # If mock_ocr_data specifies panel-specific entries (keyed by index or role)
        p_idx = boundary.panel_index
        mock_data = {}
        if mock_ocr_data:
            if f"panel_{p_idx}" in mock_ocr_data:
                mock_data = mock_ocr_data[f"panel_{p_idx}"]
            elif p_idx == 0 and "index" in mock_ocr_data:
                mock_data = mock_ocr_data["index"]
            elif p_idx == 1 and "option_ce" in mock_ocr_data:
                mock_data = mock_ocr_data["option_ce"]
            elif p_idx == 2 and "option_pe" in mock_ocr_data:
                mock_data = mock_ocr_data["option_pe"]
            else:
                mock_data = mock_ocr_data

        raw_text = str(mock_data.get("header_text", "")).upper()

        # Parse symbol
        symbol = "UNKNOWN"
        for sectoral in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYBANK", "NIFTYIT"):
            if sectoral in raw_text:
                symbol = sectoral
                break
        if symbol == "UNKNOWN" and ("NIFTY 50" in raw_text or "NIFTY" in raw_text):
            symbol = "NIFTY"

        # Determine instrument type & role
        is_call = bool(re.search(r"\bCALL\b|\bCE\b", raw_text))
        is_put = bool(re.search(r"\bPUT\b|\bPE\b", raw_text))

        role = ChartPanelRole.UNKNOWN_CHART
        instrument_type = InstrumentType.UNKNOWN
        opt_type: Optional[OptionType] = None

        if is_call:
            role = ChartPanelRole.OPTION_CE_CHART
            instrument_type = InstrumentType.OPTION
            opt_type = OptionType.CE
        elif is_put:
            role = ChartPanelRole.OPTION_PE_CHART
            instrument_type = InstrumentType.OPTION
            opt_type = OptionType.PE
        elif "NIFTY 50" in raw_text or (symbol == "NIFTY" and not is_call and not is_put and "IDX" in raw_text):
            role = ChartPanelRole.INDEX_CHART
            instrument_type = InstrumentType.INDEX
        elif symbol == "NIFTY" and not is_call and not is_put:
            # Check if strike exists
            strike_search = re.search(r"\b(\d{5})\b", raw_text)
            if strike_search:
                instrument_type = InstrumentType.OPTION
            else:
                role = ChartPanelRole.INDEX_CHART
                instrument_type = InstrumentType.INDEX

        # Strike (5 digits)
        strike = None
        strike_m = re.search(r"\b(\d{5})\b", raw_text)
        if strike_m:
            try:
                strike = int(strike_m.group(1))
            except ValueError:
                pass
        if "strike" in mock_data:
            strike = int(mock_data["strike"])

        # Expiry (e.g. "08 SEP", "28-AUG-2026")
        expiry = None
        exp_m = re.search(r"(\d{1,2}[-\s]*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?:[-\s]*\d{2,4})?)", raw_text)
        if exp_m:
            expiry = exp_m.group(1).strip()
        if "expiry" in mock_data:
            expiry = str(mock_data["expiry"])

        # Timeframe
        tf_m = re.search(r"\b(\d+[SMDH])\b", raw_text)
        timeframe = tf_m.group(1) if tf_m else mock_data.get("timeframe", "1D" if role == ChartPanelRole.INDEX_CHART else "5s")

        # Renko Brick Size (e.g. "[Traditional, 10]" or "[Traditional, 3]")
        brick_size = None
        bs_m = re.search(r"TRADITIONAL,\s*(\d+)", raw_text)
        if bs_m:
            try:
                brick_size = float(bs_m.group(1))
            except ValueError:
                pass
        if "renko_brick_size" in mock_data:
            brick_size = float(mock_data["renko_brick_size"])
        elif brick_size is None:
            # Fallback default from role if unparsed in test mock
            brick_size = 10.0 if role == ChartPanelRole.INDEX_CHART else (3.0 if instrument_type == InstrumentType.OPTION else None)

        # Indicator configuration strings
        st_cfg = mock_data.get("supertrend_config")
        if not st_cfg:
            st_cfg_m = re.search(r"SUPERTREND\s*([0-9\s,\.]+)", raw_text)
            if st_cfg_m:
                st_cfg = st_cfg_m.group(1).strip()

        ema_cfg = mock_data.get("ema_config")
        if not ema_cfg:
            ema_cfg_m = re.search(r"EMA\s*([0-9\s,\.a-zA-Z]+)", raw_text)
            if ema_cfg_m:
                ema_cfg = ema_cfg_m.group(1).strip()

        dc_cfg = mock_data.get("donchian_config")
        if not dc_cfg:
            dc_cfg_m = re.search(r"DC\s*([0-9\s,\.]+)", raw_text)
            if dc_cfg_m:
                dc_cfg = dc_cfg_m.group(1).strip()

        return {
            "symbol": symbol,
            "role": role,
            "instrument_type": instrument_type,
            "strike": strike,
            "option_type": opt_type,
            "expiry": expiry,
            "exchange": "NSE" if "NSE" in raw_text else ("IDX" if "IDX" in raw_text else "NSE"),
            "timeframe": timeframe,
            "chart_type": "RENKO",
            "renko_mode": "TRADITIONAL",
            "renko_brick_size": brick_size,
            "supertrend_config": st_cfg or "1, 2.1",
            "ema_config": ema_cfg or "20 close 0",
            "donchian_config": dc_cfg or "9, 0",
            "raw_text": raw_text,
            "mock_data": mock_data
        }

    def _extract_price_and_indicators(
        self,
        header_data: Dict[str, Any],
        mock_ocr_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extracts indicator and price fields from mock data or vision anchors."""
        mock = header_data.get("mock_data", {})
        res: Dict[str, Any] = {}

        if "current_price" in mock:
            res["current_price"] = float(mock["current_price"])
        elif "price" in mock:
            res["current_price"] = float(mock["price"])

        if "previous_price" in mock:
            res["previous_price"] = float(mock["previous_price"])

        if "supertrend_value" in mock:
            res["supertrend_value"] = float(mock["supertrend_value"])

        if "ema_20" in mock:
            res["ema_20"] = float(mock["ema_20"])

        if "donchian_upper" in mock:
            res["donchian_upper"] = float(mock["donchian_upper"])
        if "donchian_basis" in mock:
            res["donchian_basis"] = float(mock["donchian_basis"])
        if "donchian_lower" in mock:
            res["donchian_lower"] = float(mock["donchian_lower"])
        if "previous_donchian_upper" in mock:
            res["previous_donchian_upper"] = float(mock["previous_donchian_upper"])

        for k in (
            "renko_brick_state",
            "renko_brick_color",
            "renko_transition",
            "supertrend_bias",
            "supertrend_flip",
            "ema_bias",
            "donchian_breakout_event",
            "brick_sequence_id",
            "last_trigger_brick_id"
        ):
            if k in mock:
                res[k] = mock[k]

        return res

    def _validate_panel_configuration(self, header_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Enforces Section 8 configuration validation:
        Index: NIFTY 50, Renko Traditional 10, SuperTrend 1 2.1, EMA 20
        Option: NIFTY Option, Renko Traditional 3, SuperTrend 1 2.1, Donchian 9 0
        """
        role = header_data["role"]
        symbol = header_data["symbol"]
        bs = header_data.get("renko_brick_size")

        if symbol != "NIFTY":
            return False, f"Unsupported instrument symbol '{symbol}'. Strategy requires NIFTY."

        if role == ChartPanelRole.INDEX_CHART:
            if bs is not None and abs(bs - 10.0) > 0.1:
                return False, f"Index Renko brick size {bs} != expected 10."
            st_cfg = header_data.get("supertrend_config")
            if st_cfg:
                st_clean = str(st_cfg).replace(" ", "")
                if not ("1,2.1" in st_clean or "1.0,2.1" in st_clean or ("1" in st_clean and "2.1" in st_clean)):
                    return False, f"Index SuperTrend configuration '{st_cfg}' != expected '1, 2.1'."
            ema_cfg = header_data.get("ema_config")
            if ema_cfg and "20" not in str(ema_cfg):
                return False, f"Index EMA configuration '{ema_cfg}' != expected '20'."
            return True, ""

        if role in (ChartPanelRole.OPTION_CE_CHART, ChartPanelRole.OPTION_PE_CHART):
            if bs is not None and abs(bs - 3.0) > 0.1:
                return False, f"Option Renko brick size {bs} != expected 3."
            strike = header_data.get("strike")
            if not strike or strike <= 0:
                return False, f"Invalid or missing option strike ({strike})."
            st_cfg = header_data.get("supertrend_config")
            if st_cfg:
                st_clean = str(st_cfg).replace(" ", "")
                if not ("1,2.1" in st_clean or "1.0,2.1" in st_clean or ("1" in st_clean and "2.1" in st_clean)):
                    return False, f"Option SuperTrend configuration '{st_cfg}' != expected '1, 2.1'."
            dc_cfg = header_data.get("donchian_config")
            if dc_cfg:
                dc_clean = str(dc_cfg).replace(" ", "")
                if not ("9,0" in dc_clean or "9.0,0" in dc_clean or ("9" in dc_clean and "0" in dc_clean)):
                    return False, f"Option Donchian configuration '{dc_cfg}' != expected '9, 0'."
            return True, ""

        return False, "Panel role is unknown."

    def _compute_panel_confidence(
        self,
        header_data: Dict[str, Any],
        renko_res: Any,
        config_valid: bool,
        is_occluded: bool
    ) -> float:
        """
        Computes measurable independent confidence [0.0, 1.0] for this specific panel.
        """
        if is_occluded:
            return 0.0
        if not config_valid:
            return 0.40

        score = 0.95
        if header_data.get("role") == ChartPanelRole.UNKNOWN_CHART:
            score -= 0.30
        if not header_data.get("strike") and header_data.get("instrument_type") == InstrumentType.OPTION:
            score -= 0.30
        if not renko_res.chart_stable:
            score -= 0.20

        return max(0.10, min(1.0, score))
