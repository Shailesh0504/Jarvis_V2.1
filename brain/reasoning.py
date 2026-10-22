# brain/reasoning.py
"""Reasoning Engine for complex, multi-step problem solving and planning."""

import logging
from typing import Any, Dict, List, Optional

from core.planner import PlanStep
from core.permissions import PermissionLevel
from .llm import BaseLLMProvider

logger = logging.getLogger("jarvis.brain.reasoning")


class ReasoningEngine:
    """Provides chain-of-thought analysis and compound task decomposition."""

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm = llm_provider

    def decompose_complex_task(self, query: str, available_plugins: Dict[str, Any]) -> List[PlanStep]:
        """Decomposes a complex command into sequential steps."""
        # For mock or deterministic fallback: check for 'and', 'then'
        steps: List[PlanStep] = []
        if " then " in query.lower() or " and then " in query.lower():
            subqueries = [s.strip() for s in query.replace(" and then ", " then ").split(" then ") if s.strip()]
            for sq in subqueries:
                step = PlanStep(
                    plugin_name="system",
                    action_name="evaluate",
                    parameters={"subquery": sq},
                    description=f"Evaluate sub-command: {sq}"
                )
                steps.append(step)
        return steps

    def reason(self, question: str, context: Optional[str] = None) -> str:
        prompt = f"Question: {question}\n"
        if context:
            prompt = f"Context:\n{context}\n\n{prompt}"
        prompt += "Think carefully step by step, and formulate a clear and accurate response."
        return self.llm.generate(prompt=prompt)
