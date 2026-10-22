# plugins/trading_signals/vision/panel_detector.py
"""
Multi-Panel Chart Boundary Detection and Segmentation for Dhan / TradingView.
Detects arbitrary multi-chart layouts without assuming fixed coordinates
(e.g., 1 large + 2 small, 2 horizontal, 2 vertical, 3-column, 2x2 grid, resized panels).
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from .detector import RectRegion

logger = logging.getLogger("jarvis.trading.vision.panel_detector")


@dataclass(frozen=True)
class DetectedPanelBoundary:
    """Raw detected bounding box and functional subregions for a chart panel."""
    panel_index: int
    region: RectRegion
    header_region: RectRegion
    canvas_region: RectRegion
    price_axis_region: RectRegion
    time_axis_region: RectRegion
    confidence: float = 1.0


class MultiPanelChartDetector:
    """
    Analyzes visual workspace structure to discover independent chart panel boundaries.
    Uses edge projections, border lines, and header anchor signatures.
    """

    def __init__(
        self,
        axis_width_ratio: float = 0.12,
        header_height_ratio: float = 0.25,
        time_axis_height_ratio: float = 0.06
    ):
        self.axis_width_ratio = axis_width_ratio
        self.header_height_ratio = header_height_ratio
        self.time_axis_height_ratio = time_axis_height_ratio

    def get_workspace_bounds(self, frame_bgr: "np.ndarray") -> RectRegion:
        """
        Extracts the active chart canvas bounding box by trimming:
        - Top browser / Dhan toolbars (~10-15% on 1080p/720p)
        - Left drawing sidebar (~40-50px)
        - Bottom status tabs (~30-40px)
        """
        h, w = frame_bgr.shape[:2]
        top = int(h * 0.12) if h > 400 else int(h * 0.08)
        left = 45 if w > 500 else 10
        bottom = h - (int(h * 0.05) if h > 400 else 20)
        right = w - 5

        width = max(100, right - left)
        height = max(100, bottom - top)
        return RectRegion(x=left, y=top, w=width, h=height)

    def detect_panels(
        self,
        full_frame_bgr: "np.ndarray",
        mock_panel_rects: Optional[List[RectRegion]] = None
    ) -> List[DetectedPanelBoundary]:
        """
        Discovers individual chart panel regions across the screen.
        If mock_panel_rects is injected (for unit tests / fixtures), segments them directly.
        Otherwise performs automated visual edge and grid analysis.
        """
        if cv2 is None or np is None or full_frame_bgr is None or full_frame_bgr.size == 0:
            return []

        h, w = full_frame_bgr.shape[:2]
        if w < 350 or h < 200:
            logger.warning("[MULTI_PANEL] Frame dimensions %dx%d too small for multi-chart detection.", w, h)
            return []

        # 1. Use explicit injected panel bounding boxes if provided
        if mock_panel_rects is not None:
            return [self._build_panel_boundary(idx, rect) for idx, rect in enumerate(mock_panel_rects)]

        workspace = self.get_workspace_bounds(full_frame_bgr)
        ws_crop = workspace.crop(full_frame_bgr)
        if ws_crop is None or ws_crop.size == 0:
            return []

        # 2. Automated Visual Grid & Divider Detection
        rects = self._discover_panel_grid_rects(ws_crop, workspace)
        if not rects:
            # Fallback to single workspace panel
            rects = [workspace]

        return [self._build_panel_boundary(idx, r) for idx, r in enumerate(rects)]

    def _discover_panel_grid_rects(
        self,
        ws_bgr: "np.ndarray",
        workspace: RectRegion
    ) -> List[RectRegion]:
        """
        Detects internal vertical and horizontal split dividers within the workspace crop.
        Identifies layouts:
        - 1 large left + 2 stacked right (like reference screenshot)
        - 2 vertical columns (left and right)
        - 2 horizontal rows (top and bottom)
        - 3 columns
        - 4-grid (2x2)
        """
        h, w = ws_bgr.shape[:2]
        gray = cv2.cvtColor(ws_bgr, cv2.COLOR_BGR2GRAY)

        # Compute vertical line projections to find column splits
        # Look for prominent vertical dividers between 20% and 80% of width
        grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
        grad_x_abs = cv2.convertScaleAbs(grad_x)
        col_sums = np.sum(grad_x_abs, axis=0)

        # Detect vertical peaks
        min_col_x = int(w * 0.20)
        max_col_x = int(w * 0.80)
        candidate_cols = []
        for x in range(min_col_x, max_col_x):
            # Check local peak with threshold
            if col_sums[x] > 0.4 * np.max(col_sums) and col_sums[x] > col_sums[x - 1] and col_sums[x] > col_sums[x + 1]:
                # Avoid closely spaced duplicate peaks (min 60px distance)
                if not any(abs(x - c) < 60 for c in candidate_cols):
                    candidate_cols.append(x)

        # Sort detected vertical split positions
        candidate_cols.sort()

        # If no significant vertical divider detected, check for pure horizontal split (top/bottom)
        if not candidate_cols:
            grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
            grad_y_abs = cv2.convertScaleAbs(grad_y)
            row_sums = np.sum(grad_y_abs, axis=1)
            min_row_y = int(h * 0.25)
            max_row_y = int(h * 0.75)
            candidate_rows = []
            for y in range(min_row_y, max_row_y):
                if row_sums[y] > 0.45 * np.max(row_sums) and row_sums[y] > row_sums[y - 1] and row_sums[y] > row_sums[y + 1]:
                    if not any(abs(y - r) < 60 for r in candidate_rows):
                        candidate_rows.append(y)

            if candidate_rows:
                # 2 horizontal rows
                split_y = candidate_rows[0]
                r1 = RectRegion(x=workspace.x, y=workspace.y, w=workspace.w, h=split_y)
                r2 = RectRegion(x=workspace.x, y=workspace.y + split_y, w=workspace.w, h=workspace.h - split_y)
                return [r1, r2]

            return [workspace]

        # Process columns
        # Divide into vertical strips: [0, split_1, split_2, ..., w]
        col_bounds = [0] + candidate_cols + [w]
        panels = []

        for i in range(len(col_bounds) - 1):
            c_left = col_bounds[i]
            c_right = col_bounds[i + 1]
            c_width = c_right - c_left

            col_strip = gray[:, c_left:c_right]
            # Detect horizontal split inside this column
            grad_y = cv2.Sobel(col_strip, cv2.CV_16S, 0, 1, ksize=3)
            grad_y_abs = cv2.convertScaleAbs(grad_y)
            row_sums = np.sum(grad_y_abs, axis=1)

            min_y = int(h * 0.30)
            max_y = int(h * 0.70)
            h_splits = []
            for y in range(min_y, max_y):
                if row_sums[y] > 0.45 * np.max(row_sums) and row_sums[y] > row_sums[y - 1] and row_sums[y] > row_sums[y + 1]:
                    if not any(abs(y - r) < 60 for r in h_splits):
                        h_splits.append(y)

            if h_splits:
                # Column is split horizontally (e.g. top-right and bottom-right in Dhan layout)
                split_y = h_splits[0]
                top_p = RectRegion(
                    x=workspace.x + c_left,
                    y=workspace.y,
                    w=c_width,
                    h=split_y
                )
                bottom_p = RectRegion(
                    x=workspace.x + c_left,
                    y=workspace.y + split_y,
                    w=c_width,
                    h=workspace.h - split_y
                )
                panels.extend([top_p, bottom_p])
            else:
                # Full-height column (e.g. left NIFTY 50 panel in Dhan layout)
                p = RectRegion(
                    x=workspace.x + c_left,
                    y=workspace.y,
                    w=c_width,
                    h=workspace.h
                )
                panels.append(p)

        return panels

    def _build_panel_boundary(self, index: int, region: RectRegion) -> DetectedPanelBoundary:
        """
        Partitions an individual panel into its local functional subregions:
        - header_region (top-left strip)
        - price_axis_region (rightmost vertical strip)
        - time_axis_region (bottom horizontal strip)
        - canvas_region (central Renko plotting area)
        """
        axis_w = max(40, int(region.w * self.axis_width_ratio))
        time_h = max(20, int(region.h * self.time_axis_height_ratio))
        hdr_h = max(35, int(region.h * self.header_height_ratio))

        canvas_w = max(50, region.w - axis_w)
        canvas_h = max(50, region.h - hdr_h - time_h)

        header_region = RectRegion(
            x=region.x,
            y=region.y,
            w=canvas_w,
            h=hdr_h
        )
        price_axis_region = RectRegion(
            x=region.right - axis_w,
            y=region.y,
            w=axis_w,
            h=region.h
        )
        time_axis_region = RectRegion(
            x=region.x,
            y=region.bottom - time_h,
            w=canvas_w,
            h=time_h
        )
        canvas_region = RectRegion(
            x=region.x,
            y=region.y + hdr_h,
            w=canvas_w,
            h=canvas_h
        )

        return DetectedPanelBoundary(
            panel_index=index,
            region=region,
            header_region=header_region,
            canvas_region=canvas_region,
            price_axis_region=price_axis_region,
            time_axis_region=time_axis_region,
            confidence=1.0
        )
