# tests/test_logic_regressions.py
"""Regression coverage for audited control-flow and authorization defects."""

from unittest.mock import Mock

import pytest

from core.app import JarvisCore
from core.intent import Intent, IntentResult, IntentType
from core.permissions import PermissionGuard, PermissionLevel
from core.state import SystemState
from main import authenticate_cli_session
from plugins.manifest import PluginResult
from security.face_authenticator import FaceAuthenticator


def test_permission_levels_are_enforced_and_can_be_disabled():
    guard = PermissionGuard(default_level=PermissionLevel.EXECUTE, enforce=True)
    assert guard.is_action_allowed("system", "lock", PermissionLevel.EXECUTE)
    assert not guard.is_action_allowed("system", "shutdown", PermissionLevel.ADMIN)

    disabled = PermissionGuard(default_level=PermissionLevel.NONE, enforce=False)
    assert disabled.is_action_allowed("system", "shutdown", PermissionLevel.ADMIN)


def test_pipeline_exception_restores_idle_state():
    core = JarvisCore()
    core.initialize_subsystems()
    core.conversation_manager.process_incoming_input = Mock(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        core.process_input("hello")

    assert core.state_machine.current_state == SystemState.IDLE


def test_learned_workflow_reports_plugin_failure():
    core = JarvisCore()
    plugin_manager = Mock()
    plugin_manager.execute_action.return_value = PluginResult(success=False, error="step failed")
    core.initialize_subsystems(plugin_manager=plugin_manager)
    core.conversation_engine.process_conversation_turn = Mock(return_value=(False, None, None))
    core.dual_brain.route_and_execute = Mock(return_value=("NONE", None, None))
    core.agent.reasoner.is_complex_goal = Mock(return_value=False)
    core.classifier = Mock()
    core.classifier.classify.return_value = IntentResult(
        primary_intent=Intent(
            name="workflow",
            type=IntentType.COMMAND,
            raw_query="run it",
            entities={
                "workflow_data": {
                    "name": "broken",
                    "steps": [{"plugin": "demo", "action": "fail", "description": "Fail step"}],
                }
            },
        )
    )
    core.router.route_intent = Mock(return_value=("PLUGIN", "demo"))

    response = core.process_input("execute broken workflow xyz")

    assert "completed with errors" in response
    assert "step failed" in response


def test_cli_authentication_helper_does_not_bypass_enabled_gate(monkeypatch):
    core = Mock(config={"security": {"face_auth": {"enabled": True}}})
    monkeypatch.setattr(FaceAuthenticator, "authenticate_cli", Mock(return_value=Mock(success=False)))

    assert authenticate_cli_session(core) is False
    assert authenticate_cli_session(core, bypass_auth=True) is True


def test_pin_fallback_temporarily_locks_after_repeated_failures(tmp_path):
    auth = FaceAuthenticator(
        config={
            "security": {
                "face_auth": {
                    "master_pin": "9876",
                    "pin_max_attempts": 2,
                    "pin_lockout_seconds": 30,
                }
            }
        },
        profile_path=str(tmp_path / "profile.json"),
    )

    assert auth.verify_passcode("bad") is False
    assert auth.verify_passcode("bad") is False
    assert auth.verify_passcode("9876") is False
