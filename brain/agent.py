# brain/agent.py
"""Autonomous Agent Reasoning Engine for goal decomposition and ReAct planning."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.planner import PlanStep
from core.permissions import PermissionLevel
from .llm import BaseLLMProvider

logger = logging.getLogger("jarvis.brain.agent")


class AgentReasoner:
    """Understands high-level user goals and formulates dynamic multi-step ReAct plans."""

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        plugin_manager: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        experience_system: Optional[Any] = None
    ):
        self.llm = llm_provider
        self.plugin_manager = plugin_manager
        self.memory_manager = memory_manager
        self.experience_system = experience_system or getattr(memory_manager, "experience", None)

    def get_experience_context(self, user_goal: str):
        """Retrieves past experience context for the goal."""
        if self.experience_system:
            return self.experience_system.retrieve_experience(user_goal)
        elif hasattr(self.memory_manager, "experience") and self.memory_manager.experience:
            return self.memory_manager.experience.retrieve_experience(user_goal)
        return None

    def is_complex_goal(self, query: str) -> bool:
        """Determines if the query is a multi-step autonomous goal requiring agent orchestration."""
        lower = query.lower()

        # Regex combinations for multi-step goals
        goal_patterns = [
            r"(?:kal|recent|latest|find|search|open|khojo)\s+.*?(?:excel|file|sheet|csv|pdf|document)\s+.*?(?:total|sum|calculate|avg|average|nikalo|batao|summarize|read)",
            r"(?:calculate|find|nikalo|batao)\s+.*?(?:total|sum|average|avg)\s+.*?(?:sales|revenue|amount|column|in|of)",
            r"(?:open\s+.*?and\s+.*?|aur\s+.*?nikalo|karo\s+aur\s+)",
            r"(?:find\s+recent\s+.*?and\s+.*?)"
        ]

        for pat in goal_patterns:
            if re.search(pat, lower):
                return True

        # Multi-intent triggers & temporal connectors
        agent_indicators = [
            "kal jo", "recent file", "last file", "open karo aur", "khojo aur", "total nikalo",
            "sum nikalo", "calculate karo", "open and calculate",
            "summarize and", "file me se", "folder me se",
            "sales column", "column total",
            " and then ", " then ", " baad me "
        ]

        for ind in agent_indicators:
            if ind in lower:
                return True

        return False

    def formulate_plan(self, user_goal: str) -> List[PlanStep]:
        """
        Decomposes the high-level user goal into an executable sequence of tool actions.
        Prioritizes proven procedural memories from previous experience.
        """
        # 1. Experience Retrieval Layer: check for proven historical procedures
        exp_ctx = self.get_experience_context(user_goal)
        if exp_ctx and exp_ctx.procedures:
            top_proc = exp_ctx.procedures[0]
            if top_proc.get("confidence", 0.0) >= 0.85 and top_proc.get("steps"):
                logger.info("AgentReasoner: Continuing from verified previous experience procedure for '%s'", user_goal)
                steps = []
                for s in top_proc["steps"]:
                    steps.append(PlanStep(
                        plugin_name=s.get("plugin", ""),
                        action_name=s.get("action", ""),
                        parameters=dict(s.get("parameters", {})),
                        description=s.get("description", f"{s.get('plugin')}.{s.get('action')}")
                    ))
                return steps

        lower = user_goal.lower()
        steps: List[PlanStep] = []

        # Scenario 1: Recent Excel / CSV file lookup + Column Calculation
        # Example: "kal jo Excel file banayi thi usko open karo aur sales column ka total nikalo"
        if ("excel" in lower or "sheet" in lower or "csv" in lower or "sales" in lower or "file" in lower) and \
           ("total" in lower or "sum" in lower or "calculate" in lower or "nikalo" in lower or "average" in lower or "avg" in lower):

            # Extract column target
            col_target = "sales"
            if "sales" in lower:
                col_target = "sales"
            elif "revenue" in lower:
                col_target = "revenue"
            elif "total" in lower:
                col_target = "total"
            elif "amount" in lower:
                col_target = "amount"
            elif "price" in lower:
                col_target = "price"
            else:
                m = re.search(r"(\w+)\s+(?:column|ka total|ki sum|of)", lower)
                if m:
                    col_target = m.group(1)

            # Extract operation
            operation = "sum"
            if "average" in lower or "avg" in lower or "ausat" in lower:
                operation = "avg"
            elif "count" in lower or "kitne" in lower:
                operation = "count"
            elif "max" in lower or "highest" in lower or "sabse jyada" in lower:
                operation = "max"
            elif "min" in lower or "lowest" in lower or "sabse kam" in lower:
                operation = "min"

            # Step 1: Find recent excel/csv file
            step_find = PlanStep(
                plugin_name="files",
                action_name="find_recent_files",
                parameters={"extension": "xlsx,csv,xls", "directory": ".", "limit": 5},
                required_permission=PermissionLevel.READ,
                description="Search for recently modified Excel/spreadsheet files"
            )
            steps.append(step_find)

            # Step 2: Calculate column using path from Step 1
            step_calc = PlanStep(
                plugin_name="excel",
                action_name="calculate_column",
                parameters={
                    "path": "$files.find_recent_files.latest_file",
                    "column_name": col_target,
                    "operation": operation
                },
                required_permission=PermissionLevel.READ,
                description=f"Calculate {operation.upper()} of column '{col_target}' in the discovered file",
                depends_on=[step_find.step_id]
            )
            steps.append(step_calc)

            return steps

        # Scenario 2: Search recent PDF and summarize
        # Example: "kal jo pdf aayi thi usko summarize karo"
        if "pdf" in lower and ("summarize" in lower or "summary" in lower or "read" in lower or "batao" in lower):
            step_find = PlanStep(
                plugin_name="files",
                action_name="find_recent_files",
                parameters={"extension": "pdf", "directory": ".", "limit": 5},
                required_permission=PermissionLevel.READ,
                description="Search for recently received PDF documents"
            )
            steps.append(step_find)

            step_summary = PlanStep(
                plugin_name="pdf",
                action_name="summarize_pdf",
                parameters={"path": "$files.find_recent_files.latest_file"},
                required_permission=PermissionLevel.READ,
                description="Extract summary from the latest PDF document",
                depends_on=[step_find.step_id]
            )
            steps.append(step_summary)
            return steps

        # Scenario 3: General multi-step decomposition via LLM if provider is active
        if self.llm and type(self.llm).__name__ != "MockLLMProvider":
            return self._plan_with_llm(user_goal)

        return steps

    def _plan_with_llm(self, goal: str) -> List[PlanStep]:
        """Prompts LLM to produce a structured multi-step action plan."""
        try:
            plugin_schema = self.plugin_manager.get_plugins_summary_json() if self.plugin_manager else ""
            prompt = f"""Given the user goal: "{goal}"
Available tools:
{plugin_schema}

Decompose this into a JSON array of tool execution steps:
[
  {{
    "plugin": "plugin_name",
    "action": "action_name",
    "parameters": {{"param": "value_or_$prev_step.result"}},
    "description": "Short explanation"
  }}
]
Output strictly valid JSON array."""
            raw = self.llm.generate(prompt=prompt)
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                steps = []
                for item in parsed:
                    step = PlanStep(
                        plugin_name=item.get("plugin", ""),
                        action_name=item.get("action", ""),
                        parameters=item.get("parameters", {}),
                        description=item.get("description", "")
                    )
                    steps.append(step)
                return steps
        except Exception as e:
            logger.error(f"LLM Agent planning failed: {e}")
        return []

    def synthesize_agent_response(self, goal: str, steps_trace: List[Dict[str, Any]]) -> str:
        """Synthesizes an intelligent, context-aware final response from the agent's observation trace."""
        if not steps_trace:
            return "I could not identify the steps required to complete that goal, Boss."

        # Check if Excel calculation succeeded
        for trace in steps_trace:
            if trace.get("plugin") == "excel" and trace.get("action") == "calculate_column":
                data = trace.get("data", {})
                if isinstance(data, dict) and data.get("formatted_result"):
                    file_name = data.get("file", "the spreadsheet")
                    col_name = data.get("column", "target column")
                    op = data.get("operation", "sum").upper()
                    result_val = data.get("formatted_result")
                    count = data.get("rows_count", 0)

                    # Polite Hinglish / English natural agent response
                    if "kal" in goal.lower() or "recent" in goal.lower():
                        return f"Maine recent file '{file_name}' check ki. Usme '{col_name}' column ka Total {op} **{result_val}** hai (across {count} entries)."
                    return f"In file '{file_name}', the calculated {op} for column '{col_name}' is **{result_val}**."

        # Check for general successful results
        successful_steps = [t for t in steps_trace if t.get("success")]
        if successful_steps:
            last_step = successful_steps[-1]
            data = last_step.get("data", {})
            if isinstance(data, dict) and "message" in data:
                return str(data["message"])
            elif isinstance(data, str) and data:
                return data

        return "Maine aapka task step-by-step complete kar diya hai, Boss."
