# plugins/trading_signals/validation/confidence_gate.py
"""
Mandatory Visual Confidence Gating.
Inhibits signal generation if any required component falls below the minimum threshold.
"""

from dataclasses import dataclass
import logging

from ..models.data_feed_types import FrameConfidence

logger = logging.getLogger("jarvis.trading.validation.confidence")


@dataclass(frozen=True)
class ConfidenceGateResult:
    """Result of confidence gating."""
    is_acceptable: bool
    composite_confidence: float
    reason: str


class ConfidenceGate:
    """
    Guards signal evaluation against low-confidence OCR, blurred captures, or ambiguous indicators.
    """

    def __init__(self, min_threshold: float = 0.85):
        self.min_threshold = max(0.50, min(1.0, float(min_threshold)))

    def evaluate(self, frame_confidence: FrameConfidence) -> ConfidenceGateResult:
        """
        Evaluates component-wise and composite visual confidences.
        """
        composite = frame_confidence.composite_confidence
        if composite < self.min_threshold:
            reasons = []
            if frame_confidence.index_price_conf < self.min_threshold:
                reasons.append(f"Index price conf={frame_confidence.index_price_conf:.2f}")
            if frame_confidence.option_price_conf < self.min_threshold:
                reasons.append(f"Option price conf={frame_confidence.option_price_conf:.2f}")
            if frame_confidence.index_supertrend_conf < self.min_threshold:
                reasons.append(f"Index ST conf={frame_confidence.index_supertrend_conf:.2f}")
            if frame_confidence.option_supertrend_conf < self.min_threshold:
                reasons.append(f"Option ST conf={frame_confidence.option_supertrend_conf:.2f}")
            if frame_confidence.ema_conf < self.min_threshold:
                reasons.append(f"EMA conf={frame_confidence.ema_conf:.2f}")
            if frame_confidence.donchian_conf < self.min_threshold:
                reasons.append(f"Donchian conf={frame_confidence.donchian_conf:.2f}")
            if frame_confidence.contract_text_conf < self.min_threshold:
                reasons.append(f"Contract text conf={frame_confidence.contract_text_conf:.2f}")
            if frame_confidence.layout_conf < self.min_threshold:
                reasons.append(f"Layout conf={frame_confidence.layout_conf:.2f}")

            detail = ", ".join(reasons)
            msg = f"Visual confidence {composite:.2f} < {self.min_threshold:.2f} threshold ({detail})."
            logger.debug("[CONFIDENCE_GATE_REJECT] %s", msg)
            return ConfidenceGateResult(is_acceptable=False, composite_confidence=composite, reason=msg)

        return ConfidenceGateResult(
            is_acceptable=True,
            composite_confidence=composite,
            reason=f"Confidence {composite:.2f} meets threshold {self.min_threshold:.2f}."
        )
