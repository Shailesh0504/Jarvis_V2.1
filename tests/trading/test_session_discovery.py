# tests/trading/test_session_discovery.py
"""
Automated Trading-Chart Session Discovery Test Suite (20 Scenarios).
Verifies automatic detection, silent background activation, window switches,
tab changes, instrument switching, manual overrides, and strategy preservation.
NO BROKER API, NO DHAN API, NO ORDER EXECUTION.
"""

import numpy as np
import pytest
import time
from unittest.mock import MagicMock, patch

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
from plugins.trading_signals.models.data_feed_types import DataFeedState, FrameConfidence
from plugins.trading_signals.models.session_types import BrowserState, TradingSessionState
from plugins.trading_signals.models.signal_types import (
    CandidateSignal,
    PositionState,
    SignalType
)
from plugins.trading_signals.session.chart_session import TradingChartSession
from plugins.trading_signals.session.session_coordinator import SessionCoordinator
from plugins.trading_signals.session.session_detector import SessionClassificationResult, TradingSessionDetector
from plugins.trading_signals.vision.detector import RectRegion, SegmentedChartLayout


# --- Helpers & Fixtures ---

def make_dummy_chart_image(width=1920, height=1080):
    """Creates a valid synthetic dual-pane frame."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = (20, 20, 20)
    frame[:, width // 2 - 2 : width // 2 + 2] = (100, 100, 100)
    return frame


def make_mock_layout(confidence=0.95):
    """Creates a mock SegmentedChartLayout with customizable confidence."""
    return SegmentedChartLayout(
        index_chart_region=RectRegion(x=0, y=0, w=960, h=1080),
        option_chart_region=RectRegion(x=960, y=0, w=960, h=1080),
        index_header_region=RectRegion(x=0, y=0, w=840, h=300),
        option_header_region=RectRegion(x=960, y=0, w=840, h=300),
        index_price_axis_region=RectRegion(x=840, y=0, w=120, h=1080),
        option_price_axis_region=RectRegion(x=1800, y=0, w=120, h=1080),
        index_canvas_region=RectRegion(x=0, y=300, w=840, h=780),
        option_canvas_region=RectRegion(x=960, y=300, w=840, h=780),
        confidence=confidence
    )


@pytest.fixture
def detector():
    return TradingSessionDetector()


@pytest.fixture
def mock_layout():
    return make_mock_layout(confidence=0.95)


# --- 1. Chrome + Dhan chart detected ---
def test_chrome_dhan_chart_detected(detector, mock_layout):
    b_state, proc = detector.classify_browser("chrome.exe", is_foreground=True)
    assert b_state == BrowserState.BROWSER_FOREGROUND
    assert proc == "chrome"

    title = "NIFTY 24500 CE - tv.dhan.co - Google Chrome"
    assert detector.is_dhan_title(title) is True

    frame = make_dummy_chart_image()
    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        result = detector.inspect_session(1001, "chrome", title, frame, is_foreground=True)
        assert result.browser_state == BrowserState.BROWSER_FOREGROUND
        assert result.session_state == TradingSessionState.ACTIVE
        assert result.is_dhan_page is True
        assert result.underlying == "NIFTY"
        assert result.strike == 24500
        assert result.option_type == "CE"
        assert result.confidence >= 0.85


# --- 2. Brave + Dhan chart detected ---
def test_brave_dhan_chart_detected(detector, mock_layout):
    b_state, proc = detector.classify_browser("brave.exe", is_foreground=True)
    assert b_state == BrowserState.BROWSER_FOREGROUND
    assert proc == "brave"

    title = "NIFTY 24600 PE - tv.dhan.co - Brave"
    assert detector.is_dhan_title(title) is True

    frame = make_dummy_chart_image()
    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        result = detector.inspect_session(1002, "brave", title, frame, is_foreground=True)
        assert result.browser_state == BrowserState.BROWSER_FOREGROUND
        assert result.session_state == TradingSessionState.ACTIVE
        assert result.is_dhan_page is True
        assert result.strike == 24600
        assert result.option_type == "PE"


# --- 3. Browser open but non-Dhan page ---
def test_browser_open_non_dhan_page(detector):
    title = "Google Search - Google Chrome"
    assert detector.is_dhan_title(title) is False

    frame = make_dummy_chart_image()
    result = detector.inspect_session(1003, "chrome", title, frame, is_foreground=True)
    assert result.session_state == TradingSessionState.NO_SESSION
    assert result.is_dhan_page is False
    assert result.layout is None


# --- 4. Dhan page but chart invalid (e.g. low visual confidence / single pane) ---
def test_dhan_page_chart_invalid(detector):
    title = "NIFTY 24500 CE - tv.dhan.co - Google Chrome"
    invalid_layout = make_mock_layout(confidence=0.40)
    frame = make_dummy_chart_image()
    with patch.object(detector.region_detector, "detect_layout", return_value=invalid_layout):
        result = detector.inspect_session(1004, "chrome", title, frame, is_foreground=True)
        assert result.is_dhan_page is True
        assert result.session_state == TradingSessionState.VALIDATING
        assert result.confidence < 0.85


# --- 5. Dhan chart valid -> automatic activation ---
def test_dhan_chart_valid_automatic_activation(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.ACTIVE
        assert coord.active_session is not None
        assert coord.active_session.underlying == "NIFTY"
        assert coord.active_session.strike == 24500
        assert coord.active_session.option_type == "CE"


# --- 6. Alt+Tab away -> pause/invalidate ---
def test_alttab_away_pauses_session(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    # Step 1: Active session on Chrome
    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        assert coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        ) == TradingSessionState.ACTIVE

    # Step 2: Alt+Tab away to Notepad
    state = coord.process_tick(
        mock_hwnd=2002,
        mock_title="Untitled - Notepad",
        mock_process="notepad",
        mock_frame=None,
        mock_is_foreground=True
    )
    assert state == TradingSessionState.PAUSED
    assert coord.active_session.state == TradingSessionState.PAUSED


# --- 7. Return to Dhan -> fresh revalidation ---
def test_return_to_dhan_fresh_revalidation(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        # 1. Establish active
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )

        # 2. Alt+Tab away -> Paused
        coord.process_tick(
            mock_hwnd=2002,
            mock_title="Untitled - Notepad",
            mock_process="notepad",
            mock_frame=None,
            mock_is_foreground=True
        )
        assert coord.session_state == TradingSessionState.PAUSED

        # 3. Return to Dhan -> Fresh revalidation tick
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.ACTIVE
        assert coord.active_session.state == TradingSessionState.ACTIVE


# --- 8. Tab changes from Dhan to another site ---
def test_tab_changes_from_dhan_to_another_site(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.session_state == TradingSessionState.ACTIVE

    # Switch tab to YouTube on same chrome hwnd
    state = coord.process_tick(
        mock_hwnd=1001,
        mock_title="YouTube - Google Chrome",
        mock_process="chrome",
        mock_frame=frame,
        mock_is_foreground=True
    )
    assert state in (TradingSessionState.PAUSED, TradingSessionState.NO_SESSION)


# --- 9. Strike change -> instrument reset ---
def test_strike_change_instrument_reset(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.active_session.strike == 24500

        # User switches strike to 24600 CE
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24600 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.ACTIVE
        assert coord.active_session.strike == 24600
        assert coord.tracker.state == PositionState.FLAT


# --- 10. CE -> PE change -> stale breakout purged ---
def test_ce_to_pe_change_purges_stale_breakout(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        coord.tracker.state = PositionState.JARVIS_SIGNAL_ACTIVE

        # Switch to PE
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 PE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.active_session.option_type == "PE"
        assert coord.tracker.state == PositionState.FLAT


# --- 11. PE -> CE change -> stale breakout purged ---
def test_pe_to_ce_change_purges_stale_breakout(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 PE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        coord.tracker.state = PositionState.JARVIS_SIGNAL_ACTIVE

        # Switch to CE
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.active_session.option_type == "CE"
        assert coord.tracker.state == PositionState.FLAT


# --- 12. Expiry change -> reset ---
def test_expiry_change_resets_session(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE 28-AUG-2026 - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.active_session.expiry == "28-AUG-2026"

        # Changed expiry to 04-SEP-2026
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE 04-SEP-2026 - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.active_session.expiry == "04-SEP-2026"
        assert coord.tracker.state == PositionState.FLAT


# --- 13. Browser closed -> session closed ---
def test_browser_closed_closes_session(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.session_state == TradingSessionState.ACTIVE

    # Close browser (HWND 0 or invalid)
    state = coord.process_tick(
        mock_hwnd=0,
        mock_title="",
        mock_process="",
        mock_frame=None,
        mock_is_foreground=False
    )
    assert state == TradingSessionState.NO_SESSION
    assert coord.active_session is None


# --- 14. Stale screenshot -> rejected ---
def test_stale_screenshot_rejected(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=None,  # Missing or corrupt frame
            mock_is_foreground=True
        )
        # Without frame, remains in TRADING_PAGE_DETECTED or PAUSED
        assert state in (TradingSessionState.TRADING_PAGE_DETECTED, TradingSessionState.PAUSED)
        assert coord.active_session is None


# --- 15. Ambiguous chart identity -> stay in validating ---
def test_ambiguous_chart_identity_stays_in_validating(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    # Title has tv.dhan.co but missing option strike/type
    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="tv.dhan.co / Multi Chart View - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.VALIDATING
        assert coord.active_session is None


# --- 16. Low visual confidence -> invalid session / validating ---
def test_low_visual_confidence_stays_validating(detector):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()
    low_conf_layout = make_mock_layout(confidence=0.60)

    with patch.object(detector.region_detector, "detect_layout", return_value=low_conf_layout):
        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.VALIDATING
        assert coord.active_session is None


# --- 17. Duplicate activation prevention ---
def test_duplicate_activation_prevention(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        state1 = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        sess1 = coord.active_session
        assert state1 == TradingSessionState.ACTIVE

        # Second tick with identical window
        state2 = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state2 == TradingSessionState.ACTIVE
        assert coord.active_session is sess1  # Must preserve existing session instance


# --- 18. Manual stop / pause ---
def test_manual_stop_pause(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert coord.session_state == TradingSessionState.ACTIVE

    coord.pause_session(reason="user_voice_override")
    assert coord.session_state == TradingSessionState.PAUSED
    assert coord._manual_pause is True


# --- 19. Manual resume ---
def test_manual_resume(detector, mock_layout):
    coord = SessionCoordinator(session_detector=detector)
    frame = make_dummy_chart_image()

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout):
        coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        coord.pause_session(reason="user_voice_override")
        assert coord.session_state == TradingSessionState.PAUSED

        coord.resume_session()
        assert coord._manual_pause is False
        assert coord.session_state == TradingSessionState.ACTIVE


# --- 20. Existing Revision 4 strategy remains unchanged ---
def test_existing_revision_4_strategy_remains_unchanged(detector, mock_layout):
    """
    Verifies that under active session, visual extraction feeds into confluence engine
    and pre-dispatch gate, generating candidate signal without broker execution.
    """
    dispatched_signals = []
    coord = SessionCoordinator(
        session_detector=detector,
        notification_dispatcher=lambda sig: dispatched_signals.append(sig),
        pre_dispatch_validator=lambda cand, idx, opt, conf: True
    )

    frame = make_dummy_chart_image()

    mock_index = IndexChartState(
        underlying="NIFTY",
        current_price=24550.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.NO_FLIP,
        ema_bias=SuperTrendBias.BULLISH,
        brick_sequence_id=10,
        last_trigger_brick_id=10,
        is_valid=True
    )
    mock_option = OptionChartState(
        underlying="NIFTY",
        strike=24500,
        option_type=OptionType.CE,
        current_price=160.0,
        renko_color=RenkoColor.GREEN,
        brick_status=BrickStatus.CLOSED,
        renko_transition=RenkoTransition.NO_TRANSITION,
        supertrend_bias=SuperTrendBias.BULLISH,
        supertrend_flip=SuperTrendFlip.BULLISH_FLIP,
        donchian_upper=150.0,
        donchian_basis=125.0,
        donchian_lower=100.0,
        previous_price=140.0,
        previous_donchian_upper=150.0,
        donchian_breakout_event=True,
        brick_sequence_id=20,
        is_valid=True
    )

    extraction_mock = MagicMock()
    extraction_mock.data_feed_state = DataFeedState.LIVE_AND_VALID
    extraction_mock.index_state = mock_index
    extraction_mock.option_state = mock_option
    extraction_mock.frame_confidence = FrameConfidence(layout_conf=0.95)

    with patch.object(detector.region_detector, "detect_layout", return_value=mock_layout), \
         patch.object(coord.extractor, "extract", return_value=extraction_mock), \
         patch.object(coord, "grab_screen_crop", return_value=frame):

        state = coord.process_tick(
            mock_hwnd=1001,
            mock_title="NIFTY 24500 CE - tv.dhan.co - Google Chrome",
            mock_process="chrome",
            mock_frame=frame,
            mock_is_foreground=True
        )
        assert state == TradingSessionState.ACTIVE

        # Evaluate one active tick
        coord._evaluate_active_frame(frame, coord.active_session)

        assert len(dispatched_signals) == 1
        sig = dispatched_signals[0]
        assert sig.signal_type == SignalType.BUY
        assert sig.option_type in (OptionType.CE, "CE")
        assert sig.strike == 24500
        assert coord.tracker.state == PositionState.JARVIS_SIGNAL_ACTIVE
