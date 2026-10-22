# core/memory/working_memory.py
"""
Working Memory Tier for Jarvis V2 Conversation Redesign.
Fast, in-memory, session-scoped working state tracking:
- last N user messages & Jarvis responses
- active topic & subtopic
- current entities
- unresolved references
- recent desktop actions
- recent visual targets
- pending questions
- dynamic user states
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.core.memory.working")


@dataclass
class ConversationTurnRecord:
    speaker: str  # "user" / "jarvis"
    text: str
    normalized_text: str = ""
    dialogue_act: str = ""
    topic: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class WorkingConversationMemory:
    """Authoritative fast session-scoped working memory."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_turns: int = 20):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.max_turns = max_turns
        self.turns: List[ConversationTurnRecord] = []
        self.active_topic: str = "general"
        self.active_subtopic: Optional[str] = None
        self.current_entities: Dict[str, Any] = {}
        self.unresolved_references: List[str] = []
        self.recent_actions: List[Dict[str, Any]] = []
        self.recent_visual_targets: List[Dict[str, Any]] = []
        self.pending_questions: List[str] = []
        self.user_state: Dict[str, Any] = {}
        self.session_start: float = time.time()

    def add_turn(
        self,
        speaker: str,
        text: str,
        normalized_text: str = "",
        dialogue_act: str = "",
        topic: str = "",
        entities: Optional[Dict[str, Any]] = None
    ) -> None:
        rec = ConversationTurnRecord(
            speaker=speaker,
            text=text,
            normalized_text=normalized_text or text.lower().strip(),
            dialogue_act=dialogue_act,
            topic=topic or self.active_topic,
            entities=entities or {},
            timestamp=time.time()
        )
        self.turns.append(rec)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        if entities:
            self.current_entities.update(entities)
        if topic:
            self.active_topic = topic

    def update_entity(self, key: str, value: Any) -> None:
        self.current_entities[key] = value

    def get_entity(self, key: str, default: Any = None) -> Any:
        return self.current_entities.get(key, default)

    def record_action(self, action_name: str, target: str, success: bool = True) -> None:
        self.recent_actions.append({
            "action": action_name,
            "target": target,
            "success": success,
            "timestamp": time.time()
        })
        if len(self.recent_actions) > 10:
            self.recent_actions = self.recent_actions[-10:]

    def record_visual_target(self, target_text: str, coordinates: Optional[tuple] = None) -> None:
        self.recent_visual_targets.append({
            "target": target_text,
            "coordinates": coordinates,
            "timestamp": time.time()
        })
        if len(self.recent_visual_targets) > 5:
            self.recent_visual_targets = self.recent_visual_targets[-5:]

    def get_recent_turns(self, limit: int = 10) -> List[ConversationTurnRecord]:
        return self.turns[-limit:]

    def get_recent_dialogue_acts(self, limit: int = 5) -> List[str]:
        return [t.dialogue_act for t in self.turns[-limit:] if t.dialogue_act]

    def clear(self) -> None:
        self.turns.clear()
        self.current_entities.clear()
        self.unresolved_references.clear()
        self.recent_actions.clear()
        self.recent_visual_targets.clear()
        self.pending_questions.clear()
        self.user_state.clear()
        self.session_start = time.time()
