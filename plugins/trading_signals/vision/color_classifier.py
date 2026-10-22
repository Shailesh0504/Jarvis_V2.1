# plugins/trading_signals/vision/color_classifier.py
"""
Calibrated HSV / Tolerance-Based Color Classification Engine.
Replaces naive exact RGB equality with bounded HSV envelopes and minimum density filters.
"""

from enum import Enum
import logging
from typing import Dict, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from ..models.chart_state import RenkoColor

logger = logging.getLogger("jarvis.trading.vision.color")


class CalibratedColorClassifier:
    """
    Classifies visual chart elements (Renko bricks, SuperTrend line, Donchian bands)
    using calibrated HSV ranges and pixel density ratios.
    """

    # Calibrated HSV ranges (H: 0-179, S: 0-255, V: 0-255 in OpenCV)
    # Green: TradingView Bullish #089981 / standard green (Hue 35 - 95)
    LOWER_GREEN = (35, 50, 50)
    UPPER_GREEN = (95, 255, 255)

    # Red: TradingView Bearish #F23645 / standard red (Hue 0-10 & 165-179)
    LOWER_RED_1 = (0, 50, 50)
    UPPER_RED_1 = (10, 255, 255)
    LOWER_RED_2 = (165, 50, 50)
    UPPER_RED_2 = (179, 255, 255)

    # Blue / Cyan: Donchian Channel lines & text
    LOWER_BLUE = (98, 50, 70)
    UPPER_BLUE = (135, 255, 255)

    # Dark Grey: EMA line
    LOWER_GREY = (0, 0, 45)
    UPPER_GREY = (179, 35, 140)

    def __init__(self, min_density_ratio: float = 0.40):
        self.min_density_ratio = max(0.10, min(1.0, float(min_density_ratio)))

    def classify_brick_color(self, brick_bgr: "np.ndarray") -> Tuple[RenkoColor, float]:
        """
        Classifies whether a cropped brick image region is GREEN, RED, or UNKNOWN.
        Returns: Tuple[RenkoColor, confidence_score]
        """
        if cv2 is None or np is None or brick_bgr is None or brick_bgr.size == 0:
            return RenkoColor.UNKNOWN, 0.0

        h, w = brick_bgr.shape[:2]
        total_pixels = h * w
        if total_pixels == 0:
            return RenkoColor.UNKNOWN, 0.0

        hsv = cv2.cvtColor(brick_bgr, cv2.COLOR_BGR2HSV)

        # 1. Green mask count
        mask_green = cv2.inRange(hsv, np.array(self.LOWER_GREEN), np.array(self.UPPER_GREEN))
        green_count = int(np.count_nonzero(mask_green))
        green_density = green_count / float(total_pixels)

        # 2. Red mask count (combining both ends of hue wrap)
        mask_red1 = cv2.inRange(hsv, np.array(self.LOWER_RED_1), np.array(self.UPPER_RED_1))
        mask_red2 = cv2.inRange(hsv, np.array(self.LOWER_RED_2), np.array(self.UPPER_RED_2))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        red_count = int(np.count_nonzero(mask_red))
        red_density = red_count / float(total_pixels)

        if green_density >= self.min_density_ratio and green_density > red_density:
            conf = min(1.0, green_density / 0.80)
            return RenkoColor.GREEN, conf

        if red_density >= self.min_density_ratio and red_density > green_density:
            conf = min(1.0, red_density / 0.80)
            return RenkoColor.RED, conf

        return RenkoColor.UNKNOWN, 0.0

    def is_blue_donchian_pixel(self, bgr_pixel: Tuple[int, int, int]) -> bool:
        """Helper to test a single BGR pixel against calibrated blue channel bounds."""
        if cv2 is None or np is None:
            return False
        pix = np.uint8([[list(bgr_pixel)]])
        hsv = cv2.cvtColor(pix, cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
        return (self.LOWER_BLUE[0] <= h <= self.UPPER_BLUE[0] and
                self.LOWER_BLUE[1] <= s <= self.UPPER_BLUE[1] and
                self.LOWER_BLUE[2] <= v <= self.UPPER_BLUE[2])
