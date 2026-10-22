# JARVIS — Major Module Guide & Reference

This guide details the primary modules of the Jarvis codebase, documenting their purpose, inputs, outputs, public interfaces, dependencies, and inter-module interactions.

---

## 1. Core Orchestration Layer

### 1.1 `core/app.py` (`JarvisCore`)
- **Purpose**: The central runtime orchestrator of the assistant. Coordinates perception, gate evaluation, speech acts, dialog management, fast-path routing, execution, verification, and memory updates.
- **Inputs**: Raw text string or audio transcript (`raw_input: str`), input source (`source: "gui" | "cli" | "voice_gated"`).
- **Outputs**: Synthesized conversational response string (`str`), triggers speech playback, emits domain events.
- **Dependencies**: `InteractionGate`, `StateMachine`, `DialogManager`, `EventBus`, `MemoryManager`, `PluginManager`, `LearningManager`.
- **Public Interface**:
  - `initialize_subsystems(...)`: Wires memory, plugins, classifier, and learning layers.
  - `process_input(raw_input, source="cli") -> str`: Public entry point for all command execution.
  - `execute_action_plan(plan, ...) -> ExecutionOutcome`: High-level verified action plan execution.
  - `interrupt_active_speech(reason, interrupting_text)`: Sub-20ms speech audio cutoff on barge-in.
  - `take_sensitive_display() -> Optional[Dict]`: Retrieves one-time credentials (e.g. Wi-Fi passwords) without logging.
  - `shutdown()`: Clean release of hardware endpoints, threads, and database connections.

### 1.2 `core/universal_window_resolver.py` (`UniversalWindowResolver`, `UniversalAppNormalizer`)
- **Purpose**: Multi-signal, dynamic resolution engine that resolves desktop applications and windows independently of exact title, spelling, or ASR noise.
- **Inputs**: Spoken app/window target name (`target: str`), running windows list (`List[WindowInfo]`), conversational context.
- **Outputs**: Scored matching windows with confidence metric (0-100), disambiguated candidate selection.
- **Dependencies**: `difflib.SequenceMatcher`, `ctypes.windll.user32`.
- **Public Interface**:
  - `UniversalAppNormalizer.clean_name(name)`: Strips punctuation and extraneous symbols.
  - `UniversalAppNormalizer.collapsed_name(name)`: Collapses whitespace and hyphens.
  - `UniversalAppNormalizer.strip_noise(name)`: Strips spoken noise suffixes (*"id"*, *"ide"*, *"app"*, *"browser"*).
  - `UniversalAppNormalizer.is_relative_target(name)`: Detects demonstratives (*"yah window"*, *"isko"*, *"this"*).
  - `UniversalWindowResolver.match_windows(windows, target, context, threshold=60)`: Returns ranked candidates.
  - `UniversalWindowResolver.score_window(window, target_norm, context)`: Evaluates 8 weighted signals.

### 1.3 `core/conversational_intent.py` (`ConversationalIntentClassifier`)
- **Purpose**: Authoritative speech-act gating layer enforcing PURPOSE FIRST -> EXECUTE SECOND -> SPEAK NATURALLY THIRD.
- **Inputs**: User input text string.
- **Outputs**: `ConversationalIntentResult` with `intent_type` (`CAPABILITY_QUESTION`, `ACTION_COMMAND`, `STATUS_QUESTION`, `STATUS_AFTER_ACTION`, `TROUBLESHOOTING`, `CONFIRMATION`, `CANCELLATION`, `GREETING`).
- **Public Interface**:
  - `ConversationalIntentClassifier.classify(text, context=None) -> ConversationalIntentResult`: Authoritative speech-act classification.

---

## 2. Semantic Understanding & Goal Resolution

### 2.1 `core/semantic/goal_resolver.py` (`UniversalGoalResolver`)
- **Purpose**: Translates varied Hindi, Hinglish, and English user input into canonical semantic goals, applying priority hierarchy: `explicit target > strong semantic evidence > active context > previous context`.
- **Inputs**: Raw or normalized user input string, optional conversational context.
- **Outputs**: `SemanticResolution` decision model containing goal, intent, entities, parameters, required capabilities, and resolution decision (`EXECUTE`, `ASK_PRECISE_CLARIFICATION`, `REFUSE`).
- **Dependencies**: Modular mixins under `core/semantic/goals/`:
  - `CleanupGoalMixin`: System temp files and Recycle Bin operations.
  - `SoftwareUpdateGoalMixin`: Winget and Windows update operations.
  - `EquityResearchGoalMixin`: Indian equity and stock research workflows.
  - `ContextualGoalMixin`: Deictic pronouns, repetitions, and container follow-ups.
  - `CrossFeatureGoalMixin`: Multi-domain composite action goals.
- **Public Interface**:
  - `UniversalGoalResolver.resolve(user_input: str, context=None) -> SemanticResolution`: Core goal resolution entry point.
  - `GoalResolver`: Backward-compatible alias.

### 2.2 `core/semantic/multi_entity.py` (`MultiEntityCommandParser`)
- **Purpose**: Decomposes natural compound sentences containing multiple targets or conjunctions (*"Chrome aur Brave kholo aur dono me YouTube open karo"*).
- **Inputs**: Multi-action user utterance.
- **Outputs**: `MultiActionPlan` containing ordered list of `ActionItem`s with container bindings.
- **Public Interface**:
  - `MultiEntityCommandParser.parse(text: str, context=None) -> Optional[MultiActionPlan]`

---

## 3. Execution & Verification Subsystem

### 3.1 `core/execution/verifier.py` (`ActionVerifier`)
- **Purpose**: Truth-enforcement layer preventing false-positive success claims. Inspects OS state after an action to confirm it actually happened.
- **Inputs**: Action type, target identifier (HWND, process name, URL, tab title).
- **Outputs**: `VerificationResult` (`verified: bool`, `details: str`).
- **Public Interface**:
  - `verify_window_operation(hwnd, operation, initial_state)`: Validates `IsIconic`, `IsZoomed`, or window dismissal.
  - `verify_browser_opened(browser, initial_count)`: Confirms new browser process and window emergence.
  - `verify_browser_tab(browser, expected_url_or_title)`: Validates active tab navigation via DevTools/UIA.

### 3.2 `plugins/windows/window_manager.py` (`WindowManager`)
- **Purpose**: Authoritative manager for Windows OS windows, processes, monitors, and desktop state.
- **Inputs**: Window operations (minimize, maximize, restore, close, focus), target app names.
- **Outputs**: Operation success status, list of `WindowInfo` objects.
- **Public Interface**:
  - `resolve_window(target, context) -> Optional[WindowInfo]`
  - `find_running_application(target) -> List[WindowInfo]`
  - `minimize_target(target) -> bool`
  - `maximize_target(target) -> bool`
  - `restore_target(target) -> bool`
  - `close_target(target) -> bool`
  - `focus_target(target) -> bool`

---

## 4. Voice Perception & Delivery

### 4.1 `voice/listener.py` (`VoiceListener`)
- **Purpose**: Continuous audio capture and Voice Activity Detection (VAD) with adaptive silence thresholds (350ms for commands, 550ms for hesitations).
- **Inputs**: Live microphone audio stream via `sounddevice` / `pyaudio`.
- **Outputs**: Audio frames sent to Speech-to-Text.

### 4.2 `voice/tts.py` (`TTSManager`)
- **Purpose**: Ultra-low-latency neural speech synthesis with zero disk accumulation.
- **Inputs**: Text string to speak.
- **Outputs**: Spoken audio streamed directly through in-memory `io.BytesIO` buffers to Pygame Mixer.
- **Guarantees**: Never writes permanent `.mp3` files to disk; handles immediate speech interruption on barge-in.

---

## 5. Memory & Persistence Layer

### 5.1 `memory/database.py` (`DatabaseManager`)
- **Purpose**: Authoritative SQLite database gateway with Write-Ahead Logging (WAL) concurrency and thread-safe connection pooling.
- **Inputs**: SQL queries, parameter dictionaries.
- **Outputs**: Rows, dictionaries, or scalar counts across 44 tables in `data/jarvis.db`.

### 5.2 `memory/memory_manager.py` (`MemoryManager`)
- **Purpose**: Unified facade coordinating the 4 memory tiers: Working Memory (in-memory session), Episodic Memory (dialogue turns), Semantic Memory (durable facts), and Correction Memory (user corrections).
