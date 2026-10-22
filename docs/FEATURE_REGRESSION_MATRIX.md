# Jarvis Feature Regression Matrix

This matrix maps all core system capabilities, baseline functionality verification, refactoring status, and verification test suites.

| Feature Category | Specific Capability | Existing Status | Refactored Status | Dedicated Test Suite | Baseline Verification |
|---|---|---|---|---|---|
| **Voice & Perception** | Wake-Word Detection (Standalone / Position-Independent) | YES | PRESERVED | `tests/test_wake_word_position_independent.py` | PASS |
| **Voice & Perception** | Continuous Microphone Streaming & VAD | YES | PRESERVED | `tests/test_speech_understanding.py` | PASS |
| **Voice & Perception** | Audio Hardware Device Management (Earbuds / Dynamic Routing) | YES | PRESERVED | `tests/test_bluetooth_earbuds_live_routing.py` | PASS |
| **Voice & Perception** | Low-Latency Text-to-Speech (Zero Disk Leakage, In-Memory) | YES | PRESERVED | `tests/test_conversational_response_policy.py` | PASS |
| **Voice & Perception** | Speech Barge-In Interruption Handling (<20ms cutoff) | YES | PRESERVED | `tests/test_speech_understanding.py` | PASS |
| **Natural Language** | Hinglish / Multilingual Speech Normalization | YES | PRESERVED | `tests/test_natural_language_context_upgrade.py` | PASS |
| **Natural Language** | Early-Stage Typo & Misrecognition Repair | YES | PRESERVED | `tests/test_speech_repair_and_window_recovery.py` | PASS |
| **Natural Language** | Speech-Act Classification (Capability vs Action vs Status) | YES | PRESERVED | `tests/test_conversational_intent_speech_act.py` | PASS |
| **Natural Language** | Dialogue Act Classification (21 dialogue acts) | YES | PRESERVED | `tests/test_conversation_redesign.py` | PASS |
| **Natural Language** | Human Conversation Model (7-Dimensional Analysis) | YES | PRESERVED | `tests/test_human_conversation_model.py` | PASS |
| **Natural Language** | Multi-Entity & Conjunction Command Parsing | YES | PRESERVED | `tests/test_multi_entity_commands.py` | PASS |
| **Context & State** | Active Target & Workflow Lock (Rule 15) | YES | PRESERVED | `tests/test_natural_responses_and_workflow_lock.py` | PASS |
| **Context & State** | Deictic Pronoun Resolution ("yah window", "isko", "ise") | YES | PRESERVED | `tests/test_universal_window_resolver.py` | PASS |
| **Context & State** | Conversational Topic Tracking & Multi-Turn State | YES | PRESERVED | `tests/test_conversation_redesign.py` | PASS |
| **Desktop Automation** | Universal Window Discovery & Dynamic Scoring | YES | PRESERVED | `tests/test_universal_window_resolver.py` | PASS |
| **Desktop Automation** | Window Operations (Minimize, Maximize, Restore, Close, Focus) | YES | PRESERVED | `tests/test_window_management_architecture.py` | PASS |
| **Desktop Automation** | Windows 11 App Resolution (Win32, UWP protocols, MMC snap-ins) | YES | PRESERVED | `tests/test_windows_app_resolver.py`, `tests/test_windows_11_system_apps.py` | PASS |
| **Desktop Automation** | Screen OCR & Non-Intrusive Visual Text Interaction | YES | PRESERVED | `tests/test_visual_text_interaction.py` | PASS |
| **Browser Control** | Browser Tab Discovery & Targeted Container Closing | YES | PRESERVED | `tests/test_browser_container_activities.py` | PASS |
| **Browser Control** | Browser Preference Learning & Correction | YES | PRESERVED | `tests/test_browser_descriptor_resolution.py` | PASS |
| **Browser Control** | Human-Like Location Queries & Interactive Follow-Up | YES | PRESERVED | `tests/test_browser_status_followup.py` | PASS |
| **Knowledge Engine** | General Knowledge Engine (16 categories, anti-hallucination) | YES | PRESERVED | `tests/test_knowledge_engine.py`, `tests/test_expanded_knowledge_base.py` | PASS |
| **Knowledge Engine** | Enterprise IT & Infrastructure Engine (6-Phase Troubleshooting) | YES | PRESERVED | `tests/test_it_knowledge_engine.py` | PASS |
| **Knowledge Engine** | Calendar & Festival Knowledge Engine (Drik Panchang 2024-2028) | YES | PRESERVED | `tests/test_festival_calendar_engine.py` | PASS |
| **Finance & Trading** | Indian Equity 1-Month Research & Thesis Monitoring | YES | PRESERVED | `tests/test_indian_equity_research_engine.py` | PASS |
| **Finance & Trading** | Multi-Panel Live Options Confluence Analysis (Screen-Only) | YES | PRESERVED | `tests/trading/test_multi_panel_discovery.py` | PASS |
| **Memory & Database** | 4-Tier Memory (Working, Episodic, Semantic, Correction) | YES | PRESERVED | `tests/test_cognitive_memory.py`, `tests/test_experience_learning_system.py` | PASS |
| **Memory & Database** | SQLite Database Persistence & Concurrency (44 tables) | YES | PRESERVED | `tests/test_audited_logic_fixes.py` | PASS |
| **GUI Interface** | PySide6 Cyber-Dark Desktop Interface & Chat Bubbles | YES | PRESERVED | `tests/test_gui.py` | PASS |
| **GUI Interface** | Dynamic Microphone Selector & RMS Diagnostic Worker | YES | PRESERVED | `tests/test_manual_microphone_selection.py` | PASS |
| **GUI Interface** | Modern Reminders & Alarms Pill Badge View | YES | PRESERVED | `tests/test_gui.py` | PASS |
| **Verification Gate** | Universal Action Verification Layer (Post-Action Check) | YES | PRESERVED | `tests/test_universal_verification_layer.py` | PASS |
