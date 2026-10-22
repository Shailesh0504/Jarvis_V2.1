# JARVIS V2.1 — ARCHITECTURE TO CODE MAP
_Direct 1:1 Mapping between Architecture Diagram Components and Codebase Implementations_

---

## 1. Component to Code Mapping Matrix

| Diagram Component | Architectural Responsibility | Real Source Files | Authoritative Classes & Functions |
|---|---|---|---|
| **Camera / Vision** | Biometric face frame ingestion & low-light detection | `security/face_authenticator.py`<br>`vision/` | `FaceAuthenticator`<br>`FaceAuthenticator.authenticate()` |
| **User Voice / Text** | Audio capture & keyboard CLI/GUI event streams | `voice/voice_listener.py`<br>`main.py` | `VoiceListener`<br>`VoiceListener.listen()` |
| **Jarvis Cyber GUI** | Reactive 9-view HUD, waveform & suggestion chips | `gui/main_window.py`<br>`gui/cyber_hud.py` | `JarvisMainWindow`<br>`CyberHUDWidget` |
| **VoiceListener / STT** | Multilingual offline/cached speech recognition | `voice/stt_engine.py`<br>`voice/speech_recognizer.py` | `STTEngine`<br>`SpeechRecognizerPool` |
| **Interaction Gate** | Fail-closed biometric auth & state machine gating | `core/state.py`<br>`security/interaction_gate.py` | `RequestStateMachine`<br>`InteractionGate.verify_turn()` |
| **Streaming Audio TTS** | In-memory zero-persistence chunked audio playback | `voice/tts.py`<br>`voice/tts_streamer.py` | `TTSStreamer`<br>`TTSStreamer.stream_sentence()` |
| **Fast Command Path** | Sub-10ms deterministic bypass (volume, time, weather) | `core/app.py`<br>`core/fast_path.py` | `JarvisCore._try_fast_command_path()` |
| **Conversation / Context** | Single authoritative runtime context & frame tracking | `core/conversation.py`<br>`core/contracts/contracts.py` | `ConversationManager`<br>`TurnContext`, `ConversationFrame` |
| **TurnOutcome / Status** | Closed-loop status categorization (VERIFIED/UNVERIFIED/FAILED) | `core/contracts/contracts.py`<br>`core/telemetry/outcome_hook.py` | `TurnOutcome`<br>`ExecutionResult` |
| **Response Policy** | Conversational feedback generation (1-sentence limit) | `core/response_policy.py`<br>`core/response_engine.py` | `ConversationalResponsePolicy`<br>`ResponseEngine.render_response()` |
| **Dialog / Workflow Lock** | Multi-turn slot filling & active workflow boundary lock | `core/dialog_manager.py`<br>`core/workflow_lock.py` | `DialogManager`<br>`DialogManager.set_pending_goal()` |
| **Speech-Act / NLU** | Purpose-first gating (CAPABILITY, STATUS, ACTION) | `core/conversational_intent.py`<br>`core/nlu/` | `ConversationalIntentDetector`<br>`HinglishNLUParser` |
| **ExecutionOutcomeHook** | Single-point telemetry emission & learning gating | `core/telemetry/outcome_hook.py` | `ExecutionOutcomeHook`<br>`ExecutionOutcomeHook.on_turn_completed()` |
| **OutcomeAdapter** | Normalization of ActionOutcome and PluginResult | `core/adapters/outcome_adapter.py` | `OutcomeAdapter`<br>`OutcomeAdapter.normalize()` |
| **SemanticActionExecutor** | Primary execution engine for 5 verified handlers | `core/action_executor.py`<br>`core/semantic_executor.py` | `SemanticActionExecutor`<br>`ActionExecutor.execute_action()` |
| **Execution Strategy** | OS execution strategies (Win32, PowerShell, Spawn) | `core/execution_strategy.py` | `ExecutionStrategyEngine`<br>`Win32Strategy`, `ProcessSpawner` |
| **Verification Layer** | Physical OS state confirmation (PID, HWND, URL) | `core/verification_layer.py` | `UniversalVerificationLayer`<br>`UniversalVerificationLayer.verify()` |
| **PluginVerificationBridge**| Physical verification hook for plugin fallback executions | `core/verification_bridge.py` | `PluginVerificationBridge`<br>`PluginVerificationBridge.verify_plugin_result()` |
| **Target Discovery** | Resolution across application, browser, file, and web | `core/targets/target_engine.py`<br>`core/targets/resolver.py` | `UniversalTargetEngine`<br>`UniversalTargetEngine.resolve_target()` |
| **Window Resolver** | HWND, PID, title scoring and activation | `core/window_resolver.py`<br>`core/window_manager.py` | `UniversalWindowResolver`<br>`WindowManager.focus_window()` |
| **Knowledge Engine** | Structured GK facts & 6-phase IT troubleshooting | `core/knowledge/engine.py`<br>`core/knowledge/it/engine.py` | `KnowledgeEngine`<br>`ITKnowledgeEngine.query()` |
| **Command Router** | Legacy plugin dispatcher & fallback command routing | `core/command_router.py` | `CommandRouter`<br>`CommandRouter.dispatch()` |
| **Plugin Manager** | Lazy-loading dynamic registry for 39+ domain plugins | `core/plugin_manager.py` | `PluginManager`<br>`PluginManager.execute_plugin()` |
| **Autonomous Agent** | Multi-step goal decomposition & plan execution | `brain/autonomous_agent.py` | `AutonomousAgent`<br>`AutonomousAgent.plan_and_execute()` |
| **Agent Task Memory** | DAG/graph task representation & step checkpoints | `brain/agent_memory.py` | `AgentTaskMemory`<br>`AgentTaskMemory.save_task_graph()` |
| **Latency Tracker** | Microsecond stage benchmarking (<300ms SLA) | `core/latency.py` | `PipelineLatencyTracker`<br>`PipelineLatencyTracker.mark_first_response()`|
| **Pub/Sub EventBus** | Asynchronous decoupled internal telemetry stream | `core/event_bus.py` | `EventBus`<br>`EventBus.publish()`, `EventBus.subscribe()` |
| **Live Update Manager** | In-process module hot reloading with zero downtime | `core/live_update.py` | `LiveUpdateManager`<br>`LiveUpdateManager.reload_module()` |
| **Activity Observer** | Active window, process, and desktop state poller | `core/observer/activity_observer.py` | `ActivityObserver`<br>`ActivityObserver.poll_active_window()` |
| **Pattern Engine** | User habits, routine detection, and preference mining | `core/proactive/pattern_engine.py` | `PatternEngine`<br>`PatternEngine.detect_routines()` |
| **Continuous Learning** | 5-tier feedback, mistake learning, correction updates | `learning/learning_manager.py`<br>`learning/log_learner.py`| `LearningManager`<br>`LogLearner.extract_mistakes()` |
| **Cognitive Memory** | Canonical SSOT (Working, Episodic, Semantic, Activity) | `core/memory.py`<br>`core/observer/memory/` | `MemoryManager`<br>`ActivityMemoryRepository` |
| **Encrypted SQLite** | Local persistent WAL database (`jarvis.db`) | `data/database.py`<br>`data/storage_engine.py` | `StorageEngine`<br>`DatabaseConnectionPool` |
| **Capability Policy** | Unified risk classification (LOW/MEDIUM/HIGH/CRITICAL) | `core/policy/capability_policy.py` | `CapabilityPolicy`<br>`CapabilityPolicy.evaluate_command()` |
| **Recovery Manager** | Loop-prevented strategy escalation & retry backoff | `core/recovery/manager.py` | `RecoveryManager`<br>`RecoveryManager.decide_recovery()` |
| **Cancellation Manager**| Thread-safe cooperative cancellation & barge-in | `core/cancellation/manager.py` | `CancellationManager`<br>`CancellationToken.cancel()` |
| **Model Gateway** | Local LLM/Embedding/Vision provider routing | `core/models/gateway.py` | `ModelGateway`<br>`LocalLLMProvider`, `LocalEmbeddingProvider`|
| **Health Monitor** | 9-subsystem health diagnostics & degradation tracking | `core/observability/health.py` | `HealthMonitor`<br>`HealthMonitor.run_diagnostics()` |
| **Jarvis Runtime** | Thin 12-stage orchestrator coordinating end-to-end turn | `core/runtime/orchestrator.py` | `JarvisRuntime`<br>`JarvisRuntime.execute_turn()` |

---

## 2. Directory Architecture Reference

```
Jarvis_V2.1/
├── core/
│   ├── app.py                      # JarvisCore top-level façade & turn processor
│   ├── contracts/                  # 17 standardized typed dataclass contracts
│   ├── state.py                    # RequestStateMachine & RequestLifecycleState
│   ├── runtime/                    # JarvisRuntime thin turn lifecycle orchestrator
│   ├── recovery/                   # RecoveryManager & strategy escalation
│   ├── cancellation/               # CancellationManager & CancellationToken
│   ├── policy/                     # CapabilityPolicy & RiskTier rules
│   ├── models/                     # ModelGateway & Local/Fallback adapters
│   ├── observability/              # HealthMonitor & 9-subsystem health checkers
│   ├── conversational_intent.py    # Speech-Act gating & purpose-first classifier
│   ├── knowledge/                  # General Knowledge & IT Knowledge engines
│   ├── dialog_manager.py           # Multi-turn slot filling & workflow locks
│   ├── action_executor.py          # Unified action execution layer
│   ├── verification_layer.py       # UniversalVerificationLayer (closed-loop)
│   ├── verification_bridge.py      # Plugin physical verification bridge
│   ├── window_resolver.py          # UniversalWindowResolver HWND scoring
│   ├── response_policy.py          # Conversational response formatter
│   └── latency.py                  # PipelineLatencyTracker (sub-300ms SLA)
├── brain/                          # AutonomousAgent & AgentTaskMemory
├── learning/                       # 5-Tier LearningManager & LogLearner
├── plugins/                        # 39+ Domain skill plugins
│   └── archify/                    # Live interactive architecture visualizer
├── tests/                          # 200+ unit, integration, and golden regression suites
└── main.py                         # Application bootstrap & CLI entrypoint
```
