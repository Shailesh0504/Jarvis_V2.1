# JARVIS — AGENT ARCHITECTURE SPECIFICATION
*Version 2.5 — Desktop Personal AI Agent / Computer Agent Layer*
*Author: DeepMind Antigravity Pair-Programming Agent*

---

## 1. Executive Summary

This document specifies the architectural design and operational contracts of the **JARVIS Agent Layer**, which elevates Jarvis from a command-execution assistant into an autonomous **Personal AI Agent and Computer Agent**.

The design adheres to the non-negotiable principle: **Zero Rewrite / Zero Regression**.
- Deterministic, low-latency commands (*"Chrome kholo"*, *"volume 50 karo"*, *"AntiGravity minimize karo"*) route through the **Fast Path** ($< 15\text{ ms}$).
- Multi-step, compound, goal-oriented, or ambiguous requests route through the **Agent Path** (`Understand -> Formulate Goal -> Plan -> Decompose -> Select Tools -> Execute -> Observe -> Verify -> Recover/Replan -> Complete -> Remember`).
- Existing capabilities (`WindowManager`, `UniversalWindowResolver`, `WindowsAppResolver`, `FilesystemOperations`, `BrowserTabManager`, `ExecutionVerificationLayer`, `MemoryManager`) are encapsulated as tools within the `ToolRegistry` rather than re-implemented.

---

## 2. High-Level Architecture: Fast Path vs. Agent Path

```
                                USER REQUEST
                                     │
                                     ▼
                            REQUEST CLASSIFIER
                        (6 Categories, Regex + NLP)
                               /            \
                              /              \
                    FAST PATH                  AGENT PATH
           (Direct Command, Info, Chat)    (Multi-step, Goal, Ambiguous)
                       │                              │
                       ▼                              ▼
                 FAST DISPATCH                AGENT ORCHESTRATOR
           (FastPathEngine / Dialog)                  │
                       │                              ▼
                       │                    GOAL & PLAN FORMATION
                       │                     (Task Decomposition)
                       │                              │
                       │                              ▼
                       │                      TOOL / SKILL SELECTION
                       │                       (ToolRegistry SSOT)
                       │                              │
                       │                              ▼
                       │                     STEP EXECUTION LOOP
                       │                       (ReAct + Bounds)
                       │                              │
                       │                              ▼
                       │                       REAL OBSERVATION
                       │                    (Process, HWND, State)
                       │                              │
                       │                              ▼
                       │                     UNIVERSAL VERIFICATION
                       │                    (ExecutionVerification)
                       │                              │
                       │                     ┌────────┴────────┐
                       │                  SUCCESS           FAILURE
                       │                     │                 │
                       │                     │                 ▼
                       │                     │         RECOVERY ENGINE
                       │                     │      (Adapt/Retry/Replan)
                       │                     │                 │
                       │                     └────────┬────────┘
                       │                              │
                       │                              ▼
                       │                      MEMORY / LEARNING
                       │                   (Episodic / Experience)
                       │                              │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
                                FINAL RESPONSE
```

---

## 3. Request Classification Engine

The `RequestClassifier` parses raw user speech and assigns one of six deterministic categories:

| Category | Typical Utterance Example | Routing Path | Primary Action |
|---|---|---|---|
| `DIRECT_COMMAND` | *"Chrome kholo"*, *"Volume 50 karo"* | **FAST PATH** | Direct execution in $< 15\text{ ms}$ |
| `INFORMATION_REQUEST` | *"RAM kitni hai?"*, *"Windows version kya hai?"* | **FAST PATH** | Query knowledge / system engine |
| `CONVERSATIONAL` | *"Kaise ho?"*, *"Tum kaun ho?"* | **FAST PATH** | Conversational gating policy |
| `MULTI_STEP_TASK` | *"AntiGravity kholo aur usko minimize karo"* | **AGENT PATH** | Decompose into sequential steps |
| `GOAL_ORIENTED_TASK` | *"Python files 1500 lines se badi hain unki list banao"* | **AGENT PATH** | Formulate autonomous multi-step plan |
| `AMBIGUOUS_TASK` | *"Isko thik karo."*, *"Fix this issue"* | **AGENT PATH** | Resolve demonstrative pronouns or ask |

---

## 4. Agent Lifecycle State Machine

The Agent operates under an explicit finite state machine (`AgentState`):

```
IDLE
 │
 ▼
UNDERSTANDING ──► WAITING_FOR_CLARIFICATION (Ambiguity / User Approval)
 │
 ▼
PLANNING
 │
 ▼
EXECUTING ◄────────┐
 │                 │
 ▼                 │
OBSERVING          │ (Alternative Action)
 │                 │
 ▼                 │
VERIFYING          │
 ├── SUCCESS ──────┼──► [Next Step]
 └── FAILURE       │
      │            │
      ▼            │
  RECOVERING ──────┘
      │
      ▼
  REPLANNING
 │
 ▼
COMPLETED / FAILED / CANCELLED
```

---

## 5. Tool Registry & Single Source of Truth

The `ToolRegistry` exposes system capabilities as typed, bounded agent tools without duplicating logic:

| Tool Name | Underlying Single-Source Subsystem | Risk Level |
|---|---|---|
| `desktop.open_application` | `WindowsAppResolver` & `ExecutionStrategyEngine` | `LOW` |
| `desktop.window_operation` | `WindowManager` (`plugins.windows.window_manager`) | `LOW` |
| `browser.open_url` | `UniversalTargetDiscoveryEngine` / Web Browser | `LOW` |
| `filesystem.find_large_files` | Python standard library file scanners | `SAFE` |
| `filesystem.read_file` | Safe local filesystem reader with line bounds | `SAFE` |
| `system.get_info` | `psutil` + `platform` OS telemetry | `SAFE` |
| `system.set_volume` | `plugins.audio.volume_controller.set_system_volume` | `LOW` |

---

## 6. Observation and Universal Verification

Every action step enforces the invariant:
$$\text{Execution} \longrightarrow \text{Observation} \longrightarrow \text{Verification} \longrightarrow \text{State Truth}$$

1. **`AgentObserver`**:
   - Inspects foreground window handle (`HWND`), title, and process name.
   - Matches running processes and windows using `UniversalAppNormalizer`.
   - Checks minimized, maximized, and visible flags via Windows API.
2. **`AgentVerifier`**:
   - Reuses `ExecutionVerificationLayer`.
   - Verifies whether an app launched by confirming its OS process and window.
   - Verifies minimization by asserting that the target window has the `IsIconic` bit set.

---

## 7. Failure Recovery and Replanning

When a step fails, the agent does not repeat blind loops:
- **`ALREADY_IN_STATE`**: If an app was commanded to open but its process already exists, the recovery engine adapts by issuing a `restore` or `focus` window operation.
- **`TRANSIENT_DELAY`**: If an application takes time to render, the agent applies backoff retries bounded by `max_retries_per_step = 2`.
- **`WRONG_TARGET` / `RESOURCE_MISSING`**: The `AgentReplanner` substitutes alternative tools (e.g. web version fallback if desktop executable is missing).

---

## 8. Safety Policies and Human-in-the-Loop

1. **Configurable Execution Policy (`AgentPolicy`)**:
   - `max_retries_per_step`: 2 (strictly prevents infinite loops).
   - `max_total_steps`: 10 (bounds task graph depth).
   - `step_timeout_seconds`: 15.0s.
   - `task_timeout_seconds`: 60.0s.
2. **Human-in-the-Loop Confirmation Gates**:
   - Any action tagged with `AgentRiskLevel.HIGH` or `CRITICAL` pauses the agent in `WAITING_FOR_CLARIFICATION` until explicit approval is granted.
3. **Dry-Run Mode (`AGENT_DRY_RUN=true`)**:
   - Simulates plan generation and decomposes steps without executing OS mutations.
4. **Cancellation and Resume**:
   - User phrases (*"stop"*, *"ruk jao"*, *"task cancel karo"*) transition state to `CANCELLED` and safely abort active plans.

---

## 9. End-to-End Scenarios Validation

| Scenario | Input Command | Resolution & Execution Path |
|---|---|---|
| **Scenario 1** | *"Chrome kholo"* | Fast Path $\rightarrow$ Direct app resolver $\rightarrow$ $< 15\text{ ms}$ response |
| **Scenario 2** | *"AntiGravity kholo aur usko minimize karo"* | Multi-step task $\rightarrow$ Step 1: Launch AntiGravity $\rightarrow$ Step 2: Minimize AntiGravity (deictic pronoun "usko" resolved to AntiGravity) |
| **Scenario 3** | *"Is folder mein jo Python files 1500 lines se badi hain unki list banao"* | Goal-oriented task $\rightarrow$ `filesystem.find_large_files` $\rightarrow$ Reports count and top files |
| **Scenario 4** | *"Is project ko organize karo"* | Goal-oriented task $\rightarrow$ Step 1: System inspection $\rightarrow$ Step 2: File structure audit $\rightarrow$ Reports recommendations |
