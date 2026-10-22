# core/intelligence/coordinator.py
"""
Proactive Intelligence Coordinator for Jarvis V2.
Orchestrates the entire proactive lifecycle: observation, activity memory,
evidence-based pattern mining, opportunistic decision evaluation, suggestion rate-limiting,
conversational action execution, and continuous preference adaptation.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.observer.activity_memory import ActivityMemory
from core.observer.activity_observer import ProactiveActivityObserver
from core.observer.models import ActivityEvent
from .decision_engine import ProactiveDecisionEngine
from .executor import ProactiveActionExecutor
from .models import ProactiveSuggestion, SuggestionState, SuggestionUrgency
from .pattern_engine import PatternLearningEngine
from .preference_learner import AdaptivePreferenceLearner
from .suggestion_manager import SuggestionManager

logger = logging.getLogger("jarvis.core.intelligence.coordinator")


class ProactiveIntelligenceCoordinator:
    """
    Central coordinator orchestrating proactive intelligence subsystems in Jarvis V2.
    Ensures zero-interruption focus protection, evidence-based habit learning,
    conversational confirmations, and verified action execution.
    """

    def __init__(
        self,
        db: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        app_core: Optional[Any] = None,
        speaker: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.db = db
        self.event_bus = event_bus
        self.app_core = app_core
        self.speaker = speaker
        self.config = config or {}

        # 1. Activity & Context Memory (Phase 3)
        max_ram_events = self.config.get("memory_events_limit", 200)
        self.memory = ActivityMemory(db=self.db, max_history=max_ram_events)

        # 2. Activity Observer (Phases 1 & 2)
        obs_interval = self.config.get("poll_interval_sec", 1.0)
        self.observer = ProactiveActivityObserver(
            poll_interval=obs_interval,
            event_bus=self.event_bus,
            memory=self.memory
        )

        # 3. Pattern Learning Engine (Phase 4)
        self.pattern_engine = PatternLearningEngine(db=self.db)

        # 4. Proactive Decision Engine (Phase 5)
        min_conf = self.config.get("min_confidence_threshold", 0.70)
        enable_guard = self.config.get("enable_distraction_guard", True)
        self.decision_engine = ProactiveDecisionEngine(
            pattern_engine=self.pattern_engine,
            memory=self.memory,
            min_confidence=min_conf,
            enable_distraction_guard=enable_guard
        )

        # 5. Suggestion Manager & Cooldowns (Phase 6)
        global_cd = self.config.get("min_suggestion_interval_sec", 900.0)
        self.suggestion_manager = SuggestionManager(
            pattern_engine=self.pattern_engine,
            min_global_cooldown_sec=global_cd
        )

        # 6. Proactive Action Executor (Phase 7)
        self.executor = ProactiveActionExecutor(
            suggestion_manager=self.suggestion_manager,
            app_core=self.app_core,
            speaker=self.speaker
        )

        # 7. Adaptive Preference Learner (Phase 8)
        self.preference_learner = AdaptivePreferenceLearner(
            pattern_engine=self.pattern_engine
        )

        # Wire observer callbacks
        self.observer.add_listener(self._on_activity_observed)

        self._running = False
        self._maintenance_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        """Returns True if the coordinator and observer background threads are running."""
        return self._running

    def start(self) -> None:
        """Starts background observation and maintenance threads."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._stop_event.clear()

            # Start observer thread
            self.observer.start()

            # Start periodic maintenance worker
            self._maintenance_thread = threading.Thread(
                target=self._maintenance_loop,
                name="ProactiveCoordinatorMaintenanceWorker",
                daemon=True
            )
            self._maintenance_thread.start()
            logger.info("ProactiveIntelligenceCoordinator started successfully.")

    def stop(self) -> None:
        """Stops observer and coordinator maintenance threads cleanly."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._stop_event.set()

            self.observer.stop()
            if self._maintenance_thread and self._maintenance_thread.is_alive():
                self._maintenance_thread.join(timeout=2.0)

            logger.info("ProactiveIntelligenceCoordinator stopped cleanly.")

    def _on_activity_observed(self, event: ActivityEvent) -> None:
        """
        Main pipeline callback invoked whenever an ActivityEvent is emitted by the observer.
        Mines patterns, evaluates decision opportunities, checks cooldowns, and presents suggestions.
        """
        try:
            # Step 1: Mine patterns in PatternLearningEngine
            self.pattern_engine.observe_event(event)

            # Step 2: Evaluate opportunistic proactive trigger in ProactiveDecisionEngine
            suggestion = self.decision_engine.evaluate_opportunity(event)
            if not suggestion:
                return

            # Step 3: Check rate-limits, per-pattern cooldowns, and rejection backoffs
            allowed, reason = self.suggestion_manager.can_present_suggestion(suggestion)
            if not allowed:
                logger.debug("Suggestion '%s' withheld: %s", suggestion.target, reason)
                return

            # Step 4: Register presented suggestion and prompt user
            self.suggestion_manager.register_presented(suggestion)
            self._present_suggestion_to_user(suggestion)

        except Exception as e:
            logger.error("Error in proactive coordinator pipeline: %s", e, exc_info=True)

    def _present_suggestion_to_user(self, suggestion: ProactiveSuggestion) -> None:
        """Presents the suggestion via speech and UI event."""
        prompt_text = suggestion.rationale or f"Kya aap {suggestion.target} kholna chahte hain?"
        logger.info("Proactive Suggestion Prompt: '%s'", prompt_text)

        # Notify via EventBus if available
        if self.event_bus and hasattr(self.event_bus, "emit"):
            try:
                self.event_bus.emit("proactive.suggestion.proposed", suggestion.to_dict())
            except Exception as e:
                logger.debug("Failed to emit suggestion event on event bus: %s", e)

        # Speak prompt if speaker is available
        if self.speaker and hasattr(self.speaker, "speak"):
            try:
                self.speaker.speak(prompt_text)
            except Exception as e:
                logger.debug("Failed to speak proactive suggestion prompt: %s", e)

    def _maintenance_loop(self) -> None:
        """Periodic background maintenance loop running temporal decay and memory retention pruning."""
        while not self._stop_event.is_set():
            # Run maintenance once every hour (or sleep until stop)
            if self._stop_event.wait(timeout=3600.0):
                break

            try:
                # Apply temporal decay to stale habits
                decayed = self.preference_learner.apply_temporal_decay()
                # Prune history older than retention window (default 7 days)
                retention_days = int(self.config.get("memory_retention_days", 7))
                pruned = self.memory.prune_history(retention_days=retention_days)
                logger.debug("Proactive maintenance completed: %d patterns decayed, %d events pruned", decayed, pruned)
            except Exception as e:
                logger.debug("Error during proactive maintenance loop: %s", e)
