# JARVIS — CHANGELOG
All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.2.0] - 2026-09-19

### Added
- **Universal Application & Window Resolution Engine (`UniversalWindowResolver`, `UniversalAppNormalizer`)**:
  - Eliminates exact string matching dependency across all desktop applications by evaluating 8 weighted signals (process exact +95, collapsed match +92, window title +86, token subset +85, fuzzy match +60-80, foreground bonus +15).
  - Normalizes speech variations, punctuation, and compound prefixes (*"anti gravity"* $\rightarrow$ *"antigravity"*).
  - Strips spoken ASR noise suffixes (*"ID"*, *"IDE"*, *"App"*, *"Browser"*, *"Window"*).
  - Resolves deictic demonstrative references (*"yah window"*, *"yeh window"*, *"isko"*, *"this"*, *"current"*) to the active foreground window.
  - State-aware action execution delivering truthful feedback (*"Chrome already minimized hai, Boss."*).
- **Domain Goal Modularization (`core/semantic/goals/`)**:
  - Modularized `UniversalGoalResolver` into 5 domain mixins (`CleanupGoalMixin`, `SoftwareUpdateGoalMixin`, `EquityResearchGoalMixin`, `ContextualGoalMixin`, `CrossFeatureGoalMixin`), reducing `core/semantic/goal_resolver.py` from 2,171 lines to 438 lines while preserving 100% backward compatibility.
- **Comprehensive Project Documentation Suite**:
  - `docs/FEATURE_REGRESSION_MATRIX.md`: Complete capability-to-test mapping preserving all 32 core features.
  - `docs/REFACTOR_CANDIDATES.md`: Confidence and risk evaluation of early prototype stubs.
  - `PROJECT_STRUCTURE.md`: Full architectural directory map and reading order.
  - `MODULE_GUIDE.md`: Deep dive into core orchestration, semantic, execution, and voice modules.
  - `DEVELOPMENT.md`: Developer guide, startup modes, and coding invariants.
  - `TESTING.md`: Test suite organization, headless PySide6 guidelines, and mocking standards.
  - `TROUBLESHOOTING.md`: Diagnostic handbook for audio, window resolution, and database concurrency.

## [2.1.0] - 2026-09-06

### Added
- **Universal Action Verification Layer**: Strict post-execution verification for all desktop and browser actions (`verify_browser_opened`, `verify_browser_tab`, `verify_window_state`). Prohibits claiming false execution success.
- **Natural Multi-Entity & Multi-Action Architecture**:
  - `EntityKnowledgeBase`: Span extraction across applications, browsers, websites, and system tools.
  - `MultiEntityCommandParser`: Decomposes compound conjunction commands (*"Chrome kholo aur usme YouTube play karo"*).
  - `MultiActionExecutor`: Runs sequential `UNDERSTAND -> EXECUTE -> VERIFY -> RECOVER` loops with honest Hinglish status reporting.
- **Dedicated Windows Application Resolver (`WindowsAppResolver`)**:
  - Pre-seeded catalogue of 40+ Windows 11 apps (`data/windows_apps.json`).
  - 6-tier resolution hierarchy: UWP protocol launchers (`microsoft.windows.camera:`), Start Menu executables, shell commands, and custom aliases.
  - Entity-aware typo intercept protecting system terms (e.g. prevents *"microsft store"* from corrupting into *"storage"*).
- **Confirmation State Machine (`ConfirmationManager`)**:
  - Multi-turn confirmation state machine for destructive actions (restart, shutdown, file deletion).
  - Native bilingual intent classifier supporting English, Hindi, and Hinglish affirmations (*"haan"*, *"kar do"*, *"bilkul"*) and rejections (*"nahi"*, *"mat karo"*, *"ruk jao"*).
  - Bypass for typed GUI/CLI inputs from mic speech cooldown suppression.
- **Options Trading Confluence Engine (`trading.options.signals`)**:
  - Screen-only live chart analysis for NIFTY Index and Option contracts.
  - Automated browser chart discovery (Chrome, Brave, Edge, Firefox) with Alt-Tab/minimized pause handling.
  - Strict broker truth invariant: visual analysis only, zero broker API or order dispatch capabilities.
- **In-Process Zero-Downtime Live Reload (`LiveUpdateManager`)**:
  - Decoupled persistent PySide6 GUI host from reloadable logic modules.
  - Debounced file watcher reloading modules and EventBus subscriptions without terminating the GUI window.

### Changed
- **NLU Understanding Pipeline**:
  - Enhanced 8-stage semantic pipeline eliminating fake *"Main samajh gaya"* conversational responses on ambiguous or unknown queries.
  - Standardized website resolution via `WebsiteKnowledgeStore` with separate URL extraction from natural conversational phrases.
- **Preference Memory System**:
  - Added `ExecutionPreferenceManager` backing persistent browser and application preferences in SQLite.
  - Integrated correction fast-paths allowing users to update defaults (*"Chrome nahi Brave use karo"*) without manual configuration.
- **EventBus Hardening**:
  - Added canonical `EventTopics` constants and async non-blocking event dispatch.
  - Isolated subscriber exception boundaries to ensure a failed handler never interrupts event distribution.

### Fixed
- **GUI Thread Deadlock**: Resolved Qt-GIL freeze in `THINKING` state by decoupling `TTSManager` re-entrant locks and migrating `TaskWorker` to native `QThread`.
- **Chat Auto-Scroll**: Fixed chat view requiring manual scrolling by connecting `rangeChanged` signals to deferred `scroll_to_bottom` event loop passes.
- **Collateral Tab Closures**: Fixed browser tab close commands terminating unintended tabs or active windows by enforcing active title matching before `Ctrl+W`.
- **Camera / App Close Collision**: Fixed *"close camera"* closing unrelated browser windows by resolving UWP `ApplicationFrameHost` window identities.
- **SQLite Concurrency Locks**: Hardened database connections with Write-Ahead Logging (`WAL`), 5000ms busy timeout, and connection acquisition locks.

---

## [2.0.0] - 2026-08-15

### Added
- **Complete Core Re-architecture (`JarvisCore`)**:
  - Centralized state machine: `IDLE`, `WAKE_DETECTED`, `LISTENING`, `PROCESSING`, `RESPONDING`.
  - Pub/Sub `EventBus` coordinating perception, intelligence, and execution components.
- **Multi-Tier Cognitive Memory System**:
  - Working, Short-Term, Episodic, Semantic, Procedural, and Activity memory stores.
  - SQLite backend (`data/jarvis.db`) with automatic historical pruning.
- **Proactive Intelligence & Observer Engine**:
  - `ActivityObserver` tracking active window titles, processes, and user idle duration.
  - `PatternLearningEngine` mining recurring habits and routines.
  - `SuggestionManager` proposing non-disruptive actions based on user behavior.
- **Modern PySide6 Cyber-Dark GUI**:
  - 9 integrated views: Dashboard, Chat, Plugins, Memory, Learning, Workflows, Reminders, Activity Log, and Settings.
  - Real-time telemetry monitoring (CPU, RAM, Uptime, Cognitive Facts count).
- **Biometric Security Engine**:
  - Local OpenCV face authentication gating system access and sensitive operations.
  - Master PIN fallback and anti-bruteforce lockout timer.
- **Modular Plugin Framework (`PluginManager`)**:
  - Dynamic discovery and lazy-loading for 35+ specialized plugins.
  - Self-describing manifests with permission isolation.

---

## [1.5.0] - 2026-06-01

### Added
- Neural speech synthesis via Edge-TTS supporting Hindi and English neural voices.
- Bilingual Hinglish speech-to-text processing using phonetic normalization.
- Basic desktop automation tools: volume control, window switching, keyboard/mouse macros via PyAutoGUI.
- WhatsApp Desktop and system notification dispatch plugins.

### Changed
- Migrated configuration management from scattered JSON files to a unified `config.yaml`.
- Replaced legacy console logging with structured rotating log files in `logs/`.

---

## [1.0.0] - 2026-03-10

### Added
- Initial proof-of-concept release of Jarvis voice assistant.
- Offline rule-based intent matching via regex and keyword lookups.
- Windows SAPI5 offline text-to-speech integration.
- SpeechRecognition microphone input with basic wake word detection.
- Simple application launching and web search routing.
