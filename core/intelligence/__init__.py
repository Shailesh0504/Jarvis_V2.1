# core/intelligence/__init__.py
"""
Proactive Intelligence and User Activity Learning package.
Houses the PatternLearningEngine, ProactiveDecisionEngine, SuggestionManager,
and related intelligence models.
"""

from .models import (
    ContextualSuggestion,
    PatternRecord,
    PatternType,
    ProactiveSuggestion,
    SuggestionCategory,
    SuggestionChip,
    SuggestionScore,
    SuggestionState,
    SuggestionUrgency,
    TimePeriod,
)
from .pattern_engine import PatternLearningEngine
from .decision_engine import ProactiveDecisionEngine
from .suggestion_manager import SuggestionManager, get_suggestion_manager
from .executor import ProactiveActionExecutor
from .preference_learner import AdaptivePreferenceLearner
from .coordinator import ProactiveIntelligenceCoordinator
from .confidence import (
    ConfidenceTier,
    ConfidenceAction,
    InterpretationConfidence,
    ConfidenceEngine,
    get_confidence_engine,
)
from .self_improvement import (
    SelfImprovementEngine,
    FeedbackType,
    LearningPromotionStatus,
    RegressionCase,
    get_self_improvement_engine,
)
from .answer_verification import (
    AnswerVerificationEngine,
    AnswerSource,
    GroundingStatus,
    AnswerVerificationResult,
    get_answer_verifier,
)

__all__ = [
    "PatternRecord",
    "PatternType",
    "TimePeriod",
    "ProactiveSuggestion",
    "SuggestionCategory",
    "SuggestionChip",
    "SuggestionScore",
    "ContextualSuggestion",
    "SuggestionState",
    "SuggestionUrgency",
    "PatternLearningEngine",
    "ProactiveDecisionEngine",
    "SuggestionManager",
    "get_suggestion_manager",
    "ProactiveActionExecutor",
    "AdaptivePreferenceLearner",
    "ProactiveIntelligenceCoordinator",
    "ConfidenceTier",
    "ConfidenceAction",
    "InterpretationConfidence",
    "ConfidenceEngine",
    "get_confidence_engine",
    "SelfImprovementEngine",
    "FeedbackType",
    "LearningPromotionStatus",
    "RegressionCase",
    "get_self_improvement_engine",
    "AnswerVerificationEngine",
    "AnswerSource",
    "GroundingStatus",
    "AnswerVerificationResult",
    "get_answer_verifier",
]
