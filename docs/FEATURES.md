# JARVIS — FEATURE REGISTRY

> **Purpose:** Machine-readable, human-readable index of the actual Jarvis feature set.
>
> **Source of truth:** The repository implementation is authoritative.
> `FEATURES.md` is an indexed registry of implemented features, not a specification.
>
> **Do not list planned, speculative, abandoned, or nonexistent features as active.**
>
> **Keep this file structured, concise, searchable, and synchronized with the repository.**

---

# 1. REGISTRY RULES

## 1.1 Core Rules

1. Every active feature should have a unique `feature_id`.
2. Feature IDs must be namespaced.
3. Every feature should map to its real implementation location.
4. Every feature should identify its owner module.
5. Intents and aliases must be registered.
6. Dependencies should be recorded when relevant.
7. Every feature must have a risk tier.
8. Every feature should have a lifecycle status.
9. Important tests should be mapped to the feature.
10. Changes to a feature must update its registry entry in the same task.
11. Removed features should not disappear without trace.
12. Deprecated features should be marked `deprecated` before final removal.
13. Never create duplicate feature IDs.
14. Never knowingly create duplicate aliases for competing features.
15. Registry data must reflect actual code.

---

# 2. FEATURE ID CONVENTION

Use hierarchical namespaced IDs.

Preferred:

```text
system.app.launch
system.app.close
system.volume.set

browser.chrome.open
browser.brave.open
browser.tab.close

media.youtube.play
media.youtube.pause
media.youtube.search

productivity.excel.select
productivity.excel.formula
productivity.excel.fill_down

communication.whatsapp.send
communication.email.send

memory.context.store
memory.episodic.store
memory.preference.learn

proactive.observer.desktop
proactive.pattern.detect
proactive.suggestion.generate

workflow.create
workflow.execute

reminder.create
reminder.cancel

companion.smalltalk.chat
companion.checkin.proactive
companion.greeting.personalized
companion.mood.support
companion.humor.banter
```

Avoid flat IDs such as:

```text
open1
excel2
youtube3
memory4
```

A feature ID must describe its domain and capability.

---

# 3. STATUS VALUES

Allowed lifecycle statuses:

```text
experimental
active
maintenance
deprecated
disabled
removed
```

Meaning:

### experimental

Implemented but still being actively evaluated.

### active

Supported and currently used.

### maintenance

Stable but receiving limited changes.

### deprecated

Still present but should no longer receive new usage.

### disabled

Implemented but intentionally disabled.

### removed

No longer implemented. Keep historical entry only when useful for traceability.

---

# 4. RISK TIERS

Use:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

### LOW

Examples:

```text
open application
read system status
play media
read screen state
casual conversation / small talk
personalized greeting
```

### MEDIUM

Examples:

```text
close application
change system setting
UI automation click
move/modify non-sensitive UI state
proactive check-in (frequency-limited, no external side effect)
```

### HIGH

Examples:

```text
delete file
send message
modify shared state
modify database records
execute consequential automation
```

### CRITICAL

Examples:

```text
financial operation
irreversible operation
security-sensitive operation
operation affecting other features' data
high-impact external action
```

Risk must describe the capability, not simply the implementation complexity.

> **Note for companion/personality features:** risk here is not just about system capability — it's also about the *emotional* footprint. A feature that references stored personal facts, initiates unprompted check-ins, or comments on mood should default to LOW/MEDIUM capability risk, but is still governed by the tone rules in §40 regardless of tier — a "harmless" companion feature can still be badly designed if it fosters dependency or overclaims understanding.

---

# 5. REGISTRY SCHEMA

Each feature entry should contain these fields:

```text
feature_id
name
description
domain
status
risk_tier
owner_module
file_path
entrypoint
intents
aliases
dependencies
events_published
events_consumed
permissions
confirmation_required
test_paths
regression_tier
last_modified
notes
```

Not every field must contain a value when genuinely not applicable.

Do not invent values.

---

# 6. FEATURE ENTRY TEMPLATE

Use this template for every feature:

```yaml
feature_id: domain.capability.name
name: Human-readable feature name
description: One-line description
domain: core|infrastructure|system|browser|media|productivity|communication|memory|proactive|workflow|utility|security|companion|other
status: active
risk_tier: LOW

owner_module: path.to.owner
file_path:
  - path/to/file.py

entrypoint:
  - function_or_class_name

intents:
  - intent.name

aliases:
  - "example phrase"
  - "another phrase"

dependencies:
  modules:
    - path.to.module
  features:
    - domain.other.feature
  plugins:
    - plugin_name
  events:
    - EVENT_NAME
  databases:
    - database_name

events_published:
  - EVENT_NAME

events_consumed:
  - EVENT_NAME

permissions:
  - permission.name

confirmation_required: false

test_paths:
  - tests/path/test_feature.py

regression_tier: 2

last_modified: YYYY-MM-DD

notes: ""
```

---

# 7. CURRENT FEATURE REGISTRY

> The entries below must be populated from the actual repository.
>
> Do not mark a feature `active` merely because it is mentioned in architecture documentation.
>
> If the repository does not verify it, do not invent it.

---

## 7.0 CORE & RUNTIME INFRASTRUCTURE

### Feature: Zero-Downtime Live Background Code Update

```yaml
feature_id: core.infrastructure.zero_downtime_update
name: Zero-Downtime Live Background Code Update
description: In-process background file watcher and transaction manager that hot-reloads plugins, modules, and worker runtimes without closing or destroying the GUI host window
domain: core
status: active
risk_tier: LOW
owner_module: core.update_manager
file_path:
  - core/update_manager.py
  - core/reload_policy.py
  - core/reloader.py
  - gui/app.py
entrypoint:
  - LiveUpdateManager
intents: []
aliases: []
dependencies:
  modules:
    - core.reload_policy
    - core.reloader
    - core.event_bus
  features: []
  plugins: []
  events: []
  databases: []
events_published:
  - system.update.status
  - system.update.full_restart_needed
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_live_update_manager.py
  - tests/test_auto_reloader.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Maintains persistent GUI host lifetime. File modifications never terminate the GUI."
```

### Feature: Priority-Based Application Resolver & Windows System App Launcher

```yaml
feature_id: core.apps.resolver
name: Priority-Based Application Resolver (Delegated / Shared Component)
role: delegated_shared_component
authoritative_owner: core.windows.app_resolver
description: High-level delegated application resolution adapter (ResolvedApp, AppResolver) providing query parsing, shortcut extraction, and legacy fallback. Defers and delegates all canonical Windows application specs, system app definitions, entity extraction, and fuzzy alias matching to the authoritative owner core.windows.app_resolver.
domain: core
status: active
risk_tier: LOW
owner_module: core.apps.resolver
file_path:
  - core/apps/resolver.py
  - core/apps/registry.py
  - core/apps/aliases.py
  - core/apps/detector.py
  - core/execution/strategies.py
  - core/execution/verifier.py
  - plugins/windows/window_manager.py
entrypoint:
  - core.apps.resolver.AppResolver
  - core.apps.resolver.get_app_resolver
intents:
  - OPEN_APP
aliases:
  - "open camera"
  - "camera kholo"
  - "camera chalao"
  - "launch camera"
  - "start camera"
  - "open calculator"
  - "calculator kholo"
  - "open settings"
  - "settings kholo"
  - "open notepad"
  - "open paint"
  - "open task manager"
  - "open file explorer"
  - "open control panel"
  - "open command prompt"
  - "open powershell"
  - "open snipping tool"
dependencies:
  modules:
    - core.windows_app_resolver
    - core.apps.registry
    - core.apps.detector
    - core.execution.strategies
    - core.execution.verifier
  features:
    - core.windows.app_resolver
    - core.execution.gateway
  plugins:
    - windows
  events: []
  databases: []
events_published: []
events_consumed: []
permissions:
  - windows.execute
confirmation_required: false
test_paths:
  - tests/test_app_resolver_system_apps.py
  - tests/test_application_resolution_layer.py
regression_tier: 2
last_modified: 2026-09-13
notes: "DELEGATED COMPONENT: Delegates entity extraction, fuzzy matching, and system app definitions directly to authoritative owner core.windows.app_resolver. Preserves backwards-compatible ResolvedApp dataclass."
```

### Feature: Windows Application Resolver & Entity-Aware Context Spell Corrector

```yaml
feature_id: core.windows.app_resolver
name: Windows Application Resolver & Entity-Aware Context Spell Corrector (Authoritative Owner)
role: authoritative_owner
delegated_components:
  - core.apps.resolver
  - core.apps.registry
description: Authoritative Single Source of Truth (SSOT) for Windows application resolution in Jarvis. Implements a dedicated 6-tier Windows application hierarchy (User Learned, Registry data/windows_apps.json, Installed Discovery, Execution Aliases, PATH Lookup, Fallback) with fuzzy STT typo handling (e.g. microsft store -> Microsoft Store), UWP protocol launch/verification, safe process termination (WinStore.App.exe, SystemSettings.exe), bare-word disambiguation, and user alias learning. Powers all downstream resolvers and window managers.
domain: core
status: active
risk_tier: LOW
owner_module: core.windows_app_resolver
file_path:
  - core/windows_app_resolver.py
  - data/windows_apps.json
  - brain/spelling_resolver.py
  - core/apps/resolver.py
  - core/apps/registry.py
  - core/entities/knowledge.py
  - core/semantic/parsers/windows.py
  - core/semantic/parsers/aliases.py
  - core/execution/strategies.py
entrypoint:
  - core.windows_app_resolver.WindowsAppResolver
  - core.windows_app_resolver.get_windows_app_resolver
intents:
  - OPEN_APP
  - WINDOW_CLOSE
  - LEARN_ALIAS
aliases:
  - "open microsoft store"
  - "open microsft store"
  - "microsoft store kholo"
  - "microsoft store open karo"
  - "close microsoft store"
  - "microsoft store band karo"
  - "store se mera matlab Microsoft Store hai"
  - "jab main 'store' bolun to Microsoft Store open karna"
dependencies:
  modules:
    - data.windows_apps
    - brain.spelling_resolver
    - core.alias_manager
    - core.execution.strategies
  features: []
  plugins:
    - windows
  events: []
  databases:
    - custom_aliases
events_published: []
events_consumed: []
permissions:
  - windows.execute
confirmation_required: false
test_paths:
  - tests/test_windows_app_resolver.py
  - tests/test_windows_11_system_apps.py
  - tests/test_spelling_resolver.py
  - tests/test_app_resolver_system_apps.py
  - tests/test_multi_entity_commands.py
regression_tier: 2
last_modified: 2026-09-13
notes: "AUTHORITATIVE OWNER (SSOT): Single authoritative owner for Windows application resolution. Supplies app specs, process names, and launch targets consumed by core.apps.resolver, WindowManager, and TargetEngine. Intercepts application entities before generic spell-checking to avoid corrupting app names."
```

### Feature: Live Chat View & Auto-Scroller

```yaml
feature_id: gui.chat.view
name: Live Chat View & Auto-Scroller
description: Interactive conversational stream panel with rich HTML typography, selectable text, command history navigation, dynamic context chips, and layout-synchronized auto-scrolling to keep latest messages pinned to the bottom.
domain: gui
status: active
risk_tier: LOW
owner_module: gui.views.chat_view
file_path:
  - gui/views/chat_view.py
  - gui/app.py
entrypoint:
  - gui.views.chat_view.ChatView
  - gui.views.chat_view.LiveChatBrowser
intents: []
aliases: []
dependencies:
  modules:
    - PySide6.QtWidgets
    - PySide6.QtCore
    - PySide6.QtGui
  features: []
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_gui.py
regression_tier: 2
last_modified: 2026-09-06
notes: "Maintains scrollbar pinned to maximum on rangeChanged when new messages expand document layout, while pausing auto-scroll when user manually scrolls up to read history."
```

### Feature: Saved Websites GUI Management (View, Edit, Delete, Enable/Disable, Test/Open, Search)

```yaml
feature_id: gui.websites.manager
name: Saved Websites GUI Management
description: Professional cyber-dark GUI panel in Jarvis desktop interface enabling users to view, live-edit target URLs, toggle active state (enable/disable), test open in default browser, search, and delete saved website shortcuts without modifying code.
domain: gui
status: active
risk_tier: LOW
owner_module: gui.views.websites_view
file_path:
  - gui/views/websites_view.py
  - gui/app.py
  - core/website_knowledge.py
entrypoint:
  - gui.views.websites_view.WebsitesView
  - gui.views.websites_view.AddEditWebsiteDialog
intents: []
aliases: []
dependencies:
  modules:
    - PySide6.QtWidgets
    - PySide6.QtCore
    - PySide6.QtGui
    - core.website_knowledge
  features:
    - web.website_resolution.user_learning
  plugins:
    - browser
  events: []
  databases:
    - data/jarvis.db.website_knowledge
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_websites_gui_view.py
  - tests/test_gui.py
regression_tier: 2
last_modified: 2026-09-16
notes: "Live edit updates SQLite and cache immediately so the next 'open <alias>' voice/text query resolves to the updated URL without application restart."
```

### Feature: Conversation Interrupted Domain Event & Barge-In Dispatch

```yaml
feature_id: infrastructure.eventbus.conversation_interrupted
name: Conversation Interrupted Domain Event & Barge-In Dispatch
description: Standardized EventBus domain event and state invalidation emitted upon active speech interruption or user barge-in with backwards-compatible argument support (generation_id, turn_id, interrupted_at) and dict-like .get access
domain: infrastructure
status: active
risk_tier: LOW
owner_module: core.event_bus
file_path:
  - core/event_bus.py
  - core/app.py
entrypoint:
  - core.event_bus.ConversationInterrupted
  - core.app.JarvisCore.interrupt_active_speech
intents: []
aliases: []
dependencies:
  modules:
    - core.event_bus
    - core.conversation
  features: []
  plugins: []
  events: []
  databases: []
events_published:
  - conversation.interrupted
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_barge_in.py
  - tests/test_event_bus_architecture.py
regression_tier: 2
last_modified: 2026-09-06
notes: "Supports both canonical dataclass parameters (previous_generation_id, previous_turn_id, interrupting_input, timestamp) and caller alias signatures (generation_id, turn_id, interrupted_at) with dict-like get() access."
```

### Feature: Human-Like Conversational Response & Feedback Policy

```yaml
feature_id: core.response.policy
name: Human-Like Conversational Response & Feedback Policy
description: Centralized conversational formatting and response generation engine enforcing concise, natural, context-aware feedback (DIRECT ANSWER -> OPTIONAL USEFUL DETAIL -> STOP) without technical process metadata, raw paths, or debug brackets.
domain: core
status: active
risk_tier: LOW
owner_module: core.response_policy
file_path:
  - core/response_policy.py
  - core/semantic/parsers/system.py
  - core/app.py
  - plugins/screen/plugin.py
entrypoint:
  - core.response_policy.ConversationalResponsePolicy
  - core.response_policy.get_response_policy
intents:
  - check_status
  - screen_inspect
aliases:
  - "chrome open hai kya?"
  - "chrome chal raha hai?"
  - "chrome active hai kya?"
  - "chrome open nahi hai na?"
  - "kaunsa chrome window open hai?"
  - "kaunsa window active hai?"
  - "screen par kya hai?"
dependencies:
  modules:
    - win32gui
  features: []
  plugins:
    - screen
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversational_response_policy.py
  - tests/test_question_vs_command_status.py
  - tests/test_screen_inspection.py
regression_tier: 2
last_modified: 2026-09-07
notes: "Strips internal window title suffixes (- Google Chrome), filters process names (.exe), detects minimization and foreground states, and distinguishes affirmative/negative/active status inquiries."
```

### Feature: Conversational Intent & Speech-Act Classification Layer

```yaml
feature_id: core.conversational.speech_act
name: Conversational Intent & Speech-Act Classification Layer
description: Authoritative 12-category speech-act classifier separating capability questions, action commands, status checks, troubleshooting, confirmations, and small talk before execution so action keywords alone never trigger commands.
domain: core
status: active
risk_tier: LOW
owner_module: core.conversational_intent
file_path:
  - core/conversational_intent.py
  - core/app.py
  - core/semantic/parsers/system.py
entrypoint:
  - core.conversational_intent.ConversationalIntentClassifier
  - core.conversational_intent.ConversationalIntentType
intents:
  - CAPABILITY_QUESTION
  - ACTION_COMMAND
  - STATUS_QUESTION
  - STATUS_AFTER_ACTION
  - TROUBLESHOOTING
  - CONFIRMATION
  - CANCELLATION
  - CLARIFICATION
  - INFORMATION_QUESTION
  - GREETING
  - CONVERSATION
  - FOLLOW_UP
aliases:
  - "kya tum system lock kar sakte ho?"
  - "system lock karo"
  - "system lock hai kya?"
  - "system lock kyun nahi ho raha?"
  - "system lock hua?"
  - "Chrome open kar sakte ho?"
  - "Chrome open karo"
  - "Chrome open hua?"
  - "can you open Chrome?"
  - "tum Excel chala sakte ho?"
  - "can you restart the computer?"
  - "haan karo"
  - "nahi"
dependencies:
  modules: []
  features:
    - core.response.policy
  plugins:
    - system
    - apps
  events:
    - response.completed
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversational_intent_speech_act.py
  - tests/test_question_vs_command_status.py
  - tests/test_capability_architecture.py
  - tests/test_conversational_benchmark_flows.py
regression_tier: 2
last_modified: 2026-09-27
notes: "Enforces: Understand PURPOSE first -> Execute second -> Speak naturally third. Only ACTION_COMMAND or confirmed actions execute. 2026-09-27 human-like upgrade: VLC capability (clean 'mere liye' entity), feminine sakti/saktey forms + bare-capability overview, Hindi discourse/ellipsis inheritance ('to open karo'->last target), complaint-recovery execution ('bola tha...kyun nahi kartey'->apologize+open), 'sab thik hai' wellbeing ack. 2026-09-27 round 2: proactive open offer on capability answers ('Kya main VLC aapke liye open kar dun?' + open_app_offer confirmation, haan/yes opens), praise-preamble + karke-dikhao suffix stripping, wellbeing STATUS_UPDATE direct ack (no SMALL_TALK override). 2026-09-27 round 3 (43-example benchmark): EMAIL/MESSAGE/MEETING/REMINDER/ALARM slot workflows with mid-lock corrections, proactive open offer, weather/music/mailbox/app-restart/volume-repeat follow-ups, multi-command split, crash guard, kal-protection, visual/web-search disambiguation."
```

### Feature: Knowledge-Based General Knowledge (GK) Engine
```yaml
feature_id: core.knowledge.engine
name: General Knowledge & Reasoning Subsystem
description: Knowledge-based general knowledge and reasoning engine organizing static facts, entities, relations, and scientific concepts without storing thousands of individual Q&A pairs.
status: active
risk_tier: LOW
owner_module: core.knowledge
file_path:
  - core/knowledge/models.py
  - core/knowledge/entity_store.py
  - core/knowledge/reasoning_store.py
  - core/knowledge/synonyms.py
  - core/knowledge/router.py
  - core/knowledge/formatter.py
  - core/knowledge/engine.py
  - core/app.py
  - brain/llm.py
entrypoint:
  - core.knowledge.KnowledgeEngine
  - core.knowledge.get_knowledge_engine
intents:
  - general_knowledge_query
  - factual_inquiry
  - reasoning_inquiry
  - time_sensitive_inquiry
aliases:
  - "India ki capital kya hai?"
  - "Bharat ki rajdhani kya hai?"
  - "What is the capital of India?"
  - "Tell me India's capital"
  - "India ka currency kya hai?"
  - "Photosynthesis kya hota hai?"
  - "Why does the sky appear blue?"
  - "Explain gravity simply"
  - "Who is the current Prime Minister?"
  - "Today's weather?"
  - "What is the capital of France?"
dependencies:
  modules: []
  features:
    - core.conversational.speech_act
  plugins: []
  events:
    - response.completed
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_knowledge_engine.py
regression_tier: 2
last_modified: 2026-09-07
notes: "Stores structured entities and relations across 16 categories. Resolves diverse natural phrasings to single facts. Anti-hallucination on LOW confidence."
```

### Feature: IT & Infrastructure Technical Knowledge Engine

```yaml
feature_id: knowledge.it_engine
name: IT & Infrastructure Technical Knowledge Engine
status: active
risk_tier: LOW
owner_module: core.knowledge.it
file_path:
  - core/knowledge/it/models.py
  - core/knowledge/it/concept_store.py
  - core/knowledge/it/troubleshooting_store.py
  - core/knowledge/it/command_store.py
  - core/knowledge/it/classifier.py
  - core/knowledge/it/context_tracker.py
  - core/knowledge/it/engine.py
  - core/knowledge/it/__init__.py
  - core/knowledge/router.py
  - core/knowledge/engine.py
  - core/app.py
entrypoint:
  - core.knowledge.it.ITKnowledgeEngine
  - core.knowledge.it.get_it_knowledge_engine
intents:
  - it_knowledge_inquiry
  - it_troubleshooting_query
  - it_command_explanation
  - it_configuration_howto
aliases:
  - "Windows Server 2019 mein DNS kya hai?"
  - "RDP connect nahi ho raha, kya check karu?"
  - "Azure VM kya hota hai?"
  - "What does ipconfig do?"
  - "domain user login kyun nahi kar paa raha?"
  - "Server ka disk full ho gaya hai."
  - "Azure VM reachable nahi hai."
  - "DHCP IP nahi de raha."
  - "IIS website open nahi ho rahi."
  - "Server 2019 mein DNS configure kar raha hoon -> ab next kya karu?"
dependencies:
  modules: []
  features:
    - knowledge.general_core
    - core.conversational.speech_act
  plugins: []
  events:
    - response.completed
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_it_knowledge_engine.py
regression_tier: 2
last_modified: 2026-09-08
notes: "Dedicated enterprise IT knowledge engine covering Windows Desktop, Windows Server 2019, Microsoft Azure, Networking, and Enterprise Infrastructure. 6-phase structured troubleshooting, safe command catalog with strict execution decoupling, and multi-turn contextual tracking."
```

### Calendar & Festival Knowledge Engine

```yaml
feature_id: knowledge.calendar.festival_date
name: Indian Festival Date Resolution (Year-Aware)
status: active
risk_tier: LOW
owner_module: core.knowledge.calendar
file_path:
  - core/knowledge/calendar/models.py
  - core/knowledge/calendar/festival_store.py
  - core/knowledge/calendar/year_inference.py
  - core/knowledge/calendar/intent_classifier.py
  - core/knowledge/calendar/formatter.py
  - core/knowledge/calendar/engine.py
  - core/knowledge/calendar/__init__.py
  - core/knowledge/router.py
  - core/knowledge/models.py
  - core/knowledge/__init__.py
  - core/knowledge/pipeline/normalizer.py
  - core/knowledge/pipeline/classifier.py
entrypoint:
  - core.knowledge.calendar.FestivalCalendarEngine
  - core.knowledge.calendar.get_festival_calendar_engine
intents:
  - FESTIVAL_DATE_QUERY
  - NATIONAL_DAY_QUERY
  - FESTIVAL_DURATION
aliases:
  - "Ganpati kab hai?"
  - "Diwali is saal kab hai?"
  - "2026 mein Holi kab padegi?"
  - "Agle saal Janmashtami kab hai?"
  - "Republic Day kab hai?"
  - "Independence Day kab hai?"
  - "Teachers Day kab hai?"
  - "Navratri 2027 kab se kab tak?"
  - "Ganesh Chaturthi kitne din chalti hai?"
dependencies:
  modules: []
  features:
    - knowledge.general_core
    - core.knowledge.engine
  plugins: []
  events:
    - response.completed
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_festival_calendar_engine.py
regression_tier: 2
last_modified: 2026-09-08
notes: "Year-aware Indian festival date resolution. 30+ festivals covering Hindu, Sikh, Buddhist, Jain, Islamic, Christian, and national observances. Dates pre-verified from Drik Panchang for 2024-2028. Current year ALWAYS from datetime.now() — never hardcoded. Step 3.5 in KnowledgeRouter."
```

```yaml
feature_id: knowledge.calendar.festival_info
name: Indian Festival Definition & Description
status: active
risk_tier: LOW
owner_module: core.knowledge.calendar
file_path:
  - core/knowledge/calendar/festival_store.py
  - core/knowledge/calendar/engine.py
  - core/knowledge/calendar/intent_classifier.py
entrypoint:
  - core.knowledge.calendar.FestivalCalendarEngine
intents:
  - FESTIVAL_INFO
aliases:
  - "Ganesh Chaturthi kya hai?"
  - "Diwali kya hota hai?"
  - "What is Holi?"
  - "Republic Day ke baare mein batao"
  - "Navratri explain karo"
dependencies:
  features: [knowledge.calendar.festival_date]
confirmation_required: false
test_paths:
  - tests/test_festival_calendar_engine.py
regression_tier: 2
last_modified: 2026-09-08
notes: "Returns bilingual (Hinglish/English) summaries for all 30+ festival entries."
```

```yaml
feature_id: knowledge.calendar.upcoming_events
name: Upcoming Festival Finder
status: active
risk_tier: LOW
owner_module: core.knowledge.calendar
file_path:
  - core/knowledge/calendar/festival_store.py
  - core/knowledge/calendar/engine.py
  - core/knowledge/calendar/intent_classifier.py
entrypoint:
  - core.knowledge.calendar.FestivalCalendarEngine
intents:
  - UPCOMING_FESTIVAL
  - MONTH_FESTIVAL
aliases:
  - "Agla festival kaunsa hai?"
  - "Next festival kab hai?"
  - "Upcoming tyohaar kaunsa hai?"
  - "September mein kaun sa festival hai?"
  - "Is month mein koi festival hai?"
dependencies:
  features: [knowledge.calendar.festival_date]
confirmation_required: false
test_paths:
  - tests/test_festival_calendar_engine.py
regression_tier: 2
last_modified: 2026-09-08
notes: "Computes next upcoming festival from datetime.now().date() — never hardcoded. Also resolves month-based festival queries."
```

```yaml
feature_id: knowledge.calendar.national_days
name: Indian National Day Observances
status: active
risk_tier: LOW
owner_module: core.knowledge.calendar
file_path:
  - core/knowledge/calendar/festival_store.py
  - core/knowledge/calendar/engine.py
entrypoint:
  - core.knowledge.calendar.FestivalCalendarEngine
intents:
  - NATIONAL_DAY_QUERY
aliases:
  - "Republic Day kab hai?"
  - "Gantantra Diwas kab hai?"
  - "Independence Day kab hai?"
  - "Gandhi Jayanti kab hai?"
  - "Teachers Day kab hai?"
  - "Childrens Day kab hai?"
  - "Constitution Day kab hai?"
  - "26 January kab hai?"
dependencies:
  features: [knowledge.calendar.festival_date]
confirmation_required: false
test_paths:
  - tests/test_festival_calendar_engine.py
regression_tier: 2
last_modified: 2026-09-08
notes: "Fixed-date national observances with entries for 2024-2034. Republic Day (26 Jan), Independence Day (15 Aug), Gandhi Jayanti (2 Oct), Teachers' Day (5 Sep), Children's Day (14 Nov), Constitution Day (26 Nov), National Science Day (28 Feb)."
```

---

## 7.1 SYSTEM & WINDOWS

### Feature: Application Launcher

```yaml
feature_id: system.app.launch
name: Application Launcher
description: Opens installed/local desktop applications.
domain: system
status: active
risk_tier: LOW
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - app.open
aliases:
  - "open application"
  - "application kholo"
  - "app kholo"
dependencies:
  modules: []
  features: []
  plugins: []
  events: []
  databases: []
events_published:
  - VERIFY_FROM_REPO
events_consumed:
  - VERIFY_FROM_REPO
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 2
last_modified: VERIFY_FROM_REPO
notes: "Application resolution must prefer a valid local application before website fallback."
```

### Feature: Application Close

```yaml
feature_id: system.app.close
name: Application Close
description: Closes a selected application or window.
domain: system
status: active
risk_tier: MEDIUM
owner_module: core.execution.strategies
file_path:
  - plugins/windows/window_manager.py
  - core/execution/strategies.py
  - core/execution/verifier.py
  - learning/vocabulary_layer.py
entrypoint:
  - plugins.windows.window_manager.WindowManager.execute_operation
  - core.execution.strategies.ExecutionStrategyEngine.close_target_verified
intents:
  - app.close
aliases:
  - "close app"
  - "application band karo"
  - "app band karo"
  - "brave browser close karo"
  - "chrome browser close karo"
dependencies:
  modules:
    - psutil
  features: []
  plugins:
    - windows
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_browser_descriptor_resolution.py
  - tests/test_universal_verification_layer.py
regression_tier: 2
last_modified: 2026-09-16
notes: "Protected by DESCRIPTOR_GUARDS in VocabularyLayer.resolve_text; background crash handlers/daemons filtered out in WindowManager.is_process_running."
```

---

# 8. BROWSER

### Feature: Browser Open

```yaml
feature_id: browser.open
name: Browser Open
description: Opens a requested browser or browser context.
domain: browser
status: active
risk_tier: LOW
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - browser.open
aliases:
  - "open chrome"
  - "chrome kholo"
  - "open brave"
  - "brave kholo"
dependencies:
  modules: []
  features:
    - system.app.launch
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_browser_status_followup.py
  - tests/test_conversational_benchmark_flows.py
regression_tier: 2
last_modified: 2026-09-27
notes: "Must preserve application-vs-website resolution. 2026-09-27: explicit browser container honored on website opens ('chatgpt ko edge browser me open karo' -> Edge, never default/preference override) + natural success message (site + browser, no raw URL echo)."
```

### Feature: Browser Tab Control

```yaml
feature_id: browser.tab.control
name: Browser Tab Control
description: Opens, closes, switches, or manages browser tabs with strict tab isolation and window state preservation.
domain: browser
status: active
risk_tier: MEDIUM
owner_module: core.target_engine
file_path:
  - core/target_engine.py
  - core/semantic/parsers/windows.py
entrypoint:
  - core.target_engine.BrowserTabManager
  - core.target_engine.UniversalTargetDiscoveryEngine
intents:
  - browser.tab.close
  - browser.tab.switch
  - UNIVERSAL_TARGET_ACTION
aliases:
  - "dhan tab close karo"
  - "YouTube wala tab band karo"
  - "GLPI ka tab band karo"
  - "current tab close karo"
dependencies:
  modules:
    - plugins.windows.window_manager
  features: []
  plugins:
    - windows
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_tab_close_isolation.py
  - tests/test_app_close_vs_tab_close.py
  - tests/test_browser_tab_window_state.py
  - tests/test_universal_target_engine.py
regression_tier: 2
last_modified: 2026-09-06
notes: "Strict tab isolation invariant: closing a browser tab NEVER calls window_manager.execute_operation('close') and verifies active tab title matches target before pressing Ctrl+W, preventing collateral closure of ChatGPT or neighboring tabs."
```

---

# 9. WEB & MEDIA

### Feature: YouTube Search

```yaml
feature_id: media.youtube.search
name: YouTube Search
description: Searches YouTube for requested content.
domain: media
status: active
risk_tier: LOW
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - youtube.search
aliases:
  - "youtube par search karo"
  - "youtube search karo"
dependencies:
  modules: []
  features: []
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 2
last_modified: VERIFY_FROM_REPO
notes: ""
```

### Feature: YouTube Playback

```yaml
feature_id: media.youtube.play
name: YouTube Playback
description: Plays a selected YouTube video.
domain: media
status: active
risk_tier: LOW
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - youtube.play
aliases:
  - "play song"
  - "song chalao"
  - "video play karo"
dependencies:
  modules: []
  features:
    - media.youtube.search
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 2
last_modified: VERIFY_FROM_REPO
notes: ""
```

---

### Feature: Smart Website Resolver & User-Learned Aliases

```yaml
feature_id: web.website_resolution.user_learning
name: Smart Website Resolver & User-Learned Aliases
description: Resolves persistent user-taught website phrases conservatively, then launches the resolved HTTP(S) URL without reusing the original phrase as a navigation target.
domain: browser
status: active
risk_tier: LOW
owner_module: plugins.browser.website_resolver
file_path:
  - core/website_knowledge.py
  - plugins/browser/website_resolver.py
  - core/target_engine.py
  - core/app.py
entrypoint:
  - WebsiteKnowledgeStore.learn
  - WebsiteResolver.resolve
  - UniversalTargetDiscoveryEngine.execute
intents:
  - OPEN_WEBSITE
  - LEARN_ALIAS
aliases:
  - "human 3d kholo"
  - "website ko map karo"
dependencies:
  modules:
    - core.context.SessionContext
    - memory.database.DatabaseManager
  features: []
  plugins:
    - browser
  events: []
  databases:
    - data/jarvis.db.website_knowledge
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_smart_website_resolver.py
  - tests/test_websites_gui_view.py
  - tests/test_custom_website_alias.py
  - tests/test_universal_verification_layer.py
regression_tier: 3
last_modified: 2026-09-16
notes: "Unknown names ask for a URL; learned aliases win over built-ins. Browser API acceptance is success, while unobservable page/window state is reported as verification_unknown rather than launch failure."
```

---

# 10. PRODUCTIVITY

## Excel

### Feature: Excel Cell Selection

```yaml
feature_id: productivity.excel.select
name: Excel Cell Selection
description: Selects cells or ranges in Excel.
domain: productivity
status: active
risk_tier: MEDIUM
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - excel.select
aliases:
  - "cell select karo"
  - "C2 select karo"
dependencies:
  modules: []
  features: []
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 2
last_modified: VERIFY_FROM_REPO
notes: ""
```

### Feature: Excel Formula

```yaml
feature_id: productivity.excel.formula
name: Excel Formula Operations
description: Creates or edits formulas in Excel.
domain: productivity
status: active
risk_tier: MEDIUM
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - excel.formula
aliases:
  - "formula lagao"
  - "formula set karo"
dependencies:
  modules: []
  features:
    - productivity.excel.select
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 2
last_modified: VERIFY_FROM_REPO
notes: ""
```

### Feature: Excel Fill Down

```yaml
feature_id: productivity.excel.fill_down
name: Excel Fill Down
description: Fills a formula or value downward through a selected range.
domain: productivity
status: active
risk_tier: MEDIUM
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - excel.fill_down
aliases:
  - "neeche fill karo"
  - "fill down karo"
dependencies:
  modules: []
  features:
    - productivity.excel.select
    - productivity.excel.formula
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: ""
```

---

# 11. COMMUNICATION

### Feature: WhatsApp Message Send

```yaml
feature_id: communication.whatsapp.send
name: WhatsApp Message Send
description: Sends a WhatsApp message to a selected contact.
domain: communication
status: active
risk_tier: HIGH
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - whatsapp.send
aliases:
  - "whatsapp message bhejo"
  - "message send karo"
dependencies:
  modules: []
  features: []
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions:
  - communication.send
confirmation_required: true
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: "External side effect. Must not execute twice for one logical request."
```

### Feature: Email Send

```yaml
feature_id: communication.email.send
name: Email Send
description: Sends email through the configured email system.
domain: communication
status: active
risk_tier: HIGH
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - email.send
aliases:
  - "email bhejo"
  - "mail send karo"
dependencies:
  modules: []
  features: []
  plugins:
    - VERIFY_FROM_REPO
  events: []
  databases: []
events_published: []
events_consumed: []
permissions:
  - communication.send
confirmation_required: true
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: "Do not expose credentials or send duplicates."
```

---

# 12. MEMORY

### Feature: Conversation Context

```yaml
feature_id: memory.context.runtime
name: Runtime Conversation Context
description: Maintains current conversational, desktop, task, and user context via authoritative RuntimeContext.
domain: memory
status: active
risk_tier: LOW
owner_module: core.context
file_path:
  - core/context.py
  - core/desktop_task/context.py
entrypoint:
  - core.context.RuntimeContext
  - core.context.get_runtime_context
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - context.updated
  databases: []
events_published:
  - context.updated
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_runtime_context.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Must remain the single authoritative runtime context."
```

### Feature: Episodic Memory

```yaml
feature_id: memory.episodic.store
name: Episodic Memory
description: Stores meaningful past conversations and session history.
domain: memory
status: active
risk_tier: LOW
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - MEMORY_UPDATED
  databases:
    - VERIFY_FROM_REPO
events_published:
  - MEMORY_UPDATED
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: ""
```

### Feature: Preference Learning

```yaml
feature_id: memory.preference.learn
name: Preference Learning
description: Learns repeated user preferences from meaningful evidence.
domain: memory
status: active
risk_tier: LOW
owner_module: core.intelligence.preference_learner
file_path:
  - core/intelligence/preference_learner.py
entrypoint:
  - core.intelligence.preference_learner.AdaptivePreferenceLearner
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - learning.detected
    - memory.created
  databases:
    - data/jarvis.db
events_published:
  - memory.created
events_consumed:
  - learning.detected
permissions: []
confirmation_required: false
test_paths:
  - tests/test_proactive_preference_learner.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Single observations must not create permanent critical behavior changes."
```

### Feature: Relational Database Persistence

```yaml
feature_id: memory.persistence.database
name: Relational Database Persistence
description: Thread-safe relational SQLite persistence store managing 13 normalized tables with WAL mode concurrency and busy-timeout protection.
domain: infrastructure
status: active
risk_tier: HIGH
owner_module: memory.database
file_path:
  - memory/database.py
entrypoint:
  - memory.database.DatabaseManager
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events: []
  databases:
    - data/jarvis.db
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_phase_4_eventbus_governance.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Primary shared persistence infrastructure. Schema or connection changes carry high risk of database locking."
```

---

# 13. PROACTIVE INTELLIGENCE

### Feature: Desktop Activity Observer

```yaml
feature_id: proactive.observer.desktop
name: Desktop Activity Observer
description: Observes meaningful desktop state such as foreground application, window, browser context, and idle state.
domain: proactive
status: active
risk_tier: LOW
owner_module: core.observer.activity
file_path:
  - core/observer/activity.py
  - core/observer/models.py
entrypoint:
  - core.observer.activity.ProactiveActivityObserver
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events: []
  databases: []
events_published:
  - activity.observed
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_proactive_observer.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Must not block the main interaction path."
```

### Feature: Habit Detection

```yaml
feature_id: proactive.pattern.detect
name: Habit Pattern Detection
description: Detects repeated activity patterns from meaningful historical events.
domain: proactive
status: active
risk_tier: LOW
owner_module: core.intelligence.pattern_engine
file_path:
  - core/intelligence/pattern_engine.py
  - core/intelligence/models.py
entrypoint:
  - core.intelligence.pattern_engine.PatternLearningEngine
intents: []
aliases: []
dependencies:
  modules: []
  features:
    - proactive.observer.desktop
  plugins: []
  events:
    - activity.observed
  databases:
    - data/jarvis.db
events_published:
  - learning.detected
events_consumed:
  - activity.observed
permissions: []
confirmation_required: false
test_paths:
  - tests/test_proactive_pattern_engine.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Patterns require repeated evidence and must remain revisable."
```

### Feature: Proactive Suggestion

```yaml
feature_id: proactive.suggestion.generate
name: Proactive Suggestion Manager
description: Determines when Jarvis should proactively suggest a useful action and dispatches user-confirmed plans.
domain: proactive
status: active
risk_tier: MEDIUM
owner_module: core.intelligence.suggestion_manager
file_path:
  - core/intelligence/suggestion_manager.py
  - core/intelligence/executor.py
entrypoint:
  - core.intelligence.suggestion_manager.SuggestionManager
  - core.intelligence.executor.ProactiveActionExecutor
intents: []
aliases: []
dependencies:
  modules: []
  features:
    - proactive.observer.desktop
    - proactive.pattern.detect
    - memory.context.runtime
    - security.action.policy
    - core.execution.gateway
  plugins: []
  events:
    - activity.observed
    - learning.detected
  databases: []
events_published:
  - proactive.suggestion.proposed
  - action.planned
events_consumed:
  - activity.observed
  - learning.detected
permissions: []
confirmation_required: true
test_paths:
  - tests/test_proactive_suggestion_manager.py
  - tests/test_phase_3_execution_convergence.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Silence is a valid outcome. Proactive suggestions must not bypass Policy/Decision/Execution. Includes ProactiveActionExecutor as internal execution component dispatching approved plans to core.execution.gateway."
```

---

# 14. WORKFLOWS

### Feature: Workflow Creation

```yaml
feature_id: workflow.create
name: Workflow Creation
description: Creates reusable multi-step workflows from supported actions.
domain: workflow
status: active
risk_tier: MEDIUM
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - workflow.create
aliases:
  - "workflow banao"
  - "routine banao"
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - STATE_CHANGED
  databases:
    - VERIFY_FROM_REPO
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: ""
```

### Feature: Workflow Execution

```yaml
feature_id: workflow.execute
name: Workflow Execution
description: Executes a previously defined multi-step workflow.
domain: workflow
status: active
risk_tier: HIGH
owner_module: VERIFY_FROM_REPO
file_path:
  - VERIFY_FROM_REPO
entrypoint:
  - VERIFY_FROM_REPO
intents:
  - workflow.execute
aliases:
  - "workflow chalao"
  - "routine run karo"
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - COMMAND_STARTED
    - COMMAND_EXECUTED
    - COMMAND_FAILED
  databases:
    - VERIFY_FROM_REPO
events_published: []
events_consumed: []
permissions:
  - workflow.execute
confirmation_required: true
test_paths:
  - VERIFY_FROM_REPO
regression_tier: 3
last_modified: VERIFY_FROM_REPO
notes: "Long-running workflows should support safe cancellation where practical."
```

---

# 15. REMINDERS & TIME

### Feature: Reminder Creation

```yaml
feature_id: reminder.create
name: Reminder Creation
description: Creates one-time or recurring reminders.
domain: utility
status: active
risk_tier: MEDIUM
owner_module: plugins.reminder
file_path:
  - plugins/reminder/plugin.py
  - core/app.py
entrypoint:
  - plugins.reminder.plugin.ReminderPlugin.execute
intents:
  - reminder.create
aliases:
  - "reminder lagao"
  - "mujhe yaad dilana"
dependencies:
  modules: []
  features: []
  plugins: []
  events: []
  databases:
    - data/reminders.db
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_reminder_architecture.py
  - tests/test_plugin_reminder.py
regression_tier: 3
last_modified: 2026-09-19
notes: "Explicit reminder creation bypasses the date fast path. Low-confidence generic chat defers recognized reminder listing/management to the existing semantic parser and executor. Scheduler and storage implementation unchanged."
```

---

# 16. EVENTBUS FEATURES

### Feature: Event Bus

```yaml
feature_id: infrastructure.eventbus
name: Pub/Sub Event Bus
description: Provides decoupled event-based communication between Jarvis subsystems with canonical EventTopics and typed domain events.
domain: infrastructure
status: active
risk_tier: HIGH
owner_module: core.event_bus
file_path:
  - core/event_bus.py
entrypoint:
  - core.event_bus.EventBus
  - core.event_bus.EventTopics
  - core.event_bus.get_event_bus
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events: []
  databases: []
events_published:
  - action.planned
  - policy.evaluated
  - execution.completed
  - activity.observed
  - proactive.suggestion.proposed
  - system.state.changed
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_phase_4_eventbus_governance.py
  - tests/test_event_bus.py
  - tests/test_event_bus_architecture.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Shared infrastructure. Changes require producer/consumer analysis."
```

---

# 17. POLICY / SECURITY

### Feature: Action Policy

```yaml
feature_id: security.action.policy
name: Action Policy Engine
description: Centralizes permission, risk, and confirmation decisions for actionable operations via ActionRiskLevel and PermissionGuard.
domain: security
status: active
risk_tier: HIGH
owner_module: core.permissions
file_path:
  - core/permissions.py
  - core/confirmation.py
entrypoint:
  - core.permissions.PermissionGuard
  - core.permissions.ActionRiskLevel
  - core.permissions.validate_action_plan
  - core.confirmation.is_affirmative
intents: []
aliases: []
dependencies:
  modules: []
  features: []
  plugins: []
  events:
    - policy.evaluated
  databases: []
events_published:
  - policy.evaluated
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_phase_3_execution_convergence.py
  - tests/test_plugin_permissions.py
  - tests/test_system_confirmation.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Must remain the authoritative permission/risk boundary. Cross-boundary execution validation shared with core.execution.gateway."
```

### Feature: Authoritative Confirmation State Machine

```yaml
feature_id: core.confirmation.manager
name: Authoritative Confirmation State Machine
description: Dedicated, multi-lingual confirmation lifecycle manager handling pending destructive actions (restart, shutdown, file deletion, process termination) with stateful YES/NO/AMBIGUOUS classification, timeout protection, and safe OS execution.
domain: core
status: active
risk_tier: HIGH
owner_module: core.confirmation_manager
file_path:
  - core/confirmation_manager.py
  - core/confirmation.py
  - core/interaction_gate.py
entrypoint:
  - core.confirmation_manager.ConfirmationManager
  - core.confirmation_manager.PendingConfirmation
  - core.confirmation.classify_confirmation
  - core.confirmation.is_affirmation
  - core.confirmation.is_cancellation
  - core.confirmation.is_ambiguous
intents:
  - SYSTEM_CONFIRMATION_RESPONSE
aliases:
  - "haan"
  - "yes"
  - "kar do"
  - "theek hai"
  - "nahi"
  - "cancel"
  - "mat karo"
  - "rehne do"
  - "हाँ"
  - "नहीं"
dependencies:
  modules:
    - core.confirmation
    - core.interaction_gate
  features:
    - security.action.policy
  plugins:
    - system
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: true
test_paths:
  - tests/test_confirmation_manager.py
  - tests/test_system_confirmation.py
  - tests/test_authoritative_interaction_gate.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Authoritative interceptor executing at Step 2.Pending before generic workflow/intent routing. Dispatches YES to execute pending action, NO to cancel, AMBIGUOUS to clarify without losing context, and protects typed input from TTS mic suppression."
```

### Feature: Robust 8-Stage NLU Understanding Pipeline

```yaml
feature_id: core.nlu.understanding_pipeline
name: Robust 8-Stage NLU Understanding Pipeline
description: Multi-tier natural language understanding pipeline featuring text normalization, typo/spell correction (Levenshtein distance), fuzzy candidate evaluation, Hinglish synonym normalization, context resolution, semantic parsing, calibrated confidence scoring, and confidence-gated action decision making. Confident destructive actions (restart, shutdown) strictly trigger confirmation, while ambiguous commands prompt natural clarification and unknown commands receive an honest clarification request without fake understanding responses.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.semantic
file_path:
  - core/semantic/normalizer.py
  - brain/spelling_resolver.py
  - core/semantic/orchestrator.py
  - core/semantic/parsers/system.py
  - core/apps/registry.py
  - core/apps/aliases.py
  - core/app.py
  - brain/llm.py
entrypoint:
  - core.semantic.normalizer.HinglishNormalizer.normalize_text
  - brain.spelling_resolver.SpellingResolver.resolve
  - core.semantic.orchestrator.SemanticPipelineOrchestrator.parse
  - core.app.JarvisCore.process_input
intents:
  - SYSTEM_RESTART
  - SYSTEM_SHUTDOWN
  - OPEN_APP
aliases:
  - "retstart the system"
  - "restat the system"
  - "restard computer"
  - "chrom kholo"
  - "youtub kholo"
dependencies:
  modules:
    - core.semantic
    - brain.spelling_resolver
    - core.confirmation_manager
  features:
    - core.confirmation.manager
  plugins:
    - system
    - browser
    - apps
test_paths:
  - tests/test_understanding_pipeline.py
  - tests/test_spelling_resolver.py
  - tests/test_system_confirmation.py
  - tests/test_semantic_orchestrator.py
regression_tier: 3
last_modified: 2026-09-06
notes: "8-stage NLU pipeline with STT typo resilience, Levenshtein distance 1 candidate matching, confirmation gating for destructive actions, and elimination of fake LLM acknowledgments."
```

### Feature: Decision Core & Action Planner


```yaml
feature_id: core.decision.engine
name: Central Decision Core & Action Planner
description: Centralized intent-to-plan resolution and confirmation evaluation engine producing typed ActionPlan models.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.decision_core
file_path:
  - core/decision_core.py
  - core/execution/models.py
entrypoint:
  - core.decision_core.DecisionCore
  - core.decision_core.get_decision_core
  - core.execution.models.ActionPlan
intents: []
aliases: []
dependencies:
  modules:
    - core.confirmation
    - core.permissions
  features:
    - memory.context.runtime
    - security.action.policy
  plugins: []
  events:
    - action.planned
  databases: []
events_published:
  - action.planned
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_decision_core.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Must remain the single point of action formulation before policy check and execution."
```

### Feature: Unified ActionPlan Execution Gateway

```yaml
feature_id: core.execution.gateway
name: Unified ActionPlan Execution Gateway
description: Central convergence execution boundary dispatching validated ActionPlan instances across plugins, handlers, shell, and workflows.
domain: core
status: active
risk_tier: HIGH
owner_module: core.app
file_path:
  - core/app.py
entrypoint:
  - core.app.JarvisCore.execute_action_plan
intents: []
aliases: []
dependencies:
  modules:
    - core.permissions
    - core.event_bus
  features:
    - security.action.policy
    - infrastructure.eventbus
  plugins: []
  events:
    - execution.completed
  databases: []
events_published:
  - execution.completed
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_phase_3_execution_convergence.py
regression_tier: 3
last_modified: 2026-09-06
notes: "Authoritative execution boundary. Cross-boundary security validation enforced by security.action.policy."
```

---

# 17B. COMPANION & PERSONALITY (NEW DOMAIN)

> These features are what make Jarvis feel like a consistent "smart friend" rather than a bag of disconnected commands. They carry low *system* risk but real *tone/relationship* responsibility — see §40 for the governance rules that apply across all of them.

### Feature: Casual Conversation / Small Talk

```yaml
feature_id: companion.smalltalk.chat
name: Casual Conversation
description: Handles open-ended small talk and casual back-and-forth when the user isn't issuing a command.
domain: companion
status: active
risk_tier: LOW
owner_module: brain.conversation
file_path:
  - brain/conversation/engine.py
entrypoint:
  - brain.conversation.engine.ConversationEngine
intents:
  - smalltalk.chat
aliases:
  - "kya haal hai"
  - "kya kar raha hai"
  - "bore ho raha hoon"
dependencies:
  modules: []
  features:
    - memory.context.runtime
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversation_intelligence.py
regression_tier: 3
last_modified: 2026-09-19
notes: "Must not compete with real intents — only fires when no actionable command is detected. See §40 for tone rules."
conversation_update: "Early non-executable greetings, small talk, acknowledgements and fallback dialogue reuse ConversationEngine. Low-confidence chat defaults defer recognized commands to the existing command boundary classifier. Bounded user/assistant history is passed to the configured chat provider; offline fallback remains available. Commands and workflow confirmations keep their existing priority."
```

### Feature: Personalized Greeting

```yaml
feature_id: companion.greeting.personalized
name: Personalized Greeting
description: Greets the user using known name/context/time-of-day instead of a generic scripted line.
domain: companion
status: active
risk_tier: LOW
owner_module: brain.conversation
file_path:
  - brain/conversation/engine.py
entrypoint:
  - brain.conversation.engine.ConversationEngine
intents:
  - greeting.default
aliases:
  - "good morning jarvis"
  - "hey jarvis"
dependencies:
  modules: []
  features:
    - memory.preference.learn
    - memory.episodic.store
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversation_intelligence.py
regression_tier: 3
last_modified: 2026-09-19
notes: "Personalize using stored facts the user actually gave — never invented details."
conversation_update: "Uses only saved user_name/current_project facts through MemoryManager. Project callbacks occur during greetings, at most once per 30 minutes per engine session; no background check-ins or scheduled reminder claims."
```

### Feature: Proactive Check-in

```yaml
feature_id: companion.checkin.proactive
name: Proactive Check-in
description: Occasionally checks in based on observed patterns (e.g. long inactivity, repeated late-night sessions) without being asked.
domain: companion
status: disabled
risk_tier: MEDIUM
owner_module: core.intelligence
file_path: []
entrypoint: []
intents: []
aliases: []
dependencies:
  modules: []
  features:
    - proactive.observer.desktop
    - proactive.pattern.detect
    - memory.context.runtime
  plugins: []
  events:
    - learning.detected
  databases: []
events_published: []
events_consumed:
  - learning.detected
permissions: []
confirmation_required: false
test_paths: []
regression_tier: 3
last_modified: 2026-09-06
notes: "Planned companion capability; not implemented in repository. Frequency-capped (see §40). Silence is a valid outcome."
```

### Feature: Mood-Aware Support

```yaml
feature_id: companion.mood.support
name: Mood-Aware Support
description: Responds with acknowledgement/warmth when the user's phrasing signals stress, frustration, or a bad day — without diagnosing or overclaiming understanding.
domain: companion
status: active
risk_tier: LOW
owner_module: brain.conversation
file_path:
  - brain/conversation/engine.py
entrypoint:
  - brain.conversation.engine.ConversationEngine
intents:
  - mood.acknowledge
aliases:
  - "aaj bura din tha"
  - "thak gaya hoon"
dependencies:
  modules: []
  features:
    - memory.context.runtime
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversation_intelligence.py
regression_tier: 3
last_modified: 2026-09-19
notes: "Acknowledge only — never diagnose, never claim a clinical read, never discourage the user from real human/professional support if distress seems serious. See §40."
conversation_update: "Existing dialogue state remembers the listening-versus-advice choice, handles follow-up workload details, and clears support context on cancellation, topic change or expiry. Emotional disclosures are not saved as profile facts. No diagnoses or invented action completion."
```

### Feature: Humor / Banter

```yaml
feature_id: companion.humor.banter
name: Humor & Banter
description: Light jokes/wordplay in casual exchanges, matched to the user's tone.
domain: companion
status: active
risk_tier: LOW
owner_module: brain.conversation
file_path:
  - brain/conversation/engine.py
entrypoint:
  - brain.conversation.engine.ConversationEngine
intents:
  - smalltalk.humor
aliases:
  - "joke sunao"
  - "kuch funny bolo"
dependencies:
  modules: []
  features:
    - companion.smalltalk.chat
  plugins: []
  events: []
  databases: []
events_published: []
events_consumed: []
permissions: []
confirmation_required: false
test_paths:
  - tests/test_conversation_intelligence.py
regression_tier: 1
last_modified: 2026-09-06
notes: ""
```

---

# 17C. TRADING DECISION SUPPORT (NEW DOMAIN)

## Trading Signal Engine (Screen-Only Decision Support)

### Feature: Screen-Only Live Options Confluence Signal Engine

```yaml
feature_id: trading.options.signals
name: Screen-Only Live Options Confluence Signal Engine, Automatic Session Discovery & Multi-Panel Dhan Understanding
domain: trading
owner: plugins.trading_signals
status: active
risk_tier: LOW
description: Screen-only real-time confluence evaluation of multi-panel Dhan/TradingView NIFTY Index and Option charts (Renko, SuperTrend, Donchian upper breakout) with Automatic Session Discovery and Dynamic Multi-Panel Understanding. Autonomously discovers arbitrary chart layouts (1 Index + CE + PE, swapped positions, 3-column, 2x2 grid, resized splits) without coordinate assumptions. Evaluates CE and PE candidates independently against NIFTY index, enforces strict panel boundary isolation, gates on configuration validity (Renko 10/3, ST 1 2.1, EMA 20, DC 9 0), handles occlusion per-panel without cross-contamination, purges stale breakouts on contract switch, and generates concise BUY/EXIT notifications. Strictly decision-support only; NO broker API, NO order placement, NO auto-execution.
entry_point: plugins/trading_signals/plugin.py:TradingSignalsPlugin
files:
  - plugins/trading_signals/plugin.py
  - plugins/trading_signals/commands.py
  - plugins/trading_signals/manifest.py
  - plugins/trading_signals/permissions.py
  - plugins/trading_signals/models/panel_types.py
  - plugins/trading_signals/models/chart_state.py
  - plugins/trading_signals/models/session_types.py
  - plugins/trading_signals/session/chart_session.py
  - plugins/trading_signals/session/session_detector.py
  - plugins/trading_signals/session/session_coordinator.py
  - plugins/trading_signals/session/panel_classifier.py
  - plugins/trading_signals/observer/chart_screen_observer.py
  - plugins/trading_signals/strategy/confluence_engine.py
  - plugins/trading_signals/strategy/exit_evaluator.py
  - plugins/trading_signals/state/position_tracker.py
  - plugins/trading_signals/state/idempotency.py
  - plugins/trading_signals/gate/pre_dispatch_gate.py
  - plugins/trading_signals/validation/pair_validator.py
  - plugins/trading_signals/validation/confidence_gate.py
  - plugins/trading_signals/vision/detector.py
  - plugins/trading_signals/vision/panel_detector.py
  - plugins/trading_signals/vision/panel_extractor.py
  - plugins/trading_signals/vision/renko_detector.py
  - plugins/trading_signals/vision/donchian_verifier.py
  - plugins/trading_signals/vision/color_classifier.py
  - plugins/trading_signals/vision/extractor.py
  - plugins/trading_signals/notification/dispatcher.py
intents:
  - trading.signal.start
  - trading.signal.stop
  - trading.signal.status
  - trading.strategy.set_mode
  - trading.state.reset
  - trading.session.pause
  - trading.session.resume
  - trading.session.analyze
aliases:
  - "start trading monitor"
  - "start signal engine"
  - "options signal on"
  - "trading monitor chalu karo"
  - "stop trading monitor"
  - "stop signal engine"
  - "options signal band karo"
  - "trading status"
  - "signal status"
  - "set strategy mode"
  - "reset signal state"
  - "pause analysis"
  - "pause trading"
  - "pause chart analysis"
  - "trading pause karo"
  - "resume analysis"
  - "resume trading"
  - "resume chart analysis"
  - "trading resume karo"
  - "analyze this chart"
  - "analyze current chart"
  - "is chart ko analyze karo"
dependencies:
  internal:
    - core.event_bus
    - plugins.manifest
    - plugins.base
    - core.permissions
  external:
    - cv2
    - numpy
    - PIL.ImageGrab
    - win32gui
  events:
    - trading.signal.generated
  databases: []
events_published:
  - trading.signal.generated
events_consumed: []
permissions:
  - screen
  - screen.read
confirmation_required: false
test_paths:
  - tests/trading/test_multi_panel_discovery.py
  - tests/trading/test_session_discovery.py
  - tests/trading/test_strategy_modes.py
  - tests/trading/test_donchian_breakout.py
  - tests/trading/test_calibrated_tolerance.py
  - tests/trading/test_renko_lifecycle.py
  - tests/trading/test_position_lifecycle.py
  - tests/trading/test_pre_dispatch_gate.py
  - tests/trading/test_pair_validation.py
  - tests/trading/test_idempotency.py
  - tests/trading/test_notification_dispatcher.py
  - tests/trading/test_vision_fixtures.py
  - tests/trading/test_plugin_actions.py
regression_tier: 2
last_modified: 2026-09-06
notes: "Strict invariant: JARVIS_SIGNAL_ACTIVE != ACTUAL_BROKER_POSITION. Strictly zero broker order placement. Automatic foreground Dhan chart discovery with multi-panel layout understanding (1+2, swapped, 3-column, 2x2 grid), zero coordinate assumptions, isolated per-panel processing, independent concurrent CE/PE confluence evaluation, occlusion/config gating, and speech-only BUY/EXIT notifications."
```

---

# 18. REGISTRY INDEX

Once the actual repository has been scanned, maintain a compact index here.

| Feature ID                        | Name                             | Domain         | Status       | Risk   | Owner                            | Tests                                          | Regression |
| ---------------------------------- | -------------------------------- | -------------- | ------------ | ------ | -------------------------------- | ---------------------------------------------- | ---------- |
| `system.app.launch`                | Application Launcher             | system         | active       | LOW    | VERIFY                           | VERIFY                                         | Tier 2     |
| `system.app.close`                 | Application Close                | system         | active       | MEDIUM | VERIFY                           | VERIFY                                         | Tier 2     |
| `browser.open`                     | Browser Open                     | browser        | active       | LOW    | VERIFY                           | VERIFY                                         | Tier 2     |
| `media.youtube.search`             | YouTube Search                   | media          | active       | LOW    | VERIFY                           | VERIFY                                         | Tier 2     |
| `media.youtube.play`               | YouTube Playback                 | media          | active       | LOW    | VERIFY                           | VERIFY                                         | Tier 2     |
| `productivity.excel.select`        | Excel Cell Selection             | productivity   | active       | MEDIUM | VERIFY                           | VERIFY                                         | Tier 2     |
| `productivity.excel.formula`       | Excel Formula Operations         | productivity   | active       | MEDIUM | VERIFY                           | VERIFY                                         | Tier 2     |
| `productivity.excel.fill_down`     | Excel Fill Down                  | productivity   | active       | MEDIUM | VERIFY                           | VERIFY                                         | Tier 3     |
| `communication.whatsapp.send`      | WhatsApp Message Send            | communication  | active       | HIGH   | VERIFY                           | VERIFY                                         | Tier 3     |
| `communication.email.send`         | Email Send                       | communication  | active       | HIGH   | VERIFY                           | VERIFY                                         | Tier 3     |
| `memory.context.runtime`           | Runtime Conversation Context     | memory         | active       | LOW    | core                             | tests/test_runtime_context.py                  | Tier 3     |
| `core.decision.engine`             | Central Decision Core & Action Planner | core     | active       | MEDIUM | core.decision_core               | tests/test_decision_core.py                    | Tier 3     |
| `core.execution.gateway`           | Unified ActionPlan Execution Gateway | core     | active       | HIGH   | core.app                         | tests/test_phase_3_execution_convergence.py   | Tier 3     |
| `memory.episodic.store`            | Episodic Memory                  | memory         | active       | LOW    | memory                           | tests/test_contextual_proactive_suggestions.py | Tier 3     |
| `memory.preference.learn`          | Preference Learning              | memory         | active       | LOW    | core.intelligence.preference_learner | tests/test_proactive_preference_learner.py | Tier 3     |
| `memory.persistence.database`      | Relational Database Persistence  | infrastructure | active       | HIGH   | memory.database                  | tests/test_phase_4_eventbus_governance.py      | Tier 3     |
| `proactive.observer.desktop`       | Desktop Activity Observer        | proactive      | active       | LOW    | core.observer.activity           | tests/test_proactive_observer.py             | Tier 3     |
| `proactive.pattern.detect`         | Habit Pattern Detection          | proactive      | active       | LOW    | core.intelligence.pattern_engine | tests/test_proactive_pattern_engine.py       | Tier 3     |
| `proactive.suggestion.generate`    | Proactive Suggestion Manager     | proactive      | active       | MEDIUM | core.intelligence.suggestion_manager | tests/test_proactive_suggestion_manager.py | Tier 3     |
| `workflow.create`                  | Workflow Creation                | workflow       | active       | MEDIUM | task_engine                      | tests/test_proactive_workflow_synthesis.py    | Tier 3     |
| `workflow.execute`                 | Workflow Execution               | workflow       | active       | HIGH   | task_engine                      | tests/test_proactive_system_integration.py     | Tier 3     |
| `reminder.create`                  | Reminder Creation                | utility        | active       | MEDIUM | plugins                          | VERIFY                                         | Tier 2     |
| `infrastructure.eventbus`          | Pub/Sub Event Bus                | infrastructure | active       | HIGH   | core.event_bus                   | tests/test_phase_4_eventbus_governance.py      | Tier 3     |
| `security.action.policy`           | Action Policy Engine             | security       | active       | HIGH   | core.permissions                 | tests/test_phase_3_execution_convergence.py   | Tier 3     |
| `companion.smalltalk.chat`         | Casual Conversation              | companion      | active       | LOW    | brain.conversation               | tests/test_conversation_intelligence.py        | Tier 2     |
| `companion.greeting.personalized`  | Personalized Greeting            | companion      | active       | LOW    | brain.conversation               | tests/test_conversation_intelligence.py        | Tier 2     |
| `companion.checkin.proactive`      | Proactive Check-in               | companion      | disabled     | MEDIUM | core.intelligence                | None (Unimplemented)                           | Tier 3     |
| `companion.mood.support`           | Mood-Aware Support               | companion      | active       | LOW    | brain.conversation               | tests/test_conversation_intelligence.py        | Tier 2     |
| `companion.humor.banter`           | Humor & Banter                   | companion      | active       | LOW    | brain.conversation               | tests/test_conversation_intelligence.py        | Tier 1     |
| `trading.options.signals`          | Screen-Only Options Signal Engine| trading        | active       | LOW    | plugins.trading_signals          | tests/trading/                                 | Tier 2     |

> **IMPORTANT:** The table above is a registry template/seed. Replace `VERIFY` values with actual repository values after the first registry audit.

---

# 19. ALIAS INDEX

Maintain aliases in one searchable section to detect collisions.

| Alias                               | Feature ID                        | Intent               | Domain    |
| ----------------------------------- | ---------------------------------- | --------------------- | --------- |
| `chrome kholo`                      | `browser.open`                     | `browser.open`        | browser   |
| `open chrome`                       | `browser.open`                     | `browser.open`        | browser   |
| `chrome chala do`                   | `browser.open`                     | `browser.open`        | browser   |
| `antigravity application open karo` | `system.app.launch`                | `app.open`             | system    |
| `antigravity ki website kholo`      | `browser.open`                     | `website.open`         | browser   |
| `open antigravity`                  | `system.app.launch`                | `app.open`             | system    |
| `kya haal hai`                      | `companion.smalltalk.chat`         | `smalltalk.chat`       | companion |
| `good morning jarvis`               | `companion.greeting.personalized`  | `greeting.default`     | companion |
| `aaj bura din tha`                  | `companion.mood.support`           | `mood.acknowledge`     | companion |
| `joke sunao`                        | `companion.humor.banter`           | `smalltalk.humor`      | companion |
| `start trading monitor`             | `trading.options.signals`          | `trading.signal.start` | trading   |
| `stop trading monitor`              | `trading.options.signals`          | `trading.signal.stop`  | trading   |
| `trading status`                    | `trading.options.signals`          | `trading.signal.status`| trading   |
| `set strategy mode`                 | `trading.options.signals`          | `trading.strategy.set_mode` | trading |
| `reset signal state`                | `trading.options.signals`          | `trading.state.reset`  | trading   |
| `pause analysis`                    | `trading.options.signals`          | `trading.session.pause`| trading   |
| `resume analysis`                   | `trading.options.signals`          | `trading.session.resume`| trading  |
| `analyze this chart`                | `trading.options.signals`          | `trading.session.analyze`| trading |

Before adding a new alias:

1. Search this index.
2. Search the registry.
3. Search actual intent definitions.
4. Check whether another feature already owns the phrase.
5. Prefer specificity + context over duplicate aliases.

> **Companion-specific collision note:** smalltalk/greeting aliases are the most likely to accidentally shadow a real command (e.g. "kya kar raha hai" vs. a status-check intent). Companion intents must sit **last** in priority order, after every specific/actionable intent has failed to match.

---

# 20. INTENT INDEX

Maintain one searchable mapping between intents and owning features.

| Intent             | Feature ID                        | Owner              | Risk   |
| ------------------- | ---------------------------------- | ------------------ | ------ |
| `app.open`          | `system.app.launch`                | VERIFY             | LOW    |
| `app.close`         | `system.app.close`                 | VERIFY             | MEDIUM |
| `browser.open`      | `browser.open`                     | VERIFY             | LOW    |
| `youtube.search`    | `media.youtube.search`             | VERIFY             | LOW    |
| `youtube.play`      | `media.youtube.play`               | VERIFY             | LOW    |
| `excel.select`      | `productivity.excel.select`        | VERIFY             | MEDIUM |
| `excel.formula`     | `productivity.excel.formula`       | VERIFY             | MEDIUM |
| `excel.fill_down`   | `productivity.excel.fill_down`     | VERIFY             | MEDIUM |
| `whatsapp.send`     | `communication.whatsapp.send`      | VERIFY             | HIGH   |
| `email.send`        | `communication.email.send`         | VERIFY             | HIGH   |
| `smalltalk.chat`    | `companion.smalltalk.chat`         | brain.conversation | LOW    |
| `greeting.default`  | `companion.greeting.personalized`  | brain.conversation | LOW    |
| `mood.acknowledge`  | `companion.mood.support`           | brain.conversation | LOW    |
| `smalltalk.humor`   | `companion.humor.banter`           | brain.conversation | LOW    |
| `trading.signal.start` | `trading.options.signals`       | plugins.trading_signals | LOW |
| `trading.signal.stop`  | `trading.options.signals`       | plugins.trading_signals | LOW |
| `trading.signal.status`| `trading.options.signals`       | plugins.trading_signals | LOW |
| `trading.strategy.set_mode` | `trading.options.signals`  | plugins.trading_signals | LOW |
| `trading.state.reset`  | `trading.options.signals`       | plugins.trading_signals | LOW |
| `trading.session.pause`| `trading.options.signals`       | plugins.trading_signals | LOW |
| `trading.session.resume`| `trading.options.signals`      | plugins.trading_signals | LOW |
| `trading.session.analyze`| `trading.options.signals`     | plugins.trading_signals | LOW |

---

# 21. SHARED COMPONENT INDEX

The following components are considered shared infrastructure.

Any change to these requires broader impact analysis:

```text
context
decision
intent detection
entity extraction
normalization
command router
EventBus
memory
policy
plugin manager
target resolver
application resolver
browser resolver
listener
speaker
configuration
database repositories
```

For each shared component, identify:

```text
owner
file_path
callers
consumers
plugins
events
tests
risk
```

---

# 22. DEPENDENCY GRAPH

For important features, maintain dependency relationships.

Example:

```text
media.youtube.play
    ├── media.youtube.search
    ├── browser.open
    ├── infrastructure.eventbus
    └── security.action.policy
```

Another:

```text
proactive.suggestion.generate
    ├── proactive.observer.desktop
    ├── proactive.pattern.detect
    ├── memory.context.runtime
    ├── security.action.policy
    └── workflow.execute
```

Companion domain:

```text
companion.checkin.proactive
    ├── proactive.observer.desktop
    ├── proactive.pattern.detect
    └── memory.context.runtime

companion.greeting.personalized
    ├── memory.preference.learn
    └── memory.episodic.store
```

Do not invent dependency edges.

Only record dependencies verified from the repository.

---

# 23. EVENT MAP

Maintain important EventBus relationships.

Example:

```text
activity.observed
    ↓
proactive.pattern.detect
    ↓
learning.detected
    ↓
proactive.suggestion.generate
    ↓
proactive.suggestion.proposed
    ↓
USER CONFIRMATION
    ↓
core.decision.engine
    ↓
action.planned
    ↓
policy.evaluated (security.action.policy)
    ↓
execution.completed (core.execution.gateway)
```

Trading domain:

```text
desktop.screen.observed (chart frame)
    ↓
chart_region.segmented & extracted
    ↓
temporal_confirmation (closed Renko brick)
    ↓
confluence.evaluated (strategy engine)
    ↓
pre_dispatch.revalidated (4 invariants: window, brick, boundary, confidence >= 0.85)
    ↓
trading.signal.generated (SignalNotificationDispatcher)
    ↓
user.notified (concise BUY/EXIT string via EventBus & TTS)
```

The map must match actual implementation.

---

# 24. TEST MAP

Each important feature should map to at least one meaningful test path where practical.

Example:

```text
system.app.launch
→ tests/test_plugin_apps.py

media.youtube.play
→ tests/test_youtube_plugin_v2.py

productivity.excel.fill_down
→ tests/test_desktop_workflow.py

memory.context.runtime
→ tests/test_runtime_context.py

core.execution.gateway
→ tests/test_phase_3_execution_convergence.py

proactive.suggestion.generate
→ tests/test_proactive_suggestion_manager.py

companion.mood.support
→ tests/test_conversation_intelligence.py

companion.checkin.proactive
→ None (Unimplemented)

trading.options.signals
→ tests/trading/test_multi_panel_discovery.py
→ tests/trading/test_session_discovery.py
→ tests/trading/test_strategy_modes.py
→ tests/trading/test_donchian_breakout.py
→ tests/trading/test_calibrated_tolerance.py
→ tests/trading/test_renko_lifecycle.py
→ tests/trading/test_position_lifecycle.py
→ tests/trading/test_pre_dispatch_gate.py
→ tests/trading/test_pair_validation.py
→ tests/trading/test_idempotency.py
→ tests/trading/test_notification_dispatcher.py
→ tests/trading/test_vision_fixtures.py
→ tests/trading/test_plugin_actions.py
```

Use actual paths from the repository.

Do not invent test paths.

---

# 25. FEATURE CHANGE RULES

When a feature is modified:

1. Locate its registry entry.
2. Update the entry in the same task.
3. Update aliases/intents if changed.
4. Update dependencies if changed.
5. Update tests if changed.
6. Update risk tier if capability changed.
7. Update status if lifecycle changed.
8. Update `last_modified`.
9. Update `architecture.txt` only if shared architecture changed.
10. Run the appropriate regression tier.

---

# 26. NEW FEATURE RULE

Before creating a new feature:

```text
User Request
    ↓
Search FEATURES.md
    ↓
Search feature ID / intent / aliases
    ↓
Search repository
    ↓
Existing feature?
    ├── YES → extend/reuse
    └── NO  → create new feature
```

Never create a new feature simply because the existing implementation is difficult to find.

---

# 27. ALIAS COLLISION RULE

Before adding a new alias:

```text
New alias
    ↓
FEATURES.md search
    ↓
Intent registry search
    ↓
Repository search
    ↓
Collision?
   ├── YES → resolve ownership/context
   └── NO  → register
```

Never silently allow a new generic alias to override a more specific existing feature.

---

# 28. INTENT COLLISION RULE

Before adding an intent:

```text
New intent
    ↓
Check existing intent owner
    ↓
Check aliases
    ↓
Check priority
    ↓
Check contextual routing
    ↓
Check negative cases
```

Generic intents must not outrank specific intents. Companion intents (§17B) are the most generic in the whole registry and must always be the last fallback, never a competing first match.

---

# 29. FEATURE REMOVAL

Do not immediately erase removed feature history.

Preferred lifecycle:

```text
active
 ↓
deprecated
 ↓
disabled
 ↓
removed
```

Before removal:

* search registry
* search repo
* search dynamic loading
* search configuration
* search plugins
* search tests
* search fallback paths
* verify replacement

When finally removing a feature:

* delete implementation only when safe
* remove active aliases
* update dependent features
* update tests
* update architecture if applicable
* update this registry
* preserve a historical note if useful

---

# 30. REGISTRY VALIDATION

The registry must periodically be validated against the repository.

Validation should detect:

```text
- duplicate feature IDs
- duplicate aliases
- stale file paths
- missing feature files
- invalid owner modules
- deprecated features still active
- removed features still registered as active
- nonexistent tests
- invalid dependencies
- unknown intents
- orphaned registry entries
```

Preferred validator:

```bash
python tools/validate_registry.py
```

If no validator exists, identify that as a tooling gap.

Do not falsely claim registry validity without verification.

---

# 31. REGISTRY UPDATE POLICY

`FEATURES.md` is updated when:

### MUST UPDATE

* new feature added
* feature removed
* feature renamed
* feature moved
* feature ownership changes
* aliases change
* intents change
* dependencies change
* risk changes
* lifecycle status changes
* test mapping changes
* feature contract changes

### NORMALLY NO UPDATE

* internal implementation bug fix that changes none of the registry fields
* formatting
* comments
* logging text
* test-only refactoring that does not change feature mapping

When uncertain, determine whether the feature's identity, ownership, capability, interface, dependency, risk, or lifecycle changed.

---

# 32. RELATIONSHIP WITH `architecture.txt`

`FEATURES.md` and `architecture.txt` have different responsibilities.

```text
FEATURES.md
→ feature-level catalog

architecture.txt
→ high-level system architecture
```

Do NOT put every feature implementation detail into `architecture.txt`.

Do NOT use `FEATURES.md` as a replacement for architecture documentation.

For a major subsystem:

```text
Feature Registry
+
architecture.txt
```

may both need updates.

---

# 33. RELATIONSHIP WITH `AGENTS.md`

```text
AGENTS.md
→ HOW agents must work

FEATURES.md
→ WHAT features exist and where they live

architecture.txt
→ HOW the system is architecturally organized

tests/
→ WHAT verified behavior must continue to work
```

An agent should typically:

```text
Read AGENTS.md
    ↓
Check FEATURES.md
    ↓
Read relevant architecture.txt section
    ↓
Inspect actual repository
    ↓
Modify minimally
    ↓
Test
    ↓
Update FEATURES.md when feature metadata changed
    ↓
Update architecture.txt when architecture changed
```

---

# 34. SESSION DISCOVERY RULE

At the start of a new session:

1. Read `AGENTS.md`.
2. Search `FEATURES.md` for the requested feature/intent/alias.
3. Read relevant `architecture.txt` sections when necessary.
4. Inspect the actual implementation.
5. Check recent relevant `AGENT_LOG.md` entries if the area was recently modified.

This is intended to reduce unnecessary rediscovery.

---

# 35. FEATURE REPORTING

For any feature change, the final report should include:

```text
Feature ID:
Feature name:
Status:
Risk:
Owner:
Files changed:
Aliases changed:
Intents changed:
Dependencies changed:
Tests changed:
Regression tier:
architecture.txt:
```

---

# 36. REGISTRY QUALITY RULES

Keep entries:

* concise
* factual
* searchable
* structured
* current
* non-duplicative

Do not turn the registry into long prose documentation.

Prefer:

```text
feature_id
owner
path
intent
alias
dependency
risk
test
```

over paragraphs.

---

# 37. FINAL REGISTRY INVARIANTS

These rules must always remain true:

```text
1. Every active feature has one unique feature_id.
2. One feature_id maps to one authoritative implementation owner.
3. Registry paths must correspond to real repository paths.
4. Active registry entries must represent implemented functionality.
5. Deprecated features must not be treated as newly available capabilities.
6. Intent/alias ownership must be discoverable.
7. Shared dependencies must be visible.
8. Risk tier must reflect actual capability.
9. Test mapping must not claim nonexistent tests.
10. Registry must never contradict verified repository behavior.
11. A feature must not have two competing authoritative owners.
12. Registry maintenance must not modify production behavior.
```

---

# 38. FIRST REGISTRY AUDIT

If this registry has not yet been populated from the actual repository, perform a one-time audit.

Audit order:

```text
1. Discover project structure
2. Discover plugins
3. Discover intents
4. Discover aliases
5. Discover handlers
6. Discover commands
7. Discover workflows
8. Discover memory systems
9. Discover proactive systems
10. Discover EventBus events
11. Discover tests
12. Build feature IDs
13. Detect duplicates
14. Assign risk tiers
15. Map dependencies
16. Validate registry
```

Do NOT claim that a 5000+ feature inventory is complete until the repository has actually been scanned and the registry validator passes.

---

# 39. REGISTRY MAINTENANCE CHECKLIST

Before finishing a meaningful feature task:

```text
[ ] Feature ID exists
[ ] Feature ID is unique
[ ] Owner is correct
[ ] File path is correct
[ ] Intent mapping is correct
[ ] Alias mapping is correct
[ ] Dependencies are correct
[ ] Risk tier is correct
[ ] Status is correct
[ ] Test mapping is correct
[ ] last_modified is current
[ ] No collision introduced
[ ] No duplicate feature created
[ ] architecture.txt reviewed if architecture changed
[ ] If a companion/personality feature: tone rules (§40) checked, not just capability risk
```

---

# 40. PERSONALITY & TONE GOVERNANCE (applies to all `companion.*` features)

At 5000+ features, it's easy for the "personality" to end up inconsistent — one feature warm, another robotic, another oddly clingy. These rules keep every companion-facing feature behaving like **one** consistent friend, not several competing personas.

1. **One persona, everywhere.** Tone (warm, casual, Hinglish-natural) is a cross-cutting concern — don't let each feature author invent its own voice. If a shared "response style" helper/config exists, every companion feature routes through it instead of hardcoding its own phrasing conventions.
2. **Personalize only from what's actually stored.** Greetings, callbacks, and check-ins may reference facts the user genuinely gave (name, stated preference, a project mentioned earlier) — never invented or inferred personal details.
3. **Frequency-cap proactive companion behavior.** `companion.checkin.proactive` and similar features must respect cooldowns and repeated-rejection signals (same rule as `proactive.suggestion.generate`, §13). Silence is always a valid, correct outcome — Jarvis doesn't need to fill every quiet moment.
4. **Acknowledge, don't diagnose.** `companion.mood.support` and anything like it may recognize a bad day and respond warmly — it must never claim a clinical read, must never use unstated personal facts to explain how the user feels, and must not discourage the user from real human or professional support if something seems more serious than a passing mood.
5. **No dependency-fostering design.** Companion features should make Jarvis pleasant and useful to talk to — not something designed to maximize how much the user relies on it emotionally instead of on people in their life. No manufactured neediness, no guilt-tripping if the user goes quiet, no romantic/exclusive-relationship framing.
6. **Companion intents are always last in priority.** They exist to catch what no actionable intent claimed (see §28) — a smart friend that occasionally misfires into a real command is a bug, not charm.
7. **Honesty over charm.** If Jarvis doesn't know something or can't do something, companion tone should make *that* land warmly — it should never fabricate confidence to sound more like a capable friend.

---

# 41. MASTER RULE

> **FEATURES.md must describe the real feature landscape of the repository, not the feature landscape an agent wishes existed.**

When uncertain:

```text
Repository evidence
    >
FEATURES.md assumptions
```
architecture.txt
→ HOW the system is architecturally organized

tests/
→ WHAT verified behavior must continue to work
```

An agent should typically:

```text
Read AGENTS.md
    ↓
Check FEATURES.md
    ↓
Read relevant architecture.txt section
    ↓
Inspect actual repository
    ↓
Modify minimally
    ↓
Test
    ↓
Update FEATURES.md when feature metadata changed
    ↓
Update architecture.txt when architecture changed
```

---

# 34. SESSION DISCOVERY RULE

At the start of a new session:

1. Read `AGENTS.md`.
2. Search `FEATURES.md` for the requested feature/intent/alias.
3. Read relevant `architecture.txt` sections when necessary.
4. Inspect the actual implementation.
5. Check recent relevant `AGENT_LOG.md` entries if the area was recently modified.

This is intended to reduce unnecessary rediscovery.

---

# 35. FEATURE REPORTING

For any feature change, the final report should include:

```text
Feature ID:
Feature name:
Status:
Risk:
Owner:
Files changed:
Aliases changed:
Intents changed:
Dependencies changed:
Tests changed:
Regression tier:
architecture.txt:
```

---

# 36. REGISTRY QUALITY RULES

Keep entries:

* concise
* factual
* searchable
* structured
* current
* non-duplicative

Do not turn the registry into long prose documentation.

Prefer:

```text
feature_id
owner
path
intent
alias
dependency
risk
test
```

over paragraphs.

---

# 37. FINAL REGISTRY INVARIANTS

These rules must always remain true:

```text
1. Every active feature has one unique feature_id.
2. One feature_id maps to one authoritative implementation owner.
3. Registry paths must correspond to real repository paths.
4. Active registry entries must represent implemented functionality.
5. Deprecated features must not be treated as newly available capabilities.
6. Intent/alias ownership must be discoverable.
7. Shared dependencies must be visible.
8. Risk tier must reflect actual capability.
9. Test mapping must not claim nonexistent tests.
10. Registry must never contradict verified repository behavior.
11. A feature must not have two competing authoritative owners.
12. Registry maintenance must not modify production behavior.
```

---

# 38. FIRST REGISTRY AUDIT

If this registry has not yet been populated from the actual repository, perform a one-time audit.

Audit order:

```text
1. Discover project structure
2. Discover plugins
3. Discover intents
4. Discover aliases
5. Discover handlers
6. Discover commands
7. Discover workflows
8. Discover memory systems
9. Discover proactive systems
10. Discover EventBus events
11. Discover tests
12. Build feature IDs
13. Detect duplicates
14. Assign risk tiers
15. Map dependencies
16. Validate registry
```

Do NOT claim that a 5000+ feature inventory is complete until the repository has actually been scanned and the registry validator passes.

---

# 39. REGISTRY MAINTENANCE CHECKLIST

Before finishing a meaningful feature task:

```text
[ ] Feature ID exists
[ ] Feature ID is unique
[ ] Owner is correct
[ ] File path is correct
[ ] Intent mapping is correct
[ ] Alias mapping is correct
[ ] Dependencies are correct
[ ] Risk tier is correct
[ ] Status is correct
[ ] Test mapping is correct
[ ] last_modified is current
[ ] No collision introduced
[ ] No duplicate feature created
[ ] architecture.txt reviewed if architecture changed
[ ] If a companion/personality feature: tone rules (§40) checked, not just capability risk
```

---

# 40. PERSONALITY & TONE GOVERNANCE (applies to all `companion.*` features)

At 5000+ features, it's easy for the "personality" to end up inconsistent — one feature warm, another robotic, another oddly clingy. These rules keep every companion-facing feature behaving like **one** consistent friend, not several competing personas.

1. **One persona, everywhere.** Tone (warm, casual, Hinglish-natural) is a cross-cutting concern — don't let each feature author invent its own voice. If a shared "response style" helper/config exists, every companion feature routes through it instead of hardcoding its own phrasing conventions.
2. **Personalize only from what's actually stored.** Greetings, callbacks, and check-ins may reference facts the user genuinely gave (name, stated preference, a project mentioned earlier) — never invented or inferred personal details.
3. **Frequency-cap proactive companion behavior.** `companion.checkin.proactive` and similar features must respect cooldowns and repeated-rejection signals (same rule as `proactive.suggestion.generate`, §13). Silence is always a valid, correct outcome — Jarvis doesn't need to fill every quiet moment.
4. **Acknowledge, don't diagnose.** `companion.mood.support` and anything like it may recognize a bad day and respond warmly — it must never claim a clinical read, must never use unstated personal facts to explain how the user feels, and must not discourage the user from real human or professional support if something seems more serious than a passing mood.
5. **No dependency-fostering design.** Companion features should make Jarvis pleasant and useful to talk to — not something designed to maximize how much the user relies on it emotionally instead of on people in their life. No manufactured neediness, no guilt-tripping if the user goes quiet, no romantic/exclusive-relationship framing.
6. **Companion intents are always last in priority.** They exist to catch what no actionable intent claimed (see §28) — a smart friend that occasionally misfires into a real command is a bug, not charm.
7. **Honesty over charm.** If Jarvis doesn't know something or can't do something, companion tone should make *that* land warmly — it should never fabricate confidence to sound more like a capable friend.

---

# 41. MASTER RULE

> **FEATURES.md must describe the real feature landscape of the repository, not the feature landscape an agent wishes existed.**

When uncertain:

```text
Repository evidence
    >
FEATURES.md assumptions
```

Correct stale registry data instead of modifying working code merely to match the registry.

Never use the registry as an excuse for uncontrolled refactoring.

---

# 42. FEATURE ENTRY: nlp.hindi_vocab_engine

```yaml
feature_id: nlp.hindi_vocab_engine
name: Natural Language Semantic Vocabulary & Knowledge Base (700+ Terms)
status: active
risk_tier: LOW
owner_module: core.semantic.hindi_vocab
file_path: core/semantic/hindi_vocab.py
categories:
  - MOVEMENT (aana, jaana, chalna, rukna, baithna, uthna, daudna, lautna, mudna, kudna, girna, chadhna, utarna + inflections)
  - DIRECTION (upar, niche, aage, peeche, idhar, udhar, yahan, wahan, andar, bahar, left, right, pass, door, seedha, beech, tirchha, charon taraf)
  - OBJECT_REFERENCE (ye/yeh/iska/iski/iske/inhe/inme/isme/jiska/jiski=THIS/RELATIVE; wo/woh/uska/uski/unhe/unme/usme=THAT)
  - BODY_STATE (bhookh, pyaas, neend, thakan, dard, garmi, sardi, aaram, tabiyat kharab, bimar, chakkar, swasth)
  - EMOTION (khushi, dukh, gussa, pyaar, nafrat, dar, tension, pareshani, excited, bored, shant, confused, confident)
  - TIME (abhi, baad mein, pehle, kal, aaj, parso, subah, dopahar, shaam, raat, roz, kabhi kabhi, jaldi, der se, hamesha, kabhi nahi)
  - ACTION (kholo, band karo, chalao, rok do, bhejo, lao, le jao, rakho, hatao, dikhao, chhupao, likho, padho, bolo, sunao, dhoondo, copy, paste, refresh, download, upload, badhao, ghatao)
  - QUANTITY (thoda, zyada, kam, sab, kuch, koi, ek, do, saare, aadha, poora, bilkul nahi, dugna, teen, chaar)
  - REFERENCE (ye wala, wo wala, pehla, doosra, teesra, chautha, last wala, upar wala, niche wala, pichla, agla, beech wala, wahi wala, naya wala, purana wala)
entrypoints:
  - core.semantic.hindi_vocab.HindiVocabEngine.classify
  - core.semantic.hindi_vocab.HindiVocabEngine.enrich_speech_entities
  - core.semantic.hindi_vocab.HindiVocabEngine.get_empathetic_response
  - core.semantic.hindi_vocab.HindiVocabEngine.resolve_object_reference
  - core.semantic.hindi_vocab.HindiVocabEngine.get_quantity_modifier
  - core.semantic.hindi_vocab.HindiVocabEngine.get_direction_for_scroll
  - core.semantic.hindi_vocab.HindiVocabEngine.disambiguate_kal
integrations:
  - core/semantic/normalizer.py (thoda/ek preserved as quantity, action synonyms added)
  - core/speech_understanding.py (KNOWN_ENTITIES enriched, thoda removed from fillers)
  - core/contextual_resolver.py (object reference + direction scroll resolution)
  - core/conversational_intent.py (empathetic response generation for body/emotion states)
  - core/semantic/__init__.py (all classes exported)
dependencies: []
tests: tests/test_natural_language_vocab_kb.py (116 tests), tests/test_hindi_vocab_engine.py (163 tests) — 100% pass (279/279)
last_modified: 2026-09-12
```

---

# 43. FEATURE ENTRY: nlp.lexicon_engine

```yaml
feature_id: nlp.lexicon_engine
name: Local Vocabulary & Dictionary Intelligence Engine
status: active
risk_tier: LOW
owner_module: core.semantic.lexicon
file_path: core/semantic/lexicon.py
categories:
  - SYSTEM_RESTART (restart, reboot, restart the PC, reboot my computer, system ko restart karo, PC dobara start karo, dobara start, phir se start, wapas start)
  - OPEN_APPLICATION (open, launch, start, chalao, khol do, khol de, kholiye, kholo, open karo, launch karo, start karo, chalu karo, run)
  - CLOSE_TARGET (band karo, close karo, exit karo, kill karo, rok do, hatao)
  - SYSTEM_SHUTDOWN (shutdown karo, power off karo, turn off karo, band karo system)
  - ABBREVIATIONS (pc->computer, calc->calculator, ppt->powerpoint, doc->word, xls->excel, yt->youtube, wa->whatsapp, bt->bluetooth, wifi->wi-fi, cmd->command prompt, ps->powershell, vol->volume, mic->microphone, cam->camera, msg->message, app->application, microsft->microsoft)
entrypoints:
  - core.semantic.lexicon.LexiconEngine.is_system_restart_utterance
  - core.semantic.lexicon.LexiconEngine.is_open_action
  - core.semantic.lexicon.LexiconEngine.extract_open_target
  - core.semantic.lexicon.LexiconEngine.expand_abbreviation
  - core.semantic.lexicon.LexiconEngine.get_canonical_term
  - core.semantic.lexicon.LexiconEngine.analyze
integrations:
  - core/semantic/__init__.py (exported classes and helper functions)
  - core/semantic/parsers/system.py (is_system_restart_utterance integrated into parse_system_control)
  - core/semantic/constants.py (expanded OPEN_VERBS with full variations)
  - core/semantic/parsers/media.py (guarded bare action verbs from media hijacking)
  - core/semantic/orchestrator.py (integrated into SemanticPipelineOrchestrator)
dependencies: []
tests: tests/test_vocabulary_lexicon_engine.py (26 tests, 100% pass)
last_modified: 2026-09-12
```

---

# 44. FEATURE ENTRY: nlp.intelligent_spelling_resolver

```yaml
feature_id: nlp.intelligent_spelling_resolver
name: Intelligent Spelling & Phonetic Clarification Engine
status: active
risk_tier: LOW
owner_module: brain.spelling_resolver
file_path: brain/spelling_resolver.py
capabilities:
  - Silent High-Confidence Typo Correction (retstart->restart, microsft->microsoft, excell->excel, exel->excel, chrme->chrome, crome->chrome, blutooth->bluetooth, blootooth->bluetooth)
  - Natural Spoken Acknowledgement Generation ("open exel" -> "Ji, Microsoft Excel khol raha hoon.")
  - Personalized Ambiguous Clarifications ("Shailesh, aap Excel keh rahe hain ya Word?" when user_name is available)
  - Pre-Intent Gating Resolution (executes at start of conversational turn prior to speech understanding and fast-path execution)
entrypoints:
  - brain.spelling_resolver.SpellingResolver.resolve
  - brain.spelling_resolver.SpellingClarificationFormatter.format_auto_ack
  - brain.spelling_resolver.SpellingClarificationFormatter.format_clarification
integrations:
  - core/app.py (early-stage turn resolution, auto-ack consumption, pending spelling confirmation handling)
  - core/semantic/orchestrator.py (pre-dispatch spelling resolution for direct callers)
  - core/dialog_manager.py (pending spelling confirmation management)
dependencies:
  - core.windows_app_resolver.WindowsAppResolver
tests: tests/test_intelligent_spelling.py (17 tests, 100% pass), tests/test_spelling_resolver.py (68 tests, 100% pass)
last_modified: 2026-09-12
```

---

# 45. FEATURE ENTRY: conversation.speech_act_gating_empathy

```yaml
feature_id: conversation.speech_act_gating_empathy
name: Conversation-First Behavior & Empathetic Speech-Act Gating
status: active
risk_tier: LOW
owner_module: core.conversational_intent
file_path: core/conversational_intent.py
capabilities:
  - Strict Speech-Act Gating (distinguishes casual chat, fatigue, emotional states, small-talk, questions, and commands prior to execution)
  - Empathetic Physical/Emotional State Responses ("Today bahut thak gaya hoon." -> "Kaafi tiring day raha lagta hai. Thoda rest kar lijiye.")
  - Complete Application/Command Isolation (guarantees casual utterances NEVER search for apps or trigger broken command fallbacks)
entrypoints:
  - core.conversational_intent.ConversationalIntentClassifier.classify
  - core.conversational_intent.ConversationalIntentClassifier._detect_conversational_turn
integrations:
  - core/app.py (Step 2.ConversationalGating intercepts CONVERSATION and GREETING before app/workflow resolution)
  - core/semantic/hindi_vocab.py (HindiVocabEngine body state and emotion enrichment)
dependencies: []
tests: tests/test_conversation_first_and_multicommand.py, tests/test_conversational_intent_speech_act.py
last_modified: 2026-09-12
```

---

# 46. FEATURE ENTRY: system.temporal.day_date_resolver

```yaml
feature_id: system.temporal.day_date_resolver
name: Robust Date, Day-of-Week & Relative Temporal Resolver
status: active
risk_tier: LOW
owner_module: core.time_context
file_path: core/time_context.py
capabilities:
  - Multi-Lingual Weekday Queries ("aaj konsa din hai", "aaj kya din hai", "what day is today")
  - Multi-Lingual Date Queries ("what is date today", "what date is today", "aaj ki tarikh", "today date")
  - Ultra-Low Latency FastPath Interception (< 2ms response via _try_fast_command_path in core/app.py)
  - Knowledge Engine GK Guarding (excludes date/day/time queries from GK fallbacks)
entrypoints:
  - core.time_context.TimeContext.resolve_time_query
  - core.time_context.get_time_context
integrations:
  - core/app.py (_try_fast_command_path direct resolution)
  - core/knowledge/router.py (is_knowledge_candidate exclusion guard)
dependencies: []
tests: tests/test_conversation_first_and_multicommand.py, tests/test_time_context.py
last_modified: 2026-09-12
```

---

# 47. FEATURE ENTRY: commands.multi_entity_distributive_executor

```yaml
feature_id: commands.multi_entity_distributive_executor
name: Multi-Command Distributive Action Parser & Sequential Executor
status: active
risk_tier: LOW
owner_module: core.semantic.multi_entity
file_path: core/semantic/multi_entity.py
capabilities:
  - Distributive Conjunction Parsing ("Chrome aur Brave kholo aur dono me YouTube open karo." -> Open Chrome, Open Brave, Open YouTube in Chrome, Open YouTube in Brave)
  - Multi-App Sequential Execution ("Excel, Word aur Chrome kholo." -> executes all 3 with verified OS state check)
  - Transparent Container-Aware Response Synthesis ("Chrome, Brave, YouTube (Chrome) aur YouTube (Brave) sab open ho gaye, Boss.")
entrypoints:
  - core.semantic.multi_entity.MultiEntityCommandParser.parse
  - core.execution.multi_executor.MultiActionExecutor.execute_plan
integrations:
  - core/app.py (Step 5.0 Natural Multi-Entity / Multi-Action Command Interceptor)
  - core/entities/knowledge.py (EntityKnowledgeBase entity extraction)
dependencies:
  - core.execution.strategies.ExecutionStrategyEngine
  - core.execution.verifier.ExecutionVerificationLayer
tests: tests/test_conversation_first_and_multicommand.py, tests/test_multi_entity_commands.py
last_modified: 2026-09-12
```

---

# 48. FEATURE ENTRY: core.natural_responses.synthesizer

```yaml
feature_id: core.natural_responses.synthesizer
name: Natural Response Generation & Conversational Language Mirroring Engine
status: active
risk_tier: LOW
owner_module: core.natural_responses
file_path:
  - core/natural_responses.py
  - core/response_policy.py
  - core/execution/multi_executor.py
capabilities:
  - Concise, context-aware natural feedback avoiding robotic templates ("Command executed successfully.", "Operation completed.", "Target application launched successfully.")
  - Dynamic rotational variation for app launching, closing, website navigation, device toggling, and multi-entity operations
  - Conversational language mirroring (Rule 11): Hinglish inputs receive natural Hinglish responses; English inputs receive English responses
  - Multi-browser special case synthesis ("Ji, dono browsers open kar diye.")
entrypoints:
  - core.natural_responses.NaturalResponseSynthesizer.open_app
  - core.natural_responses.NaturalResponseSynthesizer.close_app
  - core.natural_responses.NaturalResponseSynthesizer.open_website
  - core.natural_responses.NaturalResponseSynthesizer.toggle_device
  - core.natural_responses.NaturalResponseSynthesizer.multi_entity_result
  - core.natural_responses.NaturalResponseSynthesizer.generate_password
tests: tests/test_natural_responses_and_workflow_lock.py, tests/test_conversational_response_policy.py
last_modified: 2026-09-12
```

---

# 49. FEATURE ENTRY: security.password_generation_workflow

```yaml
feature_id: security.password_generation_workflow
name: Cryptographic Password Generator & Multi-Turn Workflow Lock
status: active
risk_tier: LOW
owner_module: core.semantic.parsers.security
file_path:
  - core/semantic/parsers/security.py
  - core/dialog_manager.py
  - core/app.py
capabilities:
  - Structured entity extraction for password generation (e.g. "8 digit password generate karo" -> length=8)
  - Cryptographically secure random password generation (uppercase, lowercase, digits, symbols) with automatic clipboard copy
  - Active multi-turn workflow lock (Rule 15): prompts "Kitne characters ka?" when length is omitted, locks turn, and resolves subsequent user response ("12.") directly into the workflow
  - Robust cancellation and topic shift handling inside active workflow locks
entrypoints:
  - core.semantic.parsers.security.parse_password_generation
  - core.semantic.parsers.security.generate_secure_password
  - core.dialog_manager.DialogManager.set_lock
  - core.dialog_manager.DialogManager.process_locked_turn
tests: tests/test_natural_responses_and_workflow_lock.py
last_modified: 2026-09-12
```

# 50. FEATURE ENTRY: knowledge.expanded_factual_base

```yaml
feature_id: knowledge.expanded_factual_base
name: Expanded Multilingual Natural Language Knowledge Base (250+ Entities)
status: active
risk_tier: LOW
owner_module: core.knowledge
file_path:
  - core/knowledge/data/__init__.py
  - core/knowledge/data/indian_states.py
  - core/knowledge/data/countries.py
  - core/knowledge/data/science_and_astronomy.py
  - core/knowledge/data/computing_and_tech.py
  - core/knowledge/data/leaders_and_inventors.py
  - core/knowledge/data/acronyms_and_geography.py
  - core/knowledge/data/monuments_and_wonders.py
  - core/knowledge/data/historical_figures.py
  - core/knowledge/entity_store.py
  - core/knowledge/synonyms.py
  - core/knowledge/router.py
  - core/knowledge/formatter.py
capabilities:
  - 251 consolidated unique entities with 689 indexed aliases across all 16 general knowledge categories
  - All 28 Indian States and 8 Union Territories with capitals, languages, largest cities, and landmarks
  - 42 major world countries with capitals, currencies, continents, and languages
  - Solar system, galaxies, periodic table elements, biology concepts, and universal physics constants
  - Computing and networking architecture (TCP/IP, UDP, DNS, HTTP/HTTPS, SSD/HDD, BIOS, Firewalls, Cloud, AI, ML)
  - Historical leaders, Nobel laureates, freedom fighters, and visionary inventors
  - Iconic Indian monuments (Taj Mahal, Statue of Unity, Qutub Minar, Red Fort) and World Wonders
  - Physical geography (Mariana Trench, Lake Baikal, Caspian Sea, Angel Falls, Nile, Amazon, Thar Desert)
  - Smart property key aliasing and multilingual natural response synthesis in Hindi, English, and Hinglish
  - Strict anti-hallucination gating with transparent refusal on unverifiable queries
entrypoints:
  - core.knowledge.get_knowledge_engine
  - core.knowledge.KnowledgeEngine.query
  - core.knowledge.entity_store.EntityStore.search_entities
  - core.knowledge.router.KnowledgeRouter.route_query
tests: tests/test_expanded_knowledge_base.py, tests/test_knowledge_engine.py
last_modified: 2026-09-12
```

---

# 51. FEATURE ENTRY: knowledge.scientific_conceptual_reasoning

```yaml
feature_id: knowledge.scientific_conceptual_reasoning
name: Scientific & Conceptual Multilingual Reasoning Models
status: active
risk_tier: LOW
owner_module: core.knowledge
file_path:
  - core/knowledge/reasoning_store.py
  - core/knowledge/models.py
  - core/knowledge/router.py
capabilities:
  - Bilingual (Hindi/Hinglish and English) explanations for complex "Why" and "How" questions
  - Aerodynamic lift and Bernoulli airfoil principle explaining how airplanes fly
  - Chlorophyll selective light absorption explaining why plant leaves are green
  - Mechanical wave physics explaining why sound cannot travel in space/vacuum
  - Speed of light vs speed of sound explaining why lightning is seen before thunder
  - Earth axial rotation explaining day and night cycles
  - Microscopic droplet terminal velocity and thermal updrafts explaining why clouds float
  - Lunar and solar gravitational bulges explaining ocean tides
entrypoints:
  - core.knowledge.reasoning_store.ReasoningStore.find_concept
  - core.knowledge.router.KnowledgeRouter._check_reasoning
tests: tests/test_expanded_knowledge_base.py
last_modified: 2026-09-12
```

---

# 52. FEATURE ENTRY: system.lifecycle_exit_shutdown

```yaml
feature_id: system.lifecycle_exit_shutdown
name: Authoritative Application Lifecycle Exit and Shutdown Control
status: active
risk_tier: MEDIUM
owner_module: core.app
file_path:
  - core/app.py
  - core/conversational_intent.py
capabilities:
  - High-priority preemption of conversational fallback loops for exit and farewell directives
  - Instant transition to SystemState.SHUTDOWN on "exit", "bye", "quit", "goodbye", "alvida", "terminate"
  - Speech-act gating protection preventing capability questions ("can you exit?") from triggering shutdown
  - Clean farewell confirmation synthesis with emission of "system.shutdown" event
entrypoints:
  - core.app.JarvisCore.process_input (Step 2.ExitShutdown)
  - core.conversational_intent.ConversationalIntentClassifier.classify
tests: tests/test_exit_and_bye_behavior.py
last_modified: 2026-09-12
```

# 53. FEATURE ENTRY: voice.wake_word.position_independent

```yaml
feature_id: voice.wake_word.position_independent
name: Universal Position-Independent Wake-Word Detection and Extraction
status: active
risk_tier: LOW
owner_module: voice.wake_word
file_path:
  - voice/wake_word.py
  - core/conversation.py
capabilities:
  - Position-independent wake-word detection across beginning, middle, end, and standalone in utterances
  - Standalone token-boundary matching with lookaround boundaries preventing false positives (jarvisian, jarvises, myjarvisapp, jarvis123, jarvis-app)
  - Punctuation-aware and quote-aware wake token removal with clean utterance preservation
  - Backward and forward compatible WakePosition equality (beginning/prefix, middle/embedded, end/suffix, standalone)
  - JARVIS_ADDRESSED boolean flag and structured [WAKE] logging emission
  - Conversational verb preservation (Zara suno Jarvis -> Zara suno)
  - Unified single-source wake detection delegating core.conversation to voice.wake_word
  - Standalone wake affirmative verbal response ('Yes, I\\'m listening.') with post-playback self-voice acoustic echo prevention
entrypoints:
  - voice.wake_word.WakeWordDetector.detect
  - voice.wake_word.contains_standalone_wake_word
  - core.conversation.WakeWordDetector.detect_and_strip
  - core.interaction_gate.InteractionGate.evaluate
tests:
  - tests/test_wake_word_position_independent.py
  - tests/test_wake_word_universal.py
  - tests/test_voice_and_wake_word.py
  - tests/test_soft_whispered_wake_word.py
  - tests/test_standalone_wake_echo_prevention.py
last_modified: 2026-10-01
```

# 54. FEATURE ENTRY: gui.settings.manual_microphone_selection

```yaml
feature_id: gui.settings.manual_microphone_selection
name: GUI Settings Manual Microphone Selection & Hardware Diagnostics
status: active
risk_tier: LOW
owner_module: gui.views.settings_view
file_path:
  - gui/views/settings_view.py
  - voice/device_manager.py
  - core/app.py
  - config.yaml
capabilities:
  - Manual microphone selection dropdown in GUI Settings with auto-detect option (Bluetooth > USB > Default)
  - Driver deduplication across Windows host APIs (WASAPI, DirectSound, MME) with visual badges ([Bluetooth], [USB], [Default], [Internal/Analog])
  - Immediate real-time hot-switching of active audio recording streams upon preference selection without application restart
  - Device refresh scan button to detect newly connected or paired microphones and Bluetooth earbuds on the fly
  - Non-blocking 1.2s audio capture diagnostic ("Test Mic") measuring RMS signal and peak levels via background worker thread
  - Seamless configuration persistence in config.yaml under voice.preferred_microphone with automatic boot-time restoration
entrypoints:
  - gui.views.settings_view.SettingsView._populate_microphones
  - gui.views.settings_view.SettingsView._refresh_microphones
  - gui.views.settings_view.SettingsView._test_microphone
  - voice.device_manager.AudioDeviceManager.set_manual_device
  - voice.device_manager.AudioDeviceManager.get_unique_input_devices
  - voice.device_manager.AudioDeviceManager.test_device_audio
tests:
  - tests/test_manual_microphone_selection.py
  - tests/test_audio_device_manager.py
  - tests/test_gui.py
last_modified: 2026-09-13
```

# 55. FEATURE ENTRY: browser.container_activities.targeted_resolution

```yaml
feature_id: browser.container_activities.targeted_resolution
name: Browser-Contained Activities & Targeted Tab Resolution
status: active
risk_tier: LOW
owner_module: core.semantic.parsers.windows
file_path:
  - core/semantic/parsers/windows.py
  - core/semantic/multi_entity.py
  - core/execution/multi_executor.py
  - core/target_engine.py
  - core/entities/knowledge.py
capabilities:
  - Natural language container-activity recognition across Hindi, English, and Hinglish ("chrome wala youtube band kar do", "chrome me chatgpt kholo", "close youtube in brave", "brave ka netflix band karo")
  - Multi-Entity container-binding preventing host browser applications from being parsed as standalone targets to terminate
  - Host process protection ensuring browser processes are never terminated when user targets internal tabs or web services
  - Targeted tab closure via BrowserTabManager closing only the specific matching tab inside the designated container browser
  - Natural conversational feedback acknowledging container-scoped actions ("Chrome mein YouTube band kar diya, Boss.") and friendly not-found reports
entrypoints:
  - core.semantic.parsers.windows.parse_universal_target_action
  - core.semantic.parsers.windows.parse_app_close
  - core.semantic.multi_entity.MultiEntityCommandParser.parse
  - core.execution.multi_executor.MultiActionExecutor._execute_single_item
  - core.target_engine.UniversalTargetDiscoveryEngine.execute
# 56. FEATURE ENTRY: system.windows11.administrative_tools

```yaml
feature_id: system.windows11.administrative_tools
name: Windows 11 Administrative Tools & Snap-ins Support (Open & Close)
status: active
risk_tier: LOW
owner_module: core.windows_app_resolver
file_path:
  - data/windows_apps.json
  - core/windows_app_resolver.py
  - core/execution/strategies.py
  - plugins/windows/window_manager.py
  - core/target_engine.py
  - core/execution/verifier.py
capabilities:
  - Full catalog of Windows 11 system tools, management snap-ins (.msc), and control applets (.cpl): Computer Management, Disk Management, Event Viewer, Performance Monitor, Resource Monitor, Group Policy Editor, Local Security Policy, System Information, System Configuration, Windows Defender Firewall, DirectX Diagnostic, Disk Cleanup, Task Scheduler, Local Users and Groups, Certificate Manager, Network Connections, Programs and Features, System Properties
  - Natural English, Hindi, and Hinglish open/close parsing with zero website fallthrough or UnknownWebsiteError confusion
  - Native .msc and .cpl execution handling in direct_executable strategy via os.startfile/ShellExecute without WinError 193 or WinError 740 elevation crashes
  - Safe window-targeted closing for MMC snap-ins sharing mmc.exe without cross-snap-in process termination or taskbar disruption
  - Dynamic WindowsAppResolver title, process, and alias enrichment in WindowManager and TargetMatcher with 1.0 confidence matching
  - Accurate closure verification ensuring snap-in dismissal is confirmed when window closes without requiring all host processes to die
entrypoints:
  - core.windows_app_resolver.WindowsAppResolver.resolve_application
  - core.windows_app_resolver.WindowsAppResolver.load_registry
  - core.execution.strategies.ExecutionStrategyEngine._dispatch_app_strategy
  - plugins.windows.window_manager.WindowManager.find_windows_for_app
  - plugins.windows.window_manager.WindowManager.is_process_running
  - plugins.windows.window_manager.WindowManager.execute_operation
  - core.target_engine.TargetMatcher.rank
  - core.execution.verifier.ExecutionVerificationLayer.verify_window_operation
tests:
  - tests/test_windows_11_system_apps.py
  - tests/test_windows_app_resolver.py
  - tests/test_universal_verification_layer.py
last_modified: 2026-09-13
```

# 57. FEATURE ENTRY: conversation.human_model

```yaml
feature_id: conversation.human_model
name: Human Conversation Model (7-Dimensional Holistic Understanding & Empathy)
status: active
risk_tier: LOW
owner_module: brain.conversation.model
file_path:
  - brain/conversation/model.py
  - brain/conversation/__init__.py
  - brain/conversation/engine.py
  - brain/conversation/response_generator.py
  - brain/conversation/context_tracker.py
  - core/app.py
capabilities:
  - Multi-dimensional human conversation frame analysis encompassing:
    1. Words (Shabd): Raw natural speech, Hinglish/Hindi slang, normalization.
    2. Context (Sandarbh): Active desktop window, application, website, file, active target state.
    3. Intention (Uddeshya): Conversational speech-act gating (Action Command vs Capability Question vs Status vs Troubleshooting vs Banter).
    4. Emotion (Bhaavna): Affective state classification (Frustration/Anger, Anxiety/Stress, Joy/Celebration, Fatigue/Tiredness, Sadness, Calm) with intensity scoring and cue extraction.
    5. Previous Conversation (Pichhli Baatcheet): Multi-turn history, anaphora resolution ('isme', 'usko', 'usme', 'wahi wala') via active context and previous turns.
    6. Correction (Sudhaar): Conversational repair detection ('nahi, chrome nahi edge', 'nahi brave mein kholo') with entity updating and preference adjustment.
    7. Situation (Sthiti): Environmental and time context (time-of-day, day-part, late night, work hours) tuning response brevity and tone.
  - Emotion and situation empathetic response adaptation across ConversationResponseGenerator and JarvisCore turns.
  - Zero duplicate logic, reusing HindiVocabEngine, ContextResolver, ConversationalIntentClassifier, TimeContext, and LearningManager.
entrypoints:
  - brain.conversation.model.HumanConversationModel.analyze_turn
  - brain.conversation.model.EmotionAnalyzer.analyze
  - brain.conversation.engine.ConversationEngine.process_conversation_turn
  - brain.conversation.response_generator.ConversationResponseGenerator.generate
  - core.app.JarvisCore._process_input
tests:
  - tests/test_human_conversation_model.py
  - tests/test_conversational_response_policy.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_self_improvement_integration.py
  - tests/test_hindi_vocab_engine.py
  - tests/test_natural_language_vocab_kb.py
  - tests/test_time_context.py
last_modified: 2026-09-19
conversation_update: "Conversation tracker now retains paired user/assistant history and active questions; expiry clears stale entity references while preserving the configured TTL. Existing HumanConversationModel remains the emotion/situation analyzer."
```

# 58. FEATURE ENTRY: network.wifi.credential_retrieval

```yaml
feature_id: network.wifi.credential_retrieval
name: System Wi-Fi Password Intent Disambiguation & Secure Credential Retrieval
status: active
risk_tier: LOW
owner_module: core.knowledge.router
file_path:
  - core/knowledge/router.py
  - core/conversational_intent.py
  - main.py
  - plugins/network/plugin.py
capabilities:
  - Disambiguates system Wi-Fi password queries ('what is wifi password of my system?', 'mere system ka wifi password kya hai', 'wifi password kya hai') from General Knowledge acronym lookups ('what is wifi?', 'wifi stands for').
  - Excludes system credential inquiries from is_knowledge_candidate and guards acronym full_form inference against conflicting attribute requests.
  - Classifies Wi-Fi password queries as ACTION_COMMAND in ConversationalIntentClassifier routing to copy_wifi_password while preserving non-executable gating for capability questions ('kya tum wifi password nikal sakte ho?').
  - Secures credentials by copying the active Wi-Fi password to the system clipboard and returning structured items in sensitive_display for CLI and GUI without leaking plain secrets into spoken TTS responses or logs.
entrypoints:
  - core.knowledge.router.KnowledgeRouter.is_knowledge_candidate
  - core.knowledge.router.KnowledgeRouter._check_entity_property
  - core.conversational_intent.ConversationalIntentClassifier.classify
  - plugins.network.plugin.NetworkPlugin.copy_wifi_password
  - main.run_interactive_cli
tests:
  - tests/test_wifi_password_intent.py
  - tests/test_network_speed.py
  - tests/test_plugin_network.py
  - tests/test_conversational_intent_speech_act.py
last_modified: 2026-09-13
```

# 59. FEATURE ENTRY: intent.universal_categories.meaning_normalization

```yaml
feature_id: intent.universal_categories.meaning_normalization
name: Universal Intent Categories & Semantic Meaning Normalization
status: active
risk_tier: LOW
owner_module: core.intent
file_path:
  - core/intent.py
  - core/semantic/models.py
  - core/apps/registry.py
  - core/semantic/parsers/windows.py
  - core/conversational_intent.py
  - brain/conversation/model.py
capabilities:
  - Meaning normalization: maps diverse conversational expressions ('Chrome kholo', 'Chrome open karo', 'Bhai Chrome chala de', 'Chrome start kar', 'Can you open Chrome?', 'Please launch Chrome', 'Chrome khol do') to canonical intent ('OPEN_APPLICATION') and canonical entity ('chrome') without creating redundant per-phrase rules.
  - Distinguishes 15 Universal Intent Categories: COMMAND, QUESTION, INFORMATION_REQUEST, GENERAL_CONVERSATION, FOLLOW_UP, CORRECTION, CONFIRMATION, REJECTION, CANCELLATION, TROUBLESHOOTING, REQUEST_FOR_CLARIFICATION, SYSTEM_INFORMATION, ACTION_RESULT, COMPLAINT, SMALL_TALK.
  - Extensible UniversalCategoryRegistry allowing runtime registration of new semantic categories without duplicating or fragmenting the intent pipeline.
  - Backwards compatibility: IntentName ensures legacy tests asserting 'OPEN_APP' remain 100% compatible while providing semantic 'OPEN_APPLICATION' and unified .entity property on SemanticAction.
  - Conversational speech-act gating: ensures capability questions ('Can you open Chrome?') identify semantic meaning while remaining gated from premature execution.
entrypoints:
  - core.intent.UniversalIntentCategory
  - core.intent.UniversalCategoryRegistry
  - core.semantic.models.IntentName
  - core.semantic.models.SemanticAction.entity
  - core.conversational_intent.ConversationalIntentClassifier.classify
  - brain.conversation.model.HumanConversationModel.analyze_turn
tests:
  - tests/test_universal_intent_categories.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_human_conversation_model.py
  - tests/test_windows_app_resolver.py
  - tests/test_vocabulary_lexicon_engine.py
  - tests/test_wifi_password_intent.py
last_modified: 2026-09-13
```

# 60. FEATURE ENTRY: intelligence.confidence

```yaml
feature_id: intelligence.confidence
name: Accuracy & Confidence Calibration Engine
status: active
risk_tier: LOW
owner_module: core.intelligence.confidence
file_path:
  - core/intelligence/confidence.py
  - core/intelligence/__init__.py
  - brain/conversation/model.py
  - core/app.py
capabilities:
  - Multi-dimensional confidence scoring maintaining 5 internal sub-confidences:
    1. intent_confidence (certainty in intent classification / pattern matching)
    2. entity_confidence (certainty in identified target entities vs ambiguous text)
    3. context_confidence (alignment with active window / workflow context)
    4. action_confidence (feasibility and safety of planned command execution)
    5. answer_confidence (factual grounding and certainty for knowledge retrieval)
  - 3-tier authoritative action gating enforcing the 'galat answer se better clarification' principle:
    - HIGH (>= 0.85): EXECUTE / ANSWER directly.
    - MEDIUM (0.60 <= conf < 0.85): USE_CONTEXT / VERIFY before acting.
    - LOW (< 0.60): CLARIFY rather than guessing or hallucinating wrong actions/answers.
  - Critical dimension collapse protection (< 0.40 floors) preventing ungrounded actions.
  - Destructive action capping requiring explicit verification regardless of raw confidence.
  - Natural clarification question generator targeting specific deficit dimensions (ambiguous entities, missing target, missing action, knowledge refusal).
  - Adaptive turn feedback recording for self-learning calibration.
entrypoints:
  - core.intelligence.confidence.ConfidenceEngine
  - core.intelligence.confidence.InterpretationConfidence
  - core.intelligence.confidence.ConfidenceTier
  - core.intelligence.confidence.ConfidenceAction
  - core.intelligence.confidence.get_confidence_engine
  - brain.conversation.model.HumanConversationFrame.confidence
  - core.app.JarvisCore.confidence_engine
tests:
  - tests/test_accuracy_confidence_engine.py
  - tests/test_universal_intent_categories.py
  - tests/test_human_conversation_model.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_knowledge_engine.py
last_modified: 2026-09-13
```

# 61. FEATURE ENTRY: intelligence.self_improvement

```yaml
feature_id: intelligence.self_improvement
name: Self-Improvement & Continuous Learning Engine
status: active
risk_tier: LOW
owner_module: core.intelligence.self_improvement
file_path:
  - core/intelligence/self_improvement.py
  - core/intelligence/__init__.py
  - learning/learner.py
  - learning/habit_layer.py
  - core/app.py
capabilities:
  - Authoritative Single Source of Truth (SSOT) orchestrating all 9 continuous learning capabilities:
    1. interaction evaluation (evaluate_interaction: end-to-end outcome scoring, auto-distilling procedural memories on success, recording anti-patterns and regression cases on failure)
    2. feedback detection (detect_feedback: detects Hindi/Hinglish/English sentiment, complaints, satisfaction, dissatisfaction, corrections)
    3. mistake detection (detect_mistake: analyzes failures, identifies root cause, maps recovery strategies, links diagnostics)
    4. correction learning (learn_correction: parses user verbal corrections, resolves contextual targets, stores preferences, auto-generates regression cases)
    5. pattern learning (learn_pattern: tracks frequency, habits, app transitions, and repeated workflows)
    6. confidence scoring (score_confidence: evidence-based scaling from 1 occurrence [0.35] to 6+ [0.90+], calibrated by failure penalties)
    7. learning promotion (promote_learning: verifies strict promotion thresholds [frequency >= 3, confidence >= 0.80] before graduating candidates to active policy)
    8. learning rollback (rollback_learning: safe versioned revert of preferences, rules, or habits without destructive physical data loss, maintaining audit history)
    9. regression generation (generate_regression_case: generates structured replayable test cases from corrections and mistakes to prevent silent regressions)
  - Zero duplicate logic: consolidates and reuses LearningManager, ExperienceLearningSystem, HabitLayer, ApprovalManager, and DiagnosticEngine.
  - Integration with JarvisCore: wired into initialize_subsystems and _record_turn_feedback.
entrypoints:
  - core.intelligence.self_improvement.SelfImprovementEngine
  - core.intelligence.self_improvement.FeedbackType
  - core.intelligence.self_improvement.LearningPromotionStatus
  - core.intelligence.self_improvement.RegressionCase
  - core.intelligence.self_improvement.get_self_improvement_engine
  - learning.learner.LearningManager.self_improvement
  - core.app.JarvisCore.self_improvement_engine
tests:
  - tests/test_self_improvement_engine.py
  - tests/test_self_improvement_integration.py
  - tests/test_accuracy_confidence_engine.py
  - tests/test_universal_intent_categories.py
  - tests/test_execution_preference.py
last_modified: 2026-09-13
```

# 62. FEATURE ENTRY: execution.verification

```yaml
feature_id: execution.verification
name: Outcome Verification & Real System State Observation Engine
status: active
risk_tier: LOW
owner_module: core.execution.verifier
file_path:
  - core/execution/verifier.py
  - core/execution/models.py
  - core/execution/__init__.py
  - core/execution/strategies.py
  - core/execution/multi_executor.py
  - core/target_engine.py
  - core/app.py
capabilities:
  - Authoritative Outcome Verification answering: 'Did what Jarvis executed ACTUALLY succeed in changing the system state?'
  - Decouples command execution completion from task success: zero exceptions during execute() never implies success.
  - Multi-tier verification hierarchy observing real OS state:
    1. Process Level: confirms process creation or termination via Win32 process list and PIDs.
    2. Window Level: confirms window appearance, visibility, foreground focus, and title matching via Win32 Shell COM and WindowManager.
    3. Window State: inspects HWND placement, maximizing, minimizing, restoring, and dismissal via Win32 API.
    4. Browser Tabs & Windows: validates URL fragments, page titles, and window count increments across Chrome, Brave, Edge, Firefox without false-positive process checks.
    5. Filesystem: verifies file existence, directory creation, byte contents, and deletion on disk.
    6. System & Hardware Settings: verifies volume levels, display toggles, and device states via live fetchers.
  - Unified dispatch entrypoint: ExecutionVerificationLayer.verify_outcome(...) dynamically dispatches across application, browser, window, folder, file, setting, and custom verifiers.
  - Honest unverified classification: explicitly classifies actions without concrete observers as UNVERIFIED rather than claiming false success.
  - Single Source of Truth singleton accessor: get_execution_verifier(window_manager).
entrypoints:
  - core.execution.verifier.ExecutionVerificationLayer
  - core.execution.verifier.ExecutionVerificationLayer.verify_outcome
  - core.execution.verifier.get_execution_verifier
  - core.execution.models.VerificationResult
  - core.execution.models.ExecutionResult
  - core.app.JarvisCore.execution_verifier
tests:
  - tests/test_outcome_verification_feature.py
  - tests/test_universal_verification_layer.py
  - tests/test_execution_verification_layer.py
  - tests/test_multi_entity_commands.py
last_modified: 2026-09-13
```

# 63. FEATURE ENTRY: intelligence.answer_verification

```yaml
feature_id: intelligence.answer_verification
name: Answer Verification & Factual Grounding Engine
status: active
risk_tier: LOW
owner_module: core.intelligence.answer_verification
file_path:
  - core/intelligence/answer_verification.py
  - core/intelligence/__init__.py
  - core/knowledge/router.py
  - core/knowledge/entity_store.py
  - core/knowledge/synonyms.py
  - core/app.py
capabilities:
  - Authoritative Answer Verification and Factual Grounding Layer for Jarvis knowledge and conversational answers:
    Evaluates: 'Is this factual claim grounded in authoritative knowledge, uncontradicted, sufficiently confident, and fresh?'
  - Decouples answer generation from truthfulness: generation or retrieval never automatically implies factual correctness without grounding.
  - Multi-dimension answer inspection pipeline:
    1. Answer Source Attribution: categorizes provenance across STRUCTURED_KB, REASONING_ENGINE, IT_KNOWLEDGE, CALENDAR_ENGINE, SYSTEM_TELEMETRY, LIVE_SEARCH, USER_PROFILE_KB, LLM_FALLBACK, UNVERIFIED_HALLUCINATION, and UNKNOWN.
    2. Freshness & Currency Requirement: detects time-sensitive leadership positions ('India ka PM kaun hai?'), live environmental states ('aaj weather kya hai?'), real-time financial markets, and fast-moving software releases ('Windows ka latest version kya hai?'). Strictly rejects static guessing on live metrics, mandating live data feeds.
    3. Factual Grounding: performs triple verification (entity_id, property_name, proposed_value) against authoritative EntityStore, ReasoningStore, ITKnowledgeEngine, and FestivalCalendarEngine.
    4. Contradiction Detection: catches claims directly contradicting known ground truth (e.g. claiming Mumbai is capital of India), overrides or rejects false assertions with detailed conflict rationale.
    5. Multi-Tier Confidence Calibration: integrates with intelligence.confidence (HIGH >= 0.85 -> direct answer; MEDIUM >= 0.60 -> contextual verify; LOW < 0.60 -> honest refusal preventing hallucination).
  - Wired into KnowledgeRouter: every candidate result in KnowledgeRouter._verify_and_finalize_result is vetted, verified, and stamped with answer_verification metadata.
  - Wired into JarvisCore: initialized at startup as core.answer_verifier and logged on TurnContext.metadata.
  - Single Source of Truth singleton accessor: get_answer_verifier().
entrypoints:
  - core.intelligence.answer_verification.AnswerVerificationEngine
  - core.intelligence.answer_verification.AnswerVerificationEngine.verify_answer
  - core.intelligence.answer_verification.AnswerVerificationEngine.check_freshness_requirement
  - core.intelligence.answer_verification.AnswerVerificationEngine.detect_contradictions
  - core.intelligence.answer_verification.AnswerVerificationEngine.verify_grounding
  - core.intelligence.answer_verification.get_answer_verifier
  - core.intelligence.answer_verification.AnswerSource
  - core.intelligence.answer_verification.GroundingStatus
  - core.intelligence.answer_verification.AnswerVerificationResult
  - core.app.JarvisCore.answer_verifier
tests:
  - tests/test_answer_verification_engine.py
  - tests/test_knowledge_engine.py
  - tests/test_it_knowledge_engine.py
  - tests/test_accuracy_confidence_engine.py
last_modified: 2026-09-13
```

---

# 64. FEATURE ENTRY: nlp.uncertainty_and_input_recovery

```yaml
feature_id: nlp.uncertainty_and_input_recovery
name: Incomplete, Garbled & Uncertain Input Handling Engine
status: active
risk_tier: LOW
owner_module: core.speech_understanding
file_path:
  - core/speech_understanding.py
  - core/conversational_intent.py
  - core/intent.py
  - core/app.py
capabilities:
  - Authoritative input quality evaluation and uncertainty gating for voice transcripts and text:
    Distinguishes CLEAN, INCOMPLETE_FRAGMENT, UNINTELLIGIBLE, AMBIGUOUS, and EMPTY inputs.
  - Zero False Intent Forcing:
    Garbled and corrupted transcripts (e.g. '-[p-o0p-\\', '!@#$%', home-row mash) are never forced into COMMAND, GENERAL_KNOWLEDGE, SEARCH, or APPLICATION. Assigned intent=UNKNOWN, confidence <= 0.10, action=NONE.
  - 4-Way Pragmatic Distinction:
    1. UNKNOWN: Cannot determine meaningful content -> polite natural retry prompt.
    2. AMBIGUOUS: Understands action, but target is ambiguous ('open it') -> asks targeted clarification.
    3. INCOMPLETE_FRAGMENT: Partial word or dangling phrase ('clo') -> reconstructs from context or asks to complete.
    4. RECOVERED: Successfully reconstructed from active context and dispatched safely.
  - Contextual Recovery Engine:
    Inspects Active Window, Active Context (application, website), Recent Conversation History, and Known Entities to reconstruct meaning:
    • Fragment recovery: 'clo' after opening Chrome -> 'close chrome' (confidence >= 0.85).
    • Standalone verb recovery: 'close' with active app -> 'close <app>'.
    • Acoustic confusion recovery: 'grave' in browser context -> 'Brave'.
    • Ambiguous pronoun resolution: 'open it' after referencing a document -> 'open <doc>'.
  - Non-Aggressive Autocorrect Guard:
    Ordinary words in neutral context (e.g. 'save the grave danger') are strictly preserved and never mutated into browser names.
  - Dynamic Rotated Natural Responses (NaturalUncertaintyResponder):
    Rotates varied, human-like prompts across Hinglish and English to prevent robotic repetition.
  - Developer/Debug Visibility & 7-Field Telemetry:
    Records raw_input, normalized_input, input_quality, detected_intent, confidence, context_used, recovered_interpretation on turn.metadata["speech_diagnostics"].
  - Learning Integration Threshold:
    Candidate contextual speech patterns require repeated validated evidence (>= 3 occurrences) before promotion; single turn is never permanently learned.
entrypoints:
  - core.speech_understanding.InputQuality
  - core.speech_understanding.InputQualityEvaluator
  - core.speech_understanding.InputQualityEvaluator.evaluate_quality
  - core.speech_understanding.ContextualRecoveryEngine
  - core.speech_understanding.ContextualRecoveryEngine.attempt_recovery
  - core.speech_understanding.NaturalUncertaintyResponder
  - core.speech_understanding.SpeechUnderstandingEngine.process_speech_input
  - core.conversational_intent.ConversationalIntentClassifier.classify
  - core.app.JarvisCore.process_input
tests:
  - tests/test_uncertainty_and_input_quality.py
  - tests/test_universal_intent_categories.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_accuracy_confidence_engine.py
last_modified: 2026-09-13
```

---

### Feature 65: Bappa Turtle Drawing & Automated Creative Graphics
```yaml
feature_id: automation.drawing.turtle_bappa
name: Bappa Turtle Drawing & Animated Graphics
status: active
risk_tier: LOW
owner_module: plugins.automation
file_path:
  - plugins/automation/drawings/bappa_drawing.py
  - plugins/automation/drawings/__init__.py
  - plugins/automation/commands.py
  - plugins/automation/plugin.py
  - core/conversational_intent.py
  - core/knowledge/router.py
  - core/app.py
capabilities:
  - Automated Python Turtle Graphics Drawing of Lord Ganesha (Bappa):
    Coordinates and draws Head, Ears, Eyes, Pupils, Trunk, Tusks, Crown, Tilak, Body, Belly, Arms, and Legs on an 800x800 canvas.
  - Isolated Background Subprocess Execution:
    Launches via `subprocess.Popen([sys.executable, script_path])` preventing Tkinter mainloop from blocking Jarvis core or conflicting with PySide6 Qt GUI.
  - Ultra-Low Latency Fast-Path Execution (< 20ms start):
    Directly catches drawing triggers in `JarvisCore._try_fast_command_path` and delivers immediate spoken feedback ("Bappa ki drawing bana raha hoon, Boss." / "Drawing Bappa for you, Boss.").
  - Conversational Speech-Act Gating & Capability Support:
    Classifies command variations ("drawing bappa", "draw bappa", "bappa ki drawing", "bappa drawing banao") as `ACTION_COMMAND`, while capability questions ("kya tum bappa ki drawing bana sakte ho?") return informative affirmative confirmation without executing.
  - Knowledge Engine & Festival Calendar Disambiguation:
    Excludes drawing directives from festival date lookups in `KnowledgeRouter.is_knowledge_candidate`, ensuring commands containing "bappa" never trigger generic calendar replies.
entrypoints:
  - plugins.automation.drawings.bappa_drawing.draw_bappa
  - plugins.automation.plugin.AutomationPlugin.execute
  - core.conversational_intent.ConversationalIntentClassifier.classify
  - core.app.JarvisCore._try_fast_command_path
tests:
  - tests/test_turtle_bappa_drawing.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_festival_calendar_engine.py
last_modified: 2026-09-13
```

---

### Feature 66: Live Internet News Discovery & RSS Engine
```yaml
feature_id: knowledge.live_news
name: Live Internet News Discovery & RSS Engine
status: active
risk_tier: LOW
owner_module: core.knowledge.news
file_path:
  - core/knowledge/news/models.py
  - core/knowledge/news/client.py
  - core/knowledge/news/formatter.py
  - core/knowledge/news/engine.py
  - core/knowledge/news/__init__.py
  - plugins/news/commands.py
  - plugins/news/permissions.py
  - plugins/news/plugin.json
  - plugins/news/plugin.py
  - plugins/news/__init__.py
  - core/intelligence/answer_verification.py
  - core/knowledge/router.py
  - core/execution/fast_path.py
capabilities:
  - Real-Time Live Google News RSS Feed Parsing:
    Zero external dependencies utilizing standard library urllib.request and xml.etree.ElementTree to fetch breaking headlines.
  - Multi-Category & Custom Search Topic Support:
    Resolves TOP, WORLD, INDIA/NATION, TECHNOLOGY, BUSINESS, SPORTS, ENTERTAINMENT, SCIENCE, and custom search topics (e.g., 'ISRO news', 'AI news').
  - Dual-Surface Conversational Formatting:
    Produces clean numbered visual display with source attribution for GUI/chatbox and concise natural spoken flow (first 3 headlines) for TTS.
  - Multilingual Hindi/Hinglish & English Support:
    Detects language markers and formats responses in authentic Hindi/Hinglish ('Boss, abhi ki mukhya live news headlines') or English ('Here are the latest news headlines, Boss').
  - Thread-Safe In-Memory TTL Caching:
    Caches parsed headlines for 600s with thread-safety; sub-50ms latency on repeated queries with fallback to stale cache on network outages.
  - Answer Verification & Factual Grounding:
    Integrates with AnswerVerificationEngine to attribute source as AnswerSource.LIVE_SEARCH and calibrate confidence to 0.95 (GROUNDED status).
  - Multi-Path Architecture:
    Accessible via LiveNewsEngine singleton, FastPathEngine Section 8 (< 50ms fast-path), KnowledgeRouter Step 3.6, and NewsPlugin via PluginManager.
entrypoints:
  - core.knowledge.news.engine.LiveNewsEngine
  - core.knowledge.news.engine.get_live_news_engine
  - core.knowledge.news.client.GoogleNewsFeedClient
  - core.knowledge.news.formatter.NewsResponseFormatter
  - plugins.news.plugin.NewsPlugin
  - core.execution.fast_path.FastPathEngine.try_handle
  - core.knowledge.router.KnowledgeRouter.route_query
tests:
  - tests/test_live_news_engine.py
  - tests/test_answer_verification_engine.py
  - tests/test_knowledge_engine.py
last_modified: 2026-09-13
```

---

```yaml
feature_id: system.maintenance.temp_cleanup
name: Context-Aware Natural Language System Maintenance (Temp & Recycle Bin Cleanup)
description: Understands diverse natural language, Hinglish, and synonym variations for clearing temporary files and emptying recycle bin with short-term conversational context, modifier handling ('bhi' -> ALSO), follow-up repetition ('phir se karo'), and rotated natural responses.
domain: system
status: active
risk_tier: LOW

owner_module: core.semantic.parsers.system
file_path:
  - core/semantic/parsers/system.py
  - core/semantic/models.py
  - core/semantic/normalizer.py
  - core/semantic/lexicon.py
  - core/context.py
  - core/contextual_resolver.py
  - core/natural_responses.py
  - core/execution/semantic_executor.py
  - brain/semantic_parser.py
  - plugins/system/plugin.py

entrypoint:
  - core.semantic.parsers.system.parse_system_maintenance
  - brain.semantic_parser.HinglishNLUParser.parse
  - core.context.ActiveTargetContext.update_command_context
  - core.contextual_resolver.ContextualActionResolver.resolve
  - core.natural_responses.NaturalResponseSynthesizer.system_maintenance
  - core.execution.semantic_executor.SemanticActionExecutor._handle_plugin_or_intent

intents:
  - TEMP_FILE_CLEANUP
  - RECYCLE_BIN_CLEANUP
  - SYSTEM_MAINTENANCE

aliases:
  - "temp file clear karo"
  - "clear temp file"
  - "temp files delete kar do"
  - "temporary files hata do"
  - "temp bhi clean kar do"
  - "temp file bhi clear karo"
  - "temporary files ko saaf kar do"
  - "bhai temp bhi delete kar de please"
  - "temp cleanup kar do"
  - "clean temp files"
  - "phir se karo"
  - "dobara karo"
  - "temp bhi"

dependencies:
  - core.context.ActiveTargetContext
  - core.natural_responses.NaturalResponseSynthesizer
  - plugins.system.plugin.SystemPlugin

test_paths:
  - tests/test_natural_language_context_upgrade.py
  - tests/test_system_maintenance.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Canonicalizes 20+ variations; equates TEMP_FILE_CLEANUP with SYSTEM_MAINTENANCE for 100% backward compatibility; retains short-term command memory for contextual follow-ups without overriding explicit targets.
```

```yaml
feature_id: audio.volume.intelligence_and_gating
name: Audio Volume Natural Language Understanding & Directional Ambiguity Gate
file_path: core/semantic/parsers/system.py
intents:
  - SET_VOLUME
  - VOLUME_UP
  - VOLUME_DOWN
risk_tier: LOW
owner_module: core.semantic.parsers.system
status: active

aliases:
  - "volume 50 karo"
  - "awaz 80% karo"
  - "awaaz kaan phad rahi hai"
  - "kaan phat rahe hain"
  - "bahut tez hai"
  - "shor kam karo"
  - "awaaz nahi aa rahi"
  - "kuch sunai nahi de raha"
  - "thoda tez bolo"
  - "volume adjust karo"
  - "awaaz theek karo"

dependencies:
  - core.semantic.models.SemanticAction
  - plugins.system.audio.AudioController

test_paths:
  - tests/test_universal_nlu_and_anti_guessing.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Supports flexible Hindi/Hinglish volume numbers and colloquial idioms; halts blind guessing on vague volume queries with smart directional clarification.
```

---

```yaml
feature_id: media.youtube.relative_seek_and_contextual_playback
name: Relative Media Seeking & Context-Aware Playback / Resume
file_path: core/semantic/parsers/media.py
intents:
  - YOUTUBE_CONTROL
  - PLAY_MEDIA
  - RESUME_MEDIA
risk_tier: LOW
owner_module: core.semantic.parsers.media
status: active

aliases:
  - "thoda aage badhao"
  - "aage karo"
  - "skip karo"
  - "thoda peeche karo"
  - "rewind karo"
  - "gaana chalao"

dependencies:
  - core.context.ActiveTargetContext
  - core.semantic.models.SemanticAction

test_paths:
  - tests/test_universal_nlu_and_anti_guessing.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Enables unquantified relative seeking (+10s / -10s); detects active paused media in context to resume seamlessly without asking redundant questions.
```

---

```yaml
feature_id: context.action_ellipsis_and_relative_repeat
name: Action Ellipsis Inheritance & Relative Repeat Follow-ups
file_path: core/contextual_resolver.py
intents:
  - CLOSE_APPLICATION
  - OPEN_APPLICATION
  - MINIMIZE_WINDOW
  - VOLUME_UP
  - VOLUME_DOWN
  - YOUTUBE_CONTROL
risk_tier: LOW
owner_module: core.contextual_resolver
status: active

aliases:
  - "aur Excel bhi"
  - "Notepad bhi"
  - "thoda aur"
  - "aur thoda"
  - "a little more"

dependencies:
  - core.context.ActiveTargetContext
  - core.contextual_resolver.ContextualActionResolver

test_paths:
  - tests/test_universal_nlu_and_anti_guessing.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Inherits previous action verbs (close, launch, minimize) across entity ellipsis and repeats relative steps (volume, seek, maintenance).
```

---

```yaml
feature_id: system.anti_guessing_dual_target_disambiguation
name: Anti-Guessing Boundary & Dual-Target App vs Website Disambiguation
file_path: core/semantic/parsers/windows.py
intents:
  - OPEN_APPLICATION
  - OPEN_WEBSITE
risk_tier: LOW
owner_module: core.semantic.parsers.windows
status: active

aliases:
  - "antigravity kholo"
  - "antigravity application kholo"
  - "antigravity website kholo"

dependencies:
  - core.dialog_manager.DialogManager
  - core.execution.semantic_executor.SemanticExecutor
  - core.apps.aliases.WEBSITE_ALIASES

test_paths:
  - tests/test_universal_nlu_and_anti_guessing.py

regression_tier: TIER_1
last_modified: 2026-09-15
feature_id: system.universal_goal_capability_resolver
name: Universal Meaning -> Goal -> Capability Resolver
file_path: core/semantic/goal_resolver.py
intents:
  - TEMP_FILE_CLEANUP
  - RECYCLE_BIN_CLEANUP
  - SYSTEM_MAINTENANCE
  - OPEN_APPLICATION
  - CLOSE_APPLICATION
  - OPEN_WEBSITE
  - PLAY_MEDIA
  - VOLUME_UP
  - VOLUME_DOWN
  - LOCK_SYSTEM
risk_tier: LOW
owner_module: core.semantic.goal_resolver
status: active

aliases:
  - "bhai computer halka kar de"
  - "computer ko thoda clean kar do"
  - "computer ke jo temporary faltu files hain unko hata do"
  - "temp file bhi clear karo"
  - "phir se karo"
  - "isme YouTube kholo"
  - "isko band karo"

dependencies:
  - core.capabilities.CapabilityRegistry
  - core.semantic.resolution.SemanticResolution
  - core.conversational_intent.ConversationalIntentClassifier
  - core.dialog_manager.DialogManager
  - core.execution.semantic_executor.SemanticActionExecutor

test_paths:
  - tests/test_adversarial_natural_language_intelligence.py
  - tests/test_universal_goal_resolver.py
  - tests/test_natural_language_context_upgrade.py
  - tests/test_negative_constraint_cleanup.py
  - tests/test_unseen_natural_paraphrases_70.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Authoritative 11-field semantic decision model. Translates natural Hindi/Hinglish/English into canonical goals, checks capability registry, prioritizes explicit target over context, handles anaphora/modifiers ('phir se', 'same kaam ek baar aur'), conversational repair ('nahi, Chrome mein', 'nahi, Brave kholo'), clarifies indirect ambiguities ('Computer cleanup mein temp files saaf karun ya Recycle Bin bhi?'), gates unanchored pronouns against guessing, negative constraint and safety restrictor extraction ('lekin meri personal files ko touch mat karna' -> safe temp cleanup with explicit user reassurance), contrastive negation scoping with negative lookbehind ('Temporary nahi, recycle wala hata dena' -> empty_recycle_bin; 'recycle nahi temp wala' -> clear_temp_files), descriptive functional aliasing ('internet wala app', 'video wali site'), inverse action operations ('uska ulta kar'), meta-contextual assistance ('tum context se samajhne ki koshish karo'), sequential command pipelining ('Pehle browser kholo, phir usi ke andar video wali website chala dena'), active container inheritance, strict word-boundary entity alias matching preventing false-positive knowledge collisions (e.g., 'sona' inside 'personal'), and verified 100% across 70 unseen human-style test paraphrases.
```

---

```yaml
feature_id: conversation.multi_turn_state_understanding
name: Multi-Turn Conversation State & Pre-Routing Contextual Interpretation
file_path: core/dialog_manager.py
owner_module: core.dialog_manager
status: active

aliases:
  - "movie chalao -> Kaunsi movie play karun, Boss? -> Inception"
  - "excel file kholo -> Sheet2 / sales"
  - "password banao -> Kitne characters ka? -> 16"
  - "nahi rehne do / cancel"
  - "laptop lock kar do (topic switch)"

dependencies:
  - core.dialog_manager.DialogManager
  - core.context.TurnContext
  - core.context.TaskContext
  - core.speech_understanding.SpeechUnderstandingEngine
  - core.execution.fast_path.FastPathEngine
  - core.app.JarvisCore

test_paths:
  - tests/test_multi_turn_conversation_state.py
  - tests/test_conversation_slot_filling.py
  - tests/test_natural_responses_and_workflow_lock.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Multi-turn conversation state understanding (TURN N + ACTIVE QUESTION + PENDING GOAL + MISSING SLOT + TURN N+1 ANSWER). Enforces that user utterances are interpreted in the context of the active conversation state before generic intent routing, NLU, or fast-path begins. Integrates authoritative interpret_turn_n_plus_1 into JarvisCore Step 2; prevents fast-path from preempting active dialog followups; protects short speech answers ('12', 'Thor', 'Dev', 'Inception') from being dropped as incomplete fragments when active dialog is pending; supports dynamic slot filling, cancellation, and clean topic switching.
```

---

```yaml
feature_id: system.desktop_wallpaper_engine
name: API-Free Desktop Wallpaper Subsystem & Natural Language Controller
file_path: core/wallpaper/wallpaper_engine.py
owner_module: core.wallpaper
status: active

aliases:
  - "wallpaper change karo"
  - "wallpaper badal do"
  - "iron man wallpaper laga do"
  - "koi achha sa wallpaper laga do"
  - "desktop wallpaper lagao"
  - "thoda dark wala"
  - "kya tum wallpaper change kar sakte ho?"

dependencies:
  - core.wallpaper.wallpaper_engine.WallpaperEngine
  - core.wallpaper.wallpaper_service.WindowsWallpaperService
  - core.wallpaper.wallpaper_cache.WallpaperCacheManager
  - core.wallpaper.image_validator.ImageValidator
  - core.wallpaper.image_downloader.ImageDownloader
  - core.wallpaper.query_enhancer.WallpaperQueryEnhancer
  - core.wallpaper.preference_tracker.WallpaperPreferenceTracker
  - core.wallpaper.search_manager.WallpaperSearchManager
  - core.execution.fast_path.FastPathEngine
  - core.conversational_intent.ConversationalIntentClassifier

test_paths:
  - tests/test_wallpaper_engine.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Zero-API-key automated desktop wallpaper engine with multi-provider fallback search (Wallhaven, Bing Images, Wikimedia Commons), display metrics detection (width, height, aspect ratio tier), structural image validation (format, resolution >= 1024x600, landscape orientation, minimum size), dedicated local application caching with automatic RGB JPEG normalization for guaranteed Windows 10/11 compatibility, LRU archive pruning, metadata.json persistence, conversational style preference tracking with TTL, truthful offline safety refusal, and seamless JarvisCore FastPath integration and capability gating.
```

```yaml
feature_id: system.live_weather_engine
name: API-Free Live Weather Engine & Natural Language Forecaster
file_path: core/weather/weather_engine.py
owner_module: core.weather
status: active

aliases:
  - "Delhi ka weather kaisa hai"
  - "aaj mausam kaisa hai"
  - "kal baarish hogi kya"
  - "aaj umbrella lena chahiye kya"
  - "Mumbai ka temperature kya hai"
  - "next 5 days forecast"
  - "kya tum weather check kar sakte ho?"

dependencies:
  - core.weather.weather_engine.WeatherEngine
  - core.weather.location_resolver.WeatherLocationResolver
  - core.weather.date_resolver.WeatherDateResolver
  - core.weather.normalizer.WeatherNormalizer
  - core.weather.fetcher.WeatherFetcher
  - core.weather.cache.WeatherCache
  - core.weather.freshness.WeatherFreshnessValidator
  - core.weather.confidence.WeatherConfidenceEvaluator
  - core.weather.source_manager.WeatherSourceManager
  - core.weather.response_generator.WeatherResponseGenerator
  - core.weather.parsers.wttr_json.WttrJsonParser
  - core.weather.parsers.open_meteo.OpenMeteoParser
  - core.weather.parsers.wttr_text.WttrTextParser
  - core.execution.fast_path.FastPathEngine
  - core.conversational_intent.ConversationalIntentClassifier

test_paths:
  - tests/test_weather_engine.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Zero-API-key live weather engine featuring hierarchical location resolution (local area cues, explicit city, conversation context, device geolocation discovery, and default fallback), system-clock aware date/period resolution (today, tonight, tomorrow, parso, weekend, multi-day, hourly), multi-source fallback chain (wttr.in JSON, Open-Meteo public, wttr.in plain text), city coordinates caching for accurate Open-Meteo fallback, independent TTL caching (10m current, 30m forecast), freshness validation, data confidence scoring, Rule 32 offline safety with truthful refusal, human-like response generation (Direct answer -> optional detail -> stop in Hinglish and English), ConversationalIntentClassifier capability question gating, and FastPathEngine Section 10 ultra-low latency execution.
```

---

```yaml
feature_id: intelligence.context_aware_suggestion_engine
name: Context-Aware Answer + Intelligent Suggestion Engine
file_path: core/intelligence/suggestion_manager.py
owner_module: core.intelligence
status: active

aliases:
  - "contextual suggestion"
  - "intelligent next step"
  - "useful next step suggestion"
  - "travel route comparison suggestion"
  - "hourly forecast suggestion"
  - "troubleshooting checklist suggestion"
  - "dns practical setup suggestion"
  - "excel formula suggestion"
  - "system cleanup suggestion"

intents:
  - "CONVERSATIONAL_ADVICE"
  - "TRAVEL_PLANNING"
  - "WEATHER_CHECK"
  - "IT_TROUBLESHOOTING"
  - "DNS_EXPLANATION_OR_SETUP"
  - "EXCEL_DUPLICATE_REMOVAL"
  - "MUSIC_DESIRE"
  - "SYSTEM_CLEANUP"
  - "BACKUP_PLANNING"

risk_tier: LOW

dependencies:
  - core.intelligence.models.ContextualSuggestion
  - core.intelligence.models.SuggestionScore
  - core.intelligence.models.SuggestionCategory
  - core.intelligence.suggestion_manager.SuggestionManager
  - core.capabilities.CapabilityRegistry
  - core.dialog_manager.DialogManager
  - core.app.JarvisCore

test_paths:
  - tests/test_context_aware_suggestion_engine.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Context-Aware Answer + Intelligent Suggestion Engine (USER QUESTION -> USER INTENT -> USER GOAL -> ANSWER -> WHAT WOULD BE USEFUL NEXT? -> OPTIONAL RELEVANT SUGGESTION). Implements strict non-intrusive negative suppression (simple completed commands, greetings, static factual GK, math calculations, and questions from Jarvis receive zero suggestions); supports positive goal recognition and next-step actions across Travel, Weather, IT troubleshooting, DNS setup, Excel formulas, Music desires, System cleanup, and Backup planning; enforces CapabilityRegistry verification to prevent hallucinating unsupported capabilities; calculates multi-factor SuggestionScore (goal alignment, context alignment, capability match, confidence, usefulness, repetition penalty) with threshold >= 0.75; logs internal Section 20 telemetry; and binds into DialogManager for seamless turn N+1 affirmative execution, rejection backoff, and topic switching.
```

### `voice.bluetooth.earbuds_live_routing`

```yaml
feature_id: voice.bluetooth.earbuds_live_routing
name: Live Bluetooth Earbuds Detection & Dual Audio Device Routing (MIC + TTS)
status: ACTIVE
owner_module: voice.device_manager

description: >
  Event-driven Windows CoreAudio COM (IMMNotificationClient) hardware audio endpoint monitor for Bluetooth Earbuds & Headsets (CMF Buds, AirPods, Galaxy Buds, boAt, Sony, etc.). Automatically extracts canonical base hardware identity across disparate input/output driver endpoints (e.g. 'Headset (CMF Buds 2)' and 'Headphones (CMF Buds 2)'), groups them into a unified PhysicalAudioHeadset, and atomically switches both MIC input and TTS output together without polling loops or restarts. Implements a thread-safe state machine (STABLE -> SWITCHING -> ACTIVE_HEADSET -> FALLING_BACK -> RECOVERED), honest capability degradation when mic is absent, natural Hinglish conversational announcements, EventBus domain events (audio.device.changed), and RuntimeContext audio state synchronization with seamless fallback to system defaults upon disconnect.

file_path: voice/device_manager.py

aliases:
  - "earbuds live detection"
  - "bluetooth earbuds routing"
  - "earbuds mic input"
  - "earbuds tts output"
  - "audio device hotplug watcher"
  - "headset pairing recognition"
  - "core.audio.device_manager"

intents:
  - "HARDWARE_AUDIO_TOPOLOGY_CHANGE"
  - "AUDIO_DEVICE_AUTO_ROUTE"

risk_tier: LOW

dependencies:
  - voice.device_manager.AudioDeviceManager
  - voice.device_manager.AudioDeviceInfo
  - voice.device_manager.PhysicalAudioHeadset
  - voice.device_manager.DeviceRole
  - voice.device_manager.AudioConnectionState
  - voice.device_manager.extract_base_headset_identity
  - core.audio.device_manager.AudioDeviceManager
  - core.context.RuntimeContext
  - core.context.AudioStateContext
  - core.event_bus.EventBus
  - core.event_bus.AudioDeviceChanged
  - voice.tts.TextToSpeech
  - voice.tts.TTSManager
  - voice.listener.PersistentAudioStream
  - voice.listener.VoiceListener

test_paths:
  - tests/test_bluetooth_earbuds_live_routing.py
  - tests/test_audio_device_manager.py
  - tests/test_persistent_voice_stream.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: Event-driven Windows CoreAudio COM notification client (IMMNotificationClient) with 300ms profile debounce; physical headset pairing recognition across disparate input/output endpoint strings; dual routing of MIC input and TTS output without restarts; honest capability degradation when microphone is missing; thread-safe state machine; natural Hinglish conversational feedback; EventBus domain event dispatch; centralized RuntimeContext synchronization; and SSOT architectural alias in core.audio.
```

---

```yaml
feature_id: voice.soft_whisper_wakeword_detection
name: Soft Speech and Whispered Wake-Word Detection
owner_module: voice.wake_word
file_path: voice/wake_word.py
status: active

aliases:
  - "whispered wake word"
  - "dheere se wake word"
  - "soft speech detection"
  - "quiet voice sensitivity"
  - "javis"
  - "jarvish"
  - "jervis"
  - "charvis"

intents:
  - "WAKE_WORD_DETECT"
  - "STANDALONE_WAKE_CONFIRM"

risk_tier: LOW

dependencies:
  - voice.wake_word.WakeWordDetector
  - voice.stt.AdaptiveNoiseGate
  - voice.audio_processor.AdaptiveVAD
  - voice.audio_processor.AudioCalibrator
  - voice.listener.VoiceListener
  - gui.views.chat_view.ChatView
  - core.interaction_gate.InteractionGate
  - core.app.JarvisCore

test_paths:
  - tests/test_soft_whispered_wake_word.py
  - tests/test_voice_interaction_gating.py
  - tests/test_persistent_voice_stream.py
  - tests/test_bluetooth_earbuds_live_routing.py

regression_tier: TIER_1
last_modified: 2026-09-15
notes: High-sensitivity acoustic and phonetic pipeline for whispered and quiet speech ('dheere se bolna'). Adds common whispered phonetic STT variants ('javis', 'jarvish', 'jervis', 'charvis', 'service', etc.) with negative filtering against false triggers ('customer service', 'windows service'); lowers AdaptiveNoiseGate threshold floor to 15.0 RMS for Bluetooth earbuds (with 2.0x gain boost) and 12.0 RMS for laptop internal mic (with 2.5x gain boost); eliminates Bluetooth SNR penalty in AdaptiveVAD and enables low-energy consonant flux whisper candidate detection; fixes standalone wake dispatch in VoiceListener and core.app ensuring immediate affirmative spoken reply ('Yes, I'm listening.').
```

---

```yaml
feature_id: gui.chat.context_suggestion_chips
name: Intelligent Context-Aware Suggestion Chips
owner_module: core.intelligence.suggestion_manager
file_path: core/intelligence/suggestion_manager.py
status: active

aliases:
  - "context suggestion chips"
  - "smart chips"
  - "suggestion chips"
  - "quick actions"
  - "contextual prompts"

intents:
  - "SUGGESTION_CHIPS_GENERATE"
  - "SLOT_FILL_CONFIRM"

risk_tier: LOW

dependencies:
  - core.intelligence.suggestion_manager.SuggestionManager
  - core.intelligence.models.SuggestionChip
  - core.context.ActiveTargetContext
  - core.dialog_manager.DialogManager
  - core.capabilities.CapabilityRegistry
  - gui.views.chat_view.ChatView

test_paths:
  - tests/test_context_aware_suggestion_chips.py
  - tests/test_context_aware_suggestion_engine.py
  - tests/test_gui.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Dynamic context-aware suggestion chips below Chat input replacing legacy static buttons. Powered by centralized SuggestionManager. Dynamically generates 3-5 chips based on active application context (Chrome, Excel, File Explorer, VLC), conversational goals (IT/RDP troubleshooting, travel, music desires), pending slot filling questions ('Kaunsa browser?', 'Kaunsa gaana?') and confirmation lifecycle. Enforces negative suppression zero-suggestion rule for pure factual Q&A/math/greetings, redundancy suppression (no already open apps/sites/matching volume), double-click execution guards, and routes all clicks through the authoritative semantic input pipeline without bypasses.
```

---

```yaml
feature_id: information.live_news.freshness_cache
name: Live News Freshness Classification and Adaptive Cache Engine
owner_module: core.knowledge.news
file_path: core/knowledge/news/engine.py
status: active

aliases:
  - "abhi ki news"
  - "latest news"
  - "breaking news"
  - "taza khabrein"
  - "aaj ki news"
  - "fresh headlines"

intents:
  - "NEWS_FETCH"
  - "LIVE_HEADLINES_GET"

risk_tier: LOW

dependencies:
  - core.knowledge.news.engine.LiveNewsEngine
  - core.knowledge.news.client.GoogleNewsFeedClient
  - core.knowledge.news.models.NewsCacheEntry
  - core.knowledge.news.models.NewsFreshnessTier
  - core.knowledge.news.models.CacheStatus
  - core.knowledge.news.formatter.NewsResponseFormatter
  - core.knowledge.router.FastKnowledgePath

test_paths:
  - tests/test_live_news_freshness.py
  - tests/test_live_news_engine.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Fixes stale cache bug where time-sensitive queries ('abhi ki news kya hai', 'latest news') received stale responses across multiple turns. Implements semantic freshness intent classification (FRESHNESS_CRITICAL, NORMAL_CACHEABLE, HISTORICAL), adaptive TTL policies (30s revalidation window for critical vs 600s for general topics vs 3600s for historical), stable article fingerprinting (hash of title, url, source, published timestamp) to reliably detect upstream changes vs unchanged feeds, transparent fallback to stale cache on network failures with user-facing honesty notice, and targeted cache invalidation. Preserves zero-persistence FastKnowledgePath grounding without stale retention.
```

---

```yaml
feature_id: conversation.future_intention_understanding
name: Future Intention and Scheduled Plan Conversational Understanding
owner_module: core.conversational_intent
file_path: core/conversational_intent.py
status: active

aliases:
  - "mujhe khana khane jaana hai"
  - "gym jana hai"
  - "doctor ke paas jana hai"
  - "meeting attend karni hai"
  - "I have to leave for lunch"
  - "presentation hai"

intents:
  - "FUTURE_INTENTION"
  - "FUTURE_EVENT"
  - "STATEMENT"

risk_tier: LOW

dependencies:
  - core.conversational_intent.ConversationalIntentClassifier
  - core.dialog_manager.DialogManager
  - core.dialog_manager.PendingReminderOffer
  - plugins.reminder.plugin.ReminderPlugin
  - core.time_context.TimeContext

test_paths:
  - tests/test_future_intention_understanding.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_plugin_reminder.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Resolves unknown command rejections ("Ye command mujhe clear nahi hui") on human future plans and obligations ("Mujhe 1:30 PM pe khana khane jaana hai."). Introduces semantic speech-act gating distinguishing FUTURE_INTENTION (personal obligations), FUTURE_EVENT (scheduled external events), EXPLICIT_REMINDER_REQUEST (direct commands), INFORMATION_QUESTION (schedule status inquiries), and STATEMENT. Extracts normalized temporal anchors supporting AM/PM, Hinglish periods, and colon-stripped punctuation ("1 30 pm"). Integrates contextual reminder offers with Turn N+1 affirmation ("haan") creating reminders via authoritative ReminderPlugin and cancellation ("nahi") declining gracefully without duplicate tables or competing reminder managers.
```

---

```yaml
feature_id: reminder.trigger_spoken_notifications
name: Real-Time Reminder Triggers, Multi-Channel Notifications, and Voice Delivery
owner_module: plugins.reminder
file_path: plugins/reminder/scheduler.py
status: active

aliases:
  - "reminder trigger"
  - "reminder notification"
  - "alarm trigger"
  - "reminder alert"

intents:
  - "REMINDER_TRIGGERED"

risk_tier: LOW

dependencies:
  - plugins.reminder.scheduler.ReminderScheduler
  - plugins.reminder.plugin.ReminderPlugin
  - core.event_bus.EventBus
  - core.event_bus.EventTopics
  - core.app.JarvisCore
  - gui.app.JarvisApp
  - voice.tts.TTSManager

test_paths:
  - tests/test_reminder_trigger_notification.py
  - tests/test_plugin_reminder.py
  - tests/test_future_intention_understanding.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Fixes reminders triggering silently with only logger.info entries. Establishes multi-channel real-time notification architecture upon reminder expiry: (1) publishes EventTopics.REMINDER_TRIGGERED across EventBus; (2) pre-loads resident plugins ('reminder') in PluginManager with EventBus propagation so background scheduler remains active; (3) triggers native Windows desktop balloon tip notification; (4) communicates cross-thread safely via Qt Signal bridge in JarvisApp, displaying visual reminder in Live Chat ('⏰ Reminder: <title>'), refreshing Reminders table, and delivering spoken audio alert via TTSManager; (5) provides headless/CLI fallback in JarvisCore speaking aloud when GUI is inactive.
```

---

```yaml
feature_id: software.update.manager
name: Production Software Update Manager
owner_module: core.software_update
file_path: core/software_update/manager.py
status: active

aliases:
  - "saare software update kar do"
  - "check karo koi software update hai"
  - "mere applications update kar do"
  - "jo updates available hain sab install kar do"
  - "Windows bhi update kar do"
  - "sab kuch latest kar do"
  - "software aur Windows dono update check karo"

intents:
  - "UPDATE_INSTALLED_SOFTWARE"
  - "UPDATE_WINDOWS"
  - "CHECK_FOR_UPDATES"
  - "EXECUTE_UPDATE_PLAN"
  - "CANCEL_UPDATE"

risk_tier: MEDIUM

dependencies:
  - core.software_update.manager.SoftwareUpdateManager
  - core.software_update.winget_provider.WingetUpdateProvider
  - core.software_update.windows_update_provider.WindowsUpdateProvider
  - core.software_update.store_provider.StoreUpdateProvider
  - core.software_update.report_builder.UpdateReportBuilder
  - plugins.software_update.plugin.SoftwareUpdatePlugin
  - core.capabilities.CapabilityRegistry
  - core.semantic.goal_resolver.UniversalGoalResolver

test_paths:
  - tests/test_software_update_manager.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Implements production-grade Software Update Manager separating WinGet applications, Windows Update OS patches, Microsoft Store apps, and unmanaged packages. Enforces update concurrency locks, truthful reporting with zero false-claim guarantees, elevation detection, pending reboot detection, multi-turn plan caching, cooperative cancellation, and unified Voice/CLI/PySide6 GUI convergence.
```

---

```yaml
feature_id: finance.equity_research
name: Indian Equity 1-Month Investment Research & Decision-Support Engine
owner_module: core.equity_research
file_path: core/equity_research/manager.py
status: active

aliases:
  - "1 month ke liye best stock batao"
  - "swing trading ke liye koi accha stock recommend karo"
  - "mere budget ke hisaab se 1 month ke liye stocks"
  - "reliance ka 1 month technical setup kaisa hai"
  - "aaj indian market kaisa hai nifty trend batao"
  - "is stock ko monitor list mein add karo"
  - "market mein short term opportunities scan karo"

intents:
  - "EQUITY_RESEARCH"
  - "SHORT_TERM_INVESTMENT_RESEARCH"
  - "ANALYZE_STOCK_SETUP"
  - "MARKET_REGIME_QUERY"
  - "MONITOR_EQUITY_THESIS"

risk_tier: LOW

dependencies:
  - core.equity_research.manager.EquityResearchManager
  - core.equity_research.market_data_provider.MarketDataProvider
  - core.equity_research.market_regime.MarketRegimeEngine
  - core.equity_research.technical_engine.TechnicalAnalysisEngine
  - core.equity_research.strategies.TrendFollowingStrategy
  - core.equity_research.strategies.BreakoutStrategy
  - core.equity_research.strategies.MeanReversionStrategy
  - core.equity_research.fundamental_engine.FundamentalEngine
  - core.equity_research.catalyst_news_engine.CatalystNewsEngine
  - core.equity_research.risk_engine.RiskEngine
  - core.equity_research.suitability_engine.SuitabilityEngine
  - core.equity_research.scorer.MultiFactorScorer
  - core.equity_research.report_builder.ReportBuilder
  - core.equity_research.monitor.ThesisMonitor
  - plugins.equity_research.plugin.EquityResearchPlugin
  - core.capabilities.CapabilityRegistry
  - core.semantic.goal_resolver.UniversalGoalResolver

test_paths:
  - tests/test_indian_equity_research_engine.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Decision-support Indian equity research engine for a 1-month horizon. Strictly prohibits guaranteed returns, certainty claims, or stale price usage. Features universe screening (>= 10 Cr ADTV), IST market session status, 10-dimension multi-factor scoring (STRONG/MODERATE/WEAK), 3-tier risk scenarios with explicit invalidation stop levels, 30-day thesis monitoring with auto-expiry, multi-turn NLP slot preservation, and SEBI compliance disclaimers.
```

---

```yaml
feature_id: finance.equity_research.slot_filling
name: Multi-Turn Equity Research Slot Filling & Compound Normalization
owner_module: core.semantic.slot_extractor
file_path: core/semantic/slot_extractor.py
status: active

aliases:
  - "1 month ke liye or mera budget 50000 and risk moderate"
  - "ek mahina ke liye, pachaas hazaar budget aur conservative risk"
  - "2.5 lakh budget hai aur aggressive risk"
  - "short term ke liye, 50k capital"

intents:
  - "EQUITY_RESEARCH"
  - "FIND_OR_SUGGEST_EQUITY"

risk_tier: LOW

dependencies:
  - core.semantic.slot_extractor.SemanticSlotExtractor
  - core.dialog_manager.DialogManager
  - core.dialog_manager.WorkflowLock
  - core.speech_understanding.InputQualityEvaluator
  - core.equity_research.manager.EquityResearchManager

test_paths:
  - tests/test_multi_turn_equity_slot_filling.py

regression_tier: TIER_1
last_modified: 2026-09-16
notes: Authoritative multi-turn slot filling and compound normalization engine for Indian equity research. Extracts and normalizes horizon, capital (including Hindi number words and lakh/crore multipliers), risk profiles, and sector preferences from single compound utterances. Prevents input quality gating false positives on large numeric inputs (e.g., 50000 zeros). Implements interruption detection to suspend workflow locks for ad-hoc commands and resumes them seamlessly.
```

---

```yaml
feature_id: finance.stock_wizard
name: Stock Query Wizard & Decision UI
owner_module: stock.stock_service
file_path: stock/stock_service.py
status: active

aliases:
  - "mujhe koi stock suggest karo"
  - "koi achha stock batao"
  - "kaunsa stock buy kar sakta hoon?"
  - "short term ke liye stock batao"
  - "long term investment ke liye stock suggest karo"
  - "mere liye stocks shortlist karo"
  - "IT sector ke stocks batao"
  - "large cap stock suggest karo"
  - "moderate risk ke stocks dikhao"

intents:
  - "STOCK_RECOMMENDATION"
  - "EQUITY_RESEARCH"
  - "FIND_OR_SUGGEST_EQUITY"

risk_tier: LOW

dependencies:
  - stock.stock_models
  - stock.stock_router.StockWebServer
  - stock.stock_service.StockService
  - stock.stock_screener.StockScreener
  - stock.stock_fundamental.StockFundamentalEngine
  - stock.stock_technical.StockTechnicalEngine
  - stock.stock_risk.StockRiskEngine
  - stock.stock_scoring.StockScoringEngine
  - stock.stock_explanation.StockExplanationEngine
  - core.dialog_manager.DialogManager
  - core.equity_research.manager.EquityResearchManager

test_paths:
  - tests/test_stock_wizard_engine.py
  - tests/test_stock_wizard_workflow.py

regression_tier: TIER_1
last_modified: 2026-09-18
notes: Interactive Stock Query Wizard and decision support modal. Opens a local cyber-dark financial dashboard upon stock recommendation voice queries, locks conversation into STOCK_SELECTION_WORKFLOW, accepts voice or interactive slot inputs, performs multi-factor screening (fundamentals, technicals, risk suitability, Composite Score), renders candidate cards with detailed metrics, Why Matched rationales, and risk warnings, and provides conversational follow-ups and filter updates.
```

---

```yaml
feature_id: finance.stock_recommendation_memory
name: Stock Recommendation Memory & Tracking System
owner_module: stock.stock_history
file_path: stock/stock_history.py
status: active

aliases:
  - "Jarvis tumne mujhe kaunsa stock suggest kiya tha?"
  - "18 September ko tumne kya stock bataya tha?"
  - "us time price kya tha?"
  - "target kya diya tha?"
  - "exit kab karna tha?"
  - "ABC ka target kya hai?"
  - "ABC kitne pe suggest kiya tha?"
  - "abhi uska status kya hai?"
  - "target 1 hit hua?"

intents:
  - "HISTORICAL_STOCK_RECOMMENDATION_QUERY"
  - "STOCK_MEMORY_RETRIEVAL"

risk_tier: LOW

dependencies:
  - stock.stock_models
  - stock.stock_targets.StockTargetEngine
  - stock.stock_history.StockHistoryDatabase
  - stock.stock_tracker.StockTrackerEngine
  - stock.stock_memory.StockMemoryEngine
  - stock.stock_service.StockService
  - stock.stock_router.StockWebServer
  - core.semantic.goal_resolver.GoalResolver

test_paths:
  - tests/test_stock_recommendation_memory.py

regression_tier: TIER_1
last_modified: 2026-09-18
```yaml
feature_id: core.timezone_manager
name: Authoritative Timezone Architecture & Subsystem Failure Isolation
owner_module: core.timezone_manager
file_path: core/timezone_manager.py
status: active

aliases:
  - "what time is it"
  - "samay kya hai"
  - "aaj kya date hai"
  - "hi"
  - "hello"
  - "stock suggest karo"
  - "mujhe best stock select kar ke do"
  - "selection window open nahi hua"

intents:
  - "TIMEZONE_RESOLUTION"
  - "CONVERSATIONAL_GREETING"
  - "EQUITY_RESEARCH"
  - "STOCK_SELECTION_WORKFLOW"

risk_tier: LOW

dependencies:
  - core.timezone_manager.TimezoneManager
  - core.app.JarvisCore
  - core.dialog_manager.DialogManager
  - core.semantic.goal_resolver.UniversalGoalResolver
  - core.execution.semantic_executor.SemanticActionExecutor
  - stock.stock_service.StockService

test_paths:
  - tests/test_timezone_and_stock_workflow_isolation.py

regression_tier: TIER_1
last_modified: 2026-09-19
notes: Authoritative Single Source of Truth for system and domain timezones across Jarvis. Enforces an immutable resolution hierarchy (in-memory cache -> Python zoneinfo.ZoneInfo -> dateutil.tz -> fixed-offset region fallback like UTC+05:30 for Asia/Kolkata -> local OS timezone -> UTC) that is mathematically guaranteed never to crash on missing Windows tzdata. Validates timezones at startup without aborting. Implements strict subsystem failure isolation ensuring stock module errors never trap or break basic conversational commands ('hi', 'hello'). Enforces action verification and honest feedback when stock window fails to open, and provides contextual recovery when users report the window did not open.
```

---

### `system.speech_repair.asr_recovery`

```yaml
feature_id: system.speech_repair.asr_recovery
name: ASR Misrecognition Recovery and Deictic Window Action Repair
owner_module: core.speech_repair
status: active
file_path: core/speech_repair.py

aliases:
  - "is window ko close karo"
  - "se window ko close karo"
  - "iss window ko close karo"
  - "ye window band karo"
  - "current window close karo"
  - "active window close karo"
  - "isko band karo"
  - "isse close karo"

intents:
  - "ASR_SPEECH_REPAIR"
  - "WINDOW_CLOSE"
  - "CLOSE_ACTIVE_WINDOW"

risk_tier: LOW

dependencies:
  - core.speech_repair.SpeechRepairEngine
  - core.conversation.ConversationManager
  - core.execution.fast_path.FastPathEngine
  - core.target_engine.UniversalTargetDiscoveryEngine
  - core.screen_text_locator.ScreenTextLocator
  - plugins.windows.window_manager.WindowManager

test_paths:
  - tests/test_speech_repair_and_window_recovery.py

regression_tier: TIER_1
last_modified: 2026-09-19
notes: Authoritative ASR Misrecognition Recovery and Speech Repair Engine. Intercepts raw STT before intent detection and visual text search. Corrects acoustic/phonetic confusions on demonstratives ('se window' -> 'is window', 'se app' -> 'is app', 'se close' -> 'isse close') using contextual n-gram patterns while strictly preserving legitimate instrumental postpositions ('mouse se click karo', 'keyboard se type karo'). Normalizes demonstrative/deictic window references ('is window', 'iss window', 'ye window', 'current window', 'isko', 'isse') directly to foreground/active window resolution, executing verified active window close ('Ji Sir, current window close kar diya.') in <10ms via FastPath and TargetEngine. Gates ScreenTextLocator to prevent UI object commands from triggering OCR/UIA visual text scans.
```

---

### `system.visual_text_interaction`

```yaml
feature_id: system.visual_text_interaction
name: Visual Text Interaction Engine
owner_module: core.visual_interaction
status: active
file_path: core/visual_interaction.py

aliases:
  - "Paramhans aashram kahan likha hai"
  - "Paramhans aashram par click karo"
  - "PARAMHANS AASHRAM kahan hai"
  - "परमहंस आश्रम कहाँ लिखा है"
  - "परमहंस आश्रम पर क्लिक करो"
  - "Rahul word par click karo"
  - "Rahul ke doosre wale par click karo"
  - "ab is par click karo"
  - "isko select karo"
  - "us word par click karo"

intents:
  - "VISUAL_TEXT_INTERACTION"
  - "FIND_TEXT"
  - "POINT_TO_TEXT"
  - "CLICK_TEXT"
  - "DOUBLE_CLICK_TEXT"
  - "SELECT_TEXT"

risk_tier: LOW

dependencies:
  - core.cross_script_matcher.CrossScriptMatcher
  - core.text_matcher.TextMatcher
  - core.visual_context.VisualContextManager
  - core.mouse_controller.MouseController
  - core.visual_reference.VisualReferenceManager
  - core.text_locator.TextLocatorEngine
  - core.visual_interaction.VisualInteractionEngine
  - core.semantic.parsers.visual.parse_visual_text_interaction
  - core.execution.semantic_executor.SemanticActionExecutor

test_paths:
  - tests/test_visual_text_interaction.py

regression_tier: TIER_1
last_modified: 2026-09-19
notes: Production-grade Visual Text Interaction Engine inspecting the user's active/focused window to locate, point to, click, double-click, or select target text. Features cross-script Latin <-> Devanagari transliteration candidate generation and canonical phonetic matching. Enforces Click Safety Invariant (default action is strictly FIND_TEXT/POINT_TO_TEXT with zero click), strict Jarvis self-exclusion (skips Jarvis windows, floating overlays, and system bars), case/whitespace/punctuation tolerance, spatial OCR line merging, deictic follow-up memory ('ab is par click karo'), and ordinal disambiguation ('Rahul ke doosre wale par click karo'). Returns verified, natural conversational feedback ('Sir, Paramhans Aashram yahan likha hai. Maine mouse usi jagah le diya hai.', 'Ji Sir, Paramhans Aashram par click kar diya.').
```

---

### `core.response_engine`

```yaml
feature_id: core.response_engine
name: Authoritative Central Response Engine & Natural Language Dialogue Synthesizer
owner_module: core.response_engine
status: active
file_path: core/response_engine.py

aliases:
  - "hi"
  - "hello"
  - "good morning"
  - "good afternoon"
  - "good evening"
  - "kaise ho"
  - "thanks"
  - "okay"
  - "great"
  - "Chrome kholo"
  - "isko band karo"
  - "ab is par click karo"

intents:
  - "GREETING"
  - "GREETING_TIME_AWARE"
  - "SMALL_TALK"
  - "THANKS"
  - "ACKNOWLEDGEMENT"
  - "COMMAND_SUCCESS"
  - "COMMAND_FAILURE"
  - "VISUAL_FIND"
  - "VISUAL_CLICK"
  - "BROWSER_TAB_ACTION"
  - "WINDOW_FOCUS"
  - "TARGET_NOT_FOUND"
  - "CLARIFICATION"
  - "RECOVERY"
  - "GOODBYE"

risk_tier: LOW

dependencies:
  - core.response_engine.ResponseEngine
  - core.response_planner.ResponsePlanner
  - core.response_style.ResponseStyleManager
  - core.response_validator.ResponseValidator
  - core.conversational_intent.ConversationalIntentClassifier

test_paths:
  - tests/test_response_engine.py
  - tests/test_conversational_response_policy.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_natural_responses_and_workflow_lock.py

regression_tier: 3
last_modified: 2026-09-19
notes: Unified, authoritative Central Response Engine for all final user-facing responses across Jarvis. Eliminates robotic and repetitive templates ('Main aapki kya madad kar sakta hoon?' strictly banned). Employs sliding-window variation memory to prevent back-to-back duplicate responses, truth-aware execution verification (never claims success for failed/unverified actions), controlled natural 'Sir' placement, situation-adaptive length (concise for simple commands/acks), and 10-point pre-speech validation safety gate (contradiction rejection, anti-robotic filter, technical leak prevention).
conversation_update: "Preserves ConversationEngine-generated content via parameters.conversation_response while retaining the shared style and validation gate. This prevents grounded names, project callbacks and follow-ups from being replaced by generic greetings."
```

---

```yaml
feature_id: conversation.intelligence.core
name: Conversational Intelligence, Dialogue Acts & Multi-Tier Memory Redesign
status: active
owner_module: core.conversation_state, core.dialogue_act, core.topic_tracker, core.reference_resolver, core.memory
file_path: core/conversation_state.py, core/dialogue_act.py, core/topic_tracker.py, core/reference_resolver.py, core/memory/

aliases:
  - "are yaar main ne abhi tak khana nahi khaya"
  - "chalo main kha ke aaya"
  - "tum kya kar rahe ho"
  - "achha hai"
  - "ye kaun se browser mein hai?"
  - "isko band karo"
  - "ab is par click karo"
  - "doosre wale pe jao"
  - "ye doosra wala hai"
  - "ab woh YouTube wala kholo"
  - "Rahul kahan likha hai?"

intents:
  - "CASUAL_STATEMENT"
  - "STATUS_UPDATE"
  - "CONTEXT_UPDATE"
  - "SMALL_TALK"
  - "ACKNOWLEDGEMENT"
  - "QUESTION"
  - "COMMAND"
  - "CORRECTION"
  - "REFERENCE_COMMAND"
  - "VISUAL_FIND"

risk_tier: LOW

dependencies:
  - core.dialogue_act.DialogueActClassifier
  - core.conversation_state.ConversationState
  - core.topic_tracker.TopicTracker
  - core.reference_resolver.ReferenceResolver
  - core.memory.working_memory.WorkingConversationMemory
  - core.memory.episodic_memory.EpisodicConversationMemory
  - core.memory.semantic_memory.SemanticConversationMemory
  - core.memory.retrieval.ConversationMemoryRetriever

test_paths:
  - tests/test_conversation_redesign.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_conversational_response_policy.py
  - tests/test_cognitive_memory.py

regression_tier: TIER_1
last_modified: 2026-09-19
notes: Fundamental redesign of Jarvis conversation architecture. Transforms Jarvis from a rigid command parser into an intelligent context-aware personal assistant. Enforces Dialogue Act Classification (21 acts) before intent resolution, preventing casual utterances or emotional statements from being misclassified as command errors. Features multi-tier memory (in-memory working session, database-backed episodic timeline with memory links, and durable semantic memory with local hybrid retrieval ranking recency + relevance + confidence). Implements deictic reference resolution across desktop, visual, and thread contexts ('ye', 'is', 'woh', 'ab', 'isko', 'doosre wale'). Seamlessly tracks and transitions user state (e.g. food eaten/not eaten) and preserves conversation threads across topic switches.
```

---

# END OF FEATURE REGISTRY

### Feature: Explicit Personal Facts and Recall

```yaml
feature_id: memory.profile.personal_facts
name: Explicit Personal Facts and Recall
owner_module: brain.personal_profile
status: active
risk_tier: MEDIUM
file_path:
  - brain/personal_profile.py
  - core/app.py
entrypoint:
  - brain.personal_profile.PersonalProfileExtractor.extract
  - core.app.JarvisCore._handle_profile_interpretation
intents: [USER_PROFILE_UPDATE, USER_PROFILE_QUERY, MEMORY_UPDATE]
aliases:
  - "mera naam Rahul hai"
  - "main Pune mein rehta hoon"
  - "mujhe coding pasand hai"
  - "mera project Atlas hai"
  - "mere baare mein kya yaad hai"
dependencies: [memory.memory_manager.MemoryManager, memory.long_term.LongTermMemory]
test_paths: [tests/test_identity_queries.py, tests/test_conversation_intelligence.py]
regression_tier: 3
last_modified: 2026-09-19
notes: Extends the existing profile extractor and handler; no new database or memory owner. Saves explicit name, city, interest, favourite food, hobby and current project into canonical keys. Retrieves/corrects these facts and summarizes only supported personal fields. Runs after pending dialogue handling, before spelling/GK/generic chat. Verifies persistence before acknowledging success; missing or failed storage is disclosed. Negated, hypothetical, sensitive and command-like disclosures are excluded. Scheduled reminders remain owned by the reminder plugin.
```

### Feature: Personal AI Agent & Computer Agent Layer

```yaml
feature_id: core.agent.orchestrator
name: Personal AI Agent & Computer Agent Layer
description: Autonomous goal decomposition, planning, observation, verification, recovery, and replanning layer on top of existing Jarvis architecture.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.agent.orchestrator
file_path:
  - core/agent/orchestrator.py
  - core/agent/request_classifier.py
  - core/agent/planner.py
  - core/agent/tool_registry.py
  - core/agent/observer.py
  - core/agent/verifier.py
  - core/agent/recovery.py
  - core/agent/replanner.py
  - core/agent/agent_state.py
  - core/agent/agent_policy.py
  - core/agent/task_manager.py
  - core/agent.py
  - core/app.py
entrypoint:
  - core.agent.orchestrator.AgentOrchestrator.execute_goal
  - core.agent.orchestrator.AutonomousAgent.execute_goal
  - core.app.JarvisCore._process_input
intents: [agent_goal, multi_step_task, goal_oriented_task, ambiguous_task]
aliases:
  - "AntiGravity kholo aur usko minimize karo"
  - "Chrome kholo, YouTube kholo aur playlist play karo"
  - "Is folder mein jo Python files 1500 lines se badi hain unki list banao"
  - "Is project ko organize karo"
  - "isko thik karo"
dependencies:
  - core.windows_app_resolver.WindowsAppResolver
  - plugins.windows.window_manager.WindowManager
  - core.universal_window_resolver.UniversalWindowResolver
  - core.execution.verifier.ExecutionVerificationLayer
  - core.event_bus.EventBus
  - memory.memory_manager.MemoryManager
events_published:
  - agent.start
  - agent.step.start
  - agent.progress
  - agent.state.changed
  - agent.finish
  - agent.approval.required
  - agent.approval.resolved
events_consumed:
  - system.shutdown
permissions: [EXECUTE, READ, MODIFY]
confirmation_required: HIGH, CRITICAL
test_paths:
  - tests/test_agent_architecture.py
  - tests/test_task_lifecycle_state_engine.py
regression_tier: 1
last_modified: 2026-09-19
notes: Explicit persistent task lifecycle state engine layered onto the existing agent (TASK_CREATED -> UNDERSTANDING -> PLANNING -> GATHERING_CONTEXT -> WAITING_FOR_APPROVAL -> EXECUTING -> VERIFYING -> RECOVERING -> COMPLETED/FAILED/CANCELLED). AgentTask now persists completed/failed step ids, aggregate retries, artifacts, user approval, result and timestamps, exposes a flat to_state_snapshot(), and renders a live task tree. HIGH/CRITICAL risk steps now TRULY block in WAITING_FOR_APPROVAL and only execute on explicit approval (fail-safe deny when no interactive approval handler is attached), reusing core/confirmation.py semantics. Bounded by max_retries_per_step=2 and max_total_steps=10, with dry-run mode (AGENT_DRY_RUN=true).
```

### Feature: `conversation.human_understanding_engine`
```yaml
feature_id: conversation.human_understanding_engine
name: Canonical Conversational Understanding & Pragmatic Meaning Engine
owner_module: brain.conversation.model
status: active
risk_tier: LOW
file_path: brain/conversation/model.py
intents:
  - CONVERSATIONAL_FRAME
  - SPEECH_ACT_GATING
  - PRAGMATIC_REASONING
  - EXPLICIT_NEGATION_INVARIANT
  - ELLIPSIS_UNDERSTANDING
  - TOPIC_THREAD_STACK
aliases:
  - natural_conversation
  - human_meaning_representation
  - pragmatic_clarification
dependencies:
  - core.conversational_intent.ConversationalIntentClassifier
  - core.dialogue_act.DialogueActClassifier
  - core.reference_resolver.ReferenceResolver
  - core.topic_tracker.TopicTracker
  - core.conversation_state.ConversationState
  - core.intelligence.confidence.ConfidenceEngine
events_published:
  - conversation.frame_analyzed
  - conversation.pragmatic_clarification
events_consumed:
  - user.input
permissions: [READ]
confirmation_required: false
test_paths:
  - tests/conversation/test_conversation_corpus.py
  - tests/conversation/test_golden_conversations.py
  - tests/test_human_conversation_model.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_conversation_frame.py
regression_tier: 1
last_modified: 2026-09-19
notes: >
  Extended from 29 to ~60 canonical dimensions including: turn_id, session_id, timestamp,
  input_quality, detected_languages, operational_intent, primary_entity, target_type,
  resolved_reference, reference_source, reference_confidence, resolver_used,
  negation_scope, exclusions, constraints, active_workflow, active_goal, pending_question,
  pending_goal, missing_slot, slot_values, correction_target, correction_value,
  frustration_signal, confirmation_state, cancellation_state,
  decision_type (canonical: EXECUTE_FAST/EXECUTE_AGENT/ANSWER/CONVERSE/CLARIFY/WAIT/CANCEL/REJECT),
  execution_allowed, agent_required, clarification_required,
  interpretation_status, ambiguity_reason, recovery_status, memory_used, evidence.
  Added to_dict() serialization and from_dict() reconstruction.
  Strict Negation Invariant gating + Pragmatic clarification gating preserved.
  ConversationFrameBridge (core/conv_frame/frame.py) enriches frame from
  SpeechUnderstanding, DialogueAct, ReferenceResolver, and context layer.
```

### Feature: `conversation.frame_bridge`
```yaml
feature_id: conversation.frame_bridge
name: ConversationFrameBridge
file_path: core/conv_frame/frame.py
status: active
risk_tier: LOW
owner_module: core/conv_frame
intents: []
aliases: []
dependencies:
  - brain.conversation.model.HumanConversationFrame
  - core.speech_understanding.SpeechUnderstandingEngine
  - core.dialogue_act.DialogueActClassifier
  - core.reference_resolver.ReferenceResolver
  - core.topic_tracker.TopicTracker
  - core.conversation_state.ConversationState
  - core.intelligence.confidence.ConfidenceEngine
events_published: []
events_consumed: []
permissions: [READ]
  - "REFERENCE_COMMAND"
  - "VISUAL_FIND"

risk_tier: LOW

dependencies:
  - core.dialogue_act.DialogueActClassifier
  - core.conversation_state.ConversationState
  - core.topic_tracker.TopicTracker
  - core.reference_resolver.ReferenceResolver
  - core.memory.working_memory.WorkingConversationMemory
  - core.memory.episodic_memory.EpisodicConversationMemory
  - core.memory.semantic_memory.SemanticConversationMemory
  - core.memory.retrieval.ConversationMemoryRetriever

test_paths:
  - tests/test_conversation_redesign.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_conversational_response_policy.py
  - tests/test_cognitive_memory.py

regression_tier: TIER_1
last_modified: 2026-09-19
notes: Fundamental redesign of Jarvis conversation architecture. Transforms Jarvis from a rigid command parser into an intelligent context-aware personal assistant. Enforces Dialogue Act Classification (21 acts) before intent resolution, preventing casual utterances or emotional statements from being misclassified as command errors. Features multi-tier memory (in-memory working session, database-backed episodic timeline with memory links, and durable semantic memory with local hybrid retrieval ranking recency + relevance + confidence). Implements deictic reference resolution across desktop, visual, and thread contexts ('ye', 'is', 'woh', 'ab', 'isko', 'doosre wale'). Seamlessly tracks and transitions user state (e.g. food eaten/not eaten) and preserves conversation threads across topic switches.
```

---

# END OF FEATURE REGISTRY

### Feature: Explicit Personal Facts and Recall

```yaml
feature_id: memory.profile.personal_facts
name: Explicit Personal Facts and Recall
owner_module: brain.personal_profile
status: active
risk_tier: MEDIUM
file_path:
  - brain/personal_profile.py
  - core/app.py
entrypoint:
  - brain.personal_profile.PersonalProfileExtractor.extract
  - core.app.JarvisCore._handle_profile_interpretation
intents: [USER_PROFILE_UPDATE, USER_PROFILE_QUERY, MEMORY_UPDATE]
aliases:
  - "mera naam Rahul hai"
  - "main Pune mein rehta hoon"
  - "mujhe coding pasand hai"
  - "mera project Atlas hai"
  - "mere baare mein kya yaad hai"
dependencies: [memory.memory_manager.MemoryManager, memory.long_term.LongTermMemory]
test_paths: [tests/test_identity_queries.py, tests/test_conversation_intelligence.py]
regression_tier: 3
last_modified: 2026-09-19
notes: Extends the existing profile extractor and handler; no new database or memory owner. Saves explicit name, city, interest, favourite food, hobby and current project into canonical keys. Retrieves/corrects these facts and summarizes only supported personal fields. Runs after pending dialogue handling, before spelling/GK/generic chat. Verifies persistence before acknowledging success; missing or failed storage is disclosed. Negated, hypothetical, sensitive and command-like disclosures are excluded. Scheduled reminders remain owned by the reminder plugin.
```

### Feature: Personal AI Agent & Computer Agent Layer

```yaml
feature_id: core.agent.orchestrator
name: Personal AI Agent & Computer Agent Layer
description: Autonomous goal decomposition, planning, observation, verification, recovery, and replanning layer on top of existing Jarvis architecture.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.agent.orchestrator
file_path:
  - core/agent/orchestrator.py
  - core/agent/request_classifier.py
  - core/agent/planner.py
  - core/agent/tool_registry.py
  - core/agent/observer.py
  - core/agent/verifier.py
  - core/agent/recovery.py
  - core/agent/replanner.py
  - core/agent/agent_state.py
  - core/agent/agent_policy.py
  - core/agent/task_manager.py
  - core/agent.py
  - core/app.py
entrypoint:
  - core.agent.orchestrator.AgentOrchestrator.execute_goal
  - core.agent.orchestrator.AutonomousAgent.execute_goal
  - core.app.JarvisCore._process_input
intents: [agent_goal, multi_step_task, goal_oriented_task, ambiguous_task]
aliases:
  - "AntiGravity kholo aur usko minimize karo"
  - "Chrome kholo, YouTube kholo aur playlist play karo"
  - "Is folder mein jo Python files 1500 lines se badi hain unki list banao"
  - "Is project ko organize karo"
  - "isko thik karo"
dependencies:
  - core.windows_app_resolver.WindowsAppResolver
  - plugins.windows.window_manager.WindowManager
  - core.universal_window_resolver.UniversalWindowResolver
  - core.execution.verifier.ExecutionVerificationLayer
  - core.event_bus.EventBus
  - memory.memory_manager.MemoryManager
events_published:
  - agent.start
  - agent.step.start
  - agent.progress
  - agent.state.changed
  - agent.finish
  - agent.approval.required
  - agent.approval.resolved
events_consumed:
  - system.shutdown
permissions: [EXECUTE, READ, MODIFY]
confirmation_required: HIGH, CRITICAL
test_paths:
  - tests/test_agent_architecture.py
  - tests/test_task_lifecycle_state_engine.py
regression_tier: 1
last_modified: 2026-09-19
notes: Explicit persistent task lifecycle state engine layered onto the existing agent (TASK_CREATED -> UNDERSTANDING -> PLANNING -> GATHERING_CONTEXT -> WAITING_FOR_APPROVAL -> EXECUTING -> VERIFYING -> RECOVERING -> COMPLETED/FAILED/CANCELLED). AgentTask now persists completed/failed step ids, aggregate retries, artifacts, user approval, result and timestamps, exposes a flat to_state_snapshot(), and renders a live task tree. HIGH/CRITICAL risk steps now TRULY block in WAITING_FOR_APPROVAL and only execute on explicit approval (fail-safe deny when no interactive approval handler is attached), reusing core/confirmation.py semantics. Bounded by max_retries_per_step=2 and max_total_steps=10, with dry-run mode (AGENT_DRY_RUN=true).
```

### Feature: `conversation.human_understanding_engine`
```yaml
feature_id: conversation.human_understanding_engine
name: Canonical Conversational Understanding & Pragmatic Meaning Engine
owner_module: brain.conversation.model
status: active
risk_tier: LOW
file_path: brain/conversation/model.py
intents:
  - CONVERSATIONAL_FRAME
  - SPEECH_ACT_GATING
  - PRAGMATIC_REASONING
  - EXPLICIT_NEGATION_INVARIANT
  - ELLIPSIS_UNDERSTANDING
  - TOPIC_THREAD_STACK
aliases:
  - natural_conversation
  - human_meaning_representation
  - pragmatic_clarification
dependencies:
  - core.conversational_intent.ConversationalIntentClassifier
  - core.dialogue_act.DialogueActClassifier
  - core.reference_resolver.ReferenceResolver
  - core.topic_tracker.TopicTracker
  - core.conversation_state.ConversationState
  - core.intelligence.confidence.ConfidenceEngine
events_published:
  - conversation.frame_analyzed
  - conversation.pragmatic_clarification
events_consumed:
  - user.input
permissions: [READ]
confirmation_required: false
test_paths:
  - tests/conversation/test_conversation_corpus.py
  - tests/conversation/test_golden_conversations.py
  - tests/test_human_conversation_model.py
  - tests/test_conversational_intent_speech_act.py
  - tests/test_conversation_frame.py
regression_tier: 1
last_modified: 2026-09-19
notes: >
  Extended from 29 to ~60 canonical dimensions including: turn_id, session_id, timestamp,
  input_quality, detected_languages, operational_intent, primary_entity, target_type,
  resolved_reference, reference_source, reference_confidence, resolver_used,
  negation_scope, exclusions, constraints, active_workflow, active_goal, pending_question,
  pending_goal, missing_slot, slot_values, correction_target, correction_value,
  frustration_signal, confirmation_state, cancellation_state,
  decision_type (canonical: EXECUTE_FAST/EXECUTE_AGENT/ANSWER/CONVERSE/CLARIFY/WAIT/CANCEL/REJECT),
  execution_allowed, agent_required, clarification_required,
  interpretation_status, ambiguity_reason, recovery_status, memory_used, evidence.
  Added to_dict() serialization and from_dict() reconstruction.
  Strict Negation Invariant gating + Pragmatic clarification gating preserved.
  ConversationFrameBridge (core/conv_frame/frame.py) enriches frame from
  SpeechUnderstanding, DialogueAct, ReferenceResolver, and context layer.
```

### Feature: `conversation.frame_bridge`
```yaml
feature_id: conversation.frame_bridge
name: ConversationFrameBridge
file_path: core/conv_frame/frame.py
status: active
risk_tier: LOW
owner_module: core/conv_frame
intents: []
aliases: []
dependencies:
  - brain.conversation.model.HumanConversationFrame
  - core.speech_understanding.SpeechUnderstandingEngine
  - core.dialogue_act.DialogueActClassifier
  - core.reference_resolver.ReferenceResolver
  - core.topic_tracker.TopicTracker
  - core.conversation_state.ConversationState
  - core.intelligence.confidence.ConfidenceEngine
events_published: []
events_consumed: []
permissions: [READ]
confirmation_required: false
test_paths:
  - tests/test_conversation_frame.py
regression_tier: 1
last_modified: 2026-09-19
notes: >
  Bridge/adapter module connecting HumanConversationFrame to core pipeline subsystems.
  Provides 5 static enrichment methods:
    enrich_from_speech_result  -> input_quality, interpretation_status, recovery_status
    enrich_from_dialogue_act   -> dialogue_act sync
    enrich_from_reference      -> resolved_reference, reference_confidence, resolver_used
    enrich_from_context        -> active_workflow, pending_question, slot_values
    derive_decision            -> decision_type, execution_allowed, agent_required
  FrameDecisionType enum: EXECUTE_FAST, EXECUTE_AGENT, ANSWER, CONVERSE, CLARIFY,
  MEMORY_UPDATE, WAIT, CANCEL, REJECT, NO_ACTION.
  Integrated into core/app.py _process_input at 4 enrichment points.
  Invariant #10 guard added: fast path blocked when frame.previous_turn_relation in
  (ANSWER, CONTINUATION) and pending_question or pending_goal is active.
  AgentOrchestrator.execute_goal() extended with optional conversation_frame param
  to consume pre-resolved fields without re-parsing.
```

### Feature: `learning.structured_mistake_log`
```yaml
feature_id: learning.structured_mistake_log
name: Structured Mistake Logging & Failure Classification
file_path: core/logger.py
status: active
risk_tier: LOW
owner_module: core/logger
intents: []
aliases: []
dependencies:
  - core.logger.MistakeCategory
  - core.logger.MistakeRecord
  - core.logger.MistakeLogWriter
events_published: []
events_consumed: []
permissions: [READ, WRITE]
confirmation_required: false
test_paths:
  - tests/test_structured_mistake_learning.py
regression_tier: 1
last_modified: 2026-09-19
notes: >
  Thread-safe JSONL logger writing failure records to logs/jarvis_mistakes.jsonl.
  Categorizes errors into 9 distinct MistakeCategory enums (INTENT_ERROR, TOOL_FAILURE,
  VERIFICATION_FAILURE, etc.), captures execution turn context, root cause, and avoidance advice,
  and redacts all passwords/tokens via SensitiveDataFilter.
```

### Feature: `learning.log_learner`
```yaml
feature_id: learning.log_learner
name: Automated Log Digestion & Mistake Reflection
file_path: core/experience/log_learner.py
status: active
risk_tier: LOW
owner_module: core/experience
intents:
  - mistake_reflection
aliases:
  - "apni galtiyon se kya seekha"
  - "mistakes analyze karo"
  - "kya seekha apni galtiyo se"
  - "mistake log"
dependencies:
  - core.experience.system.ExperienceLearningSystem
  - core.experience.evaluator.OutcomeEvaluator
  - core.experience.storage.ExperienceStorageManager
  - core.execution.fast_path.FastPathEngine
events_published: []
events_consumed: []
permissions: [READ, WRITE]
confirmation_required: false
test_paths:
  - tests/test_structured_mistake_learning.py
  - tests/test_experience_learning_system.py
regression_tier: 1
last_modified: 2026-09-19
notes: >
  Converts raw unlearned JSONL mistake records into permanent SQLite FailureMemory
  and vector embeddings. Runs automatically on startup and turn failures. FastPathEngine
  provides instant (< 120ms) Hinglish conversational reflection on lessons learned.
```

### Feature: `conversation.state_dispute_gating`
```yaml
feature_id: conversation.state_dispute_gating
name: Conversational Negation and State Dispute Gating
file_path: core/conversational_intent.py
status: active
risk_tier: LOW
owner_module: core
intents:
  - CORRECTION
aliases:
  - "lekin Chrome mein to open YouTube Nahin Hai"
  - "par Chrome mein to YouTube open nahi hai"
  - "lekin YouTube to open nahi hai"
  - "par khula nahi hai"
  - "but it is not open"
dependencies:
  - core.conversational_intent.ConversationalIntentClassifier
  - core.app.JarvisCore
events_published: []
events_consumed: []
permissions: [READ]
confirmation_required: false
test_paths:
  - tests/test_conversational_contradiction_negation.py
regression_tier: 1
last_modified: 2026-09-20
notes: >
  Detects conversational state disputes, contradictions, and negation markers in user utterances.
  Prevents blind command execution (e.g. launching Chrome when the user contradicts a previous claim)
  and routes to honest verification and clarification dialogue.
```

### Feature: `learning.browser_preference_persistence`
```yaml
feature_id: learning.browser_preference_persistence
name: Persistent Browser Preference and Vocabulary Resolution
file_path: brain/personal_profile.py
status: active
risk_tier: LOW
owner_module: brain
intents:
  - PROFILE_FACT_RECORD
  - CORRECTION
aliases:
  - "mera favorite browser Firefox hai"
  - "mera favourite brouser brave hai"
  - "nahi, maine bola tha Firefox mera favorite browser hai"
  - "browser kholo"
dependencies:
  - brain.personal_profile.PersonalProfileManager
  - learning.vocabulary_layer.VocabularyLayer
  - learning.corrections_layer.CorrectionsLayer
  - core.app.JarvisCore
events_published: []
events_consumed: []
permissions: [READ, WRITE]
confirmation_required: false
test_paths:
  - tests/test_conversational_contradiction_negation.py
regression_tier: 1
last_modified: 2026-09-20
notes: >
  Persists user's preferred browser across restarts in profile memory, user preferences,
  active context, and SQLite vocabulary entities. Ensures 'browser kholo' opens the
  learned browser persistently across restarts without reverting to default.
```

### Feature: `learning.self_learning_test_suite`
```yaml
feature_id: learning.self_learning_test_suite
name: Authoritative 10-Branch Self-Learning Test Suite
file_path: tests/test_self_learning_suite.py
status: active
risk_tier: LOW
owner_module: learning
intents:
  - CORRECTION
  - PROFILE_FACT_RECORD
aliases:
  - "self-learning test"
  - "learning validation suite"
dependencies:
  - core.intelligence.self_improvement.SelfImprovementEngine
  - learning.learner.LearningManager
  - learning.vocabulary_layer.VocabularyLayer
  - learning.corrections_layer.CorrectionsLayer
  - core.experience.system.ExperienceLearningSystem
  - brain.personal_profile.PersonalProfileExtractor
  - memory.memory_manager.MemoryManager
events_published: []
events_consumed: []
permissions: [READ, WRITE]
confirmation_required: false
test_paths:
  - tests/test_self_learning_suite.py
regression_tier: 1
last_modified: 2026-09-20
notes: >
  10-Branch automated verification suite testing: 1) Intent correction, 2) Entity correction,
  3) Command correction, 4) Preference learning, 5) Context learning, 6) Conversation correction,
  7) Error recovery & avoidance advice, 8) Negative feedback detection & penalty,
  9) Persistence after restart across cold SQLite reloads, and 10) Regression safety.
```

```yaml
feature_id: developer.code_assistant
name: Developer Code Assistant Plugin
file_path: plugins/code_assistant/plugin.py
status: active
risk_tier: LOW
owner_module: plugins.code_assistant
intents:
  - FIND_CODE_ERRORS
  - ANALYZE_CODE_FILE
  - FIND_UNUSED_FUNCTIONS
  - CHECK_ARCHITECTURE
  - RUN_PYTEST
  - SUGGEST_ERROR_FIX
  - ANALYZE_CHANGE_IMPACT
  - FIND_DEAD_CODE
  - GET_ASSISTANT_MODE
  - SET_ASSISTANT_MODE
aliases:
  - "Jarvis code mein ye error find karo"
  - "main.py analyze karo"
  - "unused functions find karo"
  - "project architecture check karo"
  - "pytest run karo"
  - "error fix suggest karo"
  - "last change ka impact batao"
  - "dead code find karo"
  - "code assistant mode check karo"
  - "code assistant mode set karo"
dependencies:
  - plugins.code_assistant.analyzer.CodeAnalysisEngine
  - plugins.base.BasePlugin
  - core.semantic.parsers.system.parse_code_assistant
  - core.execution.semantic_executor.SemanticActionExecutor._handle_code_assistant
events_published: []
events_consumed: []
permissions: [filesystem, process]
confirmation_required: false
test_paths:
  - tests/test_code_assistant_plugin.py
regression_tier: 1
last_modified: 2026-09-20
notes: >
  Developer Code Assistant Plugin for Jarvis development.
  Features 4 operational modes (READ_ONLY default, SUGGEST, PATCH, AUTO_FIX)
  with strict safety invariants against unprompted automatic file modification.
  Provides AST file analysis, unused function scanning, dead code detection,
```yaml
feature_id: developer.tools.archify
name: Archify Architecture Visualization
file_path: plugins/archify/plugin.py
owner_module: plugins.archify
risk_tier: LOW
status: active
intents:
  - SHOW_ARCHIFY
  - SHOW_ARCHITECTURE
aliases:
  - "archify dikhao"
  - "archify open karo"
  - "show archify"
  - "open archify"
  - "complete archify dikhao"
  - "jarvis architecture dikhao"
  - "jarvis ka architecture dikhao"
  - "show jarvis architecture"
  - "archify display karo"
  - "archify viewer kholo"
dependencies:
  - plugins.archify.plugin.ArchifyPlugin
  - plugins.archify.builder.compile_archify_html
  - plugins.archify.commands.ACTIONS
  - plugins.base.BasePlugin
  - core.reload_policy.classify_file_change
  - core.update_manager.LiveUpdateManager
  - core.semantic.parsers.system.parse_code_assistant
events_published: []
events_consumed: []
permissions: [filesystem, process]
confirmation_required: false
test_paths:
  - tests/test_archify_plugin.py
  - tests/test_live_update_manager.py
regression_tier: 1
last_modified: 2026-09-20
notes: >
  Interactive Archify architecture visualization plugin for Jarvis V2.1.
  Renders standalone Archify viewer artifact covering 7 system layers,
  guided view tours (Voice Command Pipeline, Proactive Memory & Learning,
  Plugin Subsystem), radar, and route probing. Integrated with
  LiveUpdateManager and FileWatcher so changes to architecture.txt or
  jarvis-architecture.json automatically recompile and update the Archify viewer.
```

```yaml
feature_id: ai.laya.system1
name: Laya System-1 Decision Engine (download + advisory integration)
file_path: core/laya/manager.py
owner_module: core.laya.manager.LayaModelManager
intents:
  - laya_download
  - laya_status
  - laya_test
aliases:
  - "laya download karo"
  - "laya model download karo"
  - "download laya model"
  - "laya status"
  - "laya model status"
  - "laya test karo"
dependencies:
  - core.laya.manager.LayaModelManager
  - core.laya.get_laya_manager
  - plugins.laya.plugin.LayaPlugin
  - plugins.laya.commands.ACTIONS
  - gui.views.settings_view.SettingsView
  - gui.views.settings_view.LayaDownloadWorker
  - config.yaml (laya section)
events_published:
  - laya.model.downloaded
events_consumed: []
permissions: [network, storage]
confirmation_required: false
test_paths:
  - tests/test_laya_model_manager.py
  - tests/test_math_intent_context_gating.py
regression_tier: 3
last_modified: 2026-09-25
risk_tier: LOW
status: active
notes: >
  Offline-first advisory System-1 engine (convaiinnovations/laya, pip laya).
  Settings Card 5 + background download worker + voice plugin share one
  singleton manager. Checkpoints: english/multilingual(Hinglish default)/
  typed-decisions. predict/fast_intent_decision/guard_check/rescue_intent never
  raise and never auto-execute; routing/guardrails opt-in (default off).
  rescue_intent has a deterministic math pre-check (no model needed) and is
  consulted on low-confidence turns in core/app.py Step 2.LayaRescue; calculation
  >=0.70 executes via the normal math plugin. Intent catalog now includes
  calculation.
```

```yaml
feature_id: system.math.intent_context_gating
name: Math intent & context gating (2+2, Hinglish math, negation guard)
file_path: plugins/math/calculator.py
owner_module: plugins.math.calculator.SpokenMathNormalizer.is_math_query
intents:
  - calculate (math plugin, via FastPath / semantic executor)
aliases:
  - "2+2=?"
  - "2+2 kitna/kitana hota hai"
  - "25 mein 15 jod do"
dependencies:
  - plugins.math.calculator.SpokenMathNormalizer.is_math_query (single owner)
  - plugins.math.calculator.MathEngine
  - core.speech_understanding.InputQualityEvaluator
  - core.speech_understanding.SpeechConfidenceModel
  - core.speech_understanding.SpeechUnderstandingEngine
  - core.execution.fast_path.FastPathEngine (Section 0 math, specialized fall-through)
  - core.conversational_intent.ConversationalIntentClassifier (math ACTION_COMMAND gate)
  - core.semantic.normalizer.HinglishNormalizer.EXCLUDED_WORDS (nahi/nahin/nhi/mat guard)
  - core.app.JarvisCore (Step 2.LayaRescue, conversation command_candidate guard)
events_published: []
events_consumed: []
permissions: [read]
confirmation_required: false
test_paths:
  - tests/test_math_intent_context_gating.py
  - tests/test_math_plugin.py
  - tests/test_plugin_math.py
regression_tier: 3
last_modified: 2026-09-25
risk_tier: LOW
status: active
notes: >
  Fixes reported "2+2=?" -> "message adhura" (InputQuality symbol/noise gates
  treated math operators as mash) and "2+2 kitana hota hai?" -> "Theek hai, Sir"
  (CONVERSATION hijack). Math is CLEAN quality, EXECUTE_VERIFIED confidence,
  ACTION_COMMAND intent, and FastPath Section 0 via MathPlugin. Specialized math
  (percent/average/interest/emi/square/equations) falls through to semantic
  percentage/finance/stats/power/solve routing. kitana/kitne/kya-hota-hai STT
  variants normalized. Negation words excluded from fuzzy correction so
  "kyun nahi ho raha" stays TROUBLESHOOTING.
```




### Feature: Unified Offline Memory Store

\\yaml
feature_id: memory.unified.offline_store
name: Unified Offline Memory Store
owner_module: memory.memory_api
status: active
risk_tier: LOW
file_path:
  - memory/memory_api.py
  - memory/database.py
  - memory/long_term.py
  - core/semantic/parsers/memory.py
  - core/semantic/orchestrator.py
  - core/execution/semantic_executor.py
  - core/app.py
  - core/laya/intelligence.py
entrypoint:
  - memory.memory_api.UnifiedMemory
  - memory.memory_api.get_unified_memory_for
  - core.semantic.parsers.memory.parse_memory_command
intents: [MEMORY_REMEMBER, MEMORY_FORGET, MEMORY_RECALL, MEMORY_PREFERENCES, MEMORY_CLEAR, MEMORY_QUERY_FACT]
aliases:
  - 'yaad rakho meri meeting 5 baje hai'
  - 'isko yaad rakhna'
  - 'ye memory delete karo'
  - 'meri preferences kya hain'
  - 'session memory clear karo'
  - 'what is my favorite color?'
dependencies: [memory.memory_manager.MemoryManager, memory.long_term.LongTermMemory]
test_paths: [tests/test_unified_memory.py, tests/test_pipeline.py]
regression_tier: 2
last_modified: 2026-09-25
notes: Single-table extension of canonical memories (memory_type/importance/last_used_at/expires_at/metadata_json); no new DB. Explicit commands via shared parser (orchestrator pre-reminder + core pre-gating); profiles/aliases/reminders/commands keep owners via guards. Laya data-only tool maps, zero logic coupling. Session TTL store in-process; async extraction daemon; values never logged.

### Feature: Active Container Follow-up (Workflow Lock Continuity)

```yaml
feature_id: conversation.active_container_followup
name: Active Container Follow-up (Workflow Lock Continuity)
description: Deictic follow-up ("usme report file kholo") is interpreted inside the active app/site container instead of being re-classified from scratch.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.dialog_manager
file_path:
  - core/dialog_manager.py
  - core/app.py
entrypoint:
  - core.dialog_manager.DialogManager.process_container_followup_turn
  - core.dialog_manager.DialogManager.is_container_followup
  - core.app.JarvisCore._process_input
intents: [active_container_followup, open_in_active_container]
aliases:
  - "Excel open karo -> usme report file kholo"
  - "Chrome open karo -> usme youtube kholo"
  - "vlc open karo -> usme inception chalao"
  - "Explorer open karo -> usme downloads kholo"
dependencies:
  - core.context.ActiveTargetContext
  - core.dialog_manager.DialogManager.resolve_file
  - core.dialog_manager.WorkflowLock
events_published: []
events_consumed: []
permissions: [EXECUTE, READ]
confirmation_required: false
test_paths:
  - tests/test_active_container_followup.py
regression_tier: 3
last_modified: 2026-09-26
notes: Extends the EXISTING DialogManager workflow lock; no new manager/module created. Reads ActiveTargetContext (SSOT) for the active container and reuses resolve_file + set_lock/process_locked_turn for slot filling. Narrowly guarded (leading usme/isme + an open/action verb + an active container) so bare commands and existing multi-turn desktop-task continuations are untouched. Defect fixed: pronoun-led utterances were hijacked as literal filesystem paths ("Path 'usme report' does not exist."). Document/media containers reuse windows.launch_app / vlc.play_file; browser/site containers reuse browser.open_website.
```

### Feature: Whole-Project Test Progress Runner

```yaml
feature_id: testing.full_project_progress_runner
name: Whole-Project Test Progress Runner
description: Runs the entire pytest suite and displays only a live progress percentage, with full verbose detail written to logs.
domain: testing
status: active
risk_tier: LOW
owner_module: scripts.full_test_progress
file_path:
  - scripts/full_test_progress.py
entrypoint:
  - scripts.full_test_progress.main
intents: []
aliases:
  - "python scripts/full_test_progress.py"
  - "python scripts/full_test_progress.py --background"
  - "python scripts/full_test_progress.py --status"
dependencies:
  - pytest
events_published: []
events_consumed: []
permissions: [READ]
confirmation_required: false
test_paths: []
regression_tier: 0
last_modified: 2026-09-26
notes: Operator tooling, not runtime code. In-process pytest plugin (no new dependency installed; pytest 9.1.1 with no xdist/timeout/json plugins) prints ONE updating percentage line; pytest's own verbose output is redirected to logs/full_test_<ts>.log. Writes logs/test_progress.txt (watchable one-liner), logs/test_progress.json and logs/full_test_summary.json (state/percent/counts/failures/exit_code). --background detaches the run; --status reports progress at any time. Exit code equals the failure count. Baseline: 3397 tests collected across tests/.
```

### Feature: Laya Context Resolution (Deictic Pronoun to Active Container)

```yaml
feature_id: laya.context_resolution
name: Laya Context Resolution (Deictic Pronoun to Active Container)
description: In Laya's Understand stage, a deictic pronoun ("usme report kholo") binds to the live container from ActiveTargetContext instead of being re-guessed as a new target.
domain: core
status: active
risk_tier: MEDIUM
owner_module: core.laya.intelligence
owner_class: LayaIntelligence._resolve_context
file_path:
  - core/laya/intelligence.py
  - core/context.py
entrypoint:
  - core.laya.intelligence.LayaIntelligence.decide
  - core.laya.intelligence.LayaIntelligence._resolve_context
intents: [open_in_active_container]
aliases:
  - "Excel kholo -> usme report kholo"
  - "Chrome kholo -> usme youtube kholo"
  - "isme X kholo"
dependencies:
  - core.context.ActiveTargetContext
events_published: []
events_consumed: []
permissions: [READ]
confirmation_required: false
test_paths:
  - tests/test_laya_core_orchestration.py
  - tests/test_active_container_followup.py
regression_tier: 3
last_modified: 2026-09-26
notes: Fixes dead code in the UNDERSTAND-3 Context Resolution stage. The stage existed but its write was gated by "not dec.entities.get('target')", which is always False in practice because the semantic parsers pre-populate target/site with the pronoun-inclusive phrase (target='usme report'), so the pronoun was never stripped and the container was never attached. Now a pronoun-prefixed target/site is recognised as a parse artifact and overwritten, and the live container is recorded on the decision (entities.container/container_type + context_updates.pronoun_stripped/active_container). The branch only fires on a pronoun-led target and a live container, so bare commands (Chrome kholo, volume 30 karo) are untouched. Container preference order is application -> website -> last_entity -> last_media_title.
```
\
### laya.tri_bridge_dispatchers
`yaml
feature_id: laya.tri_bridge_dispatchers
name: Laya Core Tri-Bridge Authoritative Dispatchers
owner_module: core.app
status: active
risk_tier: LOW
file_path:
  - core/app.py
  - core/execution/fast_path.py
  - core/interaction_gate.py
entrypoint:
  - core.app.JarvisCore._dispatch_fast_route
  - core.app.JarvisCore._dispatch_chat_route
  - core.app.JarvisCore._dispatch_agent_route
intents: [fast_path, chat, agent_goal]
aliases: []
dependencies:
  - core.laya.intelligence.LayaCore
  - core.execution.fast_path.FastPathEngine
  - learning.learner.LearningManager
  - core.alias_manager.CustomAliasManager
events_published:
  - response.completed
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_perfect_architecture_integration.py
  - tests/test_laya_core_orchestration.py
regression_tier: 1
last_modified: 2026-09-26
notes: Eliminates the monolithic waterfall in core/app.py by providing 3 dedicated, authoritative execution dispatchers (_dispatch_fast_route for <15ms deterministic commands with Laya verification; _dispatch_chat_route for scoped conversational dialogue and memory retrieval; _dispatch_agent_route for autonomous goal decomposition and execution tracing). Integrates FastPath with dynamic LearningManager vocabulary resolution, user preferences, and CustomAliasManager lookups. Enhances InteractionGate with multimodal attention confidence scoring.
```

### desktop.apps.antigravity_ide
```yaml
feature_id: desktop.apps.antigravity_ide
name: Dedicated Antigravity IDE Application Launcher & Resolution
owner_module: core.apps
status: active
risk_tier: LOW
file_path:
  - core/apps/aliases.py
  - core/apps/registry.py
  - plugins/windows/plugin.py
  - core/natural_responses.py
entrypoint:
  - core.apps.registry.ApplicationRegistry
  - core.apps.detector.InstalledAppDetector
intents: [OPEN_APP]
aliases:
  - antigravity ide
  - anti gravity ide
  - antigravity id
  - anti gravity id
  - google antigravity ide
  - antigravity ide app
dependencies:
  - core.apps.detector.InstalledAppDetector
  - plugins.windows.plugin.WindowsPlugin
events_published:
  - APPLICATION_OPENED
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_antigravity_app_website_resolution.py
  - tests/test_universal_nlu_and_anti_guessing.py
  - tests/test_universal_window_resolver.py
regression_tier: 1
last_modified: 2026-09-27
notes: Decouples Antigravity IDE (Antigravity IDE.exe / shortcut) from standard Antigravity app (Antigravity.exe) and the web alias (antigravity.google.com). Treats 'ide', 'editor', and 'compiler' as explicit software entities, bypassing false-positive APP_WEB_DISAMBIGUATION and launching Antigravity IDE cleanly.
```

### conversation.multi_workflow_runtime_state
```yaml
feature_id: conversation.multi_workflow_runtime_state
name: Multi-Workflow Runtime State & State Machine Layer
owner_module: core.dialog_manager
status: active
risk_tier: MEDIUM
file_path:
  - core/dialog_manager.py
  - core/pipeline/input_pipeline.py
entrypoint:
  - core.dialog_manager.DialogManager
  - core.dialog_manager.WorkflowLock
  - core.dialog_manager.WorkflowState
intents: [MULTI_TURN_DIALOG, WORKFLOW_QUERY, WORKFLOW_RESUME]
aliases:
  - kaunse kaam pending hain
  - kya pending hai
  - pehla kya hai
  - ab email continue karo
  - wahi continue karo
  - backup chhod do pehle email continue karo
dependencies:
  - core.dialog_manager.DialogManager
  - core.dialog_manager.WorkflowLock
  - core.pipeline.input_pipeline.InputPipeline
events_published:
  - workflow.state.transitioned
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_multi_workflow_runtime_state.py
regression_tier: 1
last_modified: 2026-09-27
notes: Implements Step 1 of the Conversation & Workflow Benchmark. Features authoritative WorkflowState finite state machine tracking across 12 lifecycle states (IDLE, UNDERSTANDING, WAITING_FOR_SLOT, PLANNING, EXECUTING, WAITING_FOR_CONFIRMATION, VERIFYING, COMPLETED, SUSPENDED, CANCELLED, FAILED, RECOVERING). Backwards-compatible LIFO workflow stack and suspended pool in DialogManager allowing nested interruptions (email -> weather -> backup -> excel) with seamless multi-workflow resumption by index, type, or recipient, natural pending inquiries ('Mere kaunse kaam pending hain?'), slot-level status breakdowns ('Rahul ko draft mail: subject set hai, body pending hai'), and explicit resume commands.
```

### Feature: `conversation.slot_reference_and_self_correction`
```yaml
feature_id: conversation.slot_reference_and_self_correction
name: Intra-Utterance Self-Repair, Candidate Disambiguation & Deictic Foregrounding
file_path:
  - core/speech_repair.py
  - core/dialog_manager.py
  - core/reference_resolver.py
  - core/target_engine.py
  - core/semantic/parsers/windows.py
entrypoint:
  - core.speech_repair.SpeechRepairEngine
  - core.dialog_manager.DialogManager
  - core.reference_resolver.ReferenceResolver
  - core.target_engine.UniversalTargetDiscoveryEngine
intents: [SPEECH_REPAIR, EXCEL_OPEN, OPEN_IN_ACTIVE_CONTAINER, WINDOW_FOCUS, DEICTIC_REFERENCE]
aliases:
  - "Rahul ko... nahi Rohit ko message bhejo"
  - "Chrome mat kholo, Brave kholo"
  - "5 baje meeting rakho... sorry 6 baje"
  - "Pune ka weather batao... sorry Mumbai ka"
  - "Volume 50 karo... actually 30"
  - "Folder delete karo... are nahi cancel"
  - "nayi wali"
  - "pehli wali"
  - "doosri wali"
  - "purani wali"
  - "usko foreground mein lao"
dependencies:
  - core.speech_repair.SpeechRepairEngine
  - core.dialog_manager.DialogManager
  - core.reference_resolver.ReferenceResolver
  - core.target_engine.UniversalTargetDiscoveryEngine
events_published: []
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_slot_reference_and_self_correction.py
regression_tier: 1
last_modified: 2026-09-27
notes: Implements Step 2 (State Machine transitions) & Step 3 (Slot / Reference Resolution & Intra-Utterance Self-Correction) of the Conversation & Workflow Benchmark. Features (1) Authoritative intra-utterance self-repair in SpeechRepairEngine handling false starts, negation contrast ('Chrome mat kholo, Brave kholo'), slot corrections ('Pune ka... sorry Mumbai ka', '5 baje... sorry 6 baje', 'Volume 50... actually 30'), and mid-utterance aborts ('Folder delete... are nahi cancel'); (2) Candidate options disambiguation in DialogManager supporting ordinals ('pehli wali', 'doosri wali', 'last') and recency ('nayi wali', 'purani wali') without false-positive blank workbook creation or premature cancellation; (3) Mid-workflow slot correction continuity appending next required question prompts; (4) Deictic foreground resolution in ReferenceResolver ('Usko foreground mein lao') and TargetEngine window focus execution.
```

### Feature: `voice.pipeline_performance`
```yaml
feature_id: voice.pipeline_performance
name: Fast Voice Recognition & In-Memory Response Acceleration
description: Concurrent multi-language STT, low-latency conversational endpointing, and pre-warmed zero-persistence audio caching
domain: core
status: active
risk_tier: LOW

owner_module: voice
file_path:
  - gui/views/chat_view.py
  - voice/tts.py
  - voice/listener.py
entrypoint:
  - gui.views.chat_view.VoiceListenThread
  - voice.tts.TextToSpeech
  - voice.listener.VoiceListener
intents: []
aliases: []
dependencies:
  - concurrent.futures.ThreadPoolExecutor
  - speech_recognition.Recognizer
  - edge_tts
events_published: []
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_standalone_wake_echo_prevention.py
  - tests/test_authoritative_interaction_gate.py
  - tests/test_barge_in.py
  - tests/test_gui.py
regression_tier: 1
last_modified: 2026-10-01
notes: Comprehensive latency overhaul across the voice perception and speech generation pipeline. (1) Parallel concurrent STT executor simultaneously querying Google ASR with en-IN and hi-IN with 2.5s socket timeout, returning whichever language resolves first and eliminating up to 4s of sequential network timeout cascades; (2) Tightened conversational VAD endpointing from 0.75s to 0.40s and eliminated arbitrary 0.3s sleep in GUI listener thread; (3) Zero-disk in-memory pre-synthesis of high-frequency affirmative phrases (Yes I'm listening, Theek hai Sir) in TextToSpeech.warmup() dropping speech latency from 890ms to 0.0ms; (4) 2.5s Edge TTS network timeout with instant local SAPI5 fallback.
```

### Feature: `core.command_safety_guard`
```yaml
feature_id: core.command_safety_guard
name: Multi-Layer Command & Proactive Suggestion Isolation Guard
description: Three-tier defensive protection preventing natural action commands (e.g., 'YouTube open karo') from being misclassified as affirmations/cancellations or hijacking pending background proactive suggestions and system confirmation states.
domain: core
status: active
risk_tier: LOW

owner_module: core.confirmation
file_path:
  - core/confirmation.py
  - core/intelligence/executor.py
  - core/pipeline/input_pipeline.py
entrypoint:
  - core.confirmation.is_affirmation
  - core.confirmation.is_cancellation
  - core.confirmation.classify_confirmation
  - core.intelligence.executor.ProactiveActionExecutor.handle_user_utterance
  - core.pipeline.input_pipeline.InputPipeline.process
intents: [OPEN_APP, SYSTEM_CONFIRMATION_RESPONSE, PROACTIVE_SUGGESTION_RESPONSE]
aliases:
  - "YouTube open karo"
  - "Chrome open karo"
  - "Excel open karo"
dependencies:
  - core.confirmation
  - core.intelligence.executor
  - core.pipeline.input_pipeline
events_published: []
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_action_command_suggestion_safety.py
  - tests/test_confirmation_manager.py
  - tests/test_proactive_executor.py
regression_tier: 1
last_modified: 2026-10-01
notes: Solves speech recognition action command hijacking where full commands ending in action verbs (e.g., 'open karo', 'kholo') were matching unanchored regex patterns in affirmation/cancellation detection, inadvertently confirming pending background proactive suggestions (e.g., Python suggestion triggering upon 'YouTube open karo') or pending dangerous system prompts. Introduces anchored conversational prefix matching, short-token limits (<=3 tokens) with question and verb guards, proactive target entity contradiction guards, and explicit ACTION_COMMAND conflict dismissal in InputPipeline.
```

---

```yaml
feature_id: voice.media_ducker
name: Intelligent System Media Volume Ducker and Audio Playback Coordinator
description: Automatically attenuates active Windows media sessions (YouTube, Spotify, VLC, Netflix, Chrome, Brave, Edge, etc.) to 15% during voice interaction and Jarvis spoken replies, then smoothly restores original volume. Protects Bluetooth earbuds from ENC flatline disconnect and prevents noise-floor runaway during media playback.
domain: voice
status: active
risk_tier: LOW

owner_module: voice.media_ducker
file_path:
  - voice/media_ducker.py
  - voice/stt.py
  - voice/tts.py
  - voice/listener.py
  - gui/views/chat_view.py
entrypoint:
  - voice.media_ducker.MediaDucker.get_instance
  - voice.media_ducker.MediaDucker.duck
  - voice.media_ducker.MediaDucker.unduck
  - voice.media_ducker.MediaDucker.is_media_playing
intents: []
aliases:
  - "media ducking"
  - "youtube volume ducking"
  - "voice clarity during music"
  - "earbuds voice capture"
dependencies:
  - pycaw.pycaw
  - voice.listener.VoiceListener
  - voice.stt.AdaptiveNoiseGate
  - voice.tts.TextToSpeech
  - gui.views.chat_view.VoiceListenThread
events_published: []
events_consumed: []
permissions: [READ, EXECUTE]
confirmation_required: false
test_paths:
  - tests/test_media_ducker.py
  - tests/test_persistent_voice_stream.py
  - tests/test_bluetooth_earbuds_live_routing.py
regression_tier: 1
last_modified: 2026-10-01
notes: Resolves the issue where Jarvis becomes deaf when YouTube or music is playing on the system. Clamps AdaptiveNoiseGate max_noise_floor to 48.0 RMS so continuous media playback does not escalate the threshold above conversational human speech (30-70 RMS). Protects Bluetooth TWS earbuds (CMF Buds 2) with hardware ENC digital zero silence from being misidentified as dead hardware. Dynamically detects audio-producing browser sessions (Brave, Chrome, Edge, Firefox, etc.) and media players, ducks their Windows session volume to 15% upon speech start / active listening / TTS playback, and restores them accurately to original levels upon turn completion.
```

```yaml
feature_id: conversation.self_intent_semantics
name: Semantic Self-Intent Understanding (Assistant Identity & About-Self)
owner_module: core.semantic.self_intents
status: active
risk_tier: LOW
file_path:
  - core/semantic/self_intents.py
  - core/app.py
  - core/pipeline/input_pipeline.py
entrypoint:
  - core.semantic.self_intents.detect_self_intent
  - core.semantic.self_intents.get_self_response
  - core.app.JarvisCore._handle_identity_query
intents: [ASSISTANT_IDENTITY, ASSISTANT_CREATOR_ORIGIN, ASSISTANT_CAPABILITIES, ASSISTANT_STATUS, ASSISTANT_GREETING, ASSISTANT_HELP, ASSISTANT_MEMORY, ASSISTANT_LANGUAGE, ASSISTANT_OFFLINE, ASSISTANT_TECHNOLOGY]
aliases:
  - "aap ka naam kya hai?"
  - "tum ko kisne banaya?"
  - "who create you?"
  - "tum kya kar sakte ho?"
  - "tum kaise ho?"
dependencies: [core.semantic.normalizer.HinglishNormalizer, core.conversational_intent.ConversationalIntentClassifier]
test_paths: [tests/test_self_intent_semantics.py, tests/test_identity_queries.py]
regression_tier: 2
last_modified: 2026-10-07
notes: Single authoritative owner for ASSISTANT_* semantic intents; layered normalize -> phrase -> pattern/topic -> guarded fuzzy -> token-overlap -> context -> self-knowledge response. Reuses HinglishNormalizer shorthand/STT handling and the existing CAPABILITY_GENERAL_RESP wording. Greetings are detected but deferred to the existing greeting flow; user-profile ("mera naam kya hai"), GK inventor ("Computer kisne banaya"), commands, model queries and capability-specific targets always defer. Creator info is never hallucinated. 1000-utterance paraphrase dataset (100 per intent) at 100% mapping accuracy.
```

