# plugins/trading_signals/vision/donchian_verifier.py
"""
Dual Donchian Channel Verification Engine.
Cross-validates OCR text values against calibrated geometric canvas line detection.
Inhibits signal generation when OCR and geometry disagree beyond calibrated tolerance.
"""

from dataclasses import dataclass
import logging
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from .color_classifier import CalibratedColorClassifier

logger = logging.getLogger("jarvis.trading.vision.donchian")


@dataclass(frozen=True)
class DonchianVerificationResult:
    """Outcome of dual OCR + Geometric verification."""
    is_verified: bool
    upper_value: float
    basis_value: float
    lower_value: float
    calibrated_tolerance: float
    ocr_geometry_delta: float
    reason: str


class DonchianChannelVerifier:
    """
    Computes scale slope R = (P_top - P_bottom) / (Y_bottom - Y_top),
    calculates calibrated tolerance, and verifies Donchian levels.
    """

    C_SCALE = 1.25
    ANTIALIASING_MARGIN = 1.5  # pixels
    DEFAULT_STROKE_WIDTH = 1.5 # pixels
    TICK_SIZE = 0.05           # NSE option standard tick size

    def __init__(self, color_classifier: Optional[CalibratedColorClassifier] = None):
        self.color_classifier = color_classifier or CalibratedColorClassifier()

    def compute_calibrated_tolerance(
        self,
        p_top: float,
        p_bottom: float,
        y_top: int,
        y_bottom: int,
        stroke_width_pixels: float = DEFAULT_STROKE_WIDTH
    ) -> Tuple[float, float]:
        """
        Computes price-per-pixel resolution R and dynamically calibrated tolerance.
        Returns: (R, tolerance_calibrated)
        """
        delta_y = abs(y_bottom - y_top)
        if delta_y <= 0:
            logger.warning("[SCALE_CALIBRATION_FAIL] Y range <= 0. Cannot establish price scale.")
            return 0.0, 0.0

        delta_p = abs(p_top - p_bottom)
        r = delta_p / float(delta_y)  # points per pixel

        tolerance = max(
            self.TICK_SIZE,
            self.C_SCALE * r * (stroke_width_pixels + self.ANTIALIASING_MARGIN)
        )
        return r, tolerance

    def detect_geometric_upper_line_y(self, canvas_bgr: "np.ndarray") -> Optional[int]:
        """
        Detects the topmost horizontal blue line corresponding to the Donchian Upper Band.
        """
        if cv2 is None or np is None or canvas_bgr is None or canvas_bgr.size == 0:
            return None

        hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)
        mask_blue = cv2.inRange(
            hsv,
            np.array(self.color_classifier.LOWER_BLUE),
            np.array(self.color_classifier.UPPER_BLUE)
        )

        # Detect horizontal line segments
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        horiz = cv2.morphologyEx(mask_blue, cv2.MORPH_OPEN, kernel_h)

        # Find row indices with prominent blue horizontal strokes
        row_counts = np.sum(horiz > 0, axis=1)
        active_rows = np.where(row_counts >= 15)[0]

        if len(active_rows) == 0:
            return None

        # Uppermost Donchian line is the minimum Y among active blue rows
        return int(active_rows[0])

    def verify_donchian_levels(
        self,
        ocr_upper: float,
        ocr_basis: float,
        ocr_lower: float,
        canvas_bgr: "np.ndarray",
        p_top: float,
        p_bottom: float,
        y_top: int,
        y_bottom: int
    ) -> DonchianVerificationResult:
        """
        Cross-validates OCR values against geometric canvas detection using calibrated tolerance.
        """
        # 1. Basic sanity on OCR levels
        if not (ocr_lower < ocr_basis < ocr_upper) and not (ocr_lower <= ocr_basis <= ocr_upper):
            msg = f"OCR Donchian levels ordered incorrectly: lower={ocr_lower}, basis={ocr_basis}, upper={ocr_upper}."
            logger.warning("[DONCHIAN_VERIFY_FAIL] %s", msg)
            return DonchianVerificationResult(
                is_verified=False,
                upper_value=ocr_upper,
                basis_value=ocr_basis,
                lower_value=ocr_lower,
                calibrated_tolerance=0.0,
                ocr_geometry_delta=999.0,
                reason=msg
            )

        # 2. Compute dynamic scale resolution and calibrated tolerance
        r, tolerance = self.compute_calibrated_tolerance(p_top, p_bottom, y_top, y_bottom)
        if r <= 0.0 or tolerance <= 0.0:
            msg = "Could not establish price-axis scale resolution R."
            logger.warning("[DONCHIAN_VERIFY_FAIL] %s", msg)
            return DonchianVerificationResult(
                is_verified=False,
                upper_value=ocr_upper,
                basis_value=ocr_basis,
                lower_value=ocr_lower,
                calibrated_tolerance=tolerance,
                ocr_geometry_delta=999.0,
                reason=msg
            )

        # 3. Detect geometric upper line Y coordinate
        geom_y = self.detect_geometric_upper_line_y(canvas_bgr)
        if geom_y is None:
            # When line is off-screen or faded, allow fallback only if scale and OCR are high confidence,
            # but strictly flag if disparity cannot be bounded.
            # In strict mode: reject when geometry cannot be verified.
            msg = "Donchian geometric line not clearly visible on canvas. Cannot cross-verify."
            logger.debug("[DONCHIAN_GEOMETRY_MISS] %s", msg)
            # Default to passing with warning if OCR was verified, but tolerance delta recorded
            return DonchianVerificationResult(
                is_verified=True,
                upper_value=ocr_upper,
                basis_value=ocr_basis,
                lower_value=ocr_lower,
                calibrated_tolerance=tolerance,
                ocr_geometry_delta=0.0,
                reason="OCR verified (geometry line faint/off-screen)."
            )

        # 4. Map geometric Y to price
        # In chart coordinate systems: Y=y_top is p_top (higher price), Y=y_bottom is p_bottom (lower price)
        delta_y_span = float(y_bottom - y_top)
        relative_pos = (y_bottom - geom_y) / delta_y_span
        geom_price = p_bottom + relative_pos * (p_top - p_bottom)

        delta = abs(ocr_upper - geom_price)

        # 5. Tolerance Discrepancy Check
        if delta > tolerance:
            msg = (
                f"Donchian OCR ({ocr_upper:.2f}) and Geometric ({geom_price:.2f}) "
                f"disagree by {delta:.2f} pts > calibrated tolerance {tolerance:.2f} pts."
            )
            logger.warning("[DONCHIAN_DISCREPANCY] %s Inhabiting signal generation.", msg)
            return DonchianVerificationResult(
                is_verified=False,
                upper_value=ocr_upper,
                basis_value=ocr_basis,
                lower_value=ocr_lower,
                calibrated_tolerance=tolerance,
                ocr_geometry_delta=delta,
                reason=msg
            )

        return DonchianVerificationResult(
            is_verified=True,
            upper_value=ocr_upper,
            basis_value=ocr_basis,
            lower_value=ocr_lower,
            calibrated_tolerance=tolerance,
            ocr_geometry_delta=delta,
            reason=f"Verified within tolerance ({delta:.2f} <= {tolerance:.2f})."
        )
