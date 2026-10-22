# core/topic_tracker.py
"""
Topic Tracking and Context Continuity for Jarvis V2.
Tracks active_topic, previous_topic, topic_confidence, and thread continuity.
Ensures topics do NOT reset to UNKNOWN on short acknowledgements or continuations.
"""

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional

from core.dialogue_act import DialogueAct, DialogueActResult
from core.conversation_state import ConversationState, ConversationMode

logger = logging.getLogger("jarvis.core.topic_tracker")


@dataclass
class TopicRecord:
    topic: str
    subtopic: Optional[str] = None
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)


class TopicTracker:
    """Authoritative topic tracker maintaining conversation focus and threading."""

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
        self.topic_confidence: float = 1.0
        self.topic_stack: List[str] = []
        self.history: List[TopicRecord] = []

    def push_topic(self, topic: Optional[str] = None) -> None:
        """Pushes current active topic onto topic stack before switching."""
        top = topic or self.active_topic
        if top and top != "general":
            if not self.topic_stack or self.topic_stack[-1] != top:
                self.topic_stack.append(top)
                logger.debug("[TOPIC_TRACKER] Pushed '%s' to topic_stack: %s", top, self.topic_stack)

    def pop_topic(self) -> Optional[str]:
        """Pops and returns the previous topic from the stack."""
        if self.topic_stack:
            prev = self.topic_stack.pop()
            self.previous_topic = self.active_topic
            self.active_topic = prev
            logger.debug("[TOPIC_TRACKER] Popped and restored active topic '%s'", prev)
            return prev
        return None

    def return_to_previous_workflow(self, conversation_state: Optional[ConversationState] = None) -> Optional[str]:
        """Restores the previous workflow topic from stack."""
        restored = self.pop_topic()
        if restored and conversation_state:
            conversation_state.pop_thread()
        return restored

    def track_utterance(
        self,
        text: str,
        dialogue_act_result: DialogueActResult,
        conversation_state: Optional[ConversationState] = None
    ) -> str:
        """
        Determines and updates the topic for the current turn.
        Preserves active topic on continuations, acknowledgements, and deictic commands.
        """
        raw = text.strip().lower()
        new_topic: Optional[str] = None
        new_subtopic: Optional[str] = None
        conf = dialogue_act_result.confidence

        # Case 1: Acknowledgement or continuation - KEEP active topic!
        if dialogue_act_result.act in (
            DialogueAct.ACKNOWLEDGEMENT,
            DialogueAct.CONVERSATIONAL_CONTINUATION
        ):
            logger.debug("[TOPIC_TRACKER] Preserving active topic '%s' for %s", self.active_topic, dialogue_act_result.act.value)
            return self.active_topic

        # Case 2: Explicit hint from DialogueActResult
        if dialogue_act_result.topic_hint:
            new_topic = dialogue_act_result.topic_hint
            new_subtopic = dialogue_act_result.subtopic_hint

        # Case 3: Food utterances
        if any(w in raw for w in ["khana", "lunch", "dinner", "breakfast", "food", "pet bhar gaya"]):
            new_topic = "food"
            new_subtopic = "lunch"

        # Case 4: Visual search utterances
        elif any(w in raw for w in ["kahan likha hai", "kahan par likha hai", "find text", "likha hai"]):
            new_topic = "visual_search"

        # Case 5: Deictic reference to earlier topic or thread
        elif "woh" in raw and any(w in raw for w in ["kholo", "open"]):
            # e.g. "ab woh youtube wala kholo" -> check if "youtube" or "browser" thread exists
            for term in ["youtube", "chrome", "edge", "brave", "browser"]:
                if term in raw:
                    new_topic = "browser"
                    new_subtopic = term
                    break

        # Case 6: Deictic action on current topic ("ab is par click karo", "isko band karo")
        elif dialogue_act_result.topic_hint == "reference_command":
            # Retain current topic if already in visual_search or browser
            if self.active_topic in ("visual_search", "browser", "app_control"):
                new_topic = self.active_topic
            else:
                new_topic = "desktop_action"

        # Apply topic change if recognized
        if new_topic and new_topic != "general":
            if new_topic != self.active_topic:
                # If currently in a specific app or task and moving to casual/info, push to stack
                if self.active_topic in ("excel", "browser", "app_control", "desktop_action", "visual_search") and new_topic in ("weather", "general", "casual", "small_talk"):
                    self.push_topic(self.active_topic)
                self.previous_topic = self.active_topic
                self.active_topic = new_topic
            self.subtopic = new_subtopic
            self.topic_confidence = conf
            self.history.append(TopicRecord(topic=self.active_topic, subtopic=self.subtopic, confidence=conf))

            # Sync to ConversationState
            if conversation_state:
                mode = ConversationMode.COMMAND if dialogue_act_result.is_executable_command else (
                    ConversationMode.VISUAL if self.active_topic == "visual_search" else ConversationMode.CASUAL
                )
                conversation_state.switch_topic(self.active_topic, subtopic=self.subtopic, mode=mode)

        return self.active_topic

    def get_active_topic(self) -> str:
        return self.active_topic

    def get_previous_topic(self) -> Optional[str]:
        return self.previous_topic
