# core/laya/__init__.py
"""Laya System-1 Decision Engine integration for Jarvis V2.1.

Single authoritative owner for all Laya operations:
download / status / lazy inference / advisory intent & guardrail decisions.

Upstream: convaiinnovations/laya (HF) + `pip install laya`.
Docs: https://huggingface.co/convaiinnovations/laya
"""

from .intelligence import (
    LayaCore,
    LayaDecision,
    LayaIntelligence,
    LayaResponseMode,
    LayaRoute,
    get_laya_core,
    get_laya_intelligence,
)
from .manager import (
    MODE_RULE_ONLY,
    MODE_RULE_PLUS_LAYA,
    LayaModelManager,
    get_laya_manager,
)

__all__ = [
    "LayaCore",
    "get_laya_core",
    "LayaRoute",
    "LayaModelManager",
    "get_laya_manager",
    "LayaIntelligence",
    "LayaDecision",
    "LayaResponseMode",
    "get_laya_intelligence",
    "MODE_RULE_ONLY",
    "MODE_RULE_PLUS_LAYA",
]
