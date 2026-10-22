# brain/response.py
"""Response generator creating articulate, context-aware Jarvis responses."""

import logging
from typing import Any, Dict, List, Optional

from core.planner import ExecutionPlan
from core.executor import StepExecutionResult
from .llm import BaseLLMProvider

logger = logging.getLogger("jarvis.brain.response")


class ResponseGenerator:
    """Generates natural language responses for chat and action executions."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    def chat(self, prompt: str, history: Optional[List[Dict[str, str]]] = None, memories: Optional[List[Dict[str, Any]]] = None) -> str:
        """Direct conversational response with memory context."""
        messages: List[Dict[str, str]] = []

        system_content = "You are JARVIS, the user's trusted AI friend. Be concise, intelligent, warm, and speak as an equal. Never call the user Boss."
        if memories:
            mem_str = "\n".join([f"- {m.get('key')}: {m.get('value')}" for m in memories])
            system_content += f"\n\nRelevant facts from long-term memory:\n{mem_str}"

        messages.append({"role": "system", "content": system_content})

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": prompt})

        if self.llm:
            return self.llm.chat(messages)

        return f"Ready and standing by, Boss! How can I assist you with '{prompt}'?"

    def generate_action_response(
        self,
        query: str,
        plan: Any = None,
        results: Any = None
    ) -> str:
        """Formulates a response strictly using verified execution state, never claiming unverified success."""
        from core.execution.models import ExecutionResult, ExecutionState

        # Check if single ExecutionResult passed
        if isinstance(results, ExecutionResult):
            return self.generate_verified_response(results)

        if not results:
            return "Task completed with no output, Boss."

        # If a list containing an ExecutionResult
        if isinstance(results, list) and len(results) == 1 and isinstance(results[0], ExecutionResult):
            return self.generate_verified_response(results[0])

        # Check overall success
        all_success = all(getattr(r, "success", False) for r in results)

        if not all_success:
            failures = [f"{getattr(r, 'plugin_name', 'action')}.{getattr(r, 'action_name', 'execute')}: {getattr(r, 'error', 'failed')}" for r in results if not getattr(r, "success", False)]
            return f"I encountered an issue executing your request: {'; '.join(failures)}"

        # If only one action result
        if len(results) == 1:
            res = results[0]
            data = getattr(res, "data", None)
            if isinstance(data, dict):
                # Clean formatting for common plugin outputs
                if "message" in data:
                    return str(data["message"])
                elif "datetime" in data:
                    return f"The current date and time is {data['datetime']}."
                elif "battery_percent" in data:
                    charging_str = "charging" if data.get("power_plugged") else "on battery"
                    return f"Battery is at {data['battery_percent']}% and currently {charging_str}."
                elif "files" in data:
                    files_list = data["files"]
                    return f"Found {len(files_list)} items: {', '.join(files_list[:5])}{'...' if len(files_list) > 5 else ''}."
                elif "status" in data:
                    return f"Action '{getattr(res, 'action_name', 'action')}' status: {data['status']}."
            elif isinstance(data, str) and data:
                return data
            act_name = getattr(res, "action_name", "action")
            return f"Action '{act_name}' execute ho gaya aur verify kar liya hai, Boss."

        # Multi-step summary
        actions_done = [f"{getattr(r, 'action_name', 'action')}" for r in results if getattr(r, "success", False)]
        return f"All {len(results)} steps completed successfully: {', '.join(actions_done)}."

    def generate_verified_response(self, result: Any) -> str:
        """Generates natural language response directly from an ExecutionResult."""
        from core.execution.models import ExecutionResult, ExecutionState

        if not isinstance(result, ExecutionResult):
            return str(getattr(result, "message", "Action completed."))

        target_name = result.target or result.requested_action

        if result.status == ExecutionState.SUCCESS:
            if result.data and "message" in result.data:
                return str(result.data["message"])
            return f"'{target_name}' execute ho gaya aur verify kar liya hai, Boss."

        elif result.status == ExecutionState.FAILED:
            err_detail = result.reason or result.error or "System state verification failed."
            return f"'{target_name}' poora nahi ho saka, Boss. Reason: {err_detail}"

        elif result.status == ExecutionState.UNVERIFIED:
            caveat = result.reason or "System state cannot be observed directly."
            return f"'{target_name}' command execute kar diya gaya hai, lekin direct verification possible nahi thi ({caveat})."

        elif result.status == ExecutionState.PARTIAL:
            return f"'{target_name}' partially execute hua hai. Some checks could not be verified."

        elif result.status == ExecutionState.CANCELLED:
            return f"Action '{target_name}' cancel kar diya gaya hai, Boss."

        return f"Action state: {result.status.value}."
