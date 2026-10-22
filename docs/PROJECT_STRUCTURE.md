# JARVIS — Project Structure & Organization Guide

This document provides a comprehensive directory map, package responsibilities, and structural reference for developers working on Jarvis.

---

## 1. Top-Level Directory Organization

```
Jarvis_19-09-2026/
├── main.py                     # Primary system bootstrap, CLI/GUI runtime entry point
├── setup.py                    # Automated environment setup, dependencies, system checks
├── config.yaml                 # Central system configuration (audio, UI, models, thresholds)
├── conftest.py                 # Pytest environment setup, offscreen Qt, volume presets
├── requirements.txt            # Python dependencies (local-first, Win32, PySide6, audio)
│
├── brain/                      # Cognitive processing, response synthesis, LLM providers
│   ├── classifier.py           # IntentClassifier integrating LLM and local rules
│   ├── llm.py                  # Local/API LLM provider abstractions
│   ├── response.py             # Natural response generator
│   ├── semantic_parser.py      # Semantic pipeline facade connecting core and brain
│   ├── spelling_resolver.py    # Offline high-speed spell and phonetic correction
│   └── conversation/           # Conversational models, registries, topic detectors
│
├── core/                       # Central Orchestration & Execution Engine
│   ├── app.py                  # JarvisCore — central runtime controller and lifecycle
│   ├── capabilities.py         # Capability registry and descriptors
│   ├── confirmation.py         # Confirmation state machine and gating
│   ├── context.py              # ActiveTargetContext, RuntimeContext, multi-turn state
│   ├── conversational_intent.py # Speech-act gating (CAPABILITY vs ACTION vs STATUS)
│   ├── dialog_manager.py       # Workflow lock, dialog turns, slot filling
│   ├── event_bus.py            # Pub/sub decoupled event system (EventBus, EventTopics)
│   ├── latency.py              # Sub-millisecond latency profiling and telemetry
│   ├── logger.py               # Structured logging and crash handlers
│   ├── permissions.py          # Action risk tiers (LOW, MEDIUM, HIGH, CRITICAL)
│   ├── target_engine.py        # TargetMatcher, ActionPlanner, UniversalTargetDiscovery
│   ├── universal_window_resolver.py # Multi-signal window discovery and scoring
│   ├── update_manager.py       # Live update and zero-downtime hot reloading
│   ├── windows_app_resolver.py # Windows 11 system app, UWP, and protocol resolver
│   │
│   ├── semantic/               # Natural Language Understanding & Semantic Decomposition
│   │   ├── __init__.py         # Public exports for semantic understanding
│   │   ├── constants.py        # Regex verbs, operations, service patterns
│   │   ├── goal_resolver.py    # UniversalGoalResolver orchestrator
│   │   ├── goals/              # Domain-specific modular goal mixins
│   │   │   ├── base.py         # CanonicalGoal, CanonicalSpeechAct
│   │   │   ├── cleanup_goal.py # Temp and Recycle Bin system cleanup goals
│   │   │   ├── software_update_goal.py # Winget and OS software updates
│   │   │   ├── equity_goal.py  # Indian equity and stock research goals
│   │   │   ├── contextual_goals.py # Repeat, pronoun, container follow-ups
│   │   │   └── cross_feature_goal.py # Multi-domain composite action goals
│   │   ├── hindi_vocab.py      # Bilingual 700+ Hindi/Hinglish vocabulary catalog
│   │   ├── lexicon.py          # Lexical concept definitions and analyzer
│   │   ├── models.py           # SemanticAction, ActionItem, MultiActionPlan
│   │   ├── multi_entity.py     # Multi-entity command parser and container binder
│   │   ├── normalizer.py       # HinglishNormalizer, filler stripper, text cleaner
│   │   └── orchestrator.py     # SemanticPipelineOrchestrator pipeline coordinator
│   │
│   ├── execution/              # Action Execution & Verification Subsystem
│   │   ├── fast_path.py        # Ultra-low latency command execution (<10ms)
│   │   ├── models.py           # Action execution models and contracts
│   │   ├── multi_executor.py   # MultiActionExecutor for chained commands
│   │   ├── semantic_executor.py # SemanticActionExecutor routing actions to plugins
│   │   ├── strategies.py       # Execution strategies (UWP, direct exe, shell)
│   │   └── verifier.py         # Universal Action Verifier (state truth confirmation)
│   │
│   ├── knowledge/              # Structured Knowledge & Reasoning Engines
│   │   ├── router.py           # KnowledgeRouter delegating GK, IT, and Calendar
│   │   ├── entity_store.py     # 16-category structured in-memory entity store
│   │   ├── reasoning_store.py  # Conceptual scientific reasoning models
│   │   ├── calendar/           # Festival and calendar knowledge (Drik Panchang)
│   │   └── it/                 # 5-domain IT systems and infrastructure engine
│   │
│   ├── intelligence/           # Proactive intelligence, habit discovery, suggestions
│   ├── observer/               # Screen, window, and desktop activity observers
│   └── speech_repair/          # ASR phonetic misrecognition recovery engine
│
├── desktop/                    # Desktop automation, UIA, and mouse controllers
├── data/                       # Configuration catalogs and persistent stores
│   ├── jarvis.db               # SQLite database (44 tables: conversations, memory, etc.)
│   └── windows_apps.json       # Windows 11 application and protocol definitions
│
├── gui/                        # PySide6 Cyber-Dark Desktop User Interface
│   ├── app.py                  # JarvisApp Qt application host and lifecycle
│   ├── styles.py               # Cyber-dark theme, CSS variables, typography
│   ├── components/             # Reusable UI widgets (chat bubbles, status bar, cards)
│   └── views/                  # Primary views (Chat, Dashboard, Settings, Plugins, etc.)
│
├── learning/                   # Continuous Learning & User Adaptation Engine
│   ├── learner.py              # LearningManager mining habits and patterns
│   ├── corrections_layer.py    # User spoken correction learner
│   ├── execution_preference.py # Per-target application and browser preferences
│   └── vocabulary_layer.py     # Dynamic vocabulary and alias training
│
├── memory/                     # Multi-Tier Cognitive Memory Subsystem
│   ├── database.py             # SQLite WAL-mode thread-safe database gateway
│   ├── memory_manager.py       # Unified memory facade
│   └── repositories/           # Repositories for episodic, semantic, and conversation data
│
├── plugins/                    # 35+ Extensible Domain Plugins
│   ├── base.py                 # PluginBase abstract contract
│   ├── manager.py              # Dynamic discovery, loading, and permissions
│   ├── manifest.py             # PluginManifest metadata definitions
│   ├── windows/                # WindowManager (Win32 HWND, window operations)
│   ├── browser/                # Browser automation (Chrome, Edge, Brave, tabs)
│   ├── files/                  # Filesystem operations (safe trash, search, move)
│   ├── media/                  # Media control (YouTube, playback, volume)
│   └── ...                     # Additional domain plugins (excel, system, etc.)
│
├── security/                   # Biometric authentication and action safety policies
│   ├── action_policy.py        # Risk policy validation (PermissionGuard)
│   └── face_authenticator.py   # OpenCV real-time facial biometric gate
│
├── stock/                      # Indian Equity 1-Month Research & Options Analysis
│   ├── analysis/               # Technical indicator calculators (SuperTrend, EMA, RSI)
│   ├── broker/                 # Read-only broker and data providers
│   └── indicators/             # Live chart confluence and options screening
│
├── voice/                      # Audio Perception & Speech Delivery Subsystem
│   ├── listener.py             # Continuous microphone streaming and VAD
│   ├── stt.py                  # Multilingual Speech-to-Text recognizer
│   ├── tts.py                  # Dual-engine TTS (Edge-TTS + SAPI5 in-memory)
│   ├── wake_word.py            # Standalone and position-independent wake-word detection
│   ├── device_manager.py       # Audio hardware and Bluetooth headset routing
│   └── chime.py                # Asynchronous low-latency audio cues
│
├── tests/                      # 212 Comprehensive Pytest Test Suites
├── docs/                       # Architecture, regression, and refactoring documentation
└── backup/                     # Safety backups and pre-refactoring snapshots
```

---

## 2. Reading Order for New Developers

To quickly understand the Jarvis architecture without getting lost, follow this sequence:

1. **[README.md](file:///c:/Data/Jarvis_19-09-2026/README.md)**: High-level introduction, key features, and environment setup.
2. **[ARCHITECTURE.md](file:///c:/Data/Jarvis_19-09-2026/ARCHITECTURE.md)**: Authoritative system blueprint and end-to-end multi-modal pipeline flow.
3. **[main.py](file:///c:/Data/Jarvis_19-09-2026/main.py)**: Bootstrap sequence and how subsystems are wired into `JarvisCore`.
4. **[core/app.py](file:///c:/Data/Jarvis_19-09-2026/core/app.py)**: Runtime controller, interaction gate, and turn lifecycle.
5. **[core/conversational_intent.py](file:///c:/Data/Jarvis_19-09-2026/core/conversational_intent.py)**: Speech-act classification (CAPABILITY vs ACTION vs STATUS).
6. **[core/semantic/goal_resolver.py](file:///c:/Data/Jarvis_19-09-2026/core/semantic/goal_resolver.py)**: Semantic goal resolution and domain mixins under `core/semantic/goals/`.
7. **[core/universal_window_resolver.py](file:///c:/Data/Jarvis_19-09-2026/core/universal_window_resolver.py)**: Universal window and application resolution engine.
8. **[core/execution/verifier.py](file:///c:/Data/Jarvis_19-09-2026/core/execution/verifier.py)**: Universal Action Verification layer.
9. **[plugins/windows/window_manager.py](file:///c:/Data/Jarvis_19-09-2026/plugins/windows/window_manager.py)**: Windows desktop automation and Win32 HWND operations.
10. **[gui/app.py](file:///c:/Data/Jarvis_19-09-2026/gui/app.py)** and **[gui/views/chat_view.py](file:///c:/Data/Jarvis_19-09-2026/gui/views/chat_view.py)**: Desktop user interface.
