# JARVIS — Developer & Contributor Guide

This guide provides setup instructions, coding conventions, architectural invariants, and workflow procedures for contributing to Jarvis.

---

## 1. Environment Setup

### Prerequisites
- Windows 10 or 11 (64-bit)
- Python 3.12.0
- Working microphone and audio output device

### Automated Installation
```powershell
# One-step automated deployment
python setup.py

# Or manual venv activation:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 2. Running Jarvis in Development Modes

```powershell
# Default mode: Modern PySide6 Cyber-Dark Desktop Interface
python main.py

# Interactive CLI mode (headless testing and quick debugging)
python main.py --cli

# Single query execution (scripting / automated smoke tests)
python main.py --query "what time is it"

# Development testing bypassing biometric face authentication
python main.py --no-auth

# Live hot-reloading (auto-updates when code changes without restarting GUI)
python main.py --reload

# Biometric face enrollment wizard
python main.py --enroll-face
```

---

## 3. Core Architectural Invariants

Every developer and coding agent working on Jarvis MUST adhere to these mandatory rules:

### 3.1 No Duplicate Implementation Rule (AGENTS.md §1.1)
- **Always scan before writing**: Before creating any new function, class, or module, search the codebase.
- **Reuse and extend**: If a capability belongs in `ContextManager`, `WindowManager`, `UniversalGoalResolver`, or `DatabaseManager`, extend the existing implementation. Never create competing parallel managers (`NewContextManager`, `SmartWindowManager`, etc.).
- **Single Source of Truth**:
  - Context $\rightarrow$ `RuntimeContext` / `ActiveTargetContext`
  - Window & Desktop $\rightarrow$ `WindowManager` & `UniversalWindowResolver`
  - Goals & Meanings $\rightarrow$ `UniversalGoalResolver`
  - Action Execution $\rightarrow$ `SemanticActionExecutor` & `MultiActionExecutor`
  - Memory $\rightarrow$ `MemoryManager` & `DatabaseManager`

### 3.2 Speech-Act Gating Invariant
Command keywords alone must NEVER trigger execution:
- *"Kya tum Chrome open kar sakte ho?"* is a `CAPABILITY_QUESTION` $\rightarrow$ Answer ability directly; NEVER launch Chrome.
- *"Chrome open karo"* is an `ACTION_COMMAND` $\rightarrow$ Execute and verify.
- *"Chrome open hai kya?"* is a `STATUS_QUESTION` $\rightarrow$ Report state; NEVER alter state.

### 3.3 Zero-Disk Audio Accumulation Invariant
Spoken responses must be synthesized in-memory via `io.BytesIO` buffers. Never permanently save `.mp3` files to disk. Any temporary file required by legacy drivers must be unlinked in a guaranteed `try...finally` block.

### 3.4 Minimum Change Principle
- Surgical fix > localized refactor > architectural change > rewrite.
- Preserve all public interfaces and backward-compatible aliases (`GoalResolver = UniversalGoalResolver`).

---

## 4. How to Add a New Domain Plugin

1. Create a new directory under `plugins/<plugin_name>/`.
2. Inherit from `PluginBase` (`plugins/base.py`).
3. Define the plugin manifest in `plugin.json` or inline metadata:
   - Unique `name`, `version`, `author`, `permissions` (risk tier: `LOW`, `MEDIUM`, `HIGH`).
4. Register actions and keyword aliases.
5. In `core/execution/semantic_executor.py`, add action routing if the plugin consumes semantic actions.
6. Create an automated test suite under `tests/test_<plugin_name>.py`.
7. Register the new feature in `FEATURES.md` and log the work in `AGENT_LOG.md`.
