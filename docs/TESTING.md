# JARVIS — Testing & Quality Assurance Guide

This document outlines the testing framework, test suite organization, execution commands, and guidelines for writing robust unit and integration tests for Jarvis.

---

## 1. Running Tests

Jarvis uses `pytest` with `pytest-asyncio`. A global `conftest.py` configures PySide6 to run headless in offscreen mode (`QT_QPA_PLATFORM=offscreen`) so GUI components can be tested without popping windows.

### 1.1 Running Scoped Key Test Suites
Because the repository contains 212 test files covering hardware devices, trading charts, and audio streams, developers should run scoped tests relevant to their changes:

```powershell
# Desktop Window & Application Resolution
pytest tests/test_universal_window_resolver.py -v
pytest tests/test_windows_app_resolver.py -v
pytest tests/test_window_management_architecture.py -v

# Natural Language Understanding & Speech-Acts
pytest tests/test_conversational_intent_speech_act.py -v
pytest tests/test_conversational_response_policy.py -v
pytest tests/test_multi_entity_commands.py -v
pytest tests/test_universal_goal_resolver.py -v

# Verification Layer & Action Truth
pytest tests/test_universal_verification_layer.py -v

# Structured Knowledge Engines
pytest tests/test_knowledge_engine.py -v
pytest tests/test_it_knowledge_engine.py -v
pytest tests/test_festival_calendar_engine.py -v

# Memory & Proactive Subsystems
pytest tests/test_cognitive_memory.py -v
pytest tests/test_proactive_system_integration.py -v

# Financial & Stock Research
pytest tests/test_indian_equity_research_engine.py -v
pytest tests/test_software_update_manager.py -v
```

---

## 2. Test Suite Organization

| Directory / File | Domain Under Test | Key Invariant Verified |
|---|---|---|
| `test_universal_window_resolver.py` | `core.universal_window_resolver`, `plugins.windows.window_manager` | Fuzzy match, ASR noise stripping (*"ID"*), deictic targets (*"yah window"*), state awareness (*"already minimized"*). |
| `test_conversational_intent_speech_act.py` | `core.conversational_intent` | Capability questions NEVER execute commands; status inquiries NEVER alter state. |
| `test_multi_entity_commands.py` | `core.semantic.multi_entity`, `core.execution.multi_executor` | Compound conjunction commands (*"Chrome aur Brave kholo"*), container bindings. |
| `test_universal_verification_layer.py` | `core.execution.verifier` | Post-action truth confirmation; refusal to claim unverified success. |
| `test_browser_status_followup.py` | `core.response_policy`, `core.confirmation_manager` | Human-like browser location feedback and affirmative follow-up actions. |
| `test_indian_equity_research_engine.py` | `core.equity_research`, `core.semantic.goals.equity_goal` | Multi-turn slot preservation, catalyst epistemology, zero guaranteed returns. |

---

## 3. Best Practices & Mocking Guidelines

### 3.1 Win32 API Mocking & Boolean Type Safety
When mocking `ctypes.windll.user32` functions (like `IsIconic` or `IsZoomed`) using `unittest.mock.MagicMock`:
- In Python, a `MagicMock` object evaluates to `True` in boolean context (`bool(MagicMock()) == True`).
- Always return explicit integer or boolean values (`mock_u32.IsIconic.return_value = 0`).
- Implementation code must use explicit type checks: `if isinstance(val, (int, bool)) and bool(val):` to prevent mock instances from falsely triggering *"already minimized"*.

### 3.2 Testing Asynchronous & Event-Driven Flows
- Use `core.event_bus.EventBus.subscribe(topic, handler)` with in-memory tracking lists.
- Avoid thread sleeps; prefer event synchronization or small debounces.
