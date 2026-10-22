"""Service bootstrapping, infrastructure setup, and dependency wiring for JarvisCore."""

import logging
import os
import threading
from typing import Any, Dict, List, Optional
import yaml

from core.context import SessionContext, TurnContext
from core.conversation import ConversationManager
from core.event_bus import EventBus
from core.executor import PlanExecutor
from core.permissions import PermissionGuard, PermissionLevel
from core.planner import TaskPlanner
from core.interaction_gate import InteractionGate
from core.router import CommandRouter
from core.state import StateMachine, SystemState

logger = logging.getLogger("jarvis.bootstrap")


class ServiceInitializer:
    """Orchestrates the construction and subsystem wiring of JarvisCore."""

    @classmethod
    def load_config(cls, config_path: str) -> Dict[str, Any]:
        """Loads configuration from yaml file with graceful defaults."""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        logger.warning("Config file %s not found. Using defaults.", config_path)
        return {}

    @classmethod
    def init_core_infrastructure(cls, core: Any, config_path: str = "config.yaml") -> None:
        """Initializes all baseline infrastructure components on the JarvisCore instance."""
        core.config_path = config_path
        core.config = cls.load_config(config_path)
        core._pending_sensitive_display = None
        core._pending_news_briefing = None
        core._last_profile_field = None
        core._rejected_fuzzy_candidates = set()
        core._last_spell_ack = None
        core._process_lock = threading.RLock()

        # 1. Core infrastructure
        core.state_machine = StateMachine(SystemState.INITIALIZING)
        core.event_bus = EventBus()
        core.state_machine.register_listener(
            lambda old, new: core.event_bus.emit(
                "system.state.changed",
                {
                    "old_state": old.value if hasattr(old, "value") else str(old),
                    "new_state": new.value if hasattr(new, "value") else str(new),
                }
            )
        )
        from core.logger import StructuredActionLogger
        core.action_logger = StructuredActionLogger()

        # 2. Security & permissions
        default_perm_str = core.config.get("permissions", {}).get("default_level", "EXECUTE")
        default_perm = getattr(PermissionLevel, default_perm_str, PermissionLevel.EXECUTE)
        enforce_perms = core.config.get("permissions", {}).get("enforce_permissions", True)
        core.permission_guard = PermissionGuard(default_level=default_perm, enforce=enforce_perms)

        # 3. Conversation & input processing
        wake_words = core.config.get("system", {}).get("wake_words", ["jarvis", "hey jarvis"])
        core.conversation_manager = ConversationManager(wake_words=wake_words)
        from voice.wake_word import WakeWordDetector, ConversationSessionManager
        core.wake_detector = WakeWordDetector()
        core.session_manager = ConversationSessionManager(session_timeout=15.0)
        core.interaction_gate = InteractionGate(
            wake_detector=core.wake_detector,
            session_timeout=10.0,
            max_session_commands=1,
            barge_in_enabled=True,
        )
        core.tts_manager = None

        # Audio device configuration
        try:
            from voice.device_manager import AudioDeviceManager
            preferred_mic = core.config.get("voice", {}).get("preferred_microphone", "auto")
            AudioDeviceManager().set_manual_device(preferred_mic)
        except Exception as e:
            logger.debug("Failed to initialize preferred audio device: %s", e)

        # Timezone Subsystem
        try:
            from core.timezone_manager import TimezoneManager
            configured_tz = core.config.get("system", {}).get("timezone", "Asia/Kolkata")
            core.timezone_manager = TimezoneManager.get_instance(default_timezone=configured_tz)
            core.timezone_manager.validate_on_startup()
        except Exception as e:
            logger.warning("TimezoneManager startup validation issue: %s", e)

        # 4. Deferred Subsystem references
        core.memory_manager = None
        core.learning_manager = None
        core.brain = None
        core.classifier = None
        core.plugin_manager = None
        core.response_generator = None
        core.agent = None
        core.human_conversation_model = None
        from core.intelligence.confidence import get_confidence_engine
        core.confidence_engine = get_confidence_engine()
        from core.intelligence.answer_verification import get_answer_verifier
        core.answer_verifier = get_answer_verifier()
        from core.intelligence.suggestion_manager import get_suggestion_manager
        core.suggestion_manager = get_suggestion_manager()
        core.self_improvement_engine = None
        core.auth = None

        # 5. Planning & Execution
        core.planner = TaskPlanner(permission_guard=core.permission_guard)
        core.executor = None
        core.desktop_workflows = None
        core.task_engine = None
        core.router = CommandRouter()
        from core.target_engine import UniversalTargetDiscoveryEngine
        from core.context import ActiveTargetContext, RuntimeContext
        core.target_engine = UniversalTargetDiscoveryEngine()
        core.active_context = ActiveTargetContext()
        core.runtime_context = RuntimeContext(
            session=core.conversation_manager.session,
            desktop=core.active_context,
            user=core.conversation_manager.session.user
        )
        from core.decision_core import DecisionCore
        core.decision_core = DecisionCore(
            permission_guard=core.permission_guard,
            target_engine=core.target_engine,
            runtime_context=core.runtime_context
        )

        # 5.1 Conversational Intelligence, State & Multi-Tiered Memory Layer
        from core.dialogue_act import DialogueActClassifier
        from core.conversation_state import ConversationState
        from core.topic_tracker import TopicTracker
        from core.reference_resolver import ReferenceResolver
        from core.memory import (
            WorkingConversationMemory,
            EpisodicConversationMemory,
            SemanticConversationMemory,
            ConversationMemoryRetriever,
        )
        from core.visual_reference import VisualReferenceManager

        core.dialogue_act_classifier = DialogueActClassifier
        core.conversation_state = ConversationState()
        core.topic_tracker = TopicTracker()
        core.reference_resolver = ReferenceResolver
        core.working_conv_memory = WorkingConversationMemory()
        core.episodic_conv_memory = EpisodicConversationMemory()
        core.semantic_conv_memory = SemanticConversationMemory()
        core.memory_retriever = ConversationMemoryRetriever(
            working_memory=core.working_conv_memory,
            episodic_memory=core.episodic_conv_memory,
            semantic_memory=core.semantic_conv_memory
        )
        core.visual_reference_manager = VisualReferenceManager()

        # 5.5 Execution Verification Layer & Multi-Strategy Engine
        from core.execution import (
            ExecutionVerificationLayer,
            ExecutionDiagnosticEngine,
            ExecutionStrategyEngine,
            ExecutionFeedbackHandler,
        )
        core.execution_verifier = ExecutionVerificationLayer(window_manager=core.target_engine.window_manager)
        core.target_engine.set_verifier(core.execution_verifier)
        core.execution_diagnostics = ExecutionDiagnosticEngine(window_manager=core.target_engine.window_manager)
        core.execution_strategies = ExecutionStrategyEngine(
            verifier=core.execution_verifier,
            diagnostics=core.execution_diagnostics,
            experience_system=None
        )
        core.execution_feedback = ExecutionFeedbackHandler(
            strategy_engine=core.execution_strategies,
            diagnostic_engine=core.execution_diagnostics
        )
        core.last_execution_result = None
        core.proactive_coordinator = None
        core.update_manager = None

        # Dialog Manager & Confirmation Manager
        from core.dialog_manager import DialogManager
        from core.confirmation_manager import ConfirmationManager
        core.dialog_manager = DialogManager()
        core.confirmation_manager = getattr(core.dialog_manager, "confirmation_manager", None) or ConfirmationManager()

        # Website Knowledge Store
        from core.website_knowledge import WebsiteKnowledgeStore
        core.website_knowledge = WebsiteKnowledgeStore()
        from plugins.browser.website_resolver import WebsiteResolver
        WebsiteResolver.configure_knowledge_store(core.website_knowledge)

        # Multi-Entity / Multi-Action Command Architecture
        from core.entities.knowledge import get_entity_knowledge_base
        from core.semantic.multi_entity import MultiEntityCommandParser
        from core.execution.multi_executor import MultiActionExecutor
        core.entity_knowledge = get_entity_knowledge_base()
        core.multi_entity_parser = MultiEntityCommandParser(core.entity_knowledge)
        core.multi_action_executor = MultiActionExecutor(
            strategy_engine=core.execution_strategies,
            target_engine=core.target_engine,
            verifier=core.execution_verifier,
            plugin_manager=None,
        )

        from core.execution.fast_path import FastPathEngine
        from core.execution.semantic_executor import SemanticActionExecutor
        from core.response_engine import ResponseEngine
        from core.laya import get_laya_core
        core.response_engine = ResponseEngine.get_instance()
        core.laya_core = get_laya_core()
        core.fast_path = FastPathEngine(core=core)
        core.semantic_executor = SemanticActionExecutor(core=core)

        # 5.6 Production Architecture Hardening & Orchestration Layer
        from core.policy import CapabilityPolicy
        from core.recovery import RecoveryManager
        from core.cancellation import CancellationManager
        from core.models import ModelGateway
        from core.observability import HealthMonitor
        from core.runtime import JarvisRuntime

        core.capability_policy = CapabilityPolicy(permission_guard=core.permission_guard)
        core.recovery_manager = RecoveryManager(max_retries=2)
        core.cancellation_manager = CancellationManager()
        core.health_monitor = HealthMonitor(event_bus=core.event_bus)
        core.model_gateway = ModelGateway()
        core.runtime = JarvisRuntime(
            core_app=core,
            model_gateway=core.model_gateway,
            capability_policy=core.capability_policy,
            recovery_manager=core.recovery_manager,
            cancellation_manager=core.cancellation_manager,
            health_monitor=core.health_monitor,
        )

    @classmethod
    def wire_subsystems(
        cls,
        core: Any,
        memory_manager: Optional[Any] = None,
        learning_manager: Optional[Any] = None,
        brain: Optional[Any] = None,
        classifier: Optional[Any] = None,
        plugin_manager: Optional[Any] = None,
        response_generator: Optional[Any] = None
    ) -> None:
        """Inject or wire subsystems into the core engine."""
        core.memory_manager = memory_manager
        core.learning_manager = learning_manager
        core.brain = brain
        core.classifier = classifier
        core.plugin_manager = plugin_manager
        if core.plugin_manager and not getattr(core.plugin_manager, "event_bus", None):
            core.plugin_manager.event_bus = core.event_bus
        if core.event_bus:
            core.event_bus.subscribe("reminder.triggered", core._on_reminder_triggered)
        core.target_engine.executor.plugin_manager = plugin_manager
        if hasattr(core, "multi_action_executor"):
            core.multi_action_executor.plugin_manager = plugin_manager
        core.response_generator = response_generator

        if core.memory_manager and getattr(core.memory_manager, "db", None):
            from core.website_knowledge import WebsiteKnowledgeStore
            core.website_knowledge = WebsiteKnowledgeStore(core.memory_manager.db.db_path)
            from plugins.browser.website_resolver import WebsiteResolver
            WebsiteResolver.configure_knowledge_store(core.website_knowledge)

        # Conversation Intelligence Engine
        from brain.conversation_engine import ConversationEngine
        llm_inst = getattr(core.brain, "llm", None) if core.brain else None
        core.conversation_engine = ConversationEngine(
            llm_provider=llm_inst,
            memory_manager=core.memory_manager
        )

        # Human Conversation Model
        from brain.conversation.model import HumanConversationModel
        core.human_conversation_model = HumanConversationModel(
            learning_manager=core.learning_manager,
            context_resolver=getattr(core.conversation_engine, "context_resolver", None)
        )

        # Self-Improvement Engine
        from core.intelligence.self_improvement import get_self_improvement_engine
        core.self_improvement_engine = get_self_improvement_engine(
            learning_manager=core.learning_manager,
            db=core.memory_manager.db if core.memory_manager else None
        )

        # Learning Inspector
        try:
            from core.intelligence.learning_inspector import get_learning_inspector
            core._learning_inspector = get_learning_inspector(
                db=core.memory_manager.db if core.memory_manager else None,
                learning_manager=core.learning_manager,
                self_improvement_engine=core.self_improvement_engine,
            )
            logger.info("JarvisCore: LearningInspector initialized.")
        except Exception as _li_exc:
            logger.debug("JarvisCore: LearningInspector init note: %s", _li_exc)
            core._learning_inspector = None

        # Wire authoritative MemoryManager and DB into conversational memory systems
        if core.memory_manager:
            if hasattr(core.memory_manager, "db"):
                core.episodic_conv_memory.db = core.memory_manager.db
                core.semantic_conv_memory.db = core.memory_manager.db
                core.memory_retriever.db = core.memory_manager.db
            core.episodic_conv_memory._manager = core.memory_manager
            core.semantic_conv_memory._manager = core.memory_manager
            core.memory_retriever._manager = core.memory_manager
            core.memory_retriever.episodic = core.episodic_conv_memory
            core.memory_retriever.semantic = core.semantic_conv_memory

        from core.desktop_workflow import DesktopWorkflowCoordinator
        core.desktop_workflows = DesktopWorkflowCoordinator(
            plugin_manager=core.plugin_manager,
            event_bus=core.event_bus,
            learning_manager=core.learning_manager,
        )
        if hasattr(core.desktop_workflows, "task_executor") and core.desktop_workflows.task_executor:
            core.desktop_workflows.task_executor.verifier = core.execution_strategies.verifier
            core.desktop_workflows.task_executor.execution_strategies = core.execution_strategies

        from core.task_engine import TaskContinuityEngine, TaskPersistenceManager
        persistence = TaskPersistenceManager(db_or_path=core.memory_manager.db if core.memory_manager else "data/jarvis.db")
        core.task_engine = TaskContinuityEngine(
            persistence_manager=persistence,
            plugin_manager=core.plugin_manager,
            event_bus=core.event_bus,
            permission_guard=core.permission_guard
        )
        if hasattr(core, "memory_manager") and core.memory_manager and hasattr(core.memory_manager, "working"):
            if hasattr(core, "task_engine") and core.task_engine:
                core.memory_manager.working.bind_task_state(core.task_engine.active_task)

        from core.experience import ExperienceLearningSystem
        db_ref = core.memory_manager.db if core.memory_manager else "data/jarvis.db"
        core.experience_system = ExperienceLearningSystem(db_or_path=db_ref)
        if hasattr(core, "memory_manager") and core.memory_manager and hasattr(core.memory_manager, "experience"):
            core.memory_manager.experience = core.experience_system
        if hasattr(core, "execution_strategies") and core.execution_strategies:
            core.execution_strategies.experience_system = core.experience_system
        if hasattr(core, "learning_manager") and core.learning_manager:
            if not getattr(core.learning_manager, "experience_system", None):
                core.learning_manager.experience_system = core.experience_system
            if not getattr(core.learning_manager, "event_bus", None):
                core.learning_manager.event_bus = core.event_bus

        # Ingest pending mistake log records into Experience Memory
        try:
            if hasattr(core, "experience_system") and core.experience_system:
                digested = core.experience_system.digest_log_mistakes(limit=50)
                if digested:
                    logger.info("JarvisCore: Digested %d previous mistake(s) from log into Experience Memory.", len(digested))
        except Exception as _dig_exc:
            logger.debug("JarvisCore: Startup mistake digestion note: %s", _dig_exc)

        # Detect incomplete workflows on startup
        try:
            if hasattr(core, "task_engine") and core.task_engine:
                recovered = core.task_engine.recover_incomplete_tasks()
                if recovered:
                    logger.info("JarvisCore: Recovered %d incomplete task(s) from checkpoint on startup.", len(recovered))
        except Exception as e:
            logger.warning("JarvisCore: Startup task recovery check encountered an issue: %s", e)

        if core.plugin_manager:
            core.executor = PlanExecutor(
                plugin_manager=core.plugin_manager,
                permission_guard=core.permission_guard,
                event_bus=core.event_bus
            )
            core.router.plugin_manager = core.plugin_manager

            # Autonomous Agent
            from brain.agent import AgentReasoner
            from core.agent import AutonomousAgent
            reasoner = AgentReasoner(
                llm_provider=llm_inst,
                plugin_manager=core.plugin_manager,
                memory_manager=core.memory_manager,
                experience_system=core.experience_system
            )
            core.agent = AutonomousAgent(
                reasoner=reasoner,
                plugin_manager=core.plugin_manager,
                permission_guard=core.permission_guard,
                event_bus=core.event_bus,
                memory_manager=core.memory_manager,
            )

            # Fast Brain + Smart Brain Dual-Brain Engine
            from brain.dual_brain import DualBrain
            core.dual_brain = DualBrain(plugin_manager=core.plugin_manager, llm_provider=llm_inst)

            # Activity Monitor plugin
            act_plugin = core.plugin_manager.get_plugin("activity_monitor")
            if act_plugin and hasattr(act_plugin, "observer"):
                def _sync_activity_to_context(event):
                    if hasattr(core, "active_context") and core.active_context:
                        if getattr(event, "website", None) == "youtube" and getattr(event, "content_title", None):
                            core.active_context.record_media(
                                title=event.content_title,
                                source="youtube",
                                url=getattr(event, "url", "") or ""
                            )
                        elif getattr(event, "application", None):
                            core.active_context.set_application(
                                app_name=event.application,
                                hwnd=getattr(event, "metadata", {}).get("hwnd", 0),
                                title=getattr(event, "metadata", {}).get("raw_title", "")
                            )
                act_plugin.observer.on_activity_callback = _sync_activity_to_context

        if core.memory_manager:
            core.router.memory_manager = core.memory_manager

        # Proactive Intelligence Coordinator
        proactive_cfg = core.config.get("proactive_intelligence", {})
        if proactive_cfg.get("enabled", False):
            try:
                from core.intelligence import ProactiveIntelligenceCoordinator
                speaker_inst = getattr(core, "response_generator", None) or getattr(core, "speaker", None)
                db_inst = getattr(core.memory_manager, "db", None) if core.memory_manager else None
                core.proactive_coordinator = ProactiveIntelligenceCoordinator(
                    db=db_inst,
                    event_bus=core.event_bus,
                    app_core=core,
                    speaker=speaker_inst,
                    config=proactive_cfg
                )
                core.proactive_coordinator.start()
                logger.info("JarvisCore: ProactiveIntelligenceCoordinator initialized and started.")
            except Exception as e:
                logger.warning("JarvisCore: Failed to initialize ProactiveIntelligenceCoordinator: %s", e)

        core.state_machine.transition_to(SystemState.IDLE)
        core.event_bus.emit("core.initialized", {"status": "ready"})

        # LiveUpdateManager
        sys_cfg = core.config.get("system", {})
        if sys_cfg.get("auto_reload", True):
            try:
                from core.update_manager import LiveUpdateManager
                core.update_manager = LiveUpdateManager(core=core)
                core.update_manager.start()
                logger.info("JarvisCore: LiveUpdateManager initialized and started for zero-downtime updates.")
            except Exception as e:
                logger.warning("JarvisCore: Failed to initialize LiveUpdateManager: %s", e)

        # Archify Live Auto-Update Server
        try:
            from plugins.archify.server import get_archify_server
            core.archify_server = get_archify_server()
            core.archify_server.start()
        except Exception as e:
            logger.debug("Archify server start note: %s", e)

        logger.info("Jarvis Core Subsystems successfully initialized.")
