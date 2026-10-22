# plugins/trading_signals/session/session_detector.py
"""
Deterministic Dhan Chart & Trading Session Classification Engine.
Inspects browser window context, layout geometry, instrument headers,
and visual indicators to classify trading session state.
"""

from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from ..models.data_feed_types import DataFeedState, FrameConfidence
from ..models.session_types import BrowserState, TradingSessionState
from ..vision.detector import ChartRegionDetector, SegmentedChartLayout

logger = logging.getLogger("jarvis.trading.session.detector")


@dataclass(frozen=True)
class SessionClassificationResult:
    """Result of window and visual chart session inspection."""
    browser_state: BrowserState
    session_state: TradingSessionState
    browser_name: str
    window_title: str
    hwnd: int
    is_dhan_page: bool
    underlying: str
    strike: int
    option_type: str
    expiry: str
    confidence: float
    details: str
    layout: Optional[SegmentedChartLayout] = None


class TradingSessionDetector:
    """
    Evaluates foreground application and visual chart characteristics
    to classify trading chart presence without DOM scraping or network interception.
    """

    SUPPORTED_BROWSERS = {"chrome", "brave", "edge", "msedge", "firefox"}
    DHAN_TITLE_KEYWORDS = {"dhan", "tv.dhan.co", "tradingview"}

    def __init__(
        self,
        region_detector: Optional[ChartRegionDetector] = None,
        panel_detector: Optional[Any] = None,
        panel_extractor: Optional[Any] = None,
        panel_classifier: Optional[Any] = None
    ):
        self.region_detector = region_detector or ChartRegionDetector()
        self.panel_detector = panel_detector
        self.panel_extractor = panel_extractor
        self.panel_classifier = panel_classifier

    def classify_browser(self, process_name: str, is_foreground: bool = True) -> Tuple[BrowserState, str]:
        """
        Determines whether the given process is a supported browser and its foreground state.
        """
        if not process_name:
            return BrowserState.BROWSER_NOT_SUPPORTED, ""

        clean_proc = process_name.lower().strip()
        # Strip .exe if present
        clean_proc = re.sub(r"\.exe$", "", clean_proc)

        # Normalize edge variants
        if clean_proc in ("msedge", "edge"):
            clean_proc = "edge"

        if clean_proc not in self.SUPPORTED_BROWSERS:
            return BrowserState.BROWSER_NOT_SUPPORTED, clean_proc

        if not is_foreground:
            return BrowserState.BROWSER_BACKGROUND, clean_proc

        return BrowserState.BROWSER_FOREGROUND, clean_proc

    def is_dhan_title(self, window_title: str) -> bool:
        """
        Checks whether the window title indicates a Dhan TradingView chart session.
        """
        if not window_title:
            return False
        low = window_title.lower()
        return any(k in low for k in self.DHAN_TITLE_KEYWORDS)

    def parse_header_text_metadata(self, title_or_header: str) -> Tuple[str, int, str, str]:
        """
        Extracts underlying, strike, derivative type (CE/PE), and expiry from title/header text.
        Example text: "NIFTY 24500 CE 08 SEP - tv.dhan.co"
        Returns: (underlying, strike, option_type, expiry)
        """
        if not title_or_header:
            return "UNKNOWN", 0, "UNKNOWN", ""

        text = title_or_header.upper()

        # 1. Underlying
        underlying = "UNKNOWN"
        for sectoral in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYBANK", "NIFTYIT"):
            if sectoral in text:
                underlying = sectoral
                break
        if underlying == "UNKNOWN" and re.search(r"\bNIFTY\b|NIFTY 50", text):
            underlying = "NIFTY"

        # 2. Derivative Type
        opt_type = "UNKNOWN"
        if re.search(r"\bCE\b|\bCALL\b", text):
            opt_type = "CE"
        elif re.search(r"\bPE\b|\bPUT\b", text):
            opt_type = "PE"

        # 3. Strike Price (4 to 5 digit strike e.g. 24500, 24000)
        strike = 0
        strike_match = re.search(r"\b(\d{5})\b", text)
        if strike_match:
            try:
                strike = int(strike_match.group(1))
            except ValueError:
                pass

        # 4. Expiry (e.g. "08 SEP", "15 SEP", "SEP 2026", "28-AUG-2026")
        expiry = ""
        exp_match = re.search(r"(\d{1,2}[-\s]*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(?:[-\s]*\d{2,4})?)", text)
        if exp_match:
            expiry = exp_match.group(1).strip()

        return underlying, strike, opt_type, expiry

    def inspect_session(
        self,
        hwnd: int,
        process_name: str,
        window_title: str,
        frame_bgr: Optional["np.ndarray"] = None,
        is_foreground: bool = True
    ) -> SessionClassificationResult:
        """
        Full deterministic session classification pipeline:
        Browser check -> Window title check -> Visual layout check -> Chart validation.
        """
        # 1. Browser check
        browser_state, bname = self.classify_browser(process_name, is_foreground)
        if browser_state == BrowserState.BROWSER_NOT_SUPPORTED:
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.NO_SESSION,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=False,
                underlying="UNKNOWN",
                strike=0,
                option_type="UNKNOWN",
                expiry="",
                confidence=0.0,
                details=f"Process '{process_name}' is not a supported browser."
            )

        if browser_state == BrowserState.BROWSER_BACKGROUND:
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.PAUSED,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=self.is_dhan_title(window_title),
                underlying="UNKNOWN",
                strike=0,
                option_type="UNKNOWN",
                expiry="",
                confidence=0.0,
                details=f"Browser '{bname}' is in background; session paused."
            )

        # 2. Window title check
        is_dhan = self.is_dhan_title(window_title)
        if not is_dhan:
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.NO_SESSION,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=False,
                underlying="UNKNOWN",
                strike=0,
                option_type="UNKNOWN",
                expiry="",
                confidence=0.0,
                details=f"Window title '{window_title}' does not indicate a Dhan trading chart."
            )

        # 3. Candidate Dhan page detected
        underlying, strike, opt_type, expiry = self.parse_header_text_metadata(window_title)

        # If no frame provided yet, remain in TRADING_PAGE_DETECTED
        if frame_bgr is None or (hasattr(frame_bgr, "size") and frame_bgr.size == 0):
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.TRADING_PAGE_DETECTED,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=True,
                underlying=underlying,
                strike=strike,
                option_type=opt_type,
                expiry=expiry,
                confidence=0.50,
                details="Dhan trading window detected; awaiting chart frame for validation."
            )

        # 4. Deep Visual Layout Validation (VALIDATING state)
        layout = self.region_detector.detect_layout(frame_bgr)
        if layout is None or layout.confidence < 0.85:
            # Layout ambiguous or not dual-pane
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.VALIDATING,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=True,
                underlying=underlying,
                strike=strike,
                option_type=opt_type,
                expiry=expiry,
                confidence=layout.confidence if layout else 0.30,
                details="Visual layout undergoing inspection; dual-pane chart not yet fully established.",
                layout=layout
            )

        # 5. Validate Required Strategy Constraints for NIFTY Options
        if underlying in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYBANK", "NIFTYIT"):
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.INVALID,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=True,
                underlying=underlying,
                strike=strike,
                option_type=opt_type,
                expiry=expiry,
                confidence=layout.confidence,
                details=f"Sectoral underlying '{underlying}' is not supported. Only pure NIFTY options strategy is supported.",
                layout=layout
            )

        if underlying != "NIFTY" or strike <= 0 or opt_type not in ("CE", "PE"):
            # Attempt visual multi-panel extraction from the frame
            if frame_bgr is not None:
                try:
                    if self.panel_detector is None:
                        from ..vision.panel_detector import MultiPanelChartDetector
                        self.panel_detector = MultiPanelChartDetector()
                    if self.panel_extractor is None:
                        from ..vision.panel_extractor import PanelSemanticExtractor
                        self.panel_extractor = PanelSemanticExtractor()
                    if self.panel_classifier is None:
                        from ..session.panel_classifier import PanelRoleClassifier
                        self.panel_classifier = PanelRoleClassifier()

                    boundaries = self.panel_detector.detect_panels(frame_bgr)
                    if boundaries and len(boundaries) >= 2:
                        panels = [self.panel_extractor.extract_panel(frame_bgr, b) for b in boundaries]
                        chart_set = self.panel_classifier.classify_chart_set(panels)
                        if chart_set.index_panel and (chart_set.ce_panels or chart_set.pe_panels):
                            prim_opt = chart_set.get_primary_ce_panel() or chart_set.get_primary_pe_panel()
                            if prim_opt and prim_opt.strike > 0:
                                underlying = "NIFTY"
                                strike = prim_opt.strike
                                opt_type = prim_opt.option_type.value if prim_opt.option_type else "CE"
                                expiry = prim_opt.expiry
                except Exception as e:
                    logger.debug("[SESSION_DETECTOR_MULTI_PANEL_RETRY] %s", e)

        if underlying != "NIFTY" or strike <= 0 or opt_type not in ("CE", "PE"):
            return SessionClassificationResult(
                browser_state=browser_state,
                session_state=TradingSessionState.VALIDATING,
                browser_name=bname,
                window_title=window_title,
                hwnd=hwnd,
                is_dhan_page=True,
                underlying=underlying,
                strike=strike,
                option_type=opt_type,
                expiry=expiry,
                confidence=layout.confidence * 0.75,
                details="Option contract identity (underlying, strike, or CE/PE) ambiguous in header.",
                layout=layout
            )

        # 6. All criteria met: Confirmed ACTIVE
        logger.info(
            "[SESSION_CONFIRMED_ACTIVE] Dhan chart verified on %s (HWND=%d): %s %d %s (Conf=%.2f).",
            bname,
            hwnd,
            underlying,
            strike,
            opt_type,
            layout.confidence
        )
        return SessionClassificationResult(
            browser_state=browser_state,
            session_state=TradingSessionState.ACTIVE,
            browser_name=bname,
            window_title=window_title,
            hwnd=hwnd,
            is_dhan_page=True,
            underlying=underlying,
            strike=strike,
            option_type=opt_type,
            expiry=expiry,
            confidence=layout.confidence,
            details="Supported Dhan NIFTY dual-chart active and validated.",
            layout=layout
        )
