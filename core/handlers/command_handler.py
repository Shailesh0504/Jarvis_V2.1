# core/handlers/command_handler.py
"""
Command Handler for Jarvis V2.1.
Handles:
- System commands (shutdown, restart, health, plugins list/enable/disable/reload)
- Memory commands (store fact, query fact)
- Fast-Path deterministic execution
"""

import logging
import threading
import time
from typing import Any, Optional

from core.intent import Intent, IntentType
from core.state import SystemState

logger = logging.getLogger("jarvis.handlers.command")


class CommandHandler:
    """Dispatches system, memory, and direct deterministic commands."""

    def __init__(self, core: Any):
        self.core = core

    def handle_system_command(self, intent: Intent) -> str:
        """Executes administrative and system commands."""
        core = self.core
        cmd = intent.name.lower()
        if cmd in ("exit", "quit", "shutdown"):
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.SHUTDOWN)
            return "Shutting down Jarvis systems. Goodbye, Boss."

        elif cmd in ("restart", "reload", "jarvis_reload", "system_reload"):
            from core.reloader import trigger_reload
            threading.Timer(0.4, trigger_reload).start()
            return "Jarvis ko live restart kar raha hoon, Boss..."

        elif cmd in ("status", "health"):
            state = core.state_machine.current_state.value if hasattr(core, "state_machine") else "idle"
            plugins_count = len(core.plugin_manager.get_available_plugins()) if getattr(core, "plugin_manager", None) else 0
            return f"System is operating nominally. State: {state}. Active Plugins: {plugins_count}."

        elif cmd == "plugins_list":
            if getattr(core, "plugin_manager", None):
                return "\n" + core.plugin_manager.get_plugin_status_table()
            return "Plugin Manager is not connected."

        elif cmd == "plugin_enable":
            p_name = intent.entities.get("plugin_name", "")
            if not getattr(core, "plugin_manager", None) or not p_name:
                return "Please specify a valid plugin name to enable."
            success, msg = core.plugin_manager.enable_plugin(p_name)
            return msg

        elif cmd == "plugin_disable":
            p_name = intent.entities.get("plugin_name", "")
            if not getattr(core, "plugin_manager", None) or not p_name:
                return "Please specify a valid plugin name to disable."
            success, msg = core.plugin_manager.disable_plugin(p_name)
            return msg

        elif cmd == "plugin_reload":
            p_name = intent.entities.get("plugin_name", "")
            if not getattr(core, "plugin_manager", None) or not p_name:
                return "Please specify a valid plugin name to reload."
            success, msg = core.plugin_manager.reload_plugin(p_name)
            return msg

        elif cmd in ("help", "commands"):
            if getattr(core, "plugin_manager", None):
                manifests = core.plugin_manager.get_all_manifests()
                lines = [
                    "Available Capabilities:",
                    "-----------------------------------------",
                    "• System: exit, status, help, plugins, plugin enable <name>, plugin disable <name>, plugin reload <name>",
                    "• Memory: remember my [key] is [value], what is my [key]?"
                ]
                for p_name, m in manifests.items():
                    actions = [a.name for a in m.actions]
                    lines.append(f"• {m.name.capitalize()} ({p_name}): {', '.join(actions)}")
                return "\n".join(lines)
            return "Jarvis Core v2.0 - Running in base mode."

        return f"System command '{intent.name}' processed."

    def handle_memory_command(self, intent: Intent) -> str:
        """Executes explicit memory storage and query commands."""
        core = self.core
        if not getattr(core, "memory_manager", None):
            return "Memory system is currently not connected."

        if intent.type == IntentType.MEMORY_STORE:
            key = intent.entities.get("key", "")
            value = intent.entities.get("value", "")
            category = intent.entities.get("category", "facts")
            if key and value:
                core.memory_manager.store_fact(key=key, value=value, category=category)
                return f"I have committed that to memory: {key} = {value}."
            return "I couldn't clearly identify what fact to store."

        elif intent.type == IntentType.MEMORY_QUERY:
            query = intent.entities.get("query", intent.raw_query)
            results = core.memory_manager.search_memories(query, limit=1)
            if results:
                return f"According to my memory: {results[0].get('key')}: {results[0].get('value')}."
            return f"I don't recall any information regarding '{query}'."

        return "Memory action completed."

    def dispatch_fast_route(
        self,
        turn: Any,
        laya_decision: Any,
        start_time: float,
        source: str = "cli"
    ) -> Optional[str]:
        """Sub-15ms deterministic execution for system commands, volume, time, app launch, weather, etc."""
        core = self.core
        fast_resp = core._try_fast_command_path(
            raw_text=turn.raw_input,
            normalized_input=turn.normalized_input,
            turn=turn,
            start_time=start_time,
            tracker=getattr(core, "latency_tracker", None),
            source=source
        )
        if fast_resp is not None:
            if laya_decision and hasattr(core, "laya_core") and core.laya_core:
                try:
                    verify_out = core.laya_core.verify_execution(
                        decision=laya_decision,
                        execution_result={"success": True, "message": fast_resp},
                        core=core
                    )
                    turn.metadata["laya_verification"] = verify_out
                except Exception as _ver_exc:
                    logger.debug("Laya verification note: %s", _ver_exc)

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, fast_resp)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(fast_resp, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(
                    turn.raw_input, fast_resp, intent=getattr(turn, "intent", "fast_path") or "fast_path", source=source
                )
            if getattr(core, "event_bus", None):
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": fast_resp})
            return fast_resp
        return None
