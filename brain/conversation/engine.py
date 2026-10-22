# brain/conversation/engine.py
"""
Central Conversation Intelligence Engine for Jarvis V2.
Orchestrates multi-turn context tracking, intent classification, anaphora resolution,
response strategy selection, personality management, and structured metrics logging.
"""

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .intents import ConversationalIntent
from .normalizer import ConversationNormalizer
from .classifier import ConversationClassifier, ClassificationResult
from .context_tracker import ConversationContextTracker, ContextResolver
from .strategy import StrategySelector, ResponseStrategy
from .persona import PersonalityConfig, PersonaTone
from .response_generator import ConversationResponseGenerator, HinglishPersona
from .metrics import ConversationMetricsLogger

logger = logging.getLogger("jarvis.brain.conversation.engine")


class ConversationEngine:
    """
    Core Conversation Intelligence Engine.
    Handles everyday natural dialogue without rigid phrasing, tracks dialogue state,
    and cleanly separates conversational utterances from executable plugin commands.
    """

    def __init__(self, llm_provider: Optional[Any] = None, memory_manager: Optional[Any] = None):
        self.llm = llm_provider
        self.memory = memory_manager
        self._last_memory_callback = float("-inf")
        self.personality = PersonalityConfig()
        self.context_tracker = ConversationContextTracker()
        self.context_resolver = self.context_tracker.resolver
        self.classifier = ConversationClassifier
        self.response_generator = ConversationResponseGenerator(llm_provider=llm_provider, personality=self.personality)
        self.metrics_logger = ConversationMetricsLogger()
        from .model import HumanConversationModel
        self.human_model = HumanConversationModel(
            context_resolver=self.context_resolver
        )

    def set_tone(self, tone_name: str) -> bool:
        """Sets the conversational personality tone (friendly, natural, concise, professional, humorous)."""
        return self.personality.set_tone(tone_name)

    def get_tone(self) -> str:
        """Returns the active personality tone name."""
        return self.personality.tone.value

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Returns statistical overview of dialogue quality metrics."""
        return self.metrics_logger.get_summary()

    def register_custom_phrase(self, phrase: str, intent: ConversationalIntent) -> None:
        """Registers a newly learned or user-approved phrase at runtime."""
        self.classifier.get_registry().register_custom_utterance(phrase, intent)

    def process_conversation_turn(
        self,
        user_input: str,
        recent_turns: Optional[List[Any]] = None
    ) -> Tuple[bool, str, ConversationalIntent]:
        """
        Evaluates user input.
        Returns: (is_handled_as_conversation: bool, response_text: str, intent: ConversationalIntent)
        If user_input is an executable tool/command, returns (False, "", ConversationalIntent.COMMAND).
        """
        start_t = time.perf_counter()
        turn_id = str(uuid.uuid4())[:8]
        self.context_tracker.check_expiration()
        has_active_history = bool(self.context_tracker.state.turn_count or recent_turns)
        norm_text = ConversationNormalizer.clean(user_input)

        # 1. Semantic Classification & Boundary Check
        class_res: ClassificationResult = self.classifier.classify_detailed(
            user_input,
            has_active_dialogue=has_active_history
        )

        if class_res.is_command:
            # Route to Command/Plugin Router
            self.context_tracker.state.support_mode = None
            return False, "", ConversationalIntent.COMMAND

        # 2. Check for Ambiguity / Clarification Request
        if class_res.is_ambiguous and class_res.clarification_prompt and not self.llm:
            self.context_tracker.update_user_turn(user_input, class_res.intent)
            self.context_tracker.update_assistant_turn(
                class_res.clarification_prompt,
                class_res.intent,
                asked_question=class_res.clarification_prompt
            )
            exec_time = (time.perf_counter() - start_t) * 1000
            self.metrics_logger.log_turn(
                turn_id=turn_id,
                raw_input=user_input,
                detected_intent=class_res.intent.value,
                confidence=class_res.confidence,
                strategy_used="ASK_CLARIFICATION",
                is_clarification=True,
                execution_time_ms=exec_time
            )
            return True, class_res.clarification_prompt, class_res.intent

        # 3. Resolve Anaphora ('usko', 'wahi', 'wahan', 'that one') using context history
        resolved_text, resolved_entity = self.context_resolver.resolve(
            user_input,
            recent_turns=recent_turns,
            active_entity=self.context_tracker.state.active_entity
        )
        if resolved_entity:
            logger.info(f"ContextResolver: Resolved reference in '{user_input}' -> '{resolved_text}' (Entity: {resolved_entity})")

        # 4. Strategy Selection
        strategy = StrategySelector.select_strategy(
            intent=class_res.intent,
            confidence=class_res.confidence,
            context_state=self.context_tracker.state,
            raw_text=user_input
        )

        # 5. Check Response-Awareness queries directly
        awareness_resp = self.context_tracker.resolve_response_awareness(user_input)
        if awareness_resp and not self.context_tracker.state.support_mode:
            self.context_tracker.update_user_turn(user_input, class_res.intent)
            self.context_tracker.update_assistant_turn(awareness_resp, class_res.intent)
            exec_time = (time.perf_counter() - start_t) * 1000
            self.metrics_logger.log_turn(
                turn_id=turn_id,
                raw_input=user_input,
                detected_intent=class_res.intent.value,
                confidence=1.0,
                strategy_used="RESPONSE_AWARENESS",
                context_resolved=True,
                execution_time_ms=exec_time
            )
            return True, awareness_resp, class_res.intent

        # 6. Update tracker before response generation
        self.context_tracker.update_user_turn(
            user_input,
            class_res.intent,
            entities={"entity": resolved_entity} if resolved_entity else None
        )

        # 7. Multi-dimensional Human Conversation Model Frame & Generation
        conv_frame = self.human_model.analyze_turn(
            raw_input=user_input,
            recent_turns=recent_turns
        )
        response = self.response_generator.generate(
            raw_text=user_input,
            normalized_text=norm_text,
            intent=class_res.intent,
            context_state=self.context_tracker.state,
            strategy=strategy,
            conversation_frame=conv_frame
        )
        response = self.personality.adapt_response(response)

        # A greeting may recall one fact the user explicitly saved. No invented
        # life events, background notifications or repeated check-ins.
        if class_res.intent == ConversationalIntent.GREETING and self.memory:
            try:
                name = self.memory.get_fact("user_name")
                if name and isinstance(name.get("value"), str) and self.context_tracker.state.turn_count == 1:
                    response = f"Hello {name['value']}! Kaise hain aap?"
                now = time.monotonic()
                if now - self._last_memory_callback >= 1800:
                    project = self.memory.get_fact("current_project")
                    if project and isinstance(project.get("value"), str):
                        opening = f"Hello {name['value']}!" if name and name.get("value") else "Hello!"
                        response = f"{opening} Aapne {project['value']} par kaam karne ki baat batayi thi; kaisa chal raha hai?"
                        self._last_memory_callback = now
            except Exception:
                logger.debug("Greeting memory unavailable", exc_info=True)

        # 8. Update assistant turn state
        question = re.search(r"[^.!?]*\?\s*$", response)
        self.context_tracker.update_assistant_turn(
            response, class_res.intent,
            asked_question=question.group().strip() if question else None,
        )

        # 9. Track metrics
        exec_time = (time.perf_counter() - start_t) * 1000
        self.metrics_logger.log_turn(
            turn_id=turn_id,
            raw_input=user_input,
            detected_intent=class_res.intent.value,
            confidence=class_res.confidence,
            strategy_used=strategy.value,
            context_resolved=bool(resolved_entity),
            execution_time_ms=exec_time
        )

        return True, response, class_res.intent
