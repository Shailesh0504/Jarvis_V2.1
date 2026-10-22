# plugins/trading_signals/vision/renko_detector.py
"""
Structural Visual Renko Brick Detector.
Detects visible brick column spawn and multi-frame chart stability.
Strictly eliminates price rounding or timer-based assumptions.
"""

from dataclasses import dataclass
import logging
from typing import List, Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from ..models.chart_state import BrickStatus, RenkoColor, RenkoTransition
from .color_classifier import CalibratedColorClassifier

logger = logging.getLogger("jarvis.trading.vision.renko")


@dataclass(frozen=True)
class VisibleBrickContour:
    """Detected geometric representation of a single Renko brick on canvas."""
    x: int
    y: int
    w: int
    h: int
    color: RenkoColor
    confidence: float

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2.0


@dataclass(frozen=True)
class RenkoDetectionResult:
    """Comprehensive output of Renko canvas visual analysis."""
    brick_status: BrickStatus
    active_color: RenkoColor
    transition: RenkoTransition
    consecutive_opposite_count: int
    brick_sequence_id: int
    chart_stable: bool
    multi_brick_jump: bool
    detected_bricks_count: int
    confidence: float


class RenkoVisualDetector:
    """
    Analyzes chart canvas regions to identify discrete Renko brick columns,
    verify closed brick solid contour spawn, and track transitions.
    """

    def __init__(self, min_brick_width: int = 5, min_brick_height: int = 5):
        self.min_brick_width = min_brick_width
        self.min_brick_height = min_brick_height
        self.color_classifier = CalibratedColorClassifier()
        self._last_closed_x: Optional[int] = None
        self._last_closed_color: RenkoColor = RenkoColor.UNKNOWN
        self._last_brick_sequence_id: int = 0
        self._consecutive_opposite_count: int = 0
        self._historical_canvas_fingerprint: Optional[float] = None
        self._persistence_frame_count: int = 0

    def check_chart_stability(self, canvas_bgr: "np.ndarray") -> bool:
        """
        Validates that the historical chart canvas has not undergone
        panning, scrolling, or redrawing between observation frames.
        """
        if cv2 is None or np is None or canvas_bgr is None or canvas_bgr.size == 0:
            return False

        gray = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2GRAY)
        # Focus on left 60% of canvas (historical established bricks)
        h, w = gray.shape
        hist_strip = gray[:, : int(w * 0.6)]
        current_mean = float(np.mean(hist_strip))

        if self._historical_canvas_fingerprint is None:
            self._historical_canvas_fingerprint = current_mean
            return True

        drift = abs(current_mean - self._historical_canvas_fingerprint)
        self._historical_canvas_fingerprint = current_mean

        # If historical background shifts significantly (> 5% intensity drift), chart is scrolling/animating
        if drift > 12.0:
            logger.debug("[CHART_STABILITY] Drift %.2f > 12.0. Canvas undergoing redraw or scroll.", drift)
            return False
        return True

    def detect_bricks(self, canvas_bgr: "np.ndarray") -> List[VisibleBrickContour]:
        """
        Extracts visible rectangular brick contours sorted from left to right.
        """
        if cv2 is None or np is None or canvas_bgr is None or canvas_bgr.size == 0:
            return []

        h, w = canvas_bgr.shape[:2]
        hsv = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2HSV)

        # 1. Segment Green and Red regions
        mask_green = cv2.inRange(hsv, np.array(self.color_classifier.LOWER_GREEN), np.array(self.color_classifier.UPPER_GREEN))
        mask_red1 = cv2.inRange(hsv, np.array(self.color_classifier.LOWER_RED_1), np.array(self.color_classifier.UPPER_RED_1))
        mask_red2 = cv2.inRange(hsv, np.array(self.color_classifier.LOWER_RED_2), np.array(self.color_classifier.UPPER_RED_2))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        combined_mask = cv2.bitwise_or(mask_green, mask_red)

        # 2. Morphological cleanup to solidify discrete brick boxes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cleaned = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bricks: List[VisibleBrickContour] = []

        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Filter noise: Renko bricks must be at least min dimensions
            if bw >= self.min_brick_width and bh >= self.min_brick_height:
                crop = canvas_bgr[y : y + bh, x : x + bw]
                color, conf = self.color_classifier.classify_brick_color(crop)
                if color != RenkoColor.UNKNOWN:
                    bricks.append(VisibleBrickContour(x=x, y=y, w=bw, h=bh, color=color, confidence=conf))

        # Sort left to right by X coordinate
        bricks.sort(key=lambda b: b.x)
        return bricks

    def evaluate_canvas(self, canvas_bgr: "np.ndarray") -> RenkoDetectionResult:
        """
        Full lifecycle analysis on the canvas:
        - Stability check
        - Rightmost brick column appearance
        - Closed vs Forming determination
        - Multi-brick jump detection
        """
        stable = self.check_chart_stability(canvas_bgr)
        bricks = self.detect_bricks(canvas_bgr)

        if not bricks or not stable:
            return RenkoDetectionResult(
                brick_status=BrickStatus.UNKNOWN,
                active_color=RenkoColor.UNKNOWN,
                transition=RenkoTransition.NO_TRANSITION,
                consecutive_opposite_count=0,
                brick_sequence_id=self._last_brick_sequence_id,
                chart_stable=stable,
                multi_brick_jump=False,
                detected_bricks_count=len(bricks),
                confidence=0.0
            )

        rightmost = bricks[-1]

        # Initial baseline assignment
        if self._last_closed_x is None:
            self._last_closed_x = rightmost.x
            self._last_closed_color = rightmost.color
            self._last_brick_sequence_id = 1
            return RenkoDetectionResult(
                brick_status=BrickStatus.CLOSED,
                active_color=rightmost.color,
                transition=RenkoTransition.NO_TRANSITION,
                consecutive_opposite_count=0,
                brick_sequence_id=1,
                chart_stable=True,
                multi_brick_jump=False,
                detected_bricks_count=len(bricks),
                confidence=rightmost.confidence
            )

        # Check column progression:
        # A new column is spawned if rightmost.x has progressed by at least 1 brick width
        brick_step = rightmost.x - self._last_closed_x
        avg_w = max(rightmost.w, self.min_brick_width)

        # Case A: Same column as previously observed
        if abs(brick_step) < (avg_w * 0.8):
            # Still in the same closed column or forming border
            transition = RenkoTransition.NO_TRANSITION
            return RenkoDetectionResult(
                brick_status=BrickStatus.CLOSED,
                active_color=self._last_closed_color,
                transition=transition,
                consecutive_opposite_count=self._consecutive_opposite_count,
                brick_sequence_id=self._last_brick_sequence_id,
                chart_stable=True,
                multi_brick_jump=False,
                detected_bricks_count=len(bricks),
                confidence=rightmost.confidence
            )

        # Case B: Multi-brick jump detected (e.g. gap > 2.5 brick widths)
        if brick_step > (avg_w * 2.5):
            logger.warning("[RENKO_MULTI_BRICK_JUMP] Detected X step %d px > 2.5x brick width %d px.", brick_step, avg_w)
            # Mark multi-brick jump to reject signal
            self._last_closed_x = rightmost.x
            self._last_closed_color = rightmost.color
            self._last_brick_sequence_id += 2
            return RenkoDetectionResult(
                brick_status=BrickStatus.CLOSED,
                active_color=rightmost.color,
                transition=RenkoTransition.UNKNOWN,
                consecutive_opposite_count=0,
                brick_sequence_id=self._last_brick_sequence_id,
                chart_stable=True,
                multi_brick_jump=True,  # Invariant: Must reject candidate signal
                detected_bricks_count=len(bricks),
                confidence=rightmost.confidence * 0.70
            )

        # Case C: Valid single new closed brick column spawned
        if brick_step >= (avg_w * 0.8):
            self._persistence_frame_count += 1
            # Requires at least 2 consecutive observation scans to solidify
            if self._persistence_frame_count < 2:
                # Still stabilizing contour
                return RenkoDetectionResult(
                    brick_status=BrickStatus.FORMING,
                    active_color=rightmost.color,
                    transition=RenkoTransition.NO_TRANSITION,
                    consecutive_opposite_count=self._consecutive_opposite_count,
                    brick_sequence_id=self._last_brick_sequence_id,
                    chart_stable=True,
                    multi_brick_jump=False,
                    detected_bricks_count=len(bricks),
                    confidence=rightmost.confidence * 0.80
                )

            # Solidified closed brick transition confirmed
            self._persistence_frame_count = 0
            self._last_closed_x = rightmost.x
            self._last_brick_sequence_id += 1

            # Determine transition
            if self._last_closed_color == RenkoColor.RED and rightmost.color == RenkoColor.GREEN:
                transition = RenkoTransition.RED_TO_GREEN
                self._consecutive_opposite_count = 0
            elif self._last_closed_color == RenkoColor.GREEN and rightmost.color == RenkoColor.RED:
                transition = RenkoTransition.GREEN_TO_RED
                self._consecutive_opposite_count = 1
            elif rightmost.color == RenkoColor.RED and self._last_closed_color == RenkoColor.RED:
                transition = RenkoTransition.NO_TRANSITION
                self._consecutive_opposite_count += 1
            else:
                transition = RenkoTransition.NO_TRANSITION
                self._consecutive_opposite_count = 0

            self._last_closed_color = rightmost.color

            return RenkoDetectionResult(
                brick_status=BrickStatus.CLOSED,
                active_color=rightmost.color,
                transition=transition,
                consecutive_opposite_count=self._consecutive_opposite_count,
                brick_sequence_id=self._last_brick_sequence_id,
                chart_stable=True,
                multi_brick_jump=False,
                detected_bricks_count=len(bricks),
                confidence=rightmost.confidence
            )

        return RenkoDetectionResult(
            brick_status=BrickStatus.FORMING,
            active_color=rightmost.color,
            transition=RenkoTransition.NO_TRANSITION,
            consecutive_opposite_count=self._consecutive_opposite_count,
            brick_sequence_id=self._last_brick_sequence_id,
            chart_stable=True,
            multi_brick_jump=False,
            detected_bricks_count=len(bricks),
            confidence=0.50
        )
