# brain/conversation/strategy.py
"""
Response Strategy Selector for Conversation Intelligence Layer.
Determines how Jarvis should strategically formulate its response based on intent,
confidence, conversation history, and dialogue context.
"""

from enum import Enum
import logging
from typing import Any, Dict, Optional

from .intents import ConversationalIntent

logger = logging.getLogger("jarvis.brain.conversation.strategy")


class ResponseStrategy(str, Enum):
    """Dialogue response strategies."""
    DIRECT_ANSWER = "DIRECT_ANSWER"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    CONFIRM_ACTION = "CONFIRM_ACTION"
    ACKNOWLEDGE_ONLY = "ACKNOWLEDGE_ONLY"
    EXPLAIN_REASONING = "EXPLAIN_REASONING"
    PROVIDE_EXAMPLES = "PROVIDE_EXAMPLES"
    SUGGEST_WORKFLOW = "SUGGEST_WORKFLOW"
    CONCISE_ANSWER = "CONCISE_ANSWER"
    DETAILED_ANSWER = "DETAILED_ANSWER"
    CONVERSATIONAL_REPAIR = "CONVERSATIONAL_REPAIR"
    EMPATHIC_RESPONSE = "EMPATHIC_RESPONSE"
    TOPIC_RECALL = "TOPIC_RECALL"
    ACKNOWLEDGE_AND_APOLOGIZE = "ACKNOWLEDGE_AND_APOLOGIZE"


class StrategySelector:
    """Selects the best response strategy for a dialogue turn."""

    @classmethod
    def select_strategy(
        cls,
        intent: ConversationalIntent,
        confidence: float,
        context_state: Optional[Any] = None,
        raw_text: str = ""
    ) -> ResponseStrategy:
        """Determines the appropriate strategy for the current turn."""
        cleaned = raw_text.lower().strip()

        # 0. Complaint & Listening Feedback
        if intent in (
            ConversationalIntent.USER_COMPLAINT_FEEDBACK,
            ConversationalIntent.CRITICISM_LISTENING,
            ConversationalIntent.COMPLAINT
        ):
            return ResponseStrategy.ACKNOWLEDGE_AND_APOLOGIZE

        # 1. Conversational Repair
        if intent == ConversationalIntent.CORRECTION or any(w in cleaned for w in ["nahi mera matlab", "galat", "main ye nahi keh raha tha"]):
            return ResponseStrategy.CONVERSATIONAL_REPAIR

        # 2. Topic Recall
        if any(w in cleaned for w in ["wapis usi baat par", "wapas usi baat", "back to previous", "pehle wali baat"]):
            return ResponseStrategy.TOPIC_RECALL

        # 3. Response-Awareness / Reasoning queries
        if any(w in cleaned for w in ["short mein", "in brief", "chhota karke", "1 line mein"]):
            return ResponseStrategy.CONCISE_ANSWER
        if any(w in cleaned for w in ["detail mein", "in detail", "vistaar se", "explain properly"]):
            return ResponseStrategy.DETAILED_ANSWER
        if any(w in cleaned for w in ["example do", "udharan do", "give example", "for example"]):
            return ResponseStrategy.PROVIDE_EXAMPLES
        reasoning_queries = {
            "kyun", "kyun?", "kyu", "why", "why?",
            "kaise", "kaise?", "how", "how?", "iska matlab", "iska matlab?"
        }
        if cleaned in reasoning_queries and intent not in (
            ConversationalIntent.HOW_ARE_YOU,
            ConversationalIntent.GREETING,
            ConversationalIntent.STATUS_CHECK,
        ):
            return ResponseStrategy.EXPLAIN_REASONING

        # 4. Low confidence -> Clarification (without repetitive canned phrases)
        if confidence < 0.65 and intent == ConversationalIntent.GENERAL_CHAT:
            return ResponseStrategy.ASK_CLARIFICATION

        # 5. Empathy
        if intent == ConversationalIntent.EMOTIONAL_MOOD:
            return ResponseStrategy.EMPATHIC_RESPONSE

        # 6. Acknowledgement / Short confirmation
        if intent in (ConversationalIntent.ACKNOWLEDGEMENT, ConversationalIntent.WELCOME_NO_PROBLEM):
            return ResponseStrategy.ACKNOWLEDGE_ONLY

        # 7. Suggestions & Opinions
        if intent in (ConversationalIntent.SUGGESTION_REQUEST, ConversationalIntent.OPINION_REQUEST):
            return ResponseStrategy.SUGGEST_WORKFLOW

        # Default direct answer
        return ResponseStrategy.DIRECT_ANSWER
