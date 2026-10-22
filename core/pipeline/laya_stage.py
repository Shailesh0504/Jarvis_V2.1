# core/pipeline/laya_stage.py
"""
Laya Orchestration Stage for Jarvis V2.1 Pipeline.
Handles:
- Evaluating authoritative LayaDecision across 9 core responsibilities
- Tri-Bridge route evaluation (FAST_ROUTER, CHAT, AGENT_PLANNER)
- Dynamic context scoping
- Selective memory retrieval
"""

import logging
from typing import Any, Optional

from core.laya import get_laya_core, LayaDecision, LayaRoute

logger = logging.getLogger("jarvis.pipeline.laya")


class LayaStage:
    """Invokes LayaCore to authoritatively route and orchestrate the request."""

    def __init__(self, core: Any):
        self.core = core
        self.laya_core = getattr(core, "laya_core", None) or get_laya_core()

    def evaluate(self, raw_input: str, turn: Any) -> Optional[LayaDecision]:
        """Runs LayaCore decision engine and stamps decision onto turn metadata."""
        core = self.core
        laya_decision = None
        if self.laya_core:
            try:
                laya_decision = self.laya_core.decide(
                    raw_text=raw_input,
                    normalized_text=getattr(turn, "normalized_input", raw_input),
                    active_context=getattr(core, "active_context", None),
                    dialog_manager=getattr(core, "dialog_manager", None),
                    permission_guard=getattr(core, "permission_guard", None),
                    confirmation_manager=getattr(core, "confirmation_manager", None),
                )
                if hasattr(turn, "metadata"):
                    turn.metadata["laya_decision"] = laya_decision.to_dict()
            except Exception as _ld_exc:
                logger.debug("Laya Core decision note: %s", _ld_exc)
        return laya_decision
