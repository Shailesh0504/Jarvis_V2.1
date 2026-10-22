# plugins/trading_signals/validation/pair_validator.py
"""
Pre-Validation of Instrument Underlying, Strike, Expiry, and Option Pairing Alignment.
Zero-tolerance for ambiguous or mismatched context.
"""

from dataclasses import dataclass
import logging
from typing import Optional

from ..models.chart_state import IndexChartState, OptionChartState, OptionType, SuperTrendBias

logger = logging.getLogger("jarvis.trading.validation.pair")


@dataclass(frozen=True)
class PairValidationResult:
    """Result of pre-validation check."""
    is_valid: bool
    reason: str


class PairValidator:
    """
    Validates that the visible charts represent a coherent NIFTY Index + Option trade setup.
    """

    ALLOWED_INDEX_NAMES = {"nifty", "nifty 50", "nifty50", "nifty 50 index", "nifty idx"}
    REJECTED_SUBSTRINGS = ("bank", "fin", "midcap", "next", "it", "metal", "auto")

    def validate(self, index_state: IndexChartState, option_state: OptionChartState) -> PairValidationResult:
        """
        Executes strict pre-validation checks:
        1. Index underlying verification (must be NIFTY).
        2. Option underlying verification (must be NIFTY).
        3. Valid strike price (positive integer).
        4. Valid option derivative type (CE or PE).
        5. Confluence pairing alignment:
           - Bearish index regime requires a PUT (PE) contract.
           - Bullish index regime requires a CALL (CE) contract.
        """
        # 1. Index underlying check
        clean_idx = index_state.underlying.strip().lower()
        if any(bad in clean_idx for bad in self.REJECTED_SUBSTRINGS):
            msg = f"Index underlying '{index_state.underlying}' is not recognized as NIFTY (contains rejected sectoral/other index)."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        if clean_idx not in self.ALLOWED_INDEX_NAMES:
            msg = f"Index underlying '{index_state.underlying}' is not recognized as NIFTY."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        # 2. Option underlying check
        clean_opt = option_state.underlying.strip().lower()
        if any(bad in clean_opt for bad in self.REJECTED_SUBSTRINGS):
            msg = f"Option underlying '{option_state.underlying}' does not match NIFTY."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        if clean_opt not in self.ALLOWED_INDEX_NAMES:
            msg = f"Option underlying '{option_state.underlying}' does not match NIFTY."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        # 3. Strike check
        if option_state.strike <= 0:
            msg = f"Invalid option strike detected: {option_state.strike}."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        # 4. Derivative type check
        if option_state.option_type not in (OptionType.CE, OptionType.PE):
            msg = f"Invalid or unrecognized option type: {option_state.option_type}."
            logger.warning("[PAIR_VALIDATION_FAILED] %s", msg)
            return PairValidationResult(is_valid=False, reason=msg)

        # 5. Pairing alignment with Index SuperTrend Bias
        if index_state.supertrend_bias == SuperTrendBias.BEARISH:
            if option_state.option_type != OptionType.PE:
                msg = f"Index is Bearish, but visible option is {option_state.option_type.value}. Expected PE contract."
                logger.debug("[PAIR_VALIDATION_MISMATCH] %s", msg)
                return PairValidationResult(is_valid=False, reason=msg)

        elif index_state.supertrend_bias == SuperTrendBias.BULLISH:
            if option_state.option_type != OptionType.CE:
                msg = f"Index is Bullish, but visible option is {option_state.option_type.value}. Expected CE contract."
                logger.debug("[PAIR_VALIDATION_MISMATCH] %s", msg)
                return PairValidationResult(is_valid=False, reason=msg)

        return PairValidationResult(is_valid=True, reason="Pairing valid and aligned.")
