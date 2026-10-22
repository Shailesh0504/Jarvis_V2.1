# tests/trading/test_vision_fixtures.py
"""
Vision fixtures and visual robustness tests:
- Dual-pane layout detection across varied resolutions/DPIs
- Different chart sizes (e.g. 1920x1080, 1280x720, 800x600)
- Low resolution rejection (< 400x250)
- Visible vs occluded/blank chart detection
- Antialiased lines and color classification robustness
"""

import numpy as np
import pytest
from plugins.trading_signals.vision.color_classifier import CalibratedColorClassifier
from plugins.trading_signals.vision.detector import ChartRegionDetector
from plugins.trading_signals.models.chart_state import RenkoColor


def test_dual_pane_detection_1080p():
    """Verify dual pane segmentation on 1920x1080 resolution."""
    detector = ChartRegionDetector()
    frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
    # Add vertical divider at center
    frame[:, 960:962] = [80, 80, 80]

    layout = detector.detect_layout(frame)
    assert layout is not None
    assert layout.index_chart_region.w > 800
    assert layout.option_chart_region.w > 800
    assert layout.confidence >= 0.85


def test_dual_pane_detection_720p():
    """Verify dual pane segmentation on 1280x720 resolution."""
    detector = ChartRegionDetector()
    frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
    frame[:, 640:642] = [80, 80, 80]

    layout = detector.detect_layout(frame)
    assert layout is not None
    assert layout.index_chart_region.w > 500
    assert layout.option_chart_region.w > 500


def test_dual_pane_detection_rejects_sub_minimum_resolution():
    """Rejects frames smaller than 400x250."""
    detector = ChartRegionDetector()
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    layout = detector.detect_layout(frame)
    assert layout is None


def test_color_classifier_antialiased_edges():
    """Verify brick color classifier handles antialiased fuzzy borders."""
    classifier = CalibratedColorClassifier()

    # Brick with solid green center and soft antialiased edge
    brick = np.zeros((20, 20, 3), dtype=np.uint8)
    # Antialiased perimeter (dark green / gray)
    brick[0:20, 0:2] = [20, 80, 25]
    brick[0:20, 18:20] = [20, 80, 25]
    # Solid green center
    brick[2:18, 2:18] = [35, 180, 45]

    color, conf = classifier.classify_brick_color(brick)
    assert color == RenkoColor.GREEN
    assert conf >= 0.70


def test_color_classifier_indicator_overlap():
    """Verify brick classification remains robust when an indicator line crosses it."""
    classifier = CalibratedColorClassifier()

    # Red brick with a 1-pixel blue or yellow line cutting through
    brick = np.full((20, 20, 3), (40, 40, 210), dtype=np.uint8)  # Red
    brick[10, :] = [255, 100, 0]  # Blue line cutting across

    color, conf = classifier.classify_brick_color(brick)
    # Majority density is still red (>90% of area)
    assert color == RenkoColor.RED
    assert conf > 0.85
