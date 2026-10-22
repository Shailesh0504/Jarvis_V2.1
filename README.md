# 🤖 JARVIS V2.1 — Autonomous Cognitive Desktop AI Assistant

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?logo=windows&logoColor=white)](https://microsoft.com)
[![UI Framework](https://img.shields.io/badge/UI-PySide6%20%28Qt6%29-41CD52.svg?logo=qt&logoColor=white)](https://pypi.org/project/PySide6/)
[![Offline First](https://img.shields.io/badge/Architecture-Offline--First%20%26%20Local-orange.svg)]()
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

> **Jarvis V2.1** is a high-performance, offline-first, autonomous desktop AI assistant engineered for Windows. Powered by a decoupled Pub/Sub EventBus, an 8-stage multilingual NLU pipeline, multi-tier cognitive memory, biometric face authentication, proactive habit learning, and 35+ domain automation plugins.

---

## Conversation and personal memory

Jarvis can remember explicit personal details in its existing local memory and
recall them after a restart. Try these in the chat or CLI:

| Say | Behavior |
|---|---|
| `mera naam Rahul hai` | Saves your name after verifying the write. |
| `main Pune mein rehta hoon` | Remembers your city. |
| `mujhe coding pasand hai` | Remembers your stated interest. |
| `mera project Atlas hai` | Remembers the current project. |
| `nahi, mera project Orion hai` | Replaces that project's saved value. |
| `mere baare mein kya yaad hai` | Recalls supported personal facts you provided. |
| `aaj mera mood kharab hai`, then `bas suno` | Continues a listening conversation. |
| `solution do` | Switches that conversation to practical suggestions. |
| `kal subah 8 baje papa ko call karne ka reminder laga do` | Uses the existing reminder scheduler. |

Greetings can ask about a saved project, with a 30-minute cooldown per session.
This is a conversational callback; timed reminders use the reminder plugin and
require its scheduler to be running. Feelings in the listening flow are temporary
dialogue context, not profile facts (existing conversation-history storage still
applies). Unsupported phrasing may need clarification.

The default `brain.llm_provider: mock` remains an offline, rule-based engine;
it does not provide unrestricted human-level understanding. A configured chat
provider receives up to six prior conversation exchanges and the shared persona.
Provider failures keep the local fallback available. No new provider is enabled
and no model or dependency download is required for these improvements.

## 📑 Documentation Index

| Document | Purpose |
|---|---|
| [**`README.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/README.md) | **Project guide, setup, usage instructions, & CLI/GUI execution** |
| [**`AGENTS.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/AGENTS.md) | **Operating rules, collision prevention, & regression playbooks for AI agents** |
| [**`ARCHITECTURE.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/ARCHITECTURE.md) | **Subsystem architecture, data flows, state machines, & storage schemas** |
| [**`FEATURES.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/FEATURES.md) | **Authoritative registry of all implemented features, intents, and risk tiers** |
| [**`ROADMAP.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/ROADMAP.md) | **Strategic roadmap for upcoming versions (v2.2, v2.5, v3.0)** |
| [**`CHANGELOG.md`**](file:///c:/Users/Admin/Documents/Jarvis_V2.1/CHANGELOG.md) | **Version history, feature additions, fixes, and release notes** |

---

## 🌟 Key Highlights & Capabilities

- 🗣️ **Multilingual Perception**: Natural voice recognition and command execution across **English, Hindi, and Hinglish** (*"Chrome kholo aur usme YouTube play karo"*).
- 🔒 **Biometric Security Gate**: Local OpenCV facial authentication gating sensitive operations, with master PIN fallback.
- ⚡ **Universal Action Verifier**: Guarantees truthful execution reporting — verifies window handles, browser URLs, and process states before confirming completion.
- 🧠 **Multi-Tier Cognitive Memory**: Working, Short-Term, Episodic, Semantic, Procedural, and Activity memory backed by SQLite WAL.
- 👁️ **Proactive Intelligence**: Non-intrusive background observer tracking active apps and mining recurring habits without external tracking.
- 🖥️ **Windows 11 Native Integration**: Comprehensive application resolver supporting UWP protocols (`microsoft.windows.camera:`), Start Menu executables, and shell tools.
- 🎨 **Modern Cyber-Dark GUI**: 9 integrated PySide6 views (Dashboard, Chat, Plugins, Memory, Learning, Workflows, Reminders, Activity Logs, Settings).
- 🔄 **In-Process Live Reload**: Hot-reloads modified plugins and modules without abruptly crashing or closing the GUI.

---

## 🛠️ System Prerequisites

- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Python**: Version 3.10, 3.11, or 3.12.
- **Audio Hardware**: Working microphone and speakers / headphones.
- **Webcam**: Required for biometric facial authentication (optional; can be bypassed with `--no-auth`).

---

## 🚀 Quick Start & Installation

### 1. One-Step Automated Setup (Recommended on Any PC)
Simply run the setup orchestrator from the project directory:
```powershell
python setup.py
```
This automatically verifies Python, sets up required directories, installs all dependencies from `requirements.txt`, initializes the SQLite database schema, generates portable Windows launchers (`run_jarvis.bat`), and executes a full diagnostic self-test.

### 2. Manual Installation Alternative
```powershell
# Create & activate virtual environment:
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies:
pip install --upgrade pip
pip install -r requirements.txt
```

---


## ⚙️ Configuration (`config.yaml`)

Jarvis is configured via [`config.yaml`](file:///c:/Users/Admin/Documents/Jarvis_V2.1/config.yaml):

```yaml
system:
  name: JARVIS
  version: 2.0.0
  log_level: INFO
  wake_words: ["jarvis", "hey jarvis", "ok jarvis"]

voice:
  enabled: true
  stt_engine: mock           # "mock" for dev/testing, "speech_recognition" for microphone
  tts_engine: native         # "native" (Edge-TTS) with fallback to pyttsx3/SAPI5
  voice_name: hi-IN-SwaraNeural

security:
  face_auth:
    enabled: true            # Set false or launch with --no-auth to skip
    camera_index: 0
    allow_passcode_fallback: true
    master_pin: '1234'

memory:
  db_path: data/jarvis.db

proactive_intelligence:
  enabled: true
  observer:
    poll_interval_sec: 2.0
```

---

## 💻 How to Run Jarvis

### 1. Modern Desktop GUI (Default)
Launches the full cyber-dark graphical interface with real-time dashboard telemetry, chat window, plugin manager, and memory inspector:
```powershell
python main.py
```

### 2. Interactive CLI Mode
Launches a terminal-based conversational loop:
```powershell
python main.py --cli
```

### 3. Headless Single Query
Executes a single voice/text command from the terminal or external scripts and exits:
```powershell
python main.py --query "open chrome"
python main.py --query "system volume 50"
```

### 4. Bypass Biometric Authentication (Dev / Debug Mode)
Skips the camera facial verification gate for instant startup:
```powershell
python main.py --no-auth
python main.py --cli --no-auth
```

### 5. Enroll User Biometric Face Profile
Captures and registers your face for startup authentication:
```powershell
python main.py --enroll-face
```

### 6. Live Hot-Reloading Mode
Enables in-process live auto-reloading when modifying plugin or python source files:
```powershell
python main.py --reload
```

---

## 🗣️ Common Voice & Text Commands

Jarvis understands commands in English, Hindi, and Hinglish interchangeably:

| Category | Sample Commands |
|---|---|
| **App Control** | *"Open Chrome"*, *"Camera chalao"*, *"Calculator khol do"*, *"Notepad close karo"* |
| **Multi-Entity** | *"Chrome kholo aur usme YouTube play karo"*, *"Open VS Code and Spotify"* |
| **Web & Media** | *"Play Lo-Fi music on YouTube"*, *"Brave me Google open karo"*, *"Pause video"* |
| **System & Audio** | *"Mute system"*, *"Volume 70 percent karo"*, *"Take screenshot"*, *"Lock computer"* |
| **Safety Actions** | *"Restart system"* $\rightarrow$ *Requires confirmation ("Haan restart karo")* |
| **Productivity** | *"Add reminder call Rahul at 5 PM"*, *"Show my schedule"*, *"Summarize document"* |
| **Conversational** | *"Who are you?"*, *"Jarvis tum kya-kya kar sakte ho?"*, *"Good morning"* |

---

## 🧪 Running Tests & Quality Verification

Jarvis includes a comprehensive automated test suite built with `pytest`:

```powershell
# Run the complete test suite
pytest tests/ -v

# Run specific scoped test suites
pytest tests/test_windows_app_resolver.py -v
pytest tests/test_multi_entity_commands.py -v
pytest tests/test_universal_verification_layer.py -v
pytest tests/test_proactive_system_integration.py -v
```

---

## 📁 Repository Directory Structure

```text
Jarvis_V2.1/
├── AGENTS.md                  # AI agent engineering rules & playbooks
├── AGENT_LOG.md               # Session continuity log
├── README.md                  # Main project guide (this document)
├── main.py                    # Main system entry point
├── config.yaml                # Central system configuration
├── requirements.txt           # Python dependency specifications
│
├── docs/                      # Comprehensive technical documentation
│   ├── AGENT_ARCHITECTURE.md  # Agent layer specification
│   ├── ARCHITECTURE.md        # System architecture specification
│   ├── CHANGELOG.md           # Version release changelog
│   ├── FEATURES.md            # 5000+ feature inventory & registry
│   ├── ROADMAP.md             # Strategic future milestones
│   ├── DEVELOPMENT.md         # Developer setup & guidelines
│   ├── TESTING.md             # Test strategy & test suites
│   └── TROUBLESHOOTING.md     # Diagnostics & troubleshooting
│
├── brain/                     # Conversational intelligence & LLM routing
│   ├── classifier.py          # Intent classification
│   ├── llm.py                 # LLM provider abstractions
│   ├── response.py            # Natural response generation
│   └── spelling_resolver.py   # Typo and phonetic correction
│
├── core/                      # Operating system core & execution engine
│   ├── app.py                 # JarvisCore central orchestrator
│   ├── event_bus.py           # Pub/Sub messaging EventBus
│   ├── apps/                  # Windows app resolution & registry
│   ├── confirmation/          # Safety confirmation state machine
│   ├── execution/             # Verification and execution strategies
│   └── reloader.py            # In-process live update manager
│
├── gui/                       # PySide6 desktop user interface
│   ├── views/                 # 9 specialized UI views
│   └── styles.py              # Cyber-dark theme tokens
│
├── memory/                    # Multi-tier cognitive memory
│   ├── database.py            # SQLite WAL database manager
│   ├── memory_manager.py      # Working, episodic, & semantic memory
│   └── context.py             # Active target & session context
│
├── plugins/                   # 35+ modular domain plugins
│   ├── manager.py             # Lazy loading & manifest verification
│   ├── windows/               # Windows OS window management
│   ├── media/                 # YouTube, audio, media players
│   └── ...                    # Productivity, communication, utilities
│
├── proactive/                 # Proactive intelligence & observer
│   ├── observer.py            # Background window & activity polling
│   └── pattern_engine.py      # Habit and frequency mining
│
├── security/                  # Biometrics & permission guardrails
│   └── face_authenticator.py  # OpenCV face verification
│
├── tests/                     # Automated test suites
└── voice/                     # STT, TTS, & Wake word engines
```

---

## 📄 License

Proprietary — Developed for autonomous personal desktop productivity. All rights reserved.
