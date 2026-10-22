# tests/trading/test_multi_panel_discovery.py
"""
Multi-Panel Dhan / TradingView Chart Understanding Test Suite (18 Scenarios).
Validates dynamic multi-panel discovery, role classification without coordinate assumptions,
strict panel boundary isolation, independent CE/PE evaluation, configuration validation,
ambiguity rejection, and contract-switch invalidation.
STRICTLY SCREEN-ONLY: NO BROKER API, NO DHAN API, NO ORDER EXECUTION.
"""

import numpy as np
import pytest
import time
from unittest.mock import MagicMock

from plugins.trading_signals.models.chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)
from plugins.trading_signals.models.panel_types import (
    ChartPanel,
    ChartPanelRole,
    InstrumentType,
    TradingChartSet
)
from plugins.trading_signals.models.session_types import TradingSessionState
from plugins.trading_signals.models.signal_types import CandidateSignal, PositionState, SignalType
from plugins.trading_signals.session.chart_session import TradingChartSession
from plugins.trading_signals.session.panel_classifier import PanelRoleClassifier
from plugins.trading_signals.session.session_coordinator import SessionCoordinator
from plugins.trading_signals.state.position_tracker import PositionStateTracker
from plugins.trading_signals.strategy.confluence_engine import ConfluenceSignalEngine, StrategyTriggerMode
from plugins.trading_signals.vision.detector import RectRegion
from plugins.trading_signals.vision.panel_detector import DetectedPanelBoundary, MultiPanelChartDetector
from plugins.trading_signals.vision.panel_extractor import PanelSemanticExtractor


# --- Test Fixtures & Builders ---

def make_test_frame(w=1920, h=1080):
    """Creates a synthetic BGR frame with subtle textures so it is not marked occluded."""
    frame = np.full((h, w, 3), 25, dtype=np.uint8)
    # Add grid lines and gradients to give non-zero variance
    for y in range(0, h, 40):
        frame[y : y + 2, :] = 40
    for x in range(0, w, 40):
        frame[:, x : x + 2] = 40
    return frame


def make_boundary(idx, x, y, w, h):
    """Builds a DetectedPanelBoundary with proportional subregions."""
    reg = RectRegion(x, y, w, h)
    hdr_h = int(h * 0.25)
    axis_w = int(w * 0.12)
    time_h = int(h * 0.06)
    return DetectedPanelBoundary(
        panel_index=idx,
        region=reg,
        header_region=RectRegion(x, y, w - axis_w, hdr_h),
        canvas_region=RectRegion(x, y + hdr_h, w - axis_w, h - hdr_h - time_h),
        price_axis_region=RectRegion(x + w - axis_w, y, axis_w, h),
        time_axis_region=RectRegion(x, y + h - time_h, w - axis_w, time_h),
        confidence=1.0
    )


# ==============================================================================
# 1. Reference Screenshot Layout (Left Index, Top-Right CE, Bottom-Right PE)
# ==============================================================================
def test_reference_screenshot_layout_index_ce_pe():
    frame = make_test_frame(1920, 1080)
    # Left Index panel: x=50, y=100, w=900, h=900
    # Top-Right CE panel: x=960, y=100, w=900, h=440
    # Bottom-Right PE panel: x=960, y=550, w=900, h=450
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_ce = make_boundary(1, 960, 100, 900, 440)
    b_pe = make_boundary(2, 960, 550, 900, 450)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {
            "header_text": "NIFTY 50 · 1D · NSE · Renko [Traditional, 10] · SuperTrend 1, 2.1 · EMA 20 close 0",
            "current_price": 24550.0,
            "supertrend_value": 24400.0,
            "supertrend_bias": SuperTrendBias.BULLISH
        },
        "panel_1": {
            "header_text": "NIFTY 08 SEP 23850 CALL · 5s · NSE · Renko [Traditional, 3] · SuperTrend 1, 2.1 · DC 9, 0",
            "strike": 23850,
            "expiry": "08 SEP",
            "current_price": 130.0,
            "supertrend_value": 110.0,
            "donchian_upper": 125.0
        },
        "panel_2": {
            "header_text": "NIFTY 08 SEP 23900 PUT · 5s · NSE · Renko [Traditional, 3] · SuperTrend 1, 2.1 · DC 9, 0",
            "strike": 23900,
            "expiry": "08 SEP",
            "current_price": 95.0,
            "supertrend_value": 115.0,
            "donchian_upper": 120.0
        }
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_ce, mock_ocr)
    p2 = extractor.extract_panel(frame, b_pe, mock_ocr)

    assert p0.role == ChartPanelRole.INDEX_CHART
    assert p0.is_valid_index_configuration()
    assert p1.role == ChartPanelRole.OPTION_CE_CHART
    assert p1.is_valid_option_configuration()
    assert p2.role == ChartPanelRole.OPTION_PE_CHART
    assert p2.is_valid_option_configuration()

    chart_set = classifier.classify_chart_set([p0, p1, p2])
    assert chart_set.layout_signature == "1_INDEX+1_CE+1_PE"
    assert chart_set.is_valid_for_ce()
    assert chart_set.is_valid_for_pe()
    assert chart_set.get_primary_ce_panel().strike == 23850
    assert chart_set.get_primary_pe_panel().strike == 23900


# ==============================================================================
# 2. Single Option Layout: Index + CE Only
# ==============================================================================
def test_single_option_layout_index_ce_only():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_ce = make_boundary(1, 960, 100, 900, 900)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · NSE · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 08 SEP 24000 CE · 5s · NSE · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_ce, mock_ocr)
    chart_set = classifier.classify_chart_set([p0, p1])

    assert chart_set.layout_signature == "1_INDEX+1_CE+0_PE"
    assert chart_set.is_valid_for_ce()
    assert not chart_set.is_valid_for_pe()
    assert chart_set.get_primary_ce_panel() is not None
    assert chart_set.get_primary_pe_panel() is None


# ==============================================================================
# 3. Single Option Layout: Index + PE Only
# ==============================================================================
def test_single_option_layout_index_pe_only():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_pe = make_boundary(1, 960, 100, 900, 900)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · NSE · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 08 SEP 24000 PE · 5s · NSE · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_pe, mock_ocr)
    chart_set = classifier.classify_chart_set([p0, p1])

    assert chart_set.layout_signature == "1_INDEX+0_CE+1_PE"
    assert not chart_set.is_valid_for_ce()
    assert chart_set.is_valid_for_pe()


# ==============================================================================
# 4. Swapped Positions: CE at Bottom, PE at Top (Zero Coordinate Assumption)
# ==============================================================================
def test_swapped_positions_ce_bottom_pe_top():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    # Swapped: panel 1 at top is PE, panel 2 at bottom is CE
    b_pe_top = make_boundary(1, 960, 100, 900, 440)
    b_ce_bot = make_boundary(2, 960, 550, 900, 450)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · NSE · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 08 SEP 23900 PUT · 5s · NSE · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 08 SEP 23850 CALL · 5s · NSE · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_pe_top, mock_ocr)
    p2 = extractor.extract_panel(frame, b_ce_bot, mock_ocr)

    assert p1.role == ChartPanelRole.OPTION_PE_CHART
    assert p2.role == ChartPanelRole.OPTION_CE_CHART

    chart_set = classifier.classify_chart_set([p0, p1, p2])
    assert chart_set.get_primary_pe_panel().strike == 23900
    assert chart_set.get_primary_ce_panel().strike == 23850


# ==============================================================================
# 5. Swapped Positions: Index on Right, CE on Left (Zero Coordinate Assumption)
# ==============================================================================
def test_swapped_positions_index_on_right():
    frame = make_test_frame(1920, 1080)
    # Left pane is CE, Right pane is Index
    b_ce_left = make_boundary(0, 50, 100, 900, 900)
    b_idx_right = make_boundary(1, 960, 100, 900, 900)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 08 SEP 24100 CALL · 5s · NSE · Renko [Traditional, 3]"},
        "panel_1": {"header_text": "NIFTY 50 · 1D · NSE · Renko [Traditional, 10]"}
    }

    p0 = extractor.extract_panel(frame, b_ce_left, mock_ocr)
    p1 = extractor.extract_panel(frame, b_idx_right, mock_ocr)

    assert p0.role == ChartPanelRole.OPTION_CE_CHART
    assert p1.role == ChartPanelRole.INDEX_CHART

    chart_set = classifier.classify_chart_set([p0, p1])
    assert chart_set.index_panel.role == ChartPanelRole.INDEX_CHART
    assert chart_set.get_primary_ce_panel().strike == 24100


# ==============================================================================
# 6. Resized / Unequal Split Panels (60% Index, 40% Options)
# ==============================================================================
def test_resized_unequal_split_panels():
    frame = make_test_frame(1920, 1080)
    idx_w = int(1920 * 0.60)
    opt_w = int(1920 * 0.38)
    b_idx = make_boundary(0, 20, 100, idx_w, 900)
    b_ce = make_boundary(1, idx_w + 30, 100, opt_w, 440)
    b_pe = make_boundary(2, idx_w + 30, 560, opt_w, 440)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 24500 CE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 24500 PE · 5s · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_ce, mock_ocr)
    p2 = extractor.extract_panel(frame, b_pe, mock_ocr)

    # Verify no cross-panel pixel bleed in canvas regions
    assert p0.canvas_region.right <= b_idx.region.right
    assert p1.canvas_region.x >= b_ce.region.x
    assert p1.canvas_region.bottom <= b_ce.region.bottom

    chart_set = classifier.classify_chart_set([p0, p1, p2])
    assert chart_set.layout_signature == "1_INDEX+1_CE+1_PE"


# ==============================================================================
# 7. Different Panel Dimensions (720p vs 1080p Resolution Tolerance)
# ==============================================================================
def test_different_panel_dimensions_1080p_vs_720p():
    frame_720 = make_test_frame(1280, 720)
    b_idx = make_boundary(0, 30, 60, 600, 620)
    b_ce = make_boundary(1, 650, 60, 600, 620)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 24000 CE · 5s · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame_720, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame_720, b_ce, mock_ocr)

    assert p0.confidence >= 0.85
    assert p1.confidence >= 0.85
    chart_set = classifier.classify_chart_set([p0, p1])
    assert chart_set.is_valid_for_ce()


# ==============================================================================
# 8. 3-Column Layout
# ==============================================================================
def test_3_column_layout():
    frame = make_test_frame(1920, 1080)
    col_w = 600
    b0 = make_boundary(0, 20, 100, col_w, 900)
    b1 = make_boundary(1, 640, 100, col_w, 900)
    b2 = make_boundary(2, 1260, 100, col_w, 900)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 24200 CE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 24200 PE · 5s · Renko [Traditional, 3]"}
    }

    panels = [extractor.extract_panel(frame, b, mock_ocr) for b in (b0, b1, b2)]
    chart_set = classifier.classify_chart_set(panels)

    assert chart_set.layout_signature == "1_INDEX+1_CE+1_PE"
    assert chart_set.is_valid_for_ce()
    assert chart_set.is_valid_for_pe()


# ==============================================================================
# 9. 4-Grid Layout (2x2 with an Equity Chart)
# ==============================================================================
def test_4_grid_layout_2x2():
    frame = make_test_frame(1920, 1080)
    b0 = make_boundary(0, 50, 100, 900, 440)     # Top-Left: Index
    b1 = make_boundary(1, 960, 100, 900, 440)    # Top-Right: CE
    b2 = make_boundary(2, 50, 550, 900, 450)     # Bottom-Left: PE
    b3 = make_boundary(3, 960, 550, 900, 450)    # Bottom-Right: RELIANCE

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 24300 CE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 24300 PE · 5s · Renko [Traditional, 3]"},
        "panel_3": {"header_text": "RELIANCE · 5 · NSE · Candles"}
    }

    panels = [extractor.extract_panel(frame, b, mock_ocr) for b in (b0, b1, b2, b3)]
    chart_set = classifier.classify_chart_set(panels)

    assert chart_set.index_panel is not None
    assert len(chart_set.ce_panels) == 1
    assert len(chart_set.pe_panels) == 1
    assert len(chart_set.unknown_panels) == 1
    assert chart_set.unknown_panels[0].symbol == "UNKNOWN" or chart_set.unknown_panels[0].instrument_type == InstrumentType.UNKNOWN


# ==============================================================================
# 10. Partially Occluded Panel Inhibits Only That Option
# ==============================================================================
def test_partially_occluded_panel_inhibits_only_that_option():
    frame = make_test_frame(1920, 1080)
    # Paint CE panel region with solid black to simulate overlay popup / occlusion
    frame[100:540, 960:1860] = 0

    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_ce = make_boundary(1, 960, 100, 900, 440)
    b_pe = make_boundary(2, 960, 550, 900, 450)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 24000 CE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 24000 PE · 5s · Renko [Traditional, 3]"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_ce, mock_ocr)
    p2 = extractor.extract_panel(frame, b_pe, mock_ocr)

    assert p1.is_occluded
    assert p1.confidence == 0.0
    assert not p2.is_occluded

    chart_set = classifier.classify_chart_set([p0, p1, p2])
    assert not chart_set.is_valid_for_ce()
    assert chart_set.is_valid_for_pe()


# ==============================================================================
# 11. Unreadable Panel Header Ambiguity Rejection
# ==============================================================================
def test_unreadable_panel_header_ambiguity_rejection():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_corrupt = make_boundary(1, 960, 100, 900, 900)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "### ??? &&& NO_HEADER_READABLE"}
    }

    p0 = extractor.extract_panel(frame, b_idx, mock_ocr)
    p1 = extractor.extract_panel(frame, b_corrupt, mock_ocr)

    assert p1.role == ChartPanelRole.UNKNOWN_CHART
    chart_set = classifier.classify_chart_set([p0, p1])
    assert not chart_set.is_valid_for_ce()
    assert not chart_set.is_valid_for_pe()
    assert len(chart_set.unknown_panels) == 1


# ==============================================================================
# 12. Incorrect Strike Validation
# ==============================================================================
def test_incorrect_strike_validation():
    frame = make_test_frame(1920, 1080)
    b_ce = make_boundary(0, 960, 100, 900, 900)
    extractor = PanelSemanticExtractor()

    # Missing strike
    mock_ocr = {
        "panel_0": {"header_text": "NIFTY CALL · 5s · Renko [Traditional, 3]"}
    }
    p_bad = extractor.extract_panel(frame, b_ce, mock_ocr)
    assert not p_bad.is_valid_option_configuration()
    assert "strike" in p_bad.validation_error.lower()


# ==============================================================================
# 13. Changed Expiry Resets Session
# ==============================================================================
def test_changed_expiry_resets_session():
    session = TradingChartSession(session_id="s1", instrument_identity="NIFTY", strike=24000, option_type="CE", expiry="08 SEP")
    session.update_panel_contract("panel_1", "NIFTY", 24000, "CE", "08 SEP")

    # Has expiry changed?
    assert not session.has_panel_changed("panel_1", "NIFTY", 24000, "CE", "08 SEP")
    assert session.has_panel_changed("panel_1", "NIFTY", 24000, "CE", "15 SEP")

    # Update contract
    session.update_panel_contract("panel_1", "NIFTY", 24000, "CE", "15 SEP")
    assert session.ce_expiry == "15 SEP"


# ==============================================================================
# 14. Duplicate CE Panels Rejected as Ambiguous
# ==============================================================================
def test_duplicate_ce_panels_rejected_as_ambiguous():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_ce1 = make_boundary(1, 960, 100, 900, 440)
    b_ce2 = make_boundary(2, 960, 550, 900, 450)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 23850 CE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 23900 CE · 5s · Renko [Traditional, 3]"}
    }

    panels = [extractor.extract_panel(frame, b, mock_ocr) for b in (b_idx, b_ce1, b_ce2)]
    chart_set = classifier.classify_chart_set(panels)

    assert len(chart_set.ce_panels) == 2
    assert not chart_set.is_valid_for_ce()
    assert any("duplicate ce" in reason.lower() for reason in chart_set.ambiguity_reasons)


# ==============================================================================
# 15. Duplicate PE Panels Rejected as Ambiguous
# ==============================================================================
def test_duplicate_pe_panels_rejected_as_ambiguous():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_pe1 = make_boundary(1, 960, 100, 900, 440)
    b_pe2 = make_boundary(2, 960, 550, 900, 450)

    extractor = PanelSemanticExtractor()
    classifier = PanelRoleClassifier()

    mock_ocr = {
        "panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10]"},
        "panel_1": {"header_text": "NIFTY 23850 PE · 5s · Renko [Traditional, 3]"},
        "panel_2": {"header_text": "NIFTY 23900 PE · 5s · Renko [Traditional, 3]"}
    }

    panels = [extractor.extract_panel(frame, b, mock_ocr) for b in (b_idx, b_pe1, b_pe2)]
    chart_set = classifier.classify_chart_set(panels)

    assert len(chart_set.pe_panels) == 2
    assert not chart_set.is_valid_for_pe()
    assert any("duplicate pe" in reason.lower() for reason in chart_set.ambiguity_reasons)


# ==============================================================================
# 16. Instrument Switch on Single Panel
# ==============================================================================
def test_instrument_switch_on_single_panel():
    session = TradingChartSession(session_id="s1", instrument_identity="NIFTY", strike=23850, option_type="CE", expiry="08 SEP")
    session.update_panel_contract("panel_1", "NIFTY", 23850, "CE", "08 SEP")

    # Panel switches from CE to PE
    assert session.has_panel_changed("panel_1", "NIFTY", 23850, "PE", "08 SEP")

    # Panel switches strike
    assert session.has_panel_changed("panel_1", "NIFTY", 24000, "CE", "08 SEP")


# ==============================================================================
# 17. Strategy Configuration Validation Rejection (Section 8)
# ==============================================================================
def test_strategy_configuration_validation_rejection():
    frame = make_test_frame(1920, 1080)
    extractor = PanelSemanticExtractor()

    # Index with invalid Renko size (5 instead of 10)
    b0 = make_boundary(0, 50, 100, 900, 900)
    p_idx_bad_renko = extractor.extract_panel(
        frame, b0,
        {"panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 5] · SuperTrend 1, 2.1 · EMA 20 close 0"}}
    )
    assert not p_idx_bad_renko.is_valid_index_configuration()
    assert "renko brick size" in p_idx_bad_renko.validation_error.lower()

    # Index with invalid SuperTrend (2, 3 instead of 1, 2.1)
    p_idx_bad_st = extractor.extract_panel(
        frame, b0,
        {"panel_0": {"header_text": "NIFTY 50 · 1D · Renko [Traditional, 10] · SuperTrend 2, 3.0 · EMA 20 close 0"}}
    )
    assert not p_idx_bad_st.is_valid_index_configuration()
    assert "supertrend" in p_idx_bad_st.validation_error.lower()

    # Option with invalid Donchian (20 instead of 9, 0)
    b1 = make_boundary(1, 960, 100, 900, 900)
    p_opt_bad_dc = extractor.extract_panel(
        frame, b1,
        {"panel_1": {"header_text": "NIFTY 24000 CE · 5s · Renko [Traditional, 3] · SuperTrend 1, 2.1 · DC 20, 0"}}
    )
    assert not p_opt_bad_dc.is_valid_option_configuration()
    assert "donchian" in p_opt_bad_dc.validation_error.lower()


# ==============================================================================
# 18. Concurrent CE/PE Strategy Evaluation (Both Candidates Tested Independently)
# ==============================================================================
def test_concurrent_ce_pe_strategy_evaluation():
    frame = make_test_frame(1920, 1080)
    b_idx = make_boundary(0, 50, 100, 900, 900)
    b_ce = make_boundary(1, 960, 100, 900, 440)
    b_pe = make_boundary(2, 960, 550, 900, 450)

    # Bullish scenario: Index bullish, CE has fresh Donchian breakout
    mock_ocr_bullish = {
        "panel_0": {
            "header_text": "NIFTY 50 · 1D · Renko [Traditional, 10] · SuperTrend 1, 2.1 · EMA 20 close 0",
            "current_price": 24550.0,
            "supertrend_value": 24400.0,
            "supertrend_bias": SuperTrendBias.BULLISH,
            "renko_brick_color": RenkoColor.GREEN,
            "renko_brick_state": BrickStatus.CLOSED,
            "renko_transition": RenkoTransition.NO_TRANSITION
        },
        "panel_1": {
            "header_text": "NIFTY 08 SEP 23850 CALL · 5s · Renko [Traditional, 3] · SuperTrend 1, 2.1 · DC 9, 0",
            "strike": 23850,
            "expiry": "08 SEP",
            "current_price": 130.0,
            "previous_price": 118.0,
            "donchian_upper": 120.0,
            "previous_donchian_upper": 120.0,
            "supertrend_value": 110.0,
            "supertrend_bias": SuperTrendBias.BULLISH,
            "renko_brick_color": RenkoColor.GREEN,
            "renko_brick_state": BrickStatus.CLOSED,
            "renko_transition": RenkoTransition.RED_TO_GREEN,
            "donchian_breakout_event": True
        },
        "panel_2": {
            "header_text": "NIFTY 08 SEP 23900 PUT · 5s · Renko [Traditional, 3] · SuperTrend 1, 2.1 · DC 9, 0",
            "strike": 23900,
            "expiry": "08 SEP",
            "current_price": 95.0,
            "previous_price": 105.0,
            "donchian_upper": 120.0,
            "supertrend_value": 115.0,
            "supertrend_bias": SuperTrendBias.BEARISH,
            "renko_brick_color": RenkoColor.RED,
            "renko_brick_state": BrickStatus.CLOSED,
            "donchian_breakout_event": False
        }
    }

    panel_detector = MultiPanelChartDetector()
    panel_detector.detect_panels = MagicMock(return_value=[b_idx, b_ce, b_pe])

    panel_extractor = PanelSemanticExtractor()
    original_extract = panel_extractor.extract_panel
    panel_extractor.extract_panel = lambda f, b: original_extract(f, b, mock_ocr_bullish)

    confluence_engine = ConfluenceSignalEngine(trigger_mode=StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD)
    tracker = PositionStateTracker()
    dispatched_signals = []

    coordinator = SessionCoordinator(
        panel_detector=panel_detector,
        panel_extractor=panel_extractor,
        confluence_engine=confluence_engine,
        position_tracker=tracker,
        notification_dispatcher=lambda sig: dispatched_signals.append(sig),
        pre_dispatch_validator=lambda cand, idx, opt, conf: True
    )

    session = TradingChartSession(
        session_id="test_sess",
        instrument_identity="NIFTY",
        strike=23850,
        option_type="CE",
        session_status=TradingSessionState.ACTIVE
    )
    coordinator.active_session = session

    # Process frame
    coordinator._evaluate_active_frame(frame, session)

    # In Bullish regime, CE BUY signal should be generated and dispatched
    assert len(dispatched_signals) == 1
    sig = dispatched_signals[0]
    assert sig.option_type == "CE"
    assert sig.strike == 23850
    assert tracker.state == PositionState.JARVIS_SIGNAL_ACTIVE
