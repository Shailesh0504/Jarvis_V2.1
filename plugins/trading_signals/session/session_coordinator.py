# plugins/trading_signals/session/session_coordinator.py
"""
Automated Trading Session Coordinator & Background Orchestrator.
Continuously coordinates window observation, silent session discovery,
automatic activation, pause/resume on window focus shifts, and instrument-switch resets.
"""

from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

try:
    import cv2
    import numpy as np
    from PIL import ImageGrab
except ImportError:
    cv2 = None
    np = None
    ImageGrab = None

try:
    import win32gui
except ImportError:
    win32gui = None

from ..models.chart_state import IndexChartState, OptionChartState, OptionType
from ..models.data_feed_types import DataFeedState, FrameConfidence
from ..models.panel_types import ChartPanelRole, TradingChartSet
from ..models.session_types import BrowserState, TradingSessionState
from ..models.signal_types import CandidateSignal, PositionState, SignalType
from ..session.panel_classifier import PanelRoleClassifier
from ..state.idempotency import SignalIdempotencyManager
from ..state.position_tracker import PositionStateTracker
from ..strategy.confluence_engine import ConfluenceSignalEngine
from ..strategy.exit_evaluator import ExitEvaluator
from ..validation.confidence_gate import ConfidenceGate
from ..validation.pair_validator import PairValidator
from ..vision.extractor import ChartStateExtractor
from ..vision.panel_detector import MultiPanelChartDetector
from ..vision.panel_extractor import PanelSemanticExtractor
from .chart_session import TradingChartSession
from .session_detector import SessionClassificationResult, TradingSessionDetector

logger = logging.getLogger("jarvis.trading.session.coordinator")


class SessionCoordinator(threading.Thread):
    """
    Background orchestrator providing human-like automated trading chart discovery.
    Silently activates, pauses, and revalidates chart sessions without requiring voice triggers.
    """

    def __init__(
        self,
        session_detector: Optional[TradingSessionDetector] = None,
        extractor: Optional[ChartStateExtractor] = None,
        confluence_engine: Optional[ConfluenceSignalEngine] = None,
        exit_evaluator: Optional[ExitEvaluator] = None,
        position_tracker: Optional[PositionStateTracker] = None,
        idempotency_manager: Optional[SignalIdempotencyManager] = None,
        pre_dispatch_validator: Optional[Callable[[CandidateSignal, IndexChartState, OptionChartState, FrameConfidence], bool]] = None,
        notification_dispatcher: Optional[Callable[[CandidateSignal], None]] = None,
        panel_detector: Optional[MultiPanelChartDetector] = None,
        panel_extractor: Optional[PanelSemanticExtractor] = None,
        panel_classifier: Optional[PanelRoleClassifier] = None,
        idle_poll_sec: float = 1.0,
        active_poll_sec: float = 0.5
    ):
        super().__init__(name="TradingSessionCoordinator", daemon=True)
        self.detector = session_detector or TradingSessionDetector()
        self.extractor = extractor or ChartStateExtractor()
        self.confluence_engine = confluence_engine or ConfluenceSignalEngine()
        self.tracker = position_tracker or PositionStateTracker()
        self.exit_evaluator = exit_evaluator or ExitEvaluator(position_tracker=self.tracker)
        self.idempotency = idempotency_manager or SignalIdempotencyManager()
        self.pair_validator = PairValidator()
        self.pre_dispatch_validator = pre_dispatch_validator
        self.notification_dispatcher = notification_dispatcher

        self.panel_detector = panel_detector or MultiPanelChartDetector()
        self.panel_extractor = panel_extractor or PanelSemanticExtractor()
        self.panel_classifier = panel_classifier or PanelRoleClassifier()
        self.last_chart_set: Optional[TradingChartSet] = None
        self._prev_ce_state: Optional[OptionChartState] = None
        self._prev_pe_state: Optional[OptionChartState] = None

        self.idle_poll_sec = max(0.5, float(idle_poll_sec))
        self.active_poll_sec = max(0.2, float(active_poll_sec))

        self.active_session: Optional[TradingChartSession] = None
        self._running = False
        self._stop_event = threading.Event()
        self._manual_pause = False
        self._prev_option_state: Optional[OptionChartState] = None

    def get_foreground_info(self) -> Tuple[int, str, str, bool]:
        """
        Retrieves current foreground HWND, window title, process name, and visibility.
        Uses Win32 if available; can be mocked or injected for tests.
        Returns: (hwnd, title, process_name, is_foreground)
        """
        if win32gui is None:
            return 0, "", "", False

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return 0, "", "", False

            if win32gui.IsIconic(hwnd):
                return hwnd, "", "", False

            title = win32gui.GetWindowText(hwnd).strip()

            # Process name
            pname = ""
            try:
                import ctypes
                from ctypes import wintypes
                import psutil
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pname = psutil.Process(pid.value).name().lower()
            except Exception:
                # Default inference from title if psutil unavailable
                if "chrome" in title.lower():
                    pname = "chrome"
                elif "brave" in title.lower():
                    pname = "brave"
                elif "edge" in title.lower():
                    pname = "edge"
                else:
                    pname = "browser"

            return hwnd, title, pname, True
        except Exception as e:
            logger.debug("[FOREGROUND_INSPECT_FAIL] %s", e)
            return 0, "", "", False

    def grab_screen_crop(self, hwnd: int) -> Optional["np.ndarray"]:
        """
        Captures the window client bounding box as a BGR NumPy array.
        """
        if ImageGrab is None or cv2 is None or np is None:
            return None

        bbox = None
        if win32gui is not None and hwnd:
            try:
                rect = win32gui.GetWindowRect(hwnd)
                # Filter out minimized or offscreen windows
                if rect[2] > rect[0] and rect[3] > rect[1]:
                    bbox = rect
            except Exception:
                bbox = None

        try:
            shot = ImageGrab.grab(bbox=bbox)
            rgb = np.array(shot)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            return bgr
        except Exception as e:
            logger.debug("[SCREEN_GRAB_FAIL] %s", e)
            return None

    def process_tick(
        self,
        mock_hwnd: Optional[int] = None,
        mock_title: Optional[str] = None,
        mock_process: Optional[str] = None,
        mock_frame: Optional["np.ndarray"] = None,
        mock_is_foreground: Optional[bool] = None
    ) -> TradingSessionState:
        """
        Executes a single discovery and evaluation cycle.
        Returns the current TradingSessionState.
        """
        # 1. Acquire current foreground state
        if mock_hwnd is not None:
            hwnd = mock_hwnd
            title = mock_title or ""
            proc = mock_process or ""
            is_fg = mock_is_foreground if mock_is_foreground is not None else True
        else:
            hwnd, title, proc, is_fg = self.get_foreground_info()

        # 2. Check manual pause override
        if self._manual_pause:
            if self.active_session:
                self.active_session.pause(reason="manual_pause")
            return TradingSessionState.PAUSED

        # 3. Handle window closed or focus loss
        if not hwnd:
            if self.active_session:
                self.active_session.invalidate("browser_window_closed")
                self.active_session = None
                self.tracker.on_data_feed_loss("browser_window_closed")
            return TradingSessionState.NO_SESSION

        if not is_fg:
            if self.active_session and self.active_session.is_active:
                self.active_session.pause(reason="window_minimized_or_unfocused")
                self.tracker.on_data_feed_loss("window_minimized_or_unfocused")
            return self.active_session.session_status if self.active_session else TradingSessionState.NO_SESSION

        # 4. Grab frame if active or candidate
        frame = mock_frame if mock_frame is not None else self.grab_screen_crop(hwnd)

        # 5. Classify foreground window
        classification: SessionClassificationResult = self.detector.inspect_session(
            hwnd=hwnd,
            process_name=proc,
            window_title=title,
            frame_bgr=frame,
            is_foreground=is_fg
        )

        # 6. Session Transition Logic
        if classification.session_state in (TradingSessionState.NO_SESSION, TradingSessionState.INVALID):
            if self.active_session and self.active_session.is_active:
                self.active_session.pause(reason=classification.details)
                self.tracker.on_data_feed_loss("navigated_away_from_chart")
                return TradingSessionState.PAUSED
            return classification.session_state

        if classification.session_state == TradingSessionState.PAUSED:
            if self.active_session:
                self.active_session.pause(reason=classification.details)
            return TradingSessionState.PAUSED

        # 7. Candidate or Active Session Establishment
        if classification.session_state == TradingSessionState.ACTIVE:
            # Check for existing session or create fresh
            if self.active_session is None:
                session_id = f"dhan_{classification.underlying}_{classification.strike}_{classification.option_type}_{int(time.time())}"
                self.active_session = TradingChartSession(
                    session_id=session_id,
                    browser_type=classification.browser_name,
                    hwnd=hwnd,
                    window_title=title,
                    chart_roi=classification.layout,
                    instrument_identity=classification.underlying,
                    index_chart_identity="NIFTY 50",
                    option_chart_identity=f"{classification.underlying} {classification.strike} {classification.option_type}",
                    strike=classification.strike,
                    expiry=classification.expiry,
                    option_type=classification.option_type,
                    session_status=TradingSessionState.ACTIVE
                )
                logger.info(
                    "[AUTO_SESSION_ACTIVATED] Automatically established session: %s %d %s on %s.",
                    classification.underlying,
                    classification.strike,
                    classification.option_type,
                    classification.browser_name
                )
            else:
                # Check for Instrument Switch (Strike change, CE -> PE, PE -> CE, Expiry change)
                if self.active_session.has_instrument_changed(
                    strike=classification.strike,
                    expiry=classification.expiry,
                    option_type=classification.option_type,
                    underlying=classification.underlying
                ):
                    # Invalidate all stale state: reset tracker to FLAT, clear idempotency, purge old states
                    self.active_session.reset_instrument(
                        strike=classification.strike,
                        expiry=classification.expiry,
                        option_type=classification.option_type,
                        underlying=classification.underlying
                    )
                    self.tracker.reset_to_flat(reason="instrument_switched")
                    self.idempotency.clear()
                    self._prev_option_state = None
                    logger.info(
                        "[INSTRUMENT_SWITCH_HANDLED] Stale breakouts, Renko events, and recommendation state purged."
                    )

                # If returning from PAUSED, resume
                if self.active_session.is_paused:
                    self.active_session.resume()
                    self.tracker.on_data_feed_restored()

            # 8. Strategy Evaluation on Active Frame
            if frame is not None:
                self._evaluate_active_frame(frame, self.active_session)

            return TradingSessionState.ACTIVE

        return classification.session_state

    def _evaluate_option_candidate(
        self,
        index_state: IndexChartState,
        option_state: OptionChartState,
        prev_option_state: Optional[OptionChartState],
        confidence: float,
        session: TradingChartSession
    ) -> None:
        """
        Evaluates a single option candidate against index state.
        Executes PairValidator -> ConfluenceEngine -> PreDispatchValidator -> NotificationDispatcher.
        """
        pair_check = self.pair_validator.validate(index_state, option_state)
        if not pair_check.is_valid:
            logger.debug("[PAIR_CHECK_FAIL] %s", pair_check.reason)
            return

        frame_conf = FrameConfidence(
            index_price_conf=confidence,
            option_price_conf=confidence,
            index_supertrend_conf=confidence,
            option_supertrend_conf=confidence,
            ema_conf=confidence,
            donchian_conf=confidence,
            contract_text_conf=confidence,
            layout_conf=confidence
        )

        # 1. Strategy Confluence Evaluation (BUY)
        if self.tracker.can_evaluate_buy():
            candidate = self.confluence_engine.evaluate_entry(
                index_state=index_state,
                option_state=option_state,
                previous_option_state=prev_option_state
            )
            if candidate and self.idempotency.can_dispatch(candidate):
                dispatch_ok = True
                if self.pre_dispatch_validator:
                    dispatch_ok = self.pre_dispatch_validator(
                        candidate,
                        index_state,
                        option_state,
                        frame_conf
                    )

                if dispatch_ok:
                    self.tracker.on_buy_signal_dispatched(candidate)
                    self.idempotency.record_dispatch(candidate)
                    if self.notification_dispatcher:
                        self.notification_dispatcher(candidate)
                else:
                    logger.warning("[PRE_DISPATCH_REJECTED] Candidate signal failed pre-dispatch revalidation.")

        # 2. Position-Aware Exit Evaluation
        elif self.tracker.can_evaluate_exit():
            # Only evaluate exit for active recommendation matching this option type
            if self.tracker.active_signal and self.tracker.active_signal.option_type == option_state.option_type.value:
                exit_res = self.exit_evaluator.evaluate_exit(
                    index_state=index_state,
                    option_state=option_state
                )
                if exit_res.is_exit and exit_res.candidate:
                    dispatch_ok = True
                    if self.pre_dispatch_validator:
                        dispatch_ok = self.pre_dispatch_validator(
                            exit_res.candidate,
                            index_state,
                            option_state,
                            frame_conf
                        )

                    if dispatch_ok:
                        self.tracker.on_exit_signal_dispatched(exit_res.candidate.exit_reason)
                        if self.notification_dispatcher:
                            self.notification_dispatcher(exit_res.candidate)
                    else:
                        logger.warning("[PRE_DISPATCH_REJECTED] Exit candidate signal failed pre-dispatch revalidation.")

    def _evaluate_active_frame(self, frame_bgr: "np.ndarray", session: TradingChartSession) -> None:
        """
        Extracts structured state and passes observation to the Strategy Engine.
        Supports multi-panel layout discovery with concurrent CE/PE evaluation,
        falling back to dual-pane ChartStateExtractor if needed.
        """
        # 1. Attempt Multi-Panel Layout Discovery
        chart_set: Optional[TradingChartSet] = None
        try:
            boundaries = self.panel_detector.detect_panels(frame_bgr)
            if boundaries and len(boundaries) >= 2:
                panels = [self.panel_extractor.extract_panel(frame_bgr, b) for b in boundaries]
                chart_set = self.panel_classifier.classify_chart_set(panels)
                self.last_chart_set = chart_set
        except Exception as e:
            logger.debug("[MULTI_PANEL_DISCOVERY_EXCEPTION] %s", e)
            chart_set = None

        if chart_set and chart_set.index_panel and (chart_set.ce_panels or chart_set.pe_panels):
            idx_p = chart_set.index_panel
            if not idx_p.is_valid_index_configuration():
                logger.warning("[INDEX_CONFIG_INVALID] %s. Inhibiting signal evaluation.", idx_p.validation_error)
                self.tracker.on_data_feed_loss(reason=f"index_config_invalid: {idx_p.validation_error}")
                return

            self.tracker.on_data_feed_restored()
            index_state = idx_p.to_index_chart_state()

            # Evaluate CE option panel if present
            ce_p = chart_set.get_primary_ce_panel()
            if ce_p:
                if ce_p.is_occluded:
                    logger.debug("[CE_PANEL_OCCLUDED] CE panel is occluded; CE signals inhibited.")
                elif not ce_p.is_valid_option_configuration():
                    logger.debug("[CE_CONFIG_INVALID] %s; CE signals inhibited.", ce_p.validation_error)
                else:
                    if session.has_panel_changed(ce_p.panel_id, ce_p.symbol, ce_p.strike, "CE", ce_p.expiry):
                        session.update_panel_contract(ce_p.panel_id, ce_p.symbol, ce_p.strike, "CE", ce_p.expiry)
                        self.tracker.reset_to_flat("ce_contract_switched")
                        self.idempotency.clear()
                        self._prev_ce_state = None
                    else:
                        session.update_panel_contract(ce_p.panel_id, ce_p.symbol, ce_p.strike, "CE", ce_p.expiry)

                    ce_state = ce_p.to_option_chart_state()
                    self._evaluate_option_candidate(index_state, ce_state, self._prev_ce_state, ce_p.confidence, session)
                    self._prev_ce_state = ce_state

            # Evaluate PE option panel if present
            pe_p = chart_set.get_primary_pe_panel()
            if pe_p:
                if pe_p.is_occluded:
                    logger.debug("[PE_PANEL_OCCLUDED] PE panel is occluded; PE signals inhibited.")
                elif not pe_p.is_valid_option_configuration():
                    logger.debug("[PE_CONFIG_INVALID] %s; PE signals inhibited.", pe_p.validation_error)
                else:
                    if session.has_panel_changed(pe_p.panel_id, pe_p.symbol, pe_p.strike, "PE", pe_p.expiry):
                        session.update_panel_contract(pe_p.panel_id, pe_p.symbol, pe_p.strike, "PE", pe_p.expiry)
                        self.tracker.reset_to_flat("pe_contract_switched")
                        self.idempotency.clear()
                        self._prev_pe_state = None
                    else:
                        session.update_panel_contract(pe_p.panel_id, pe_p.symbol, pe_p.strike, "PE", pe_p.expiry)

                    pe_state = pe_p.to_option_chart_state()
                    self._evaluate_option_candidate(index_state, pe_state, self._prev_pe_state, pe_p.confidence, session)
                    self._prev_pe_state = pe_state

            primary_opt = (
                ce_p.to_option_chart_state() if (ce_p and not ce_p.is_occluded and ce_p.is_valid_option_configuration())
                else (pe_p.to_option_chart_state() if (pe_p and not pe_p.is_occluded and pe_p.is_valid_option_configuration()) else None)
            )
            if primary_opt:
                session.last_validated_observation = (index_state, primary_opt)
            return

        # 2. Fallback to dual-pane ChartStateExtractor
        extraction = self.extractor.extract(frame_bgr)
        if extraction.data_feed_state != DataFeedState.LIVE_AND_VALID:
            self.tracker.on_data_feed_loss(reason=extraction.data_feed_state.value)
            return

        self.tracker.on_data_feed_restored()
        index_state = extraction.index_state
        option_state = extraction.option_state
        confidence = extraction.frame_confidence

        if not index_state or not option_state:
            return

        session.last_validated_observation = (index_state, option_state)

        # 2. Pair Validation
        pair_check = self.pair_validator.validate(index_state, option_state)
        if not pair_check.is_valid:
            logger.debug("[PAIR_CHECK_FAIL] %s", pair_check.reason)
            return

        # 3. Strategy Confluence Evaluation (BUY)
        if self.tracker.can_evaluate_buy():
            candidate = self.confluence_engine.evaluate_entry(
                index_state=index_state,
                option_state=option_state,
                previous_option_state=self._prev_option_state
            )
            if candidate and self.idempotency.can_dispatch(candidate):
                # Pre-Dispatch Revalidation Gate
                dispatch_ok = True
                if self.pre_dispatch_validator:
                    dispatch_ok = self.pre_dispatch_validator(
                        candidate,
                        index_state,
                        option_state,
                        confidence
                    )

                if dispatch_ok:
                    self.tracker.on_buy_signal_dispatched(candidate)
                    self.idempotency.record_dispatch(candidate)
                    if self.notification_dispatcher:
                        self.notification_dispatcher(candidate)
                else:
                    logger.warning("[PRE_DISPATCH_REJECTED] Candidate signal failed pre-dispatch revalidation.")

        # 4. Position-Aware Exit Evaluation
        elif self.tracker.can_evaluate_exit():
            exit_res = self.exit_evaluator.evaluate_exit(
                index_state=index_state,
                option_state=option_state
            )
            if exit_res.is_exit and exit_res.candidate:
                # Pre-Dispatch Revalidation Gate for Exit
                dispatch_ok = True
                if self.pre_dispatch_validator:
                    dispatch_ok = self.pre_dispatch_validator(
                        exit_res.candidate,
                        index_state,
                        option_state,
                        confidence
                    )

                if dispatch_ok:
                    self.tracker.on_exit_signal_dispatched(exit_res.candidate.exit_reason)
                    if self.notification_dispatcher:
                        self.notification_dispatcher(exit_res.candidate)
                else:
                    logger.warning("[PRE_DISPATCH_REJECTED] Exit candidate signal failed pre-dispatch revalidation.")

        self._prev_option_state = option_state

    @property
    def session_state(self) -> TradingSessionState:
        """Current authoritative trading session state."""
        if self._manual_pause:
            return TradingSessionState.PAUSED
        if self.active_session:
            return self.active_session.state
        return TradingSessionState.NO_SESSION

    @property
    def browser_state(self) -> BrowserState:
        """Current browser state based on foreground window."""
        hwnd, title, proc, is_fg = self.get_foreground_info()
        b_state, _ = self.detector.classify_browser(proc, is_foreground=is_fg)
        return b_state

    def get_session_info(self) -> Optional[Dict[str, Any]]:
        """Returns structured session metadata if an active session exists."""
        if not self.active_session:
            return None
        s = self.active_session
        info = {
            "session_id": s.session_id,
            "browser_type": s.browser_type,
            "browser_title": s.browser_title,
            "hwnd": s.hwnd,
            "state": s.state.value,
            "underlying": s.underlying,
            "strike": s.strike,
            "option_type": s.option_type,
            "expiry": s.expiry,
            "activated_at": s.activated_at,
            "last_seen_at": s.last_seen_at
        }
        if self.last_chart_set:
            info["layout_signature"] = self.last_chart_set.layout_signature
            info["discovered_panels_count"] = (
                (1 if self.last_chart_set.index_panel else 0)
                + len(self.last_chart_set.ce_panels)
                + len(self.last_chart_set.pe_panels)
                + len(self.last_chart_set.unknown_panels)
            )
            info["has_ce"] = len(self.last_chart_set.ce_panels) > 0
            info["has_pe"] = len(self.last_chart_set.pe_panels) > 0
        return info

    def pause_session(self, reason: str = "manual_pause") -> bool:
        """Manual voice override: pause analysis."""
        self._manual_pause = True
        if self.active_session:
            self.active_session.pause(reason=reason)
        return True

    def resume_session(self) -> bool:
        """Manual voice override: resume analysis."""
        self._manual_pause = False
        if self.active_session:
            self.active_session.resume()
        return True

    def analyze_this_chart(self) -> TradingSessionState:
        """Manual voice override: force immediate inspection of foreground chart."""
        self._manual_pause = False
        return self.process_tick()

    def run(self) -> None:
        """Main non-blocking discovery and observation thread."""
        self._running = True
        logger.info("[COORDINATOR_STARTED] Background automatic chart session discovery started.")

        while not self._stop_event.is_set():
            try:
                current_state = self.process_tick()
                # Adaptive sleep interval
                sleep_duration = self.active_poll_sec if current_state == TradingSessionState.ACTIVE else self.idle_poll_sec
                self._stop_event.wait(timeout=sleep_duration)
            except Exception as e:
                logger.error("[COORDINATOR_LOOP_ERROR] %s", e)
                self._stop_event.wait(timeout=1.0)

        self._running = False
        logger.info("[COORDINATOR_STOPPED] Background automatic chart session discovery stopped.")

    def stop(self) -> None:
        """Stops the coordinator thread cleanly."""
        self._stop_event.set()
