# brain/dual_brain.py
"""Dual-Brain Coordinator balancing Fast Brain (System 1) and Smart Brain (System 2)."""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .fast_brain import FastBrain
from .smart_brain import SmartBrain

logger = logging.getLogger("jarvis.brain.dual")


class DualBrain:
    """Coordinates System 1 (Fast Reflexive) and System 2 (Smart Deliberative) execution."""

    def __init__(self, plugin_manager: Optional[Any] = None, llm_provider: Optional[Any] = None):
        self.plugin_manager = plugin_manager
        self.fast_brain = FastBrain(plugin_manager=self.plugin_manager)
        self.smart_brain = SmartBrain(llm_provider=llm_provider, plugin_manager=self.plugin_manager)

    def route_and_execute(self, query: str) -> Tuple[str, Optional[str], Optional[Any]]:
        """
        Routes user query through Dual-Brain architecture:
        - Mode 1: FAST (<5ms) for obvious commands (Chrome kholo, Volume 50, Screenshot lo, etc.)
        - Mode 2: SMART for complex multi-step goals (Downloads organize karo + duplicate report)
        - Mode 3: STANDARD for general chat, memory queries, or single-step plugin intent
        Returns (mode, response_text, result_data).
        """
        start_time = time.perf_counter()

        # 1. Try Fast Brain (System 1 Reflexive)
        fast_match = self.fast_brain.match_fast_command(query)
        if fast_match.matched:
            executed, resp_msg, data = self.fast_brain.execute_fast(query)
            if executed:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"DualBrain: Handled by FastBrain in {elapsed_ms:.2f}ms.")
                return "FAST", resp_msg, data

        # 2. Try Smart Brain (System 2 Deliberative)
        if self.smart_brain.is_smart_deliberation_needed(query):
            plan_steps = self.smart_brain.create_deliberative_plan(query)
            if plan_steps and self.plugin_manager:
                results = []
                for step in plan_steps:
                    res = self.plugin_manager.execute_action(step.plugin_name, step.action_name, step.parameters)
                    results.append({
                        "plugin": step.plugin_name,
                        "action": step.action_name,
                        "success": res.success,
                        "data": res.data,
                        "error": res.error
                    })
                report = self.smart_brain.synthesize_smart_report(query, results)
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.info(f"DualBrain: Handled by SmartBrain in {elapsed_ms:.2f}ms.")
                return "SMART", report, results

        # 3. Standard execution pathway
        return "STANDARD", None, None
