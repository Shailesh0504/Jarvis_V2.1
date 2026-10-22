# plugins/trading_signals/vision/detector.py
"""
Chart Region and Layout Detector.
Divides dual-chart trading setups into INDEX_CHART_REGION and OPTION_CHART_REGION
with measurable geometric bounding box tolerances.
"""

from dataclasses import dataclass
import logging
from typing import Dict, Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger("jarvis.trading.vision.detector")


@dataclass(frozen=True)
class RectRegion:
    """Bounding box defined by (x, y, width, height)."""
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def crop(self, image: "np.ndarray") -> "np.ndarray":
        """Crops this region from a NumPy image array."""
        if image is None:
            return None
        return image[self.y : self.bottom, self.x : self.right]


@dataclass(frozen=True)
class SegmentedChartLayout:
    """Segmented visual hierarchy of the trading workspace."""
    index_chart_region: RectRegion
    option_chart_region: RectRegion
    index_header_region: RectRegion
    option_header_region: RectRegion
    index_price_axis_region: RectRegion
    option_price_axis_region: RectRegion
    index_canvas_region: RectRegion
    option_canvas_region: RectRegion
    confidence: float


class ChartRegionDetector:
    """
    Detects and segments dual-pane charts (e.g. TradingView/Dhan layout)
    into structured functional regions.
    """

    def __init__(self, axis_width_ratio: float = 0.12, header_height_ratio: float = 0.28):
        self.axis_width_ratio = axis_width_ratio
        self.header_height_ratio = header_height_ratio

    def detect_layout(self, full_frame_bgr: "np.ndarray") -> Optional[SegmentedChartLayout]:
        """
        Segments full frame into Left (Index) and Right (Option) chart regions.
        Enforces quantitative sanity bounds.
        """
        if cv2 is None or np is None or full_frame_bgr is None or full_frame_bgr.size == 0:
            return None

        h, w = full_frame_bgr.shape[:2]
        if w < 400 or h < 250:
            logger.warning("[REGION_DETECTOR] Frame resolution %dx%d too low for chart segmentation.", w, h)
            return None

        # 1. Detect vertical dividing boundary separating left and right charts
        # In a 2-pane TradingView layout, the split is typically near 50% width (0.45w to 0.55w)
        split_x = int(w * 0.518)  # Default center-right split position based on toolbar + layout

        # Detect if a prominent vertical divider line or margin exists near center
        gray = cv2.cvtColor(full_frame_bgr, cv2.COLOR_BGR2GRAY)
        center_strip = gray[:, int(w * 0.45) : int(w * 0.58)]
        # Vertical gradient
        grad_x = cv2.Sobel(center_strip, cv2.CV_16S, 1, 0, ksize=3)
        grad_x_abs = cv2.convertScaleAbs(grad_x)
        col_sums = np.sum(grad_x_abs, axis=0)
        if len(col_sums) > 0:
            candidate_col = int(np.argmax(col_sums))
            detected_x = int(w * 0.45) + candidate_col
            # Check if gradient peak is substantial
            if col_sums[candidate_col] > 1000:
                split_x = detected_x

        # 2. Exclude top browser/app toolbar if visible (typically top 8-12%)
        # In TradingView web app, chart area starts below navigation toolbar (~y=80-100 on standard 1080p/720p)
        top_offset = int(h * 0.18) if h > 400 else int(h * 0.12)
        bottom_offset = h - int(h * 0.05)
        chart_height = max(100, bottom_offset - top_offset)

        # 3. Form Left Pane (Index Chart Region)
        idx_w = max(150, split_x - 30)
        idx_region = RectRegion(x=30, y=top_offset, w=idx_w, h=chart_height)

        # 4. Form Right Pane (Option Chart Region)
        opt_x = split_x
        opt_w = max(150, w - opt_x - 15)
        opt_region = RectRegion(x=opt_x, y=top_offset, w=opt_w, h=chart_height)

        # 5. Segment Functional Subregions
        # Axis width: rightmost vertical strip of each pane
        idx_axis_w = int(idx_w * self.axis_width_ratio)
        opt_axis_w = int(opt_w * self.axis_width_ratio)

        idx_axis_region = RectRegion(x=idx_region.right - idx_axis_w, y=idx_region.y, w=idx_axis_w, h=idx_region.h)
        opt_axis_region = RectRegion(x=opt_region.right - opt_axis_w, y=opt_region.y, w=opt_axis_w, h=opt_region.h)

        # Header / Legend region: top strip of each pane
        hdr_h = int(chart_height * self.header_height_ratio)
        idx_hdr_region = RectRegion(x=idx_region.x, y=idx_region.y, w=idx_region.w - idx_axis_w, h=hdr_h)
        opt_hdr_region = RectRegion(x=opt_region.x, y=opt_region.y, w=opt_region.w - opt_axis_w, h=hdr_h)

        # Canvas region: remaining area where Renko bricks are plotted
        idx_canvas_region = RectRegion(
            x=idx_region.x,
            y=idx_region.y + hdr_h,
            w=idx_region.w - idx_axis_w,
            h=idx_region.h - hdr_h
        )
        opt_canvas_region = RectRegion(
            x=opt_region.x,
            y=opt_region.y + hdr_h,
            w=opt_region.w - opt_axis_w,
            h=opt_region.h - hdr_h
        )

        return SegmentedChartLayout(
            index_chart_region=idx_region,
            option_chart_region=opt_region,
            index_header_region=idx_hdr_region,
            option_header_region=opt_hdr_region,
            index_price_axis_region=idx_axis_region,
            option_price_axis_region=opt_axis_region,
            index_canvas_region=idx_canvas_region,
            option_canvas_region=opt_canvas_region,
            confidence=0.95
        )
