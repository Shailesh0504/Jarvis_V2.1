"""Agent Replanner formulating alternative plans when step recovery is exhausted.
================================================================================
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from core.agent.task_manager import AgentStep, AgentTask

logger = logging.getLogger("jarvis.agent.replanner")


class AgentReplanner:
    """Formulates alternative step sequences when a step fails permanently,
    avoiding repetitive loops and adapting the task graph dynamically.
    """

    def replan_step(self, step: AgentStep, failure_reason: str = "") -> Optional[AgentStep]:
        """Formulates a single alternative step for a failed step."""
        task = AgentTask(steps=[step])
        alts = self.replan(task, step)
        return alts[0] if alts else None

    def replan(self, task: AgentTask, failed_step: AgentStep) -> List[AgentStep]:
        """Generates substitute steps for the remaining pending portion of the task."""
        logger.info("Replanning task '%s' due to failure in step '%s'", task.task_id, failed_step.step_id)

        # 1. Alternative for failed Application Launch: fallback to browser web app
        if failed_step.tool_name == "desktop.open_application":
            target = failed_step.parameters.get("target", "")
            logger.info("Replanning: Substituting desktop launch with web application search for '%s'", target)
            if "youtube" in target.lower():
                url = "https://www.youtube.com"
            else:
                url = f"https://www.google.com/search?q={target}"

            fallback_step = AgentStep(
                description=f"Search and open web version for '{target}'",
                tool_name="browser.open_url",
                parameters={"url": url, "url_or_query": url},
                expected_outcome=f"Web search for '{target}' opened in browser",
                thought=f"Application '{target}' could not be launched locally; falling back to web browser."
            )
            return [fallback_step]

        # 2. Alternative for failed File Read: search directory
        if failed_step.tool_name == "filesystem.read_file":
            file_path = failed_step.parameters.get("file_path", "")
            base_name = file_path.split("/")[-1].split("\\")[-1]
            logger.info("Replanning: Substituting exact file read with file search for '%s'", base_name)
            search_step = AgentStep(
                description=f"Search filesystem for file '{base_name}'",
                tool_name="filesystem.find_large_files",
                parameters={"directory": ".", "extension": os.path.splitext(base_name)[1] or ".py"},
                expected_outcome=f"Matching files located for '{base_name}'",
                thought=f"Exact file '{file_path}' was missing; searching workspace for matching filename."
            )
            return [search_step]

        # 3. Default: return empty list
        return []
