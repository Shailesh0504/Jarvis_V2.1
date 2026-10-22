# core/event_bus.py
"""Event Bus for decoupled asynchronous and synchronous communication across Jarvis V2."""

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger("jarvis.event_bus")


@dataclass
class Event:
    topic: str
    data: Any = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: str = "core"
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventTopics:
    """Canonical topics for EventBus to prevent naming collisions and fragmentation."""
    USER_INPUT_RECEIVED = "user.input.received"
    VOICE_WAKEWORD_DETECTED = "voice.wakeword.detected"
    INTENT_CLASSIFIED = "intent.classified"
    COMMAND_DETECTED = "command.detected"
    ACTION_PLANNED = "action.planned"
    POLICY_EVALUATED = "policy.evaluated"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    MEMORY_CREATED = "memory.created"
    LEARNING_DETECTED = "learning.detected"
    SUGGESTION_CREATED = "suggestion.created"
    PROACTIVE_SUGGESTION_PROPOSED = "proactive.suggestion.proposed"
    ACTIVITY_OBSERVED = "activity.observed"
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_ERROR = "plugin.error"
    CORE_INITIALIZED = "core.initialized"
    SYSTEM_SHUTDOWN = "system.shutdown"
    RESPONSE_COMPLETED = "response.completed"
    CONVERSATION_INTERRUPTED = "conversation.interrupted"
    STATE_CHANGED = "system.state.changed"
    AUDIO_DEVICE_CHANGED = "audio.device.changed"
    REMINDER_TRIGGERED = "reminder.triggered"


# ==========================================
# Core Standard Domain Events
# ==========================================

@dataclass
class AudioDeviceChanged:
    topic: str = "audio.device.changed"
    event_type: str = "connected"  # connected, disconnected, changed, default_changed
    device_id: str = ""
    device_name: str = ""
    input_index: Optional[int] = None
    output_index: Optional[int] = None
    input_available: bool = False
    output_available: bool = False
    has_microphone: bool = False
    has_speaker: bool = False
    is_bluetooth: bool = False
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.has_microphone:
            self.input_available = True
        elif self.input_available:
            self.has_microphone = True
        if self.has_speaker:
            self.output_available = True
        elif self.output_available:
            self.has_speaker = True

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return self.metadata.get(key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        if key in self.metadata:
            return self.metadata[key]
        raise KeyError(key)

@dataclass
class ConversationInterrupted:
    topic: str = "conversation.interrupted"
    previous_turn_id: str = ""
    previous_generation_id: int = 0
    interrupting_input: str = ""
    reason: str = "user_barge_in"
    timestamp: float = field(default_factory=time.time)
    turn_id: str = ""
    generation_id: int = 0
    interrupted_at: Optional[float] = None

    def __init__(
        self,
        topic: str = "conversation.interrupted",
        previous_turn_id: str = "",
        previous_generation_id: int = 0,
        interrupting_input: str = "",
        reason: str = "user_barge_in",
        timestamp: Optional[float] = None,
        turn_id: str = "",
        generation_id: int = 0,
        interrupted_at: Optional[float] = None,
        **kwargs: Any
    ):
        self.topic = topic

        if turn_id:
            resolved_turn_id = str(turn_id)
        elif previous_turn_id:
            resolved_turn_id = str(previous_turn_id)
        elif "turn_id" in kwargs:
            resolved_turn_id = str(kwargs["turn_id"])
        elif "previous_turn_id" in kwargs:
            resolved_turn_id = str(kwargs["previous_turn_id"])
        else:
            resolved_turn_id = ""
        self.turn_id = resolved_turn_id
        self.previous_turn_id = resolved_turn_id

        if generation_id != 0:
            resolved_gen_id = int(generation_id)
        elif previous_generation_id != 0:
            resolved_gen_id = int(previous_generation_id)
        elif "generation_id" in kwargs:
            resolved_gen_id = int(kwargs["generation_id"])
        elif "previous_generation_id" in kwargs:
            resolved_gen_id = int(kwargs["previous_generation_id"])
        else:
            resolved_gen_id = 0
        self.generation_id = resolved_gen_id
        self.previous_generation_id = resolved_gen_id

        if interrupting_input:
            resolved_input = str(interrupting_input)
        elif "interrupting_text" in kwargs:
            resolved_input = str(kwargs["interrupting_text"])
        elif "interrupting_input" in kwargs:
            resolved_input = str(kwargs["interrupting_input"])
        else:
            resolved_input = ""
        self.interrupting_input = resolved_input

        self.reason = reason

        if timestamp is not None:
            resolved_ts = float(timestamp)
        elif interrupted_at is not None:
            resolved_ts = float(interrupted_at)
        elif "timestamp" in kwargs:
            resolved_ts = float(kwargs["timestamp"])
        elif "interrupted_at" in kwargs:
            resolved_ts = float(kwargs["interrupted_at"])
        else:
            resolved_ts = time.time()
        self.timestamp = resolved_ts
        self.interrupted_at = resolved_ts

        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


@dataclass
class UserInputReceived:
    topic: str = "user.input.received"
    text: str = ""
    source: str = "user"
    turn_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class WakeWordDetected:
    topic: str = "voice.wakeword.detected"
    wake_word: str = "jarvis"
    position: str = "prefix"
    cleaned_command: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class CommandDetected:
    topic: str = "command.detected"
    intent: str = ""
    plugin_name: str = ""
    action_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ActionPlanned:
    topic: str = "action.planned"
    plan_id: str = ""
    action: str = ""
    target: str = ""
    target_type: str = "general"
    risk_level: str = "LOW"
    confirmation_required: bool = False
    verification_strategy: str = "process_running"
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PolicyEvaluated:
    topic: str = "policy.evaluated"
    plan_id: str = ""
    allowed: bool = True
    reason: str = ""
    risk_level: str = "LOW"
    confirmation_required: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExecutionCompleted:
    topic: str = "execution.completed"
    plan_id: str = ""
    action: str = ""
    target: str = ""
    success: bool = True
    status: str = "SUCCESS"
    error: Optional[str] = None
    action_type: str = "general"
    timestamp: float = field(default_factory=time.time)


@dataclass
class ActivityObserved:
    topic: str = "activity.observed"
    event_id: str = ""
    event_type: str = ""
    application: str = ""
    website: Optional[str] = None
    title: Optional[str] = None
    importance: str = "LOW"
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProactiveSuggestionProposed:
    topic: str = "proactive.suggestion.proposed"
    suggestion_id: str = ""
    action: str = ""
    target: str = ""
    intent: str = ""
    confidence: float = 0.8
    urgency: str = "LOW"
    timestamp: float = field(default_factory=time.time)


@dataclass
class SystemStateChanged:
    topic: str = "system.state.changed"
    old_state: str = ""
    new_state: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskStarted:
    topic: str = "task.started"
    task_id: str = ""
    workflow_name: str = ""
    plan_steps: int = 1
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskCompleted:
    topic: str = "task.completed"
    task_id: str = ""
    success: bool = True
    output: str = ""
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemoryCreated:
    topic: str = "memory.created"
    memory_type: str = "semantic" # semantic, episodic, procedural, working, short_term
    key: str = ""
    value: Any = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class LearningDetected:
    topic: str = "learning.detected"
    layer: int = 2 # 1: Preferences, 2: Vocab, 3: Workflow, 4: Correction, 5: Habit
    pattern_type: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class SuggestionCreated:
    topic: str = "suggestion.created"
    suggestion_id: str = ""
    text: str = ""
    confidence: float = 0.9
    timestamp: float = field(default_factory=time.time)


@dataclass
class PluginLoaded:
    topic: str = "plugin.loaded"
    plugin_name: str = ""
    version: str = "1.0.0"
    permissions: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PluginError:
    topic: str = "plugin.error"
    plugin_name: str = ""
    action_name: str = ""
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)


# ==========================================
# Central Event Bus
# ==========================================

class EventBus:
    """Thread-safe publish-subscribe event bus supporting exact, wildcard topics, and typed domain events."""

    _default_instance: Optional["EventBus"] = None

    @classmethod
    def get_default(cls) -> "EventBus":
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    def __init__(self, history_limit: int = 100):
        if EventBus._default_instance is None:
            EventBus._default_instance = self
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._lock = threading.RLock()
        self._history: List[Event] = []
        self._history_limit = history_limit

    def subscribe(self, topic_pattern: str, handler: Callable[[Any], Any]) -> None:
        """Subscribe to a topic pattern (e.g., 'user.input.*', 'plugin.*', '*')."""
        with self._lock:
            if topic_pattern not in self._subscribers:
                self._subscribers[topic_pattern] = []
            if handler not in self._subscribers[topic_pattern]:
                self._subscribers[topic_pattern].append(handler)
                logger.debug(f"Subscribed handler to pattern '{topic_pattern}'")

    def unsubscribe(self, topic_pattern: str, handler: Callable[[Any], Any]) -> None:
        """Unsubscribe a handler from a topic pattern."""
        with self._lock:
            if topic_pattern in self._subscribers and handler in self._subscribers[topic_pattern]:
                self._subscribers[topic_pattern].remove(handler)
                if not self._subscribers[topic_pattern]:
                    del self._subscribers[topic_pattern]

    def remove_handlers_by_module(self, module_prefix: str) -> int:
        """
        Removes all event subscribers whose underlying function, class, or method
        originates from a module matching module_prefix (e.g. 'plugins.trading_signals').
        Returns the count of handlers removed.
        """
        removed_count = 0
        with self._lock:
            for pattern in list(self._subscribers.keys()):
                remaining = []
                for handler in self._subscribers[pattern]:
                    mods = []
                    if hasattr(handler, "__module__") and handler.__module__:
                        mods.append(handler.__module__)
                    if hasattr(handler, "__self__") and hasattr(handler.__self__, "__module__"):
                        mods.append(handler.__self__.__module__)

                    is_match = any(m == module_prefix or m.startswith(module_prefix + ".") for m in mods)
                    if is_match:
                        removed_count += 1
                        logger.debug(f"Removed EventBus handler {handler} from topic '{pattern}' (modules: {mods})")
                    else:
                        remaining.append(handler)
                if remaining:
                    self._subscribers[pattern] = remaining
                else:
                    del self._subscribers[pattern]
        return removed_count

    def has_subscribers(self, topic: str) -> bool:
        """Checks if any registered subscriber pattern matches the given topic."""
        with self._lock:
            for pattern, handlers in self._subscribers.items():
                if handlers and fnmatch.fnmatch(topic, pattern):
                    return True
            return False

    def publish(self, event: Event) -> None:
        """Synchronously publish an event to all matching subscribers."""
        matching_handlers = []
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history.pop(0)

            for pattern, handlers in self._subscribers.items():
                if fnmatch.fnmatch(event.topic, pattern):
                    matching_handlers.extend(handlers)

        for handler in matching_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler {handler} for topic '{event.topic}': {e}", exc_info=True)

    def publish_async(self, event: Event) -> threading.Thread:
        """Asynchronously publish an event to all matching subscribers on a background thread."""
        thread = threading.Thread(
            target=self.publish,
            args=(event,),
            name=f"EventBusAsync-{event.topic[:20]}",
            daemon=True
        )
        thread.start()
        return thread

    def emit(self, topic: str, data: Any = None, source: str = "core", **metadata) -> Event:
        """Convenience method to create and publish an event."""
        event = Event(topic=topic, data=data, source=source, metadata=metadata)
        self.publish(event)
        return event

    def emit_async(self, topic: str, data: Any = None, source: str = "core", **metadata) -> Event:
        """Convenience method to asynchronously create and publish an event."""
        event = Event(topic=topic, data=data, source=source, metadata=metadata)
        self.publish_async(event)
        return event

    def emit_domain_event(self, domain_event: Any) -> Event:
        """Emits a strongly-typed domain event instance."""
        topic = getattr(domain_event, "topic", "general.event")
        return self.emit(topic=topic, data=domain_event, source=domain_event.__class__.__name__)

    def get_history(self) -> List[Event]:
        """Returns the recent event history log."""
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Clear all subscribers and history."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()
