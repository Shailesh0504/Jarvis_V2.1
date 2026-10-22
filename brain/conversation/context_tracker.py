# brain/conversation/context_tracker.py
"""
Multi-Turn Dialogue Context Tracker & Anaphora Entity Resolver.
Maintains state across conversation turns so pronouns, follow-ups ('wahan ka weather',
'uski population', 'kyun?', 'phir?'), conversational repairs, and topic switching
are interpreted in active context.
"""

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .intents import ConversationalIntent

logger = logging.getLogger("jarvis.brain.conversation.context")


@dataclass
class ConversationState:
    """Snapshot of active multi-turn dialogue state with TTL and topic history."""
    current_topic: Optional[str] = None
    topic_history: List[str] = field(default_factory=list)
    last_user_statement: Optional[str] = None
    last_user_intent: Optional[ConversationalIntent] = None
    last_assistant_response: Optional[str] = None
    last_assistant_intent: Optional[ConversationalIntent] = None
    response_history: List[Dict[str, Any]] = field(default_factory=list)
    active_question: Optional[str] = None
    support_mode: Optional[str] = None
    support_statement: Optional[str] = None
    referenced_entities: Dict[str, Any] = field(default_factory=dict)
    active_entity: Optional[str] = None
    active_entity_type: Optional[str] = None
    turn_count: int = 0
    last_updated_time: float = field(default_factory=time.time)
    ttl_seconds: float = 300.0  # 5 minutes context expiration

    @property
    def is_expired(self) -> bool:
        """Checks whether context has expired due to inactivity."""
        return (time.time() - self.last_updated_time) > self.ttl_seconds


class ContextResolver:
    """Resolves anaphoric expressions, spatial references, and pronouns."""

    ANAPHORA_PATTERNS = [
        r'\b(usko|use|usey|isko|ise|isey|isme|usme|inhe|wahi|wahi wali|woh|wo|unhe|woh wala|is wale|iska|uska|uski|iski|unka|unke)\b',
        r'\b(wahan|waha|yahan|yaha|there|over there|here)\b',
        r'\b(that file|that app|the file|this one|previous one|that one|same wala|pehle wala|doosra)\b'
    ]

    def __init__(self):
        self._last_mentioned_entities: Dict[str, Any] = {}
        self._last_primary_entity: Optional[str] = None

    def update_context(self, entity_type: str, value: Any) -> None:
        """Saves referenced entity in context."""
        self._last_mentioned_entities[entity_type] = value
        self._last_primary_entity = str(value)

    def get_last_entity(self, entity_type: Optional[str] = None) -> Optional[Any]:
        if entity_type:
            return self._last_mentioned_entities.get(entity_type)
        if self._last_primary_entity:
            return self._last_primary_entity
        if self._last_mentioned_entities:
            return list(self._last_mentioned_entities.values())[-1]
        return None

    def resolve(self, text: str, recent_turns: Optional[List[Any]] = None, active_entity: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Detects if text contains anaphoric pronouns or spatial references and
        substitutes with referenced entities from active context or recent turns.
        """
        lowered = text.lower().strip()
        has_anaphora = any(re.search(pat, lowered) for pat in self.ANAPHORA_PATTERNS)

        if not has_anaphora:
            return text, None

        resolved_entity = active_entity or self._last_primary_entity

        # Fallback to recent turns inspection if not explicitly tracked
        if not resolved_entity and recent_turns:
            for turn in reversed(recent_turns):
                if hasattr(turn, "entities") and turn.entities:
                    for val in turn.entities.values():
                        if val:
                            resolved_entity = str(val)
                            break
                if not resolved_entity and hasattr(turn, "raw_input"):
                    raw = str(turn.raw_input).lower()
                    for app in ["chrome", "brave", "excel", "notepad", "vlc", "word", "code", "spotify", "whatsapp", "india", "delhi", "mumbai", "paris", "london", "tokyo", "weather", "calculator"]:
                        if app in raw:
                            resolved_entity = app
                            break
                if resolved_entity:
                    break

        if resolved_entity:
            # 1. Spatial references (wahan -> in <entity>, wahan ka -> <entity> ka)
            modified_text = re.sub(
                r'\b(wahan ka|waha ka|there)\b',
                f"{resolved_entity} ka",
                text,
                flags=re.IGNORECASE
            )
            modified_text = re.sub(
                r'\b(wahan|waha|there)\b',
                resolved_entity,
                modified_text,
                flags=re.IGNORECASE
            )
            # 2. Pronouns & demonstratives (uski -> <entity> ki, uska -> <entity> ka)
            modified_text = re.sub(
                r'\b(isme|usme)\b',
                f"{resolved_entity} mein",
                modified_text,
                flags=re.IGNORECASE
            )
            modified_text = re.sub(
                r'\b(uski|iski)\b',
                f"{resolved_entity} ki",
                modified_text,
                flags=re.IGNORECASE
            )
            modified_text = re.sub(
                r'\b(uska|iska|unka)\b',
                f"{resolved_entity} ka",
                modified_text,
                flags=re.IGNORECASE
            )
            modified_text = re.sub(
                r'\b(usko|use|usey|isko|ise|isey|wahi|woh wala|is wale|that one|this one|same wala|pehle wala)\b',
                resolved_entity,
                modified_text,
                flags=re.IGNORECASE
            )
            return modified_text, resolved_entity

        return text, None


class ConversationContextTracker:
    """
    Manages ongoing dialogue state, active topics, topic history stack,
    response-awareness for follow-ups, and conversational repair.
    """

    def __init__(self, ttl_seconds: float = 300.0):
        self.state = ConversationState(ttl_seconds=ttl_seconds)
        self.resolver = ContextResolver()

    def check_expiration(self) -> bool:
        """Cleans state if inactive beyond TTL."""
        if self.state.is_expired:
            logger.info("ConversationContextTracker: Context expired due to TTL. Resetting state.")
            self.clear()
            return True
        return False

    def update_user_turn(self, user_text: str, intent: ConversationalIntent, entities: Optional[Dict[str, Any]] = None) -> None:
        """Updates tracker after receiving user input."""
        self.check_expiration()
        self.state.last_user_statement = user_text
        self.state.last_user_intent = intent
        self.state.turn_count += 1
        self.state.last_updated_time = time.time()

        # Extract primary entity (e.g. India, Weather, Chrome, Excel)
        if entities:
            self.state.referenced_entities.update(entities)
            for k, v in entities.items():
                self.resolver.update_context(k, v)
                self.state.active_entity = str(v)
                self.state.active_entity_type = k

        # Auto-detect named entities from input (Countries, Cities, Apps)
        lowered = user_text.lower()
        for place in ["india", "delhi", "mumbai", "london", "paris", "tokyo", "new york", "usa", "germany", "france"]:
            if place in lowered:
                self.state.active_entity = place.title()
                self.state.active_entity_type = "place"
                self.resolver.update_context("place", self.state.active_entity)
                if not self.state.current_topic:
                    self.set_topic(self.state.active_entity)
                break

    def update_assistant_turn(self, response_text: str, intent: ConversationalIntent, asked_question: Optional[str] = None) -> None:
        """Updates tracker after assistant responds."""
        self.state.last_assistant_response = response_text
        self.state.last_assistant_intent = intent
        self.state.active_question = asked_question
        self.state.last_updated_time = time.time()

        # Save to response history for response-awareness follow-ups
        self.state.response_history.append({
            "timestamp": time.time(),
            "user": self.state.last_user_statement,
            "response": response_text,
            "intent": intent,
            "topic": self.state.current_topic,
            "entity": self.state.active_entity
        })
        if len(self.state.response_history) > 10:
            self.state.response_history.pop(0)

    def set_topic(self, topic: str) -> None:
        """Sets active conversation topic and pushes previous to topic stack."""
        if self.state.current_topic and self.state.current_topic.lower() != topic.lower():
            self.state.topic_history.append(self.state.current_topic)
        self.state.current_topic = topic

    def recall_previous_topic(self) -> Optional[str]:
        """Pops and restores previous topic from topic history stack."""
        if self.state.topic_history:
            prev = self.state.topic_history.pop()
            self.state.current_topic = prev
            logger.info(f"ConversationContextTracker: Recalled previous topic: '{prev}'")
            return prev
        return self.state.current_topic

    def get_topic(self) -> Optional[str]:
        return self.state.current_topic

    def has_active_question(self) -> bool:
        return bool(self.state.active_question)

    def resolve_response_awareness(self, user_query: str) -> Optional[str]:
        """
        Handles questions asking about what Jarvis just said:
        e.g. 'kyun?', 'kaise?', 'iska matlab?', 'example do', 'short mein batao', 'detail mein samjhao', 'dobara bolo'
        """
        if not self.state.last_assistant_response:
            return None

        last_resp = self.state.last_assistant_response.strip()
        lowered = user_query.lower().strip()

        if lowered.rstrip("?.!") in {"maine abhi kya kaha tha", "maine kya kaha", "what did i just say"}:
            user = self.state.response_history[-1].get("user") if self.state.response_history else None
            if user:
                return f"Aapne kaha tha: {user}"

        # 1. Repeat / Rephrase
        if any(w in lowered for w in ["dobara bolo", "phir se bolo", "repeat karo", "repeat please", "pardon"]):
            return f"Maine kaha tha: \"{last_resp}\""

        # 2. Short / Concise
        if any(w in lowered for w in ["short mein", "short me", "chhota karke", "in brief", "1 line mein"]):
            sentences = [s.strip() for s in last_resp.split(".") if s.strip()]
            short_ver = sentences[0] if sentences else last_resp
            return f"Short me ye hai: {short_ver}."

        # 3. Examples
        if any(w in lowered for w in ["example do", "udharan do", "give example", "for example"]):
            if self.state.active_entity:
                return f"Jaise {self.state.active_entity} ke context me, agar aap specific data check karna chahein to main calculate ya fetch kar sakta hoon."
            return "Jaise kisi application ko open karna, math calculate karna, ya location check karna."

        # 4. Detailed explanation
        if any(w in lowered for w in ["detail mein", "detail me", "in detail", "vistaar se"]):
            return f"Detail explanation: {last_resp} Iske alawa agar aapko koi specific step dekhna ho to bataiye."

        # 5. Why / How (Reasoning)
        if lowered in ["kyun?", "kyun", "why", "kyu"]:
            return f"Kyunki {last_resp.lower()} Iske baare me aur discuss karna hai?"
        if lowered in ["kaise?", "kaise", "how"]:
            return f"Ise process karne ke liye system context aur commands ka use hota hai. Aap chahein to main demo dikha sakta hoon."

        return None

    def resolve_short_reply(self, short_text: str) -> Optional[str]:
        """
        Interprets short answers (e.g. 'haan', 'nahi', 'achha', 'phir?', 'kyun?', 'woh wala')
        in active context.
        """
        cleaned = short_text.lower().strip()

        # If Jarvis previously asked a clarification question or confirmation
        if self.state.active_question:
            q = self.state.active_question
            if cleaned in ["haan", "yes", "bilkul", "sahi", "haan wahi", "sure", "zaroor"]:
                return f"Confirmed regarding '{q}'"
            elif cleaned in ["nahi", "no", "nope", "rehne do"]:
                return f"Declined regarding '{q}'"

        # Topic continuation
        if cleaned in ["phir", "fir", "phir?", "fir?", "uske baad", "and then", "aur?", "aur batao"]:
            if self.state.current_topic:
                return f"Continue topic '{self.state.current_topic}'"
            elif self.state.last_user_statement:
                return f"Continue from '{self.state.last_user_statement}'"

        return None

    def clear(self) -> None:
        """Resets active context."""
        self.state = ConversationState(ttl_seconds=self.state.ttl_seconds)
        self.resolver._last_mentioned_entities.clear()
        self.resolver._last_primary_entity = None
