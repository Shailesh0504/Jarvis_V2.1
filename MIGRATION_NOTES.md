# JARVIS V2.1 — MIGRATION & EXTENSION NOTES
_Developer Guide for Migrating Existing Components and Extending the Hardened Production Architecture_

---

## 1. Migration Overview & Backward Compatibility

The Jarvis V2.1 Architecture Hardening is **100% backward-compatible** with existing plugins, legacy intent parsers, and external scripts. No breaking changes have been introduced to public APIs on `JarvisCore` or `PluginBase`.

Existing plugins continue to execute normally through `CommandRouter` and `PluginManager`. However, plugins can now optionally benefit from automatic closed-loop physical verification, unified error recovery, and cooperative cancellation tokens.

---

## 2. Developer Extension Guide

### 2.1 Adopting Standardized Contracts (`core/contracts/`)
When building new capabilities or custom handlers, use the typed contracts rather than unstructured dictionaries:

```python
from core.contracts import UserRequest, IntentResult, Target, ExecutionPlan, ExecutionStep

# Construct typed user request
request = UserRequest(
    raw_text="open notepad",
    normalized_text="open notepad",
    source="voice",
    is_authenticated=True
)

# Define an execution step
step = ExecutionStep(
    step_id="step_1",
    action="launch",
    parameters={"app_name": "notepad"}
)
```

### 2.2 Registering Capabilities with `CapabilityPolicy`
To assign a risk tier and confirmation policy to a new feature:

```python
from core.policy import CapabilityPolicy, RiskTier, PolicyDecision

# Query capability risk
policy = CapabilityPolicy()
decision = policy.evaluate("system.delete_logs", user_confirmed=False)

if decision == PolicyDecision.CONFIRM:
    # Trigger dialog confirmation
    pass
elif decision == PolicyDecision.ALLOW:
    # Execute immediately
    pass
```

### 2.3 Integrating with `CancellationToken`
To make custom long-running loops cooperative and responsive to user barge-in (`"stop"`, `"cancel"`):

```python
from core.cancellation import CancellationToken

def my_long_running_task(cancel_token: CancellationToken):
    for item in large_dataset:
        if cancel_token.is_cancelled:
            logger.info("Task aborted by user barge-in.")
            break
        # Process item...
```

### 2.4 Registering Physical Verification for Custom Handlers
To ensure custom actions comply with the **Zero-False-Success** invariant:

```python
from core.verification_layer import UniversalVerificationLayer

verifier = UniversalVerificationLayer()
result = verifier.verify(
    target_type="application",
    target_name="notepad",
    expected_state="running"
)

if result.is_verified:
    # State confirmed on Windows OS
    pass
```

---

## 3. Deployment & Environment Verification Checklist

Before deploying changes to production environments:
1. Run the Golden Dataset replay:
   ```bash
   pytest tests/golden/test_golden_replay.py -v
   ```
2. Verify production contracts and state machine:
   ```bash
   pytest tests/test_production_contracts.py tests/test_request_state_machine.py -v
   ```
3. Verify closed-loop physical verification suite:
   ```bash
   pytest tests/test_phase_3_b3b_plugin_physical_verification.py -v
   ```
4. Verify sub-300ms latency compliance via `PipelineLatencyTracker`.
