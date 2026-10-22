# brain/conversation_engine.py
"""
Conversation Intelligence Layer & Hinglish Conversational AI Subsystem.
Maintains backwards-compatible interface while delegating to the modular
brain.conversation architecture.
"""

from brain.conversation.intents import ConversationalIntent, ConversationIntent
from brain.conversation.normalizer import ConversationNormalizer
from brain.conversation.registry import ConversationIntentRegistry
from brain.conversation.classifier import ConversationClassifier, ClassificationResult
from brain.conversation.context_tracker import ConversationContextTracker, ContextResolver, ConversationState
from brain.conversation.strategy import ResponseStrategy, StrategySelector
from brain.conversation.persona import PersonalityConfig, PersonaTone
from brain.conversation.response_generator import ConversationResponseGenerator, HinglishPersona
from brain.conversation.metrics import ConversationMetricsLogger, TurnMetric
from brain.conversation.engine import ConversationEngine

__all__ = [
    "ConversationalIntent",
    "ConversationIntent",
    "ConversationNormalizer",
    "ConversationIntentRegistry",
    "ConversationClassifier",
    "ClassificationResult",
    "ConversationContextTracker",
    "ContextResolver",
    "ConversationState",
    "ResponseStrategy",
    "StrategySelector",
    "PersonalityConfig",
    "PersonaTone",
    "ConversationResponseGenerator",
    "HinglishPersona",
    "ConversationMetricsLogger",
    "TurnMetric",
    "ConversationEngine",
]
