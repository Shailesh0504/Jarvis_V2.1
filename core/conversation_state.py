# core/conversation_state.py
"""
Dialogue and Conversation State Manager for Jarvis V2.
Maintains dialogue state, user states (e.g. has_eaten, mood), active threads,
and rolling summaries across turns.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.conversation_state")


class ConversationMode(str, Enum):
    COMMAND = "COMMAND"
    CASUAL = "CASUAL"
    INFORMATION = "INFORMATION"
    TROUBLESHOOTING = "TROUBLESHOOTING"
    VISUAL = "VISUAL"
    WORKFLOW = "WORKFLOW"
    MIXED = "MIXED"


@dataclass
class ConversationThread:
    topic: str
    subtopic: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    context_variables: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    turn_count: int = 0

    def touch(self) -> None:
        self.last_active = time.time()
        self.turn_count += 1


class ConversationState:
    """Authoritative dialogue and conversation state manager."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.active_topic: str = "general"
        self.previous_topic: Optional[str] = None
        self.subtopic: Optional[str] = None
        self.conversation_mode: ConversationMode = ConversationMode.CASUAL
        self.user_state: Dict[str, Any] = {
            "has_eaten": None,
            "is_away": False,
        }
        self.last_user_utterance: str = ""
        self.last_jarvis_response: str = ""
        self.pending_context: str = ""
        self.threads: Dict[str, ConversationThread] = {}
        self.thread_stack: List[str] = []
        self.rolling_summary: str = ""
        self.turn_count: int = 0
        self.last_updated: float = time.time()

    def update_user_state(self, key: str, value: Any) -> None:
        """Updates user state (e.g. has_eaten = False or True)."""
        self.user_state[key] = value
        self.last_updated = time.time()
        logger.debug("[CONVERSATION_STATE] Updated user_state %s = %r", key, value)

    def get_user_state(self, key: str, default: Any = None) -> Any:
        return self.user_state.get(key, default)

    def push_active_thread(self) -> None:
        """Pushes the current active topic thread onto the thread stack."""
        if self.active_topic and self.active_topic != "general":
            if not self.thread_stack or self.thread_stack[-1] != self.active_topic:
                self.thread_stack.append(self.active_topic)
                logger.debug("[CONVERSATION_STATE] Pushed '%s' to thread_stack: %s", self.active_topic, self.thread_stack)

    def pop_thread(self) -> Optional[ConversationThread]:
        """Pops and resumes the suspended thread from the stack."""
        if self.thread_stack:
            prev_topic = self.thread_stack.pop()
            logger.debug("[CONVERSATION_STATE] Popped '%s' from thread_stack to resume", prev_topic)
            return self.resume_thread(prev_topic)
        return None

    def switch_topic(
        self,
        topic: str,
        subtopic: Optional[str] = None,
        mode: Optional[ConversationMode] = None
    ) -> None:
        """Transitions conversation to a new or existing topic thread."""
        if topic != self.active_topic:
            # If leaving an active workflow or application task, push to thread stack
            if self.conversation_mode in (ConversationMode.WORKFLOW, ConversationMode.COMMAND) and self.active_topic not in ("general", "casual", "greeting"):
                self.push_active_thread()
            self.previous_topic = self.active_topic
            self.active_topic = topic
        if subtopic is not None:
            self.subtopic = subtopic
        if mode is not None:
            self.conversation_mode = mode

        thread = self.get_or_create_thread(topic)
        thread.touch()
        if subtopic:
            thread.subtopic = subtopic
        self.last_updated = time.time()
        logger.debug("[CONVERSATION_STATE] Active topic switched to '%s' (mode=%s)", self.active_topic, self.conversation_mode.value)

    def get_or_create_thread(self, topic: str) -> ConversationThread:
        if topic not in self.threads:
            self.threads[topic] = ConversationThread(topic=topic)
        return self.threads[topic]

    def resume_thread(self, topic: str) -> Optional[ConversationThread]:
        """Resumes an older conversational thread if available."""
        if topic in self.threads:
            self.switch_topic(topic)
            return self.threads[topic]
        return None

    def record_turn(
        self,
        user_text: str,
        jarvis_text: str,
        dialogue_act: Optional[str] = None,
        topic: Optional[str] = None
    ) -> None:
        self.last_user_utterance = user_text
        self.last_jarvis_response = jarvis_text
        self.turn_count += 1
        self.last_updated = time.time()

        eff_topic = topic or self.active_topic
        if eff_topic:
            if eff_topic != self.active_topic:
                self.switch_topic(eff_topic)
            else:
                th = self.get_or_create_thread(eff_topic)
                th.touch()

        # Update rolling summary with concise event
        summary_entry = f"User: {user_text[:60]} -> Jarvis: {jarvis_text[:60]}"
        if not self.rolling_summary:
            self.rolling_summary = summary_entry
        else:
            self.rolling_summary = f"{self.rolling_summary} | {summary_entry}"
            # Keep rolling summary bounded
            if len(self.rolling_summary) > 600:
                parts = self.rolling_summary.split(" | ")
                self.rolling_summary = " | ".join(parts[-4:])

    def reset_session(self) -> None:
        """Resets working dialogue state for a fresh session."""
        self.active_topic = "general"
        self.previous_topic = None
        self.subtopic = None
        self.conversation_mode = ConversationMode.CASUAL
        self.user_state.clear()
        self.user_state["has_eaten"] = None
        self.user_state["is_away"] = False
        self.last_user_utterance = ""
        self.last_jarvis_response = ""
        self.pending_context = ""
        self.threads.clear()
        self.rolling_summary = ""
        self.turn_count = 0
        self.last_updated = time.time()
