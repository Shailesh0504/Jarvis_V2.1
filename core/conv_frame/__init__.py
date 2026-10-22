# core/conv_frame/__init__.py
"""
Conversation Frame Bridge — core layer adapter for JARVIS V2.

Provides:
  FrameDecisionType   : Canonical decision types for the unified pipeline.
  ConversationFrameBridge : Static enrichment methods that populate
                            HumanConversationFrame fields from downstream
                            subsystem outputs (SpeechUnderstanding, DialogueAct,
                            ReferenceResolver, ContextLayer).

Does NOT duplicate or replace:
  - HumanConversationModel   (brain/conversation/model.py) — frame producer
  - ConversationalIntentClassifier (core/conversational_intent.py)
  - DialogueActClassifier    (core/dialogue_act.py)
  - ReferenceResolver        (core/reference_resolver.py)
  - TopicTracker             (core/topic_tracker.py)
  - ConversationState        (core/conversation_state.py)
  - ConfidenceEngine         (core/intelligence/confidence.py)
"""

from .frame import FrameDecisionType, ConversationFrameBridge

__all__ = [
    "FrameDecisionType",
    "ConversationFrameBridge",
]
