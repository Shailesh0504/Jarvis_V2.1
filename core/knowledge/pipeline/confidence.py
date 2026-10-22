# core/knowledge/pipeline/confidence.py
"""
Multi-Factor Confidence Evaluation Engine for the Jarvis Knowledge Pipeline.
Calculates a granular confidence vector across language, transcription,
classification, entity matching, relation mapping, and knowledge retrieval.
Enforces strict anti-hallucination policies on low confidence scores.
"""

from typing import Dict, Any, Optional
from ..models import ConfidenceVector, ConfidenceLevel


class GKConfidenceEvaluator:
    """Calculates multi-dimensional confidence score vector for knowledge responses."""

    # Component weights summing to 1.0
    WEIGHTS = {
        "entity": 0.30,
        "relation": 0.25,
        "knowledge": 0.20,
        "classification": 0.10,
        "transcription": 0.10,
        "language": 0.05
    }

    @classmethod
    def evaluate(
        cls,
        entity_conf: float = 1.0,
        relation_conf: float = 1.0,
        knowledge_conf: float = 1.0,
        classification_conf: float = 1.0,
        transcription_conf: float = 1.0,
        language_conf: float = 1.0,
        answer_conf: float = 1.0
    ) -> ConfidenceVector:
        """Computes weighted composite confidence score and constructs ConfidenceVector."""
        composite = (
            entity_conf * cls.WEIGHTS["entity"]
            + relation_conf * cls.WEIGHTS["relation"]
            + knowledge_conf * cls.WEIGHTS["knowledge"]
            + classification_conf * cls.WEIGHTS["classification"]
            + transcription_conf * cls.WEIGHTS["transcription"]
            + language_conf * cls.WEIGHTS["language"]
        )

        composite = max(0.0, min(1.0, composite))

        return ConfidenceVector(
            language=round(language_conf, 3),
            transcription=round(transcription_conf, 3),
            classification=round(classification_conf, 3),
            entity=round(entity_conf, 3),
            relation=round(relation_conf, 3),
            knowledge=round(knowledge_conf, 3),
            answer=round(answer_conf, 3),
            composite=round(composite, 3)
        )

    @classmethod
    def get_confidence_level(cls, score: float) -> ConfidenceLevel:
        """Determines categorical confidence level from numeric score."""
        if score >= 0.80:
            return ConfidenceLevel.HIGH
        elif score >= 0.60:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
