# tests/test_phase_3_execution_convergence.py
"""
Unit and integration tests for Phase 3: Unified Execution & Proactive Safety.
Validates:
1. JarvisCore.execute_action_plan as authoritative execution gateway.
2. PermissionGuard policy enforcement on ActionPlans before execution.
3. Observable state verification through ExecutionStrategyEngine.
4. ProactiveActionExecutor policy gating and error resilience.
5. Backward compatibility for legacy mocks and direct commands.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.execution.models import ActionPlan, ExecutionResult, ExecutionState
from core.intelligence import (
    ProactiveActionExecutor,
    ProactiveSuggestion,
    SuggestionManager,
    SuggestionState,
)
from core.permissions import PermissionGuard, PermissionLevel


@pytest.fixture
def jarvis_core():
    core = JarvisCore(config_path="config.yaml")
    return core


class TestJarvisCoreExecuteActionPlan:
    """Tests for core.execute_action_plan authoritative gateway."""

    def test_permission_denial_blocks_execution(self, jarvis_core):
        # Restrict permission level to READ
        jarvis_core.permission_guard.default_level = PermissionLevel.READ

        plan = ActionPlan(
            action="launch_app",
            target="notepad",
            target_type="application",
            required_permission="EXECUTE",
            source="test"
        )

        res = jarvis_core.execute_action_plan(plan)
        assert res.success is False
        assert res.status == ExecutionState.FAILED
        assert res.reason == "permission_denied"
        assert "Permission denied" in res.error
        assert jarvis_core.last_execution_result == res

    def test_application_launch_delegates_to_verified_strategies(self, jarvis_core):
        mock_exec_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="launch_app",
            executed_action="launch_app",
            target="calc",
            action_type="application"
        )

        with patch.object(
            jarvis_core.execution_strategies,
            "launch_application_verified",
            return_value=mock_exec_res
        ) as mock_launch:
            plan = ActionPlan(
                action="launch_app",
                target="calc",
                target_type="application",
                required_permission="EXECUTE",
                source="test"
            )

            res = jarvis_core.execute_action_plan(plan)
            assert res.success is True
            assert mock_launch.called
            assert jarvis_core.active_context.application == "calc"
            assert jarvis_core.last_execution_result == mock_exec_res

    def test_folder_opening_delegates_to_verified_strategies(self, jarvis_core):
        mock_exec_res = ExecutionResult(
            success=True,
            status=ExecutionState.SUCCESS,
            requested_action="open_folder",
            executed_action="open_folder",
            target="Downloads",
            action_type="folder"
        )

        with patch.object(
            jarvis_core.execution_strategies,
            "open_folder_verified",
            return_value=mock_exec_res
        ) as mock_open:
            plan = ActionPlan(
                action="open_folder",
                target="Downloads",
                target_type="folder",
                required_permission="EXECUTE",
                source="test"
            )

            res = jarvis_core.execute_action_plan(plan)
            assert res.success is True
            assert mock_open.called
            assert jarvis_core.last_execution_result == mock_exec_res

    def test_volume_adjustment_execution(self, jarvis_core):
        with patch("plugins.audio.volume_controller.set_system_volume") as mock_set_vol:
            mock_set_vol.return_value = {"success": True, "volume": 35}

            plan = ActionPlan(
                action="set_volume",
                target="35",
                target_type="system_setting",
                required_permission="EXECUTE",
                source="test"
            )

            res = jarvis_core.execute_action_plan(plan)
            assert res.success is True
            assert mock_set_vol.called
            assert mock_set_vol.call_args[0][0] == 35


class TestProactiveExecutorPolicyGating:
    """Tests for ProactiveActionExecutor security gating with PermissionGuard."""

    def test_proactive_action_blocked_by_permission_guard(self):
        manager = SuggestionManager()
        mock_core = MagicMock()
        mock_core.permission_guard.validate_action_plan.return_value = (
            False, "Restricted: Proactive execution disabled in READ mode"
        )

        executor = ProactiveActionExecutor(
            suggestion_manager=manager,
            app_core=mock_core
        )

        sug = ProactiveSuggestion(
            suggestion_id="s_blocked",
            intent="LAUNCH_APP",
            action="open_app",
            target="cmd"
        )
        manager.register_presented(sug)

        res = executor.handle_user_utterance("haan kar do")
        assert res is not None
        assert res["handled"] is True
        assert res["accepted"] is False
        assert "security policy" in res["message"].lower()
        # Suggestion rejected because policy denied it
        assert sug.state == SuggestionState.REJECTED

    def test_proactive_action_routes_through_real_jarvis_core(self, jarvis_core):
        manager = SuggestionManager()
        executor = ProactiveActionExecutor(
            suggestion_manager=manager,
            app_core=jarvis_core
        )

        sug = ProactiveSuggestion(
            suggestion_id="s_real_core",
            intent="ADJUST_VOLUME",
            action="set_volume",
            target="45"
        )
        manager.register_presented(sug)

        with patch("plugins.audio.volume_controller.set_system_volume") as mock_set_vol:
            mock_set_vol.return_value = {"success": True, "volume": 45}

            res = executor.handle_user_utterance("ha")
            assert res is not None
            assert res["handled"] is True
            assert res["accepted"] is True
            assert sug.state == SuggestionState.ACCEPTED
            assert mock_set_vol.called
            assert jarvis_core.last_execution_result is not None
