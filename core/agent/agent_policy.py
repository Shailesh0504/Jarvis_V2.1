"""Agent Policy - Execution safety limits, risk evaluation, and human-in-the-loop gates.
========================================================================================
Enforces strict boundaries on agent execution:
- Maximum retries per step (default 2) to prevent infinite loops.
- Maximum total plan steps (default 10) to bound multi-step workflows.
- Step and task timeouts.
- Dry run execution mode (via AGENT_DRY_RUN environment flag or config).
- Risk-based human confirmation gates (HIGH and CRITICAL operations).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Set

from .agent_state import AgentRiskLevel


@dataclass
class AgentPolicy:
    """Configurable execution safety policy for autonomous and guided agent tasks."""

    max_retries_per_step: int = 2
    max_total_steps: int = 10
    step_timeout_seconds: float = 15.0
    task_timeout_seconds: float = 60.0
    dry_run: bool = field(
        default_factory=lambda: os.getenv("AGENT_DRY_RUN", "false").strip().lower() in ("true", "1", "yes")
    )
    confirmation_risk_levels: Set[AgentRiskLevel] = field(
        default_factory=lambda: {AgentRiskLevel.HIGH, AgentRiskLevel.CRITICAL}
    )
    # Behaviour when a step needs approval but no interactive handler is attached.
    # "deny" is fail-safe: an unapproved risky step is never silently executed.
    on_missing_approval: str = "deny"

    def requires_confirmation(self, risk_level: AgentRiskLevel) -> bool:
        """Check if executing an action of the given risk level mandates user approval."""
        return risk_level in self.confirmation_risk_levels

    def resolve_missing_approval(self) -> bool:
        """Fail-safe decision when no interactive approval handler is available."""
        return str(self.on_missing_approval).strip().lower() == "allow"

    def can_retry_step(self, current_retries: int) -> bool:
        """Check if another retry attempt is permitted within policy bounds."""
        return current_retries < self.max_retries_per_step

    def is_step_count_within_limit(self, step_count: int) -> bool:
        """Check if plan step count satisfies upper complexity bounds."""
        return step_count <= self.max_total_steps
