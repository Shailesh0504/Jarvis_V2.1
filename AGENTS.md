# JARVIS — AGENTS.md
_Last restructured: 2026-09-13. Update this line whenever the file changes meaningfully._

## 0. ROLE

You are working on an existing, large, actively developed Jarvis AI voice-assistant codebase (offline, rule-based, keyword/intent-matching, built with SpeechRecognition + pyttsx3) with **5000+ features**.

This is **NOT** a greenfield project. At this scale, no agent — human or AI — holds the whole system in its head. The repository (and the registry in §8) is the source of truth. Never assume architecture, files, or behavior without verifying them.

> **Primary objective: make the requested change without breaking existing behavior — and without an agent having to re-discover the whole system from scratch every session.**

**Override note:** An explicit instruction from the user in the current session overrides a default below. These are defaults for ambiguous/unscoped requests, not a cage.

---

## 1. CORE RULES (non-negotiable — read every time)

1. **Preserve existing functionality above all else.** Never sacrifice a working feature to make one new case work.
2. **Never start coding immediately.** Understand → Check registry (§8) → Locate → Trace → Plan → Implement → Verify → Regression-check (§9) → Document.
3. **Minimum change principle.** Surgical fix > localized refactor > architectural change > rewrite. Don't refactor, rename, or "clean up" unrelated code during a focused task.
4. **No duplicate logic — ever, at this scale especially.** Before creating any new function/class/manager/feature, check the registry (§8) and search the repo for an existing equivalent. With 5000+ features, duplicate intents/aliases are the single biggest cause of silent regressions.
5. **Single authoritative owner per responsibility** — context, decision, memory, policy, plugin loading, target resolution. Never create a second competing manager for the same job.
6. **Regression risk = search everything the change touches.** A change to a shared component (router, context, EventBus, memory) requires the full shared-component checklist in §9, not just a spot check.
7. **Never claim success without verification.** "Fixed" is only true after the exact case, related cases, and the relevant regression tier were actually tested. If verification wasn't possible, say so explicitly.
8. **Never hallucinate implementation.** Don't claim a file, function, feature, or test pass exists unless confirmed from the repo/registry/runtime.
9. **Stay in scope.** A task about one feature doesn't authorize touching unrelated features unless a real dependency forces it. Unrelated bugs found along the way get *reported*, not silently fixed.
10. **Preserve public interfaces.** Changing a function/class already used elsewhere requires finding every caller first — at 5000+ features, assume more callers exist than you can guess.
11. **Never remove fallback logic** without proving it's obsolete.
12. **No destructive Git/DB/file operations** (force push, drop table, delete uncommitted work, `rm -rf`) without explicit instruction.
13. **No hardcoded secrets, credentials, or arbitrary shell execution** from untrusted input.
14. **No unnecessary dependencies.** Check if it already exists or can be done locally/offline first — this project is local-first by default.
15. **Errors must fail gracefully and locally.** One failed feature, observer, or plugin must never crash the whole assistant or take down unrelated features.
16. **Small, isolated changes.** Don't bundle a bug fix with a refactor with a dependency migration in one uncontrolled change.
17. **Update `architecture.txt` only when architecture actually changed** — not for typo/logging/formatting fixes. See §10.
18. **Every new or changed feature updates the registry (§8) in the same task.** An unregistered feature effectively doesn't exist for the next agent session.
19. **Ask when genuinely ambiguous**, especially before anything destructive or architecture-altering. Don't ask when context/registry already resolves it.
20. **Log the session before finishing** (§13) and **report using the format in §14.**

---

## 1.1 NO DUPLICATE IMPLEMENTATION RULE (MANDATORY INVARIANT)

Before implementing ANY new feature, module, class, function, database table, logic, service, or workflow:

### 1. MUST SCAN THE EXISTING CODEBASE FIRST
Do not immediately create new files or duplicate logic. First inspect:
- Existing project architecture & modules
- Existing classes, functions, and services
- Existing Context Manager, Intent Detector, Command Router, Action Executor, Conversation Manager, Memory System
- Existing Workflow/State system, database models/tables, utility/helper functions, settings, and tests
Search the entire repository for related functionality before writing code.

### 2. NEVER CREATE DUPLICATE FUNCTIONALITY
If the required functionality already exists: **DO NOT create another implementation.**
Instead:
1. Reuse the existing implementation.
2. Extend it if necessary.
3. Refactor it if necessary.
4. Integrate the new requirement into the existing architecture.
*Example:* If `ContextManager` exists, do NOT create `NewContextManager`, `ConversationContextManager`, or `SmartContextManager`. Extend the existing `ContextManager`.

### 3. NO DUPLICATE MODULES
Before creating a new module, search for equivalent functionality. Do not create parallel modules (e.g. `core/memory_manager.py` vs `core/conversation_memory.py` vs `core/smart_context.py`) when the capability belongs inside the existing architecture.

### 4. NO DUPLICATE FUNCTIONS
Before creating a function, search for equivalent functions (e.g. `normalize_text` vs `clean_text` vs `normalize_input`). Reuse or improve the existing function.

### 5. NO DUPLICATE DATABASE TABLES
Inspect existing schema, columns, and relationships. Extend existing tables instead of creating competing duplicate tables.

### 6. NO DUPLICATE MEMORY SYSTEMS
Jarvis must have ONE authoritative memory architecture:
```text
Memory System
├── Conversation Memory
├── Episodic Memory
├── Semantic Memory
├── Entity Memory
├── Correction Memory
└── Learning Memory
```
Do not build separate competing memory systems.

### 7. NO DUPLICATE INTENT DETECTION
Jarvis has ONE authoritative intent pipeline:
`Normalize → Context → Rules / Patterns → ML → AI Fallback`.
New learning capabilities must integrate into this pipeline rather than creating parallel intent systems.

### 8. NO DUPLICATE ACTION EXECUTORS
One authoritative action execution path. Do not create separate duplicate handlers for variations of the same capability (`open application`, `launch application`, `start application`). Use the unified action layer with proper intent/entity resolution.

### 9. BEFORE CREATING A NEW FILE
Ask: *"Can this functionality logically belong to an existing file/module?"*
- If YES: Modify the existing file.
- If NO: Create a new file only when there is a clear architectural boundary reason.

### 10. EXECUTION PIPELINE SEQUENCE
```text
SCAN → SEARCH → IDENTIFY EXISTING IMPLEMENTATION → REUSE → EXTEND → REFACTOR IF REQUIRED → ONLY THEN CREATE NEW CODE
```
Never jump straight from request to creating a new file.

### 11. SELF-IMPROVEMENT & LEARNING INTEGRATION
The learning/feedback layer must consume and improve existing systems rather than replacing them:
```text
Existing Jarvis (Context, Intent, Router, Executor, Memory)
                      │
                      ↓
           Learning / Feedback Layer
  (Outcome Evaluation, Correction Detection, Pattern Learning, Confidence Scoring)
```

### 12. POST-IMPLEMENTATION DUPLICATE CHECK
After implementation, scan the repository again for duplicate functions, classes, modules, tables, intent definitions, imports, dead code, or obsolete implementations. Consolidate them before finishing.

### 13. SINGLE SOURCE OF TRUTH (SSOT)
- Context → Context Manager
- Intent → Intent Detector / HinglishNLUParser
- Command → Command Router
- Action → Action Executor / ExecutionStrategyEngine / WindowManager
- Memory → Memory System
- Learning → Learning Layer
- Configuration → Config System

### 14. DO NOT REWRITE WORKING SYSTEMS
If existing functionality works correctly, do not rewrite it unnecessarily. Make the smallest surgical architectural change required and preserve all public contracts, behavior, configuration, and performance.

### 15. REQUIRED PRE-IMPLEMENTATION REPORT
Before modifying code on any non-trivial task, explicitly document:
1. Which existing modules already handle this functionality.
2. Which existing functions/classes will be reused.
3. What must be extended.
4. Whether a new file is genuinely necessary.
5. Whether any existing duplicate/dead implementation should be consolidated.

### 16. FINAL RULE
**DO NOT CREATE CODE JUST BECAUSE IT IS EASIER.**
`REUSE → EXTEND → REFACTOR → CREATE` (Never `CREATE → DUPLICATE → PATCH → CREATE ANOTHER FIX`).

---

## 2. SETUP / RUN / VERIFY

> Fill these in once with the real commands — an agent that can't run/test the project will guess instead of verifying.

```bash
# Environment setup (Windows PowerShell) - One-step automated deployment
python setup.py

# Or manual venv activation:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run Jarvis (GUI default - PySide6 cyber-dark interface)
python main.py

# Run Jarvis in interactive CLI mode
python main.py --cli

# Run Jarvis single query (headless / scripting)
python main.py --query "open chrome"

# Run Jarvis bypassing biometric face authentication (dev testing)
python main.py --no-auth

# Run Jarvis with live auto-update / hot-reloading
python main.py --reload

# Biometric face enrollment
python main.py --enroll-face

# Run full test suite
pytest tests/ -v

# Run scoped/tagged tests only (see §9)
pytest tests/test_windows_app_resolver.py -v
pytest tests/test_multi_entity_commands.py -v
pytest tests/test_universal_verification_layer.py -v
pytest tests/test_conversational_response_policy.py -v
pytest tests/test_conversational_intent_speech_act.py -v
pytest tests/test_knowledge_engine.py -v
pytest tests/test_it_knowledge_engine.py -v
pytest tests/test_proactive_system_integration.py -v
pytest tests/test_festival_calendar_engine.py -v

# Lint/format (if used)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

---

## 3. CONVERSATION & NLP BEHAVIOR

- **Natural language first.** Users mix Hindi/English/Hinglish, imperfect grammar, and STT errors. `chrome kholo`, `chrome open karo`, `bhai chrome khol` should all resolve to the same intent via normalization + entity extraction + context — not one hardcoded rule per phrasing.
- **STT is not ground truth.** If recognized text seems off ("A type ko band karo" for "A tab ko band karo"), use phonetic similarity, known vocabulary, and active context to infer intent — but ask for clarification when multiple interpretations are equally plausible.
- **Separate action / entity / target** before execution. "antigravity application open karo" → `ACTION=OPEN, ENTITY=antigravity, TARGET=APPLICATION` — never treat the whole utterance as one entity blob.
- **Application vs. website resolution order:** installed app → known alias → known service/website → configured URL → browser search fallback → clarify if ambiguous. Never silently convert an app request into a website request, or vice versa, unless the user's wording specifies it.
- **Active workflow protection.** A short reply like "Sheet2" inside an open Excel workflow belongs to that workflow — don't let generic intent detection hijack it as a new standalone command.
- **Follow-up commands inherit context** ("isme YouTube kholo" after "Chrome kholo" refers to the just-opened Chrome).
- **Smart clarification only when needed.** Bad: "Please provide more information." Good: "Antigravity application aur website dono available hain — kaunsa kholun?"
- **Conversational Feedback Policy (`DIRECT ANSWER → OPTIONAL USEFUL DETAIL → STOP`).** Keep status feedback short, natural, and human-like (target 1 sentence). Never dump raw process names (`chrome.exe`), window handles, technical metadata, or debug bracketed titles (`('Title')`) to the user. Only surface active window titles or minimization states when specifically asked or necessary.
- **Speech-Act / Conversational Intent Invariant (`PURPOSE FIRST → EXECUTE SECOND → SPEAK NATURALLY THIRD`).** Command keywords alone must NEVER determine execution. An authoritative gating layer must determine the user's speech-act before execution:
  - `CAPABILITY_QUESTION` (*"kya tum system lock kar sakte ho?"*, *"can you open Chrome?"*) $\rightarrow$ Answer ability directly; NEVER execute.
  - `ACTION_COMMAND` (*"system lock karo"*, *"Chrome open karo"*) $\rightarrow$ Execute and confirm naturally.
  - `STATUS_QUESTION` (*"system lock hai kya?"*, *"Chrome open hai kya?"*) $\rightarrow$ Answer state; NEVER alter state.
  - `STATUS_AFTER_ACTION` (*"system lock hua?"*, *"Chrome open hua?"*) $\rightarrow$ Verify and report actual state; do not re-execute.
  - `TROUBLESHOOTING` (*"system lock kyun nahi ho raha?"*, *"domain user login kyun nahi kar paa raha?"*) $\rightarrow$ Explain problem; NEVER blindly re-attempt.
  - `CONFIRMATION` (*"haan"*, *"yes"*, *"kar do"*) $\rightarrow$ Only execute if an active pending operation exists; otherwise acknowledge conversationally.
  - `CANCELLATION` (*"nahi"*, *"mat karo"*) $\rightarrow$ Cancel pending operation.
- **General Knowledge & Reasoning Invariant (`STRUCTURED KNOWLEDGE FIRST → ZERO Q&A DUPLICATION → STRICT ANTI-HALLUCINATION`).** Store structured entities, attributes, and conceptual principles (16 categories: countries, capitals, states, currencies, continents, planets, elements, history, famous people, acronyms, science basics, geography, Indian GK, tech facts) rather than thousands of natural-language Q&A pairs. Normalize diverse phrasings (*"India ki capital kya hai?"*, *"Bharat ki rajdhani kya hai?"*, *"What is the capital of India?"*) to single entity-attribute facts. Never answer from stale static knowledge for time-sensitive queries (current leadership, weather, stocks). If confidence is LOW (< 0.60), provide a transparent refusal; NEVER hallucinate. Always keep General Knowledge separate from command execution: capability questions (*"kya tum system lock kar sakte ho?"*) must NEVER trigger GK or commands.
- **IT / Infrastructure Knowledge Engine Invariant (`CONCEPTUAL STORAGE FIRST → 6-PHASE STRUCTURED TROUBLESHOOTING → ZERO COMMAND EXECUTION`).** Provide experienced IT systems administrator guidance across 5 technical domains (Windows Desktop 10/11, Windows Server 2019, Microsoft Azure, Networking, Enterprise Infrastructure):
  - **Zero Command Execution on Knowledge Queries**: Questions explaining commands (*"What does ipconfig do?"*, *"gpupdate kya karta hai?"*) strictly explain syntax, parameters, and safe examples. Commands must NEVER be executed because of a knowledge inquiry.
  - **Structured Troubleshooting Schema**:
    $$\text{Problem Identification} \longrightarrow \text{Likely Causes} \longrightarrow \text{Safe Checks} \longrightarrow \text{Commands/Tools} \longrightarrow \text{Possible Fixes} \longrightarrow \text{Verification Steps}$$
  - **Multi-Lingual Intent Normalization**: Map diverse English, Hindi, and Hinglish technical utterances (*"server 2019 mein dns kaise setup karte hain?"*, *"rdp connect nahi ho raha"*, *"azure vm ka port kaise open karun?"*) to canonical technical concepts (`concept_id`, `command_name`, `troubleshooting_id`).
  - **Multi-Turn Context Awareness**: Maintain active technical context across workflow queries (*"Server 2019 mein DNS configure kar raha hoon"* followed by *"ab next kya karu?"* inherits the active DNS context and dispenses the next procedural step).
  - **Version-Sensitive vs. Stable Knowledge**: Stable technical knowledge is answered authoritatively with Microsoft Learn documentation references; version-sensitive or current queries (*"latest Azure features"*) indicate live verification requirements rather than guessing.

---

## 3.1 8 BASIC NEEDS FOR HUMAN-LIKE JARVIS (MANDATORY INVARIANTS)

To provide an authentic, human-like companion experience, all interactions must satisfy the following 8 core architectural needs:

1. **Natural Language Understanding (NLU & Comfort Empathy)**:
   - Understand actual human meaning and emotional context rather than superficial keyword matching.
   - Example: *"Yaar, bahut garmi hai"* must be recognized as comfort/weather state, responding with ambient conditions and proactive care (*"Haan, kaafi garmi lag rahi hai! Temperature abhi 29°C hai. AC ya fan on kar doon?"*).
2. **Conversation Context & Short-Term Memory**:
   - Maintain multi-turn conversational context (`active_target`, `current_app`, `last_website`).
   - Example: *"YouTube kholo"* followed by *"Arijit Singh ka gaana chalao"* resolves the song command within YouTube without re-asking or opening a generic search.
3. **Intent & Dialogue Management (Speech-Act & Banter Discrimination)**:
   - Accurately categorize intent: command, inquiry, rhetorical question, playful banter, or frustration.
   - Example: *"Tum pagal ho kya?"* must never be treated as a system error or unhandled intent; answer with witty, polite, self-aware charm (*"Nahi Sir, mere circuits bilkul theek chal rahe hain!..."*).
4. **Conversational Reasoning & Entity Follow-ups**:
   - Understand ordinals, follow-up inquiries, and incomplete thoughts referring to recent output.
   - Example: *"News batao"* followed by *"Pehli wali detail mein batao"* resolves item #1 from the active news headlines context and provides in-depth details.
5. **Reliable Speech-to-Text (STT) & Phonetic Resilience**:
   - Robust Hindi/English/Hinglish speech processing with phonetic correction layers for STT misrecognitions (e.g., *"new batao"* $\rightarrow$ *"news batao"*, *"gane chalao"* $\rightarrow$ *"gaana chalao"*).
6. **Natural Text-to-Speech (TTS) & Text Sanitization**:
   - Expressive, natural-cadence speech. Never speak raw markdown, emoji code points, technical error traces, or bracketed debug strings.
7. **Consistent Personality & Long-Term Preference Memory**:
   - Consistent Jarvis persona (helpful, respectful, slightly witty). Persist explicit user preferences (e.g., *"Mujhe short answers pasand hain"* sets `brevity_preference = short`) and adapt response verbosity accordingly.
8. **Tool Execution & Universal Response Verification**:
   - Never say *"YouTube khol diya"* or *"Application band ho gayi"* without universal post-execution verification confirming process/window state.

---

## 4. ARCHITECTURE REFERENCE

### Intent → Decision → Execution pipeline
```
USER SPEECH → STT → NORMALIZATION → ENTITY EXTRACTION → SPEECH-ACT GATING → INTENT →
CONTEXT → DECISION → ACTION PLAN → POLICY → EXECUTION → VERIFICATION → RESULT → TTS/UI
```
Keep these responsibilities separate. Intent-detection changes are HIGH RISK: check priority order, fallback behavior, and whether a new rule could steal commands from an existing intent — with 5000+ features, an overly broad new rule is the most common way to silently break something unrelated.

### Context ownership
One authoritative runtime context for `current_app`, `current_target`, `active_task`, `workflow_state`. Other components read it or publish update *events* — they don't silently keep their own conflicting copy.

### Memory
Keep Working / Short-term / Episodic / Semantic / Procedural / Activity memory conceptually distinct, but route access through existing repositories (`MemoryRepository`, `ActivityRepository`, etc.) rather than opening databases directly. Any schema/storage-topology change is HIGH RISK.

### EventBus
Standardize event names — don't create duplicate events with the same meaning. Don't force every function call through the bus; use direct calls when a return value or strong ownership is needed.

### Plugins / Features
Every feature should be a self-contained module — its own intent rules, aliases, and handler — registered through one central loader (§8), not scattered logic entangled with other features. Before changing any shared interface, search all usages via the registry first, then the repo. Centralize permission/risk checks (open app = LOW, delete file = HIGH) in one policy boundary rather than duplicating per-feature.

### Proactive intelligence & learning
Suggestions must go through the normal Decision Core → Policy → Executor path — never bypass confirmation/verification. Learning from a single correction should not create a permanent global rule without meeting the learning policy's evidence/confidence threshold, and must stay revisable.

### Privacy & observation
Store meaningful semantic events (`APPLICATION_OPENED`, `VIDEO_PAUSED`) — not raw keystrokes, passwords, screen recordings, or clipboard contents by default.

### Async / threads / GUI
Don't convert async to sync for convenience, and don't introduce blocking calls into the listener, wake-word path, or TTS path. Check synchronization before touching shared state accessed from multiple threads. Don't block the GUI main thread.

### Performance & Latency Targets
- **Target Response Latency**:
  - Very high-confidence / deterministic commands (e.g., volume, time, joke, direct app launch): `< 300 ms` response start.
  - Simple commands: `< 500 ms` response start.
- **Adaptive Response Policy**:
  - For actions that have an inherent operating system delay (like window activation or slow app launching), stream an immediate conversational acknowledgement (`"Chrome open kar raha hoon, Boss."`) to TTS so the user hears speech in `< 50 ms` while the verified action executes asynchronously.
- **Non-blocking Pipelines**:
  - Never block the VoiceListener during TTS playback (barge-in enabled).
  - Never block TTS playback while background actions or target resolutions are executing.
  - Stream the first sentence fragment immediately to TTS rather than waiting for the entire multi-sentence response to generate.
- **TTS & Audio Storage Lifecycle (Zero-Persistence In-Memory)**:
  - **In-Memory Default**: Spoken responses are synthesized and streamed directly to audio output via `io.BytesIO` in-memory buffers.
  - **Zero Disk Accumulation**: Generated `.mp3` files must NEVER permanently accumulate in `data/audio_cache` or any local directory.
  - **Guaranteed Cleanup**: If an underlying driver or fallback requires a temporary file (`tempfile.NamedTemporaryFile`), it MUST be wrapped in a `try...finally` block that unlinks the file immediately after playback or on error.
  - **Fast Text Emission**: Background workers (`TaskWorker`) must NEVER block text display on audio synthesis; text emits immediately and TTS streams asynchronously.
  - **Barge-In Safety**: Interruption or priority cancellation resets the engine stop flag on new turns, ensuring future speech is never silently dropped.
- **Measurement**:
  - All turns track stage metrics (`PipelineLatencyTracker` in `core/latency.py`): STT, Intent Detection, Response Planning, Action Execution, TTS Startup, and Total Response Latency.
- Avoid repeated full-repo scans, redundant OCR/screenshots, or repeated model reloads at runtime — prefer caching, debouncing, and lazy loading. At 5000+ features, an O(n) check against every feature on every voice command is a real performance risk — prefer indexed/hashed lookup (see §8) over linear scans.

---

## 5. FEATURE REGISTRY (critical at this scale)

Maintain a single machine-readable index — e.g. `features_registry.json` or `FEATURES.md` — as the **first thing any agent checks**, before grepping the repo blind.

Each entry should record, at minimum:
```
feature_id, name, file_path, intents, aliases, dependencies,
risk_tier (LOW/MEDIUM/HIGH), owner_module, status (active/deprecated), last_modified
```

**Rules:**
- Before building anything new, search this registry first. Only fall back to a full repo search if the registry doesn't answer it.
- Every new feature gets an entry. Every changed feature gets its entry updated. Every removed feature gets marked `deprecated`, not silently deleted from the registry.
- If the registry doesn't exist yet, creating it is the single highest-leverage first task for this project — propose it before anything else at this scale.
- The registry is a lookup index, not documentation prose — keep entries short and structured so they stay greppable/parseable.

---

## 6. NAMING & COLLISION PREVENTION

At 5000+ features, alias/intent collisions are the #1 silent-regression source.

- Before adding any new intent keyword or alias, check the registry (§5) for existing usage — never assume a word is "free."
- Prefer namespaced feature IDs (`media.youtube.play`, `system.volume.set`) over flat names — makes collisions visible at a glance and search unambiguous.
- If two features could plausibly claim the same phrase, resolve via specificity + context, not by whichever was coded most recently.
- Never let a new "catch-all"/generic rule sit ahead of existing specific rules in priority order — generic rules go last, after all specific matches fail.

---

## 7. RISK TIERING

Classify every feature once (store it in the registry, §5):

| Tier | Examples | Rule |
|---|---|---|
| LOW | open app, read status, play media | No confirmation needed |
| MEDIUM | close app, change system setting, UI automation click | Confirm if ambiguous target |
| HIGH | delete file, send message, modify shared state/DB | Explicit confirmation always |
| CRITICAL | anything irreversible, financial, or affecting other features' data | Explicit confirmation + logged + never auto-learned |

A change that raises a feature's tier (e.g. a LOW feature gaining file-write capability) must be flagged in the final report (§14), not silently absorbed.

---

## 8. ADDING A NEW FEATURE — PLAYBOOK

1. Check registry (§5) for an existing/similar feature — extend instead of duplicating if one exists.
2. Assign a namespaced `feature_id`, classify its risk tier (§7).
3. Check for alias/intent collisions (§6) before writing any matching rule.
4. Implement as a self-contained module through the existing feature-loading mechanism — not entangled with another feature's code.
5. Add/extend registry entry (§5).
6. Test: exact phrasing, natural variations, negative cases (does it wrongly fire on an existing feature's phrase, or vice versa?).
7. Run the scoped regression tier appropriate to what it touches (§9).
8. Update `architecture.txt` only if it changed a shared boundary (§10).
9. Log the session entry (§13).

---

## 9. TESTING & REGRESSION — TIERED (mandatory at this scale)

Running all 5000+ features' tests for every change isn't feasible — but skipping regression isn't acceptable either. Tier it:

- **Tier 1 — Always:** the exact reported/requested case + its direct negative cases.
- **Tier 2 — Feature-scoped:** every feature sharing the same intent namespace, alias, or file as the change.
- **Tier 3 — Shared-component:** if the change touched context, EventBus, memory, router, or policy — run the full smoke-test set (a maintained subset covering one representative case per feature category, not all 5000).
- **Tier 4 — Full suite:** only for architecture-level changes (§10) or before a release milestone.

State explicitly in the final report which tier was run and why that tier was sufficient for this change.

Don't delete/merge tests to shrink file count — check Git history and coverage before removing any test.

---

## 10. `architecture.txt` & ARCHIFY VIEWER SYNC

`architecture.txt` documents actual implemented architecture — never planned/speculative features, never TODOs, and never individual-feature detail (that belongs in the registry, §5).

**Update it when:** subsystem ownership, data flow, lifecycle, persistence topology, or major event/plugin boundaries actually change.
**Don't update it for:** typo/logging/formatting fixes, or adding/changing an individual feature that doesn't touch shared architecture.

### Archify Live Architecture Viewer Invariant:
Whenever an architectural gap is filled or architecture changes:
1. Update [plugins/archify/jarvis-architecture.json](file:///c:/Users/Admin/Documents/Jarvis_V2.1/plugins/archify/jarvis-architecture.json) to reflect the exact verified nodes, data flows, and subsystem boundaries.
2. Immediately compile and synchronize [plugins/archify/jarvis-architecture.html](file:///c:/Users/Admin/Documents/Jarvis_V2.1/plugins/archify/jarvis-architecture.html) via:
   ```bash
   python -c "from plugins.archify.builder import sync_architecture_changes; sync_architecture_changes()"
   ```
3. Ensure all visual lenses, routes, cards, and guided paths in the HTML artifact match the current runtime reality.


---

## 11. DEPRECATION / FEATURE REMOVAL PROTOCOL

- Never hard-delete a feature in one step. Mark it `deprecated` in the registry first, disable its trigger, keep the code for one cycle.
- Search the registry + repo for anything depending on it before removal.
- Confirm no other feature's fallback path relies on the one being removed.
- Only delete the code once confirmed unused, and remove its registry entry in the same commit as the deletion (not before).

---

## 12. CHANGE IMPACT ANALYSIS (shared components)

Before modifying anything shared (router, context, EventBus, memory, policy):
```
Changed component → direct callers → indirect consumers (via registry) →
features in same namespace → event subscribers → Tier 3 smoke tests → potential regression
```
Shared-infrastructure changes always require Tier 3 minimum (§9), regardless of how small the change looks.

---

## 13. SESSION CONTINUITY LOG

No agent session remembers the last one. Maintain a lightweight running log — e.g. `AGENT_LOG.md` — appended (not rewritten) at the end of every task:

```
[date] feature_id(s) touched — one-line summary of what changed and why —
risk tier — architecture.txt updated? (y/n) — anything left unresolved
```

Check the last few entries at the start of a new session if the task relates to recently-touched areas — it's cheaper than re-discovering context from scratch.

---

## 14. FINAL RESPONSE FORMAT

```
## Changed
<files/functions/feature_ids modified>

## Root Cause
<brief actual cause>

## Fix
<what changed and why>

## Registry
UPDATED / NOT NEEDED — <feature_id entries touched>

## Verification
<tests actually performed>

## Regression Tier Run
<Tier 1/2/3/4 — why this tier was sufficient>

## Architecture
CHANGED / UNCHANGED — <impact summary if changed>

## architecture.txt
UPDATED / NOT UPDATED — <reason>

## Risk
LOW / MEDIUM / HIGH / CRITICAL — <why, and whether tier changed>

## Session Log
APPENDED — <one-line entry added to AGENT_LOG.md>

## Remaining Issues
<unrelated issues discovered but not touched, out of scope>
```