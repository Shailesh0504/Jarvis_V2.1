# tests/test_decision_core.py
"""Tests for Central DecisionCore, ActionPlan, and Policy/Confirmation utilities in Jarvis V2.1."""

import pytest
from core.confirmation import (
    ConfirmationType,
    classify_confirmation,
    is_affirmation,
    is_cancellation,
)
from core.context import RuntimeContext
from core.decision_core import DecisionCategory, DecisionCore
from core.execution.models import ActionPlan
from core.permissions import ActionRiskLevel, PermissionGuard, PermissionLevel


def test_action_plan_creation_and_attributes():
    """Verify ActionPlan structure, defaults, and dictionary export."""
    plan = ActionPlan(
        action="launch_app",
        target="antigravity",
        target_type="application",
        resolver="local_application",
        parameters={"is_new": False},
        required_permission="EXECUTE",
        risk_level="LOW",
        verification_strategy="process_running",
    )
    assert plan.action == "launch_app"
    assert plan.target == "antigravity"
    assert plan.risk_level == "LOW"
    assert plan.verification_strategy == "process_running"
    assert not plan.confirmation_required

    d = plan.to_dict()
    assert d["action"] == "launch_app"
    assert d["target"] == "antigravity"
    assert "plan_id" in d


def test_confirmation_patterns_multilingual():
    """Verify centralized affirmation and cancellation detection."""
    # English
    assert is_affirmation("yes")
    assert is_affirmation("sure")
    assert is_affirmation("go ahead")
    assert is_cancellation("no")
    assert is_cancellation("cancel")
    assert is_cancellation("don't")

    # Hindi / Hinglish
    assert is_affirmation("haan")
    assert is_affirmation("kar do")
    assert is_affirmation("bilkul")
    assert is_affirmation("wahi chalao")
    assert is_cancellation("nahi")
    assert is_cancellation("mat karo")
    assert is_cancellation("rehne do")
    assert is_cancellation("dusri wali")

    # Enum classification
    assert classify_confirmation("haan kar do") == ConfirmationType.AFFIRMATIVE
    assert classify_confirmation("nahi rehne do") == ConfirmationType.NEGATIVE
    assert classify_confirmation("open chrome") == ConfirmationType.UNSPECIFIED


def test_policy_risk_evaluation():
    """Verify policy risk levels and confirmation gating."""
    guard = PermissionGuard()

    # Critical destructive actions require confirmation
    risk, confirm = guard.evaluate_action_risk("shutdown")
    assert risk == ActionRiskLevel.CRITICAL
    assert confirm is True

    risk, confirm = guard.evaluate_action_risk("format_disk")
    assert risk == ActionRiskLevel.CRITICAL
    assert confirm is True

    # High risk actions
    risk, confirm = guard.evaluate_action_risk("delete_file", target="notes.txt")
    assert risk == ActionRiskLevel.HIGH
    assert confirm is True

    # Low risk routine actions
    risk, confirm = guard.evaluate_action_risk("launch_app", target="chrome")
    assert risk == ActionRiskLevel.LOW
    assert confirm is False


def test_decision_core_plan_action():
    """Verify DecisionCore translates requests into verified ActionPlan instances."""
    rc = RuntimeContext()
    rc.desktop.set_application("vlc")
    guard = PermissionGuard()
    dc = DecisionCore(permission_guard=guard, runtime_context=rc)

    plan = dc.plan_action(
        action="launch_app",
        target="antigravity",
        target_type="application",
        resolver="local_application",
    )
    assert plan.action == "launch_app"
    assert plan.target == "antigravity"
    assert plan.verification_strategy == "process_running"
    assert plan.risk_level == "LOW"
    assert plan.context_key == "vlc"
    assert guard.validate_action_plan(plan) is True

    # Plan a destructive action
    destr_plan = dc.plan_action(
        action="shutdown",
        target="system",
        target_type="system",
        required_permission="ADMIN",
    )
    assert destr_plan.risk_level == "CRITICAL"
    assert destr_plan.confirmation_required is True
    assert destr_plan.confirmation_prompt is not None


def test_jarvis_core_has_decision_core():
    """Verify JarvisCore initializes DecisionCore."""
    from core.app import JarvisCore
    core = JarvisCore()
    assert hasattr(core, "decision_core")
    assert isinstance(core.decision_core, DecisionCore)
    assert core.decision_core.runtime_context is core.runtime_context
