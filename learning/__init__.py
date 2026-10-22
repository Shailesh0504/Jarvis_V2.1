# learning/__init__.py
"""5-Layer Learning Module and Learning Communication Engine (LCE) for Jarvis V2."""

from .preferences_layer import PreferencesLayer
from .vocabulary_layer import VocabularyLayer
from .workflow_layer import WorkflowLayer
from .corrections_layer import CorrectionsLayer, CorrectionResult
from .habit_layer import HabitLayer
from .learner import LearningManager
from .communication_engine import LearningCommunicationEngine
from .communication_memory import CommunicationMemory
from .communication_normalizer import CommunicationNormalizer, UtteranceTokens
from .communication_matcher import CommunicationMatcher
from .communication_feedback import CommunicationFeedback

__all__ = [
    "PreferencesLayer",
    "VocabularyLayer",
    "WorkflowLayer",
    "CorrectionsLayer",
    "CorrectionResult",
    "HabitLayer",
    "LearningManager",
    "LearningCommunicationEngine",
    "CommunicationMemory",
    "CommunicationNormalizer",
    "UtteranceTokens",
    "CommunicationMatcher",
    "CommunicationFeedback",
]
