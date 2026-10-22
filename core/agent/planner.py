# core/agent/planner.py
"""
Agent Planner formulating multi-step task decompositions with tool bindings and dependency graphs.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.agent.task_manager import AgentStep, AgentTask
from core.universal_window_resolver import UniversalAppNormalizer

logger = logging.getLogger("jarvis.agent.planner")


class AgentPlanner:
    """
    Decomposes user goals into an ordered sequence of executable AgentSteps,
    assigning the appropriate registered tools and dependency links.
    """

    # Multi-action pattern regexes
    RE_CONJUNCTION_SPLIT = re.compile(
        r"\s*(?:,\s*|\s+(?:aur|and|then|aur\s+phir|aur\s+fir|fir|phir|after\s+that)\s+)\s*",
        re.IGNORECASE
    )

    # Scenarios detection
    RE_FIND_LARGE_FILES = re.compile(
        r"\b(?:files?|scripts?)\s+(?:.*?lines?\s+(?:se\s+badi|greater\s+than|>)\s*(\d+))\b|"
        r"\b(\d+)\s+lines?\s+se\s+badi\b",
        re.IGNORECASE
    )

    def create_task_from_goal(self, user_goal: str, context: Optional[Dict[str, Any]] = None) -> AgentTask:
        """Alias for plan_task."""
        return self.plan_task(user_goal, context=context)

    def plan_task(self, user_goal: str, context: Optional[Dict[str, Any]] = None) -> AgentTask:
        """Formulates an AgentTask with decomposed steps for the given goal."""
        task = AgentTask(
            user_goal=user_goal,
            raw_input=user_goal,
            context=context or {},
        )

        lower = user_goal.lower().strip()

        # Scenario 3: Filesystem Large Files Query
        # "Is folder mein jo Python files 1500 lines se badi hain unki list banao"
        line_match = self.RE_FIND_LARGE_FILES.search(lower)
        if line_match and ("file" in lower or "python" in lower or "list" in lower):
            min_lines = 1500
            for g in line_match.groups():
                if g and g.isdigit():
                    min_lines = int(g)
                    break
            ext = ".py" if "python" in lower else ""
            step = AgentStep(
                step_num=1,
                description=f"Scan filesystem for source files exceeding {min_lines} lines",
                tool_name="filesystem.find_large_files",
                parameters={"directory": ".", "extension": ext, "min_lines": min_lines, "threshold_lines": min_lines},
                expected_outcome=f"List of files with >= {min_lines} lines",
                thought=f"Scanning repository for files over {min_lines} lines."
            )
            task.steps.append(step)
            return task

        # Scenario 4: Project Organization Goal
        if ("project" in lower or "folder" in lower) and ("organize" in lower or "organise" in lower):
            step1 = AgentStep(
                step_num=1,
                description="Inspect system environment and available memory",
                tool_name="system.get_info",
                parameters={},
                expected_outcome="System environment verified",
                thought="Checking system metrics before analyzing project files."
            )
            step2 = AgentStep(
                step_num=2,
                description="Audit project file structure and line counts",
                tool_name="filesystem.find_large_files",
                parameters={"directory": ".", "extension": ".py", "min_lines": 1000},
                depends_on=[step1.step_id],
                expected_outcome="Identified candidate large files needing organization",
                thought="Inspecting project files to identify organization opportunities."
            )
            task.steps.extend([step1, step2])
            return task

        # Compound Multi-Step Sequential Actions (e.g. "AntiGravity kholo aur usko minimize karo")
        clauses = self.RE_CONJUNCTION_SPLIT.split(lower)
        clauses = [c.strip() for c in clauses if c.strip()]

        if len(clauses) > 1:
            active_target = None
            prev_step_id = None

            for idx, clause in enumerate(clauses):
                step = self._plan_single_clause(clause, active_target=active_target)
                if step:
                    if prev_step_id:
                        step.depends_on.append(prev_step_id)
                    prev_step_id = step.step_id

                    # Track active target across deictic pronoun clauses ("isko", "use", "usko")
                    if step.parameters.get("target"):
                        active_target = step.parameters["target"]

                    task.steps.append(step)

            if task.steps:
                return task

        # Single clause fallback if routed to Agent Path
        step = self._plan_single_clause(lower, active_target=None)
        if step:
            task.steps.append(step)

        return task

    def _plan_single_clause(self, clause: str, active_target: Optional[str] = None) -> Optional[AgentStep]:
        """Maps an individual natural clause to an AgentStep."""
        normalizer = UniversalAppNormalizer()

        # Check for window operations (minimize, maximize, close, restore, focus)
        is_min = any(w in clause for w in ["minimize", "minimise", "chhota karo"])
        is_max = any(w in clause for w in ["maximize", "maximise", "bada karo"])
        is_close = any(w in clause for w in ["close", "band karo", "hatao", "exit"])
        is_restore = any(w in clause for w in ["restore", "wapas lao"])
        is_focus = any(w in clause for w in ["focus", "samne lao"])

        operation = None
        if is_min: operation = "minimize"
        elif is_max: operation = "maximize"
        elif is_close: operation = "close"
        elif is_restore: operation = "restore"
        elif is_focus: operation = "focus"

        if operation:
            # Check target in clause or inherit active_target
            words = clause.split()
            target = None
            for w in ["isko", "ise", "usko", "use", "this", "it", "yah", "yeh"]:
                if w in words and active_target:
                    target = active_target
                    break

            if not target:
                norm = UniversalAppNormalizer.normalize(clause)
                clean = re.sub(r"\b(?:minimize|minimise|maximize|maximise|close|band|karo|ko|restore|focus)\b", "", norm.clean).strip()
                target = clean or active_target or "current"

            return AgentStep(
                description=f"{operation.capitalize()} window '{target}'",
                tool_name="desktop.window_operation",
                parameters={"target": target, "operation": operation},
                expected_outcome=f"Window '{target}' state set to {operation}",
                thought=f"Performing {operation} on window '{target}'."
            )

        # Check for application launch
        is_open = any(w in clause for w in ["open", "kholo", "launch", "start", "chalao"])
        if is_open:
            norm = UniversalAppNormalizer.normalize(clause)
            clean = re.sub(r"\b(?:open|kholo|launch|start|chalao|ko|app|application)\b", "", norm.clean).strip()
            target = clean or "application"

            # Check if YouTube or web URL
            if "youtube" in target:
                return AgentStep(
                    description="Open YouTube in browser",
                    tool_name="browser.open_url",
                    parameters={"url_or_query": "https://www.youtube.com", "browser": "chrome"},
                    expected_outcome="YouTube opened in browser",
                    thought="Navigating to YouTube in browser."
                )

            return AgentStep(
                description=f"Launch application '{target}'",
                tool_name="desktop.open_application",
                parameters={"target": target},
                expected_outcome=f"Application '{target}' is running",
                thought=f"Resolving and launching application '{target}'."
            )

        # Check for system telemetry
        if any(w in clause for w in ["ram", "cpu", "system info", "specs"]):
            return AgentStep(
                description="Inspect system telemetry and resources",
                tool_name="system.get_info",
                parameters={},
                expected_outcome="System telemetry retrieved",
                thought="Retrieving operating system and memory telemetry."
            )

        return None
