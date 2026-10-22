# tests/test_capability_policy.py
import pytest
from core.permissions import ActionRiskLevel
from core.policy import CapabilityPolicy, PolicyDecision


def test_capability_policy_low_risk_allow():
    policy = CapabilityPolicy()
    res = policy.evaluate(action="open", target="chrome")
    assert res.decision == PolicyDecision.ALLOW
    assert res.risk_tier == ActionRiskLevel.LOW


def test_capability_policy_high_risk_confirm():
    policy = CapabilityPolicy()
    res = policy.evaluate(action="delete", target="important_report.docx")
    assert res.decision == PolicyDecision.CONFIRM
    assert res.risk_tier == ActionRiskLevel.HIGH
    assert res.confirmation_prompt is not None


def test_capability_policy_critical_risk_confirm():
    policy = CapabilityPolicy()
    res = policy.evaluate(action="shutdown", target="system")
    assert res.decision == PolicyDecision.CONFIRM
    assert res.risk_tier == ActionRiskLevel.CRITICAL
    assert "critical" in res.reason.lower()


def test_capability_policy_preconfirmed_allow():
    policy = CapabilityPolicy()
    res = policy.evaluate(action="delete", target="temp.txt", parameters={"confirmed": True})
    assert res.decision == PolicyDecision.ALLOW
    assert res.risk_tier == ActionRiskLevel.HIGH
