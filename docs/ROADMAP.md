# JARVIS — STRATEGIC ROADMAP
_Future Engineering Roadmap & Evolution Milestones_

---

## 1. Vision & North Star

Jarvis is designed to be the ultimate **offline-first, privacy-respecting, autonomous cognitive desktop assistant**. The primary architectural philosophy is local-first intelligence: Jarvis should function seamlessly without mandatory cloud dependencies, provide sub-second voice interactions, understand natural mixed English/Hindi/Hinglish instructions, and act as a reliable pair-operator on Windows desktops.

```
[ v2.0 - v2.1 ] Stable Core & EventBus Architecture (Completed)
      │
      ▼
[ v2.2 ] Edge Neural STT & Local LLM Integration (Near-Term)
      │
      ▼
[ v2.5 ] Real-Time Duplex Voice & Autonomous Task Operator (Mid-Term)
      │
      ▼
[ v3.0 ] Multimodal Vision-Agent & Self-Evolving Plugins (Long-Term)
```

---

## 2. Release Milestones

### Phase 1: Version 2.2 — Edge Models & Neural Foundations (Near-Term)
*Target: Q4 2026*

- **Offline Multilingual Neural STT (Faster-Whisper)**
  - Integrate `faster-whisper` with GPU/CPU INT8 quantization for sub-250ms speech-to-text.
  - Support automatic language detection across Hindi, English, and regional accents.
  - Zero cloud dependency for voice transcription.

- **Local LLM Reasoning Engine (Ollama / Llama.cpp)**
  - Native integration with local models (Llama 3.2 3B/8B, Mistral 7B, Qwen 2.5 7B) via Ollama and `llama-cpp-python`.
  - Structured JSON outputs (Pydantic function calling) for complex query decomposition.
  - Dynamic fallback to cloud providers (Claude / GPT-4o) only when explicitly configured by the user.

- **Neural TTS Voice Cloning (Piper / XTTS-v2)**
  - Fast, expressive offline neural voices replacing legacy SAPI5 robotic fallbacks.
  - Support for custom synthetic voice profiles with emotional modulation (excited, neutral, focused).

- **Windows 11 Fluent UI Overhaul**
  - Acrylic and Mica translucent window materials via PySide6 window attributes.
  - Animated soundwave visualizer responding to mic input and TTS output.
  - Global system tray integration with instant minimize/summon hotkeys (`Win + J`).

---

### Phase 2: Version 2.5 — Duplex Voice & Autonomous Desktop Operator (Mid-Term)
*Target: Q1–Q2 2027*

- **Full-Duplex Speech & Instant Barge-In**
  - Continuous streaming audio loop with conversational turn-taking (< 300ms end-to-end latency).
  - Acoustic echo cancellation (AEC) enabling the user to interrupt Jarvis while it speaks without triggering audio feedback loops.

- **Autonomous Multi-Step Desktop Task Engine**
  - Directed Acyclic Graph (DAG) task runner for multi-application workflows.
  - Transactional rollback checkpoints: if an automated step fails (e.g. file rename or download), Jarvis rolls back desktop state to the previous checkpoint.
  - Automatic error recovery: re-locates misplaced UI buttons or re-tries alternative execution paths before asking the user.

- **Multimodal Screen Grounding (OmniParser / Florence-2)**
  - Screen vision parsing that detects clickable UI elements, icons, textboxes, and buttons by visual appearance rather than coordinates.
  - Resilient to UI changes, DPI scaling, and dark/light mode variations.
  - Real-time screen Q&A ("What error is shown in the terminal right now?").

- **Mobile Companion Bridge (Android / iOS)**
  - Encrypted local WebSocket / mDNS pairing between Windows desktop and mobile devices.
  - Remote voice input, push notification dispatch for completed workflows, and camera stream ingestion for ambient vision.

---

### Phase 3: Version 3.0 — Self-Evolving & Multi-Agent Intelligence (Long-Term)
*Target: Q3–Q4 2027*

- **Dynamic Self-Synthesizing Plugin Architecture**
  - When faced with an unknown command or unsupported tool, Jarvis generates a self-contained Python plugin into a secure execution sandbox (`security/sandbox/`).
  - Automated self-testing of generated plugins against test suites before production registration.
  - Automatic registration into `FEATURES.md` and `PluginManager`.

- **Multi-Agent Specialist Swarm**
  - Coordination between specialized local agents:
    - *Executive Agent*: High-level intent planner and orchestrator.
    - *Coder Agent*: Code analysis, Git operations, bug fixing.
    - *Desktop Operator*: Win32 and UI automation specialist.
    - *Auditor Agent*: Security and permission policy guardrail verification.
  - Shared blackboard communication over the Pub/Sub EventBus.

- **Local IoT & Matter / Home Assistant Hub**
  - Native discovery of smart home devices over local network (Matter, Zigbee via Home Assistant).
  - Ambient context awareness (lights, room temperature, occupancy) merged into cognitive memory.

---

## 3. Technical Debt & Quality Guardrails

| Focus Area | Objective | Metric Target |
|---|---|---|
| **Voice Latency** | Speech finished $\rightarrow$ First audio output | $< 350\text{ ms}$ (Offline) |
| **Memory Footprint** | Background resident consumption (idle) | $< 180\text{ MB}$ RAM |
| **Startup Time** | Cold launch to interactive state | $< 1.2\text{ s}$ |
| **Test Coverage** | Scoped automated regression coverage across 35+ plugins | $> 90\%$ pass rate |
| **Crash Rate** | Graceful failure boundary across all plugins | $0$ unhandled host crashes |

---

## 4. Governance & Contribution Rules

1. **Local-First Default**: No feature should require internet connectivity unless the task inherently involves web access (e.g. YouTube playback, web search, weather).
2. **Deterministic Confirmation**: High-risk system or data actions must always remain subject to explicit user confirmation (`ConfirmationManager`).
3. **Registry Synchronization**: Any new feature or architectural addition must be documented in `FEATURES.md` and `ARCHITECTURE.md` during implementation.
