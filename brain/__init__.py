# brain/__init__.py
"""Brain module for LLM reasoning, intent classification, Fast/Smart brain, and natural response generation."""

from .llm import BaseLLMProvider, MockLLMProvider, OllamaProvider, OpenAICompatibleProvider, get_llm_provider
from .prompts import SYSTEM_PROMPT, INTENT_CLASSIFICATION_PROMPT
from .classifier import IntentClassifier
from .reasoning import ReasoningEngine
from .response import ResponseGenerator
from .fast_brain import FastBrain
from .smart_brain import SmartBrain
from .dual_brain import DualBrain

__all__ = [
    "BaseLLMProvider",
    "MockLLMProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "get_llm_provider",
    "SYSTEM_PROMPT",
    "INTENT_CLASSIFICATION_PROMPT",
    "IntentClassifier",
    "ReasoningEngine",
    "ResponseGenerator",
    "FastBrain",
    "SmartBrain",
    "DualBrain",
]
