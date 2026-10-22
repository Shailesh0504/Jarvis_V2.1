# plugins/trading_signals/vision/__init__.py
"""Trading signal visual extraction components."""

from .color_classifier import CalibratedColorClassifier
from .detector import ChartRegionDetector, RectRegion, SegmentedChartLayout
from .renko_detector import RenkoVisualDetector, VisibleBrickContour, RenkoDetectionResult
from .donchian_verifier import DonchianChannelVerifier, DonchianVerificationResult
from .panel_detector import MultiPanelChartDetector, DetectedPanelBoundary
from .panel_extractor import PanelSemanticExtractor
from .extractor import ChartStateExtractor, FrameExtractionResult

__all__ = [
    "CalibratedColorClassifier",
    "ChartRegionDetector",
    "RectRegion",
    "SegmentedChartLayout",
    "RenkoVisualDetector",
    "VisibleBrickContour",
    "RenkoDetectionResult",
    "DonchianChannelVerifier",
    "DonchianVerificationResult",
    "ChartStateExtractor",
    "FrameExtractionResult",
    "MultiPanelChartDetector",
    "DetectedPanelBoundary",
    "PanelSemanticExtractor"
]
