# tests/test_execution_strategy_risk_gating.py
"""
Unit and Integration Tests for Execution Strategy Pre-Execution Risk Gating (Gap 3).
Validates:
1. Low-risk actions (open folder, open app, open website, normal window close) execute freely with ALLOW.
2. High-risk actions (delete file, kill process) and Critical actions (shutdown, reboot) halt execution
   and require confirmation with appropriate prompt.
3. Pre-confirmed actions (parameters={'confirmed': True}) bypass the gate safely and execute.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.execution.models import ExecutionResult, ExecutionState
from core.execution.strategies import ExecutionStrategyEngine
from core.policy.capability_policy import CapabilityPolicy, PolicyDecision


@pytest.fixture
def strategy_engine():
    policy = CapabilityPolicy(enforce=True)
    engine = ExecutionStrategyEngine(capability_policy=policy)
    return engine


class TestExecutionStrategyRiskGating:
    """Validates pre-execution risk gating on ExecutionStrategyEngine."""

    def test_low_risk_action_allowed_without_confirmation(self, strategy_engine):
        # Normal open folder / app / website operations
        res = strategy_engine.check_pre_execution_risk(action="open", target="notepad")
        assert res is None  # None indicates ALLOW, safe to proceed

        res_folder = strategy_engine.check_pre_execution_risk(action="open_folder", target="downloads")
        assert res_folder is None

        res_web = strategy_engine.check_pre_execution_risk(action="open_website", target="google.com")
        assert res_web is None

        res_close = strategy_engine.check_pre_execution_risk(action="close", target="notepad")
        assert res_close is None

    def test_high_risk_action_blocked_requiring_confirmation(self, strategy_engine):
        # Delete file
        res = strategy_engine.check_pre_execution_risk(action="delete", target="important_data.csv")
        assert res is not None
        assert res.success is False
        assert res.requires_confirmation is True
        assert res.confirmation_prompt is not None
        assert "important_data.csv" in res.confirmation_prompt or "delete" in res.confirmation_prompt.lower()

        # Kill process
        res_kill = strategy_engine.check_pre_execution_risk(action="kill", target="chrome.exe")
        assert res_kill is not None
        assert res_kill.success is False
        assert res_kill.requires_confirmation is True

    def test_critical_action_blocked_requiring_confirmation(self, strategy_engine):
        # Shutdown system
        res_shutdown = strategy_engine.check_pre_execution_risk(action="shutdown", target="system")
        assert res_shutdown is not None
        assert res_shutdown.success is False
        assert res_shutdown.requires_confirmation is True
        assert "Caution:" in res_shutdown.confirmation_prompt or "shutdown" in res_shutdown.confirmation_prompt.lower()

        # Format drive
        res_format = strategy_engine.check_pre_execution_risk(action="format", target="c:")
        assert res_format is not None
        assert res_format.requires_confirmation is True

    def test_confirmed_sensitive_action_allowed(self, strategy_engine):
        # Passing confirmed=True allows execution past the pre-flight gate
        res_confirmed = strategy_engine.check_pre_execution_risk(
            action="shutdown", target="system", parameters={"confirmed": True}
        )
        assert res_confirmed is None

        res_del_confirmed = strategy_engine.check_pre_execution_risk(
            action="delete", target="temp.txt", parameters={"confirmed": True}
        )
        assert res_del_confirmed is None

    def test_close_target_verified_force_kill_pre_execution_gating(self, strategy_engine):
        # Forceful kill action triggers risk gate
        res = strategy_engine.close_target_verified(
            target="chrome",
            action="kill",
        )
        assert res.success is False
        assert res.requires_confirmation is True
        assert "kill" in res.requested_action or "blocked" in res.executed_action

    def test_execute_sensitive_action_verified_flow(self, strategy_engine):
        mock_handler = MagicMock(return_value={"files_deleted": 3})

        # 1. Unconfirmed attempt: blocked by gate, handler NOT called
        res_unconfirmed = strategy_engine.execute_sensitive_action_verified(
            action="delete", target="cache_logs", handler=mock_handler
        )
        assert res_unconfirmed.success is False
        assert res_unconfirmed.requires_confirmation is True
        mock_handler.assert_not_called()

        # 2. Confirmed attempt: allowed past gate, handler executes
        res_confirmed = strategy_engine.execute_sensitive_action_verified(
            action="delete", target="cache_logs", parameters={"confirmed": True}, handler=mock_handler
        )
        assert res_confirmed.success is True
        assert res_confirmed.status == ExecutionState.SUCCESS
        assert res_confirmed.data == {"files_deleted": 3}
        mock_handler.assert_called_once()

    def test_jarvis_core_execute_action_plan_pre_execution_gating(self):
        from core.app import JarvisCore
        from core.execution.models import ActionPlan
        core = JarvisCore(config_path="config.yaml")

        # Unconfirmed sensitive action plan (shutdown)
        plan = ActionPlan(
            action="shutdown",
            target="system",
            target_type="system",
            parameters={},
            source="test"
        )
        res = core.execute_action_plan(plan)
        assert res.success is False
        assert res.requires_confirmation is True
        assert core.last_execution_result == res
        assert "shutdown" in (res.confirmation_prompt or "").lower() or "caution" in (res.confirmation_prompt or "").lower()

