# brain/conversation/__init__.py
"""
Conversation Intelligence Subsystem for Jarvis V2.
Provides natural, human-like Hindi, Hinglish, and English conversational understanding,
multi-turn context tracking, anaphora resolution, response strategies, personality management,
and quality metrics logging.
"""

from .intents import ConversationalIntent, ConversationIntent
from .normalizer import ConversationNormalizer
from .registry import ConversationIntentRegistry
from .classifier import ConversationClassifier, ClassificationResult
from .context_tracker import ConversationContextTracker, ContextResolver, ConversationState
from .strategy import ResponseStrategy, StrategySelector
from .persona import PersonalityConfig, PersonaTone
from .response_generator import ConversationResponseGenerator, HinglishPersona
from .metrics import ConversationMetricsLogger, TurnMetric
from .engine import ConversationEngine
from .model import HumanConversationModel, HumanConversationFrame, EmotionAnalyzer

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
    "HumanConversationModel",
    "HumanConversationFrame",
    "EmotionAnalyzer",
]
