# tests/test_plugin_permissions.py
"""Unit tests for Declarative Plugin Capability Permissions and Sandbox Enforcement."""

import pytest
from core.permissions import PermissionGuard, PluginCapability, PermissionDeniedError
from plugins.manifest import PluginManifest, PluginAction, PluginParameter, PermissionLevel
from plugins.pdf.plugin import PDFPlugin


def test_permission_guard_authorized_action():
    guard = PermissionGuard()
    # Allowed: pdf holding filesystem and office executes filesystem action
    assert guard.validate_plugin_action(
        plugin_name="pdf",
        action_name="read_pdf",
        required_capability="filesystem",
        declared_permissions=["filesystem", "office"]
    ) is True


def test_permission_guard_unauthorized_action_blocked():
    guard = PermissionGuard()
    # Blocked: pdf holding filesystem and office attempts system_control action
    with pytest.raises(PermissionDeniedError) as exc_info:
        guard.validate_plugin_action(
            plugin_name="pdf",
            action_name="shutdown_system",
            required_capability="system_control",
            declared_permissions=["filesystem", "office"]
        )
    assert "Security Violation" in str(exc_info.value)
    assert "system_control" in str(exc_info.value)


def test_plugin_safe_execute_blocks_unauthorized_action():
    """Verifies BasePlugin.safe_execute intercepts unauthorized capabilities."""
    pdf = PDFPlugin()
    # Inject a rogue action into manifest requiring 'microphone'
    pdf.manifest.actions.append(
        PluginAction(
            name="spy_mic",
            description="Unauthorized mic access",
            keywords=["spy mic"],
            required_capability="microphone"
        )
    )

    # Safe execute must block and return error without crashing
    res = pdf.safe_execute("spy_mic", {})
    assert res.success is False
    assert "Security Violation" in res.error
    assert "microphone" in res.error


def test_security_audit_checklist():
    guard = PermissionGuard()
    audit = guard.get_security_audit(["filesystem", "office"])

    assert audit["filesystem"] is True
    assert audit["office"] is True
    assert audit["system_control"] is False
    assert audit["microphone"] is False
    assert audit["camera"] is False
    assert audit["network"] is False
