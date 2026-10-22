# plugins/trading_signals/plugin.py
"""
Screen-Only Live Options Signal Engine Plugin for Jarvis V2.1.
NIFTY Index + Selected Option Confluence Decision Support.
Strictly Signal-Only: No broker API, no hidden order execution, no auto-trading code.
"""

import logging
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .gate.pre_dispatch_gate import PreDispatchRevalidationGate
from .manifest import MANIFEST
from .models.chart_state import IndexChartState, OptionChartState
from .models.data_feed_types import DataFeedState, FrameConfidence
from .models.session_types import BrowserState, TradingSessionState
from .models.signal_types import (
    CandidateSignal,
    PositionState,
    SignalType,
    StrategyTriggerMode
)
from .notification.dispatcher import SignalNotificationDispatcher
from .observer.chart_screen_observer import ChartScreenObserver
from .permissions import PERMISSIONS_REQUIRED
from .session.session_coordinator import SessionCoordinator
from .state.idempotency import SignalIdempotencyManager
from .state.position_tracker import PositionStateTracker
from .strategy.confluence_engine import ConfluenceSignalEngine
from .strategy.exit_evaluator import ExitEvaluator
from .validation.confidence_gate import ConfidenceGate
from .validation.pair_validator import PairValidator
from .vision.extractor import ChartStateExtractor

logger = logging.getLogger("jarvis.plugins.trading_signals")


class TradingSignalsPlugin(BasePlugin):
    """
    Controls desktop screen observation and confluence signal evaluation for NIFTY options.
    Generates strict concise recommendation signals without broker execution.
    """

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest or MANIFEST, config=config)
        cfg = self.config.get("trading_signals", {})

        # Configuration options
        mode_str = cfg.get("strategy_mode", StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD.value)
        try:
            self.strategy_mode = StrategyTriggerMode(mode_str)
        except Exception:
            self.strategy_mode = StrategyTriggerMode.REGIME_CONFIRMED_OPTION_LEAD

        self.min_confidence = float(cfg.get("min_confidence_threshold", 0.85))
        self.dual_fresh_window_bricks = int(cfg.get("dual_fresh_window_bricks", 2))
        self.window_filter = str(cfg.get("window_title_filter", "tv.dhan.co"))

        # Core Subsystems
        self.position_tracker = PositionStateTracker(cooldown_seconds=float(cfg.get("cooldown_seconds", 30.0)))
        self.idempotency = SignalIdempotencyManager(cooldown_seconds=float(cfg.get("cooldown_seconds", 30.0)))
        self.pair_validator = PairValidator()
        self.confidence_gate = ConfidenceGate(min_threshold=self.min_confidence)
        self.confluence_engine = ConfluenceSignalEngine(
            trigger_mode=self.strategy_mode,
            dual_fresh_window_bricks=self.dual_fresh_window_bricks
        )
        self.exit_evaluator = ExitEvaluator(self.position_tracker)
        self.extractor = ChartStateExtractor()
        self.dispatcher = SignalNotificationDispatcher(event_bus=getattr(self, "event_bus", None))

        self.observer: Optional[ChartScreenObserver] = None
        self.pre_dispatch_gate = PreDispatchRevalidationGate(
            min_confidence=self.min_confidence,
            window_verifier=self._check_window_foreground
        )

        self.coordinator: Optional[SessionCoordinator] = SessionCoordinator(
            extractor=self.extractor,
            confluence_engine=self.confluence_engine,
            exit_evaluator=self.exit_evaluator,
            position_tracker=self.position_tracker,
            idempotency_manager=self.idempotency,
            pre_dispatch_validator=lambda cand, idx, opt, conf: self.pre_dispatch_gate.validate_candidate(cand, idx, opt, conf).passed,
            notification_dispatcher=self.dispatcher.dispatch,
            idle_poll_sec=float(cfg.get("discovery_poll_interval", 1.0)),
            active_poll_sec=float(cfg.get("active_poll_interval", 0.5))
        )
        self.auto_discovery_enabled = bool(cfg.get("auto_discovery_enabled", True))

        # Operational state
        self.last_data_feed_state = DataFeedState.WINDOW_OCCLUDED_OR_HIDDEN
        self._prev_option_state: Optional[OptionChartState] = None

    def get_manifest(self) -> PluginManifest:
        return MANIFEST

    def initialize(self) -> bool:
        """Lifecycle hook called when the plugin is loaded."""
        super().initialize()
        if self.auto_discovery_enabled and self.coordinator:
            self.coordinator.start()
            logger.info("[TRADING_PLUGIN] SessionCoordinator auto-discovery started.")
        return True

    def shutdown(self) -> None:
        """Lifecycle hook called when plugin or Jarvis shuts down."""
        if self.coordinator and self.coordinator.is_alive():
            self.coordinator.stop()
            self.coordinator.join(timeout=2.0)
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=2.0)
            self.observer = None
        super().shutdown()

    def _check_window_foreground(self) -> bool:
        """Helper to verify target window is in foreground."""
        if self.coordinator and self.coordinator.session_state == TradingSessionState.ACTIVE:
            return self.coordinator.detector.is_supported_browser_foreground()
        if self.observer:
            return self.observer.is_target_window_foreground()
        return True

    def process_frame(self, frame_bgr: Any, mock_ocr_data: Optional[dict] = None) -> Optional[CandidateSignal]:
        """
        Processes a single visual screen frame through the complete pipeline:
        Observation -> Vision/OCR -> Normalized ChartState -> Pre-Validation -> Confluence -> Pre-Dispatch -> Dispatch
        """
        # 1. Vision Extraction
        extraction = self.extractor.extract(frame_bgr, mock_ocr_data=mock_ocr_data)
        self.last_data_feed_state = extraction.data_feed_state

        if extraction.data_feed_state != DataFeedState.LIVE_AND_VALID:
            self.position_tracker.on_data_feed_loss(reason=extraction.data_feed_state.value)
            return None

        self.position_tracker.on_data_feed_restored()

        index_state = extraction.index_state
        option_state = extraction.option_state
        confidence = extraction.frame_confidence

        if not index_state or not option_state:
            return None

        # 2. Pre-Validation Check (NIFTY Underlying, Strike, Expiry, Pair Alignment)
        pair_check = self.pair_validator.validate(index_state, option_state)
        if not pair_check.is_valid:
            return None

        # 3. Confidence Gating Check
        conf_check = self.confidence_gate.evaluate(confidence)
        if not conf_check.is_acceptable:
            self.last_data_feed_state = DataFeedState.LOW_CONFIDENCE
            return None

        # 4. BUY Confluence Evaluation (Only when FLAT)
        if self.position_tracker.can_evaluate_buy():
            confluence_res = self.confluence_engine.evaluate_buy_confluence(
                index_state=index_state,
                option_state=option_state,
                previous_option_state=self._prev_option_state
            )
            self._prev_option_state = option_state

            if confluence_res.signal_generated and confluence_res.candidate:
                candidate = confluence_res.candidate

                # Idempotency & Cooldown check
                if not self.idempotency.can_dispatch(candidate):
                    return None

                # Pre-Dispatch Synchronous Revalidation
                reval = self.pre_dispatch_gate.validate_candidate(
                    candidate=candidate,
                    fresh_index_state=index_state,
                    fresh_option_state=option_state,
                    fresh_confidence=confidence
                )
                if reval.passed:
                    self.position_tracker.on_buy_signal_dispatched(candidate)
                    self.idempotency.record_dispatch(candidate)
                    self.dispatcher.dispatch(candidate)
                    return candidate
                else:
                    logger.warning("[PRE_DISPATCH_DROPPED] Candidate signal dropped: %s", reval.reason)
                    return None

        # 5. EXIT Evaluation (Position-Aware: strictly while active recommendation is tracked)
        elif self.position_tracker.can_evaluate_exit():
            exit_res = self.exit_evaluator.evaluate_exit(
                index_state=index_state,
                option_state=option_state
            )
            self._prev_option_state = option_state

            if exit_res.is_exit and exit_res.candidate:
                candidate = exit_res.candidate

                # Pre-Dispatch Revalidation
                reval = self.pre_dispatch_gate.validate_candidate(
                    candidate=candidate,
                    fresh_index_state=index_state,
                    fresh_option_state=option_state,
                    fresh_confidence=confidence
                )
                if reval.passed:
                    self.position_tracker.on_exit_signal_dispatched(candidate.exit_reason)
                    self.dispatcher.dispatch(candidate)
                    return candidate
                else:
                    logger.warning("[PRE_DISPATCH_DROPPED] Candidate exit signal dropped: %s", reval.reason)
                    return None

        self._prev_option_state = option_state
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        """Executes trading signal actions."""
        parameters = parameters or {}

        # 1. start_signal_monitor
        if action_name == "start_signal_monitor":
            window_filter = parameters.get("window_filter", self.window_filter)
            if self.observer and self.observer.is_alive():
                return PluginResult(
                    success=True,
                    data={"running": True, "message": "Trading signal monitor is already running."}
                )

            self.observer = ChartScreenObserver(
                window_title_filter=window_filter,
                poll_interval=float(self.config.get("trading_signals", {}).get("poll_interval_sec", 0.5)),
                on_frame_callback=self.process_frame
            )
            self.observer.start()
            logger.info("[TRADING_PLUGIN] ChartScreenObserver started for filter '%s'.", window_filter)
            return PluginResult(
                success=True,
                data={
                    "running": True,
                    "window_filter": window_filter,
                    "strategy_mode": self.strategy_mode.value,
                    "message": f"Trading signal monitor started for '{window_filter}' in {self.strategy_mode.value} mode."
                }
            )

        # 2. stop_signal_monitor
        elif action_name == "stop_signal_monitor":
            stopped_anything = False
            if self.observer and self.observer.is_alive():
                self.observer.stop()
                self.observer.join(timeout=2.0)
                self.observer = None
                stopped_anything = True
                logger.info("[TRADING_PLUGIN] ChartScreenObserver stopped.")

            if self.coordinator:
                self.coordinator.pause_session(reason="monitor_stopped")
                stopped_anything = True

            return PluginResult(
                success=True,
                data={"running": False, "message": "Trading signal monitor stopped." if stopped_anything else "Trading signal monitor was not running."}
            )

        # 3. get_signal_status
        elif action_name == "get_signal_status":
            is_running = (self.observer.is_alive() if self.observer else False) or (
                self.coordinator.is_alive() and self.coordinator.session_state == TradingSessionState.ACTIVE
                if self.coordinator else False
            )
            sess_info = self.coordinator.get_session_info() if self.coordinator else None
            sess_state = self.coordinator.session_state.value if self.coordinator else TradingSessionState.NO_SESSION.value
            brow_state = self.coordinator.browser_state.value if self.coordinator else BrowserState.BROWSER_NOT_SUPPORTED.value

            active_info = None
            if self.position_tracker.active_signal:
                sig = self.position_tracker.active_signal
                active_info = {
                    "underlying": sig.underlying,
                    "strike": sig.strike,
                    "option_type": sig.option_type,
                    "entry_price": sig.entry_price,
                    "entry_time": sig.entry_timestamp,
                    "brick_sequence_id": sig.last_confirmed_brick_id
                }

            return PluginResult(
                success=True,
                data={
                    "running": is_running,
                    "signal_state": self.position_tracker.state.value,
                    "data_feed_state": self.last_data_feed_state.value,
                    "session_state": sess_state,
                    "browser_state": brow_state,
                    "active_session": sess_info,
                    "strategy_mode": self.strategy_mode.value,
                    "active_recommendation": active_info,
                    "broker_invariant": "JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION",
                    "message": f"Signal state: {self.position_tracker.state.value}, Session: {sess_state}, Data feed: {self.last_data_feed_state.value}."
                }
            )

        # 4. set_strategy_mode
        elif action_name == "set_strategy_mode":
            mode_input = str(parameters.get("mode", "")).strip().upper()
            try:
                new_mode = StrategyTriggerMode(mode_input)
                self.strategy_mode = new_mode
                self.confluence_engine.trigger_mode = new_mode
                logger.info("[TRADING_PLUGIN] Strategy mode updated to %s.", new_mode.value)
                return PluginResult(
                    success=True,
                    data={"strategy_mode": new_mode.value, "message": f"Strategy mode updated to {new_mode.value}."}
                )
            except ValueError:
                valid = [m.value for m in StrategyTriggerMode]
                return PluginResult(
                    success=False,
                    error=f"Invalid strategy mode '{mode_input}'. Allowed modes: {valid}"
                )

        # 5. reset_signal_state
        elif action_name == "reset_signal_state":
            self.position_tracker.reset_to_flat(reason="user_command")
            self.idempotency.clear()
            return PluginResult(
                success=True,
                data={"signal_state": PositionState.FLAT.value, "message": "Signal state reset to FLAT."}
            )

        # 6. pause_session
        elif action_name == "pause_session":
            reason = str(parameters.get("reason", "user_command"))
            if self.coordinator:
                self.coordinator.pause_session(reason=reason)
                return PluginResult(
                    success=True,
                    data={"session_state": self.coordinator.session_state.value, "message": f"Trading chart session paused ({reason})."}
                )
            return PluginResult(success=False, error="SessionCoordinator is not available.")

        # 7. resume_session
        elif action_name == "resume_session":
            if self.coordinator:
                self.coordinator.resume_session()
                return PluginResult(
                    success=True,
                    data={"session_state": self.coordinator.session_state.value, "message": f"Trading chart session resumed ({self.coordinator.session_state.value})."}
                )
            return PluginResult(success=False, error="SessionCoordinator is not available.")

        # 8. analyze_this_chart
        elif action_name == "analyze_this_chart":
            if self.coordinator:
                activated = self.coordinator.analyze_this_chart()
                return PluginResult(
                    success=True,
                    data={
                        "activated": activated,
                        "session_state": self.coordinator.session_state.value,
                        "message": "Chart analysis activated on foreground window." if activated else "Foreground window is not a valid Dhan chart."
                    }
                )
            return PluginResult(success=False, error="SessionCoordinator is not available.")

        return PluginResult(success=False, error=f"Unknown action: '{action_name}'")
