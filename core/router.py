# core/router.py
"""Command router dispatching classified requests to the proper subsystem."""

import logging
from typing import Any, Dict, Optional, Tuple

from .intent import Intent, IntentType

logger = logging.getLogger("jarvis.router")


class CommandRouter:
    """Decides execution route for incoming intent (System, Memory, Plugin, Chat)."""

    def __init__(self, plugin_manager: Optional[Any] = None, memory_manager: Optional[Any] = None):
        self.plugin_manager = plugin_manager
        self.memory_manager = memory_manager

    def route_intent(self, intent: Intent) -> Tuple[str, Optional[str]]:
        """
        Determines the routing destination and specific handler.
        Returns: (route_category, handler_name)
        Routes: 'SYSTEM', 'MEMORY', 'PLUGIN', 'CHAT', 'LEARNING'
        """
        if intent.type == IntentType.SYSTEM:
            return "SYSTEM", intent.name

        if intent.type in (IntentType.MEMORY_STORE, IntentType.MEMORY_QUERY):
            return "MEMORY", intent.type.value

        if intent.type == IntentType.CORRECTION:
            return "LEARNING", "CORRECTION"

        if (intent.is_multi_step or intent.metadata.get("workflow_plan")) and "workflow_data" not in intent.entities:
            return "TASK_ENGINE", intent.name

        if intent.type == IntentType.COMMAND and intent.target_plugin:
            return "PLUGIN", f"{intent.target_plugin}.{intent.target_action}"

        return "CHAT", "LLM_REASONING"
