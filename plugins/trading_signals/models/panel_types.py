# plugins/trading_signals/models/panel_types.py
"""
Domain models for multi-panel Dhan / TradingView chart understanding.
Enables independent representation, semantic role classification,
and configuration validation without hardcoded coordinate assumptions.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional

from .chart_state import (
    BrickStatus,
    IndexChartState,
    OptionChartState,
    OptionType,
    RenkoColor,
    RenkoTransition,
    SuperTrendBias,
    SuperTrendFlip
)


class ChartPanelRole(str, Enum):
    """Semantic role assigned to a chart panel based on instrument header analysis."""
    INDEX_CHART = "INDEX_CHART"
    OPTION_CE_CHART = "OPTION_CE_CHART"
    OPTION_PE_CHART = "OPTION_PE_CHART"
    UNKNOWN_CHART = "UNKNOWN_CHART"


class InstrumentType(str, Enum):
    """Underlying financial instrument category."""
    INDEX = "INDEX"
    OPTION = "OPTION"
    EQUITY = "EQUITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ChartPanel:
    """
    Independent representation of a single detected chart panel on the workspace.
    Strictly encapsulates its own local coordinate system, header metadata,
    and verified indicator observations.
    """
    panel_id: str
    role: ChartPanelRole = ChartPanelRole.UNKNOWN_CHART
    symbol: str = "NIFTY"
    instrument_type: InstrumentType = InstrumentType.UNKNOWN
    strike: Optional[int] = None
    option_type: Optional[OptionType] = None
    expiry: Optional[str] = None
    exchange: str = "NSE"
    timeframe: str = ""
    chart_type: str = "RENKO"
    renko_mode: str = "TRADITIONAL"
    renko_brick_size: Optional[float] = None

    # Expected indicator configurations (strings or parsed parameters)
    supertrend_config: Optional[str] = None     # Expected: "1, 2.1" or "1 2.1"
    ema_config: Optional[str] = None            # Expected for Index: "20 close 0" or "20"
    donchian_config: Optional[str] = None       # Expected for Options: "9, 0" or "9 0"

    # Current extracted indicator and price observations
    current_price: Optional[float] = None
    previous_price: Optional[float] = None
    renko_brick_state: BrickStatus = BrickStatus.UNKNOWN
    renko_brick_color: RenkoColor = RenkoColor.UNKNOWN
    renko_transition: RenkoTransition = RenkoTransition.NO_TRANSITION
    supertrend_bias: SuperTrendBias = SuperTrendBias.UNKNOWN
    supertrend_flip: SuperTrendFlip = SuperTrendFlip.NO_FLIP
    ema_bias: SuperTrendBias = SuperTrendBias.UNKNOWN

    donchian_upper: Optional[float] = None
    donchian_basis: Optional[float] = None
    donchian_lower: Optional[float] = None
    previous_donchian_upper: Optional[float] = None
    donchian_breakout_event: bool = False

    brick_sequence_id: int = 0
    last_trigger_brick_id: int = 0

    # Panel geometry & coordinate subregions (relative to full screen)
    region: Optional[Any] = None                # Bounding RectRegion (x, y, w, h)
    header_region: Optional[Any] = None         # Header RectRegion
    canvas_region: Optional[Any] = None         # Renko Canvas RectRegion
    price_axis_region: Optional[Any] = None     # Price Axis RectRegion
    time_axis_region: Optional[Any] = None      # Time Axis RectRegion

    # Visual health and confidence metrics
    confidence: float = 0.0
    is_occluded: bool = False
    validation_error: str = ""
    is_configuration_valid: bool = True
    raw_header_text: str = ""
    last_observed_timestamp: float = field(default_factory=time.time)

    def is_valid_index_configuration(self) -> bool:
        """
        Validates whether this panel matches the required Index strategy configuration:
        - Symbol: NIFTY 50
        - Renko Traditional with brick size 10
        - SuperTrend 1, 2.1
        - EMA 20
        """
        if not self.is_configuration_valid:
            return False
        if self.role != ChartPanelRole.INDEX_CHART:
            return False
        if "NIFTY" not in self.symbol.upper():
            return False
        if self.renko_brick_size is not None and abs(self.renko_brick_size - 10.0) > 0.01:
            return False
        if self.supertrend_config:
            st_clean = self.supertrend_config.replace(" ", "")
            if not ("1,2.1" in st_clean or "1.0,2.1" in st_clean or ("1" in st_clean and "2.1" in st_clean)):
                return False
        if self.ema_config:
            if "20" not in self.ema_config:
                return False
        return True

    def is_valid_option_configuration(self) -> bool:
        """
        Validates whether this panel matches the required Option strategy configuration:
        - Symbol: NIFTY option (CE or PE)
        - Renko Traditional with brick size 3
        - SuperTrend 1, 2.1
        - Donchian 9, 0
        """
        if not self.is_configuration_valid:
            return False
        if self.role not in (ChartPanelRole.OPTION_CE_CHART, ChartPanelRole.OPTION_PE_CHART):
            return False
        if "NIFTY" not in self.symbol.upper():
            return False
        if self.strike is None or self.strike <= 0:
            return False
        if self.renko_brick_size is not None and abs(self.renko_brick_size - 3.0) > 0.01:
            return False
        if self.supertrend_config:
            st_clean = self.supertrend_config.replace(" ", "")
            if not ("1,2.1" in st_clean or "1.0,2.1" in st_clean or ("1" in st_clean and "2.1" in st_clean)):
                return False
        if self.donchian_config:
            dc_clean = self.donchian_config.replace(" ", "")
            if not ("9,0" in dc_clean or "9.0,0" in dc_clean or ("9" in dc_clean and "0" in dc_clean)):
                return False
        return True

    def to_index_chart_state(self) -> IndexChartState:
        """Converts panel observations into normalized IndexChartState."""
        return IndexChartState(
            underlying=self.symbol or "NIFTY",
            current_price=self.current_price or 0.0,
            renko_color=self.renko_brick_color,
            brick_status=self.renko_brick_state,
            renko_transition=self.renko_transition,
            supertrend_bias=self.supertrend_bias,
            supertrend_flip=self.supertrend_flip,
            ema_bias=self.ema_bias,
            brick_sequence_id=self.brick_sequence_id,
            last_trigger_brick_id=self.last_trigger_brick_id,
            is_valid=(not self.is_occluded and self.confidence >= 0.85 and self.is_configuration_valid)
        )

    def to_option_chart_state(self) -> OptionChartState:
        """Converts panel observations into normalized OptionChartState."""
        opt_type = self.option_type or (
            OptionType.CE if self.role == ChartPanelRole.OPTION_CE_CHART else OptionType.PE
        )
        return OptionChartState(
            underlying=self.symbol or "NIFTY",
            strike=self.strike or 0,
            option_type=opt_type,
            current_price=self.current_price or 0.0,
            renko_color=self.renko_brick_color,
            brick_status=self.renko_brick_state,
            renko_transition=self.renko_transition,
            supertrend_bias=self.supertrend_bias,
            supertrend_flip=self.supertrend_flip,
            donchian_upper=self.donchian_upper or 0.0,
            donchian_basis=self.donchian_basis or 0.0,
            donchian_lower=self.donchian_lower or 0.0,
            previous_price=self.previous_price,
            previous_donchian_upper=self.previous_donchian_upper,
            donchian_breakout_event=self.donchian_breakout_event,
            brick_sequence_id=self.brick_sequence_id,
            is_valid=(not self.is_occluded and self.confidence >= 0.85 and self.is_configuration_valid)
        )


@dataclass
class TradingChartSet:
    """
    Structured aggregation of all chart panels detected across the screen.
    Guarantees cross-panel isolation and enables independent multi-option confluence.
    """
    index_panel: Optional[ChartPanel] = None
    ce_panels: List[ChartPanel] = field(default_factory=list)
    pe_panels: List[ChartPanel] = field(default_factory=list)
    unknown_panels: List[ChartPanel] = field(default_factory=list)
    ambiguity_reasons: List[str] = field(default_factory=list)
    layout_signature: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def has_valid_index(self) -> bool:
        """True if exactly one valid, unoccluded NIFTY index panel is present."""
        if not self.index_panel:
            return False
        return (
            not self.index_panel.is_occluded
            and self.index_panel.confidence >= 0.85
            and self.index_panel.is_valid_index_configuration()
        )

    def is_valid_for_ce(self) -> bool:
        """True if valid Index exists and exactly one unambiguous, valid CE option exists."""
        if not self.has_valid_index:
            return False
        if len(self.ce_panels) != 1:
            return False
        ce = self.ce_panels[0]
        return not ce.is_occluded and ce.confidence >= 0.85 and ce.is_valid_option_configuration()

    def is_valid_for_pe(self) -> bool:
        """True if valid Index exists and exactly one unambiguous, valid PE option exists."""
        if not self.has_valid_index:
            return False
        if len(self.pe_panels) != 1:
            return False
        pe = self.pe_panels[0]
        return not pe.is_occluded and pe.confidence >= 0.85 and pe.is_valid_option_configuration()

    def get_primary_ce_panel(self) -> Optional[ChartPanel]:
        """Returns the single valid CE panel, or None if ambiguous / missing."""
        if len(self.ce_panels) == 1:
            return self.ce_panels[0]
        return None

    def get_primary_pe_panel(self) -> Optional[ChartPanel]:
        """Returns the single valid PE panel, or None if ambiguous / missing."""
        if len(self.pe_panels) == 1:
            return self.pe_panels[0]
        return None

    def all_panels(self) -> List[ChartPanel]:
        """List of all discovered panels regardless of role."""
        panels = []
        if self.index_panel:
            panels.append(self.index_panel)
        panels.extend(self.ce_panels)
        panels.extend(self.pe_panels)
        panels.extend(self.unknown_panels)
        return panels
