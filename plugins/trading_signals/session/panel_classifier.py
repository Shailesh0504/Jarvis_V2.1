# plugins/trading_signals/session/panel_classifier.py
"""
Cross-Panel Role Classifier & Ambiguity Disambiguator.
Groups extracted ChartPanels into a TradingChartSet, verifies semantic requirements,
and rejects ambiguous multi-panel states rather than making guessing assumptions.
"""

import logging
from typing import List, Optional

from ..models.panel_types import (
    ChartPanel,
    ChartPanelRole,
    TradingChartSet
)

logger = logging.getLogger("jarvis.trading.session.panel_classifier")


class PanelRoleClassifier:
    """
    Evaluates independently extracted ChartPanels and constructs an authoritative TradingChartSet.
    Strictly role-driven based on header semantics; screen coordinates are ignored.
    """

    def classify_chart_set(self, panels: List[ChartPanel]) -> TradingChartSet:
        """
        Groups panels by role and validates cross-panel consistency.
        """
        chart_set = TradingChartSet()
        index_candidates: List[ChartPanel] = []

        for p in panels:
            if p.role == ChartPanelRole.INDEX_CHART:
                index_candidates.append(p)
            elif p.role == ChartPanelRole.OPTION_CE_CHART:
                chart_set.ce_panels.append(p)
            elif p.role == ChartPanelRole.OPTION_PE_CHART:
                chart_set.pe_panels.append(p)
            else:
                chart_set.unknown_panels.append(p)

        # 1. Index Chart Disambiguation
        if len(index_candidates) == 1:
            chart_set.index_panel = index_candidates[0]
        elif len(index_candidates) > 1:
            chart_set.ambiguity_reasons.append(
                f"Multiple ({len(index_candidates)}) Index chart panels detected. Ambiguous index role."
            )
            chart_set.unknown_panels.extend(index_candidates)
        else:
            chart_set.ambiguity_reasons.append("No valid NIFTY 50 index chart panel detected.")

        # 2. Option CE Disambiguation (Section 13)
        if len(chart_set.ce_panels) > 1:
            chart_set.ambiguity_reasons.append(
                f"Duplicate CE option panels ({len(chart_set.ce_panels)}) detected without single focal selection."
            )

        # 3. Option PE Disambiguation (Section 13)
        if len(chart_set.pe_panels) > 1:
            chart_set.ambiguity_reasons.append(
                f"Duplicate PE option panels ({len(chart_set.pe_panels)}) detected without single focal selection."
            )

        # 4. Generate unique layout signature
        n_idx = 1 if chart_set.index_panel else 0
        n_ce = len(chart_set.ce_panels)
        n_pe = len(chart_set.pe_panels)
        chart_set.layout_signature = f"{n_idx}_INDEX+{n_ce}_CE+{n_pe}_PE"

        logger.debug(
            "[CHART_SET_CLASSIFIED] Signature: %s (Panels: %d total, %d ambiguity warnings).",
            chart_set.layout_signature,
            len(panels),
            len(chart_set.ambiguity_reasons)
        )

        return chart_set
