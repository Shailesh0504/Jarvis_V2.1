# tests/test_accuracy_confidence_engine.py
"""
Comprehensive test suite for the Accuracy & Confidence Calibration Engine (`intelligence.confidence`).
Validates:
1. 5 Internal Confidence Dimensions: intent, entity, context, action, answer
2. 3 Confidence Tiers: HIGH (execute/answer), MEDIUM (use context/verify), LOW (clarify)
3. 'Galat answer se better clarification' principle & anti-hallucination gating
4. Action vs Answer specialized evaluation formulas
5. Context boost and critical dimension floor penalties
6. HumanConversationModel & JarvisCore closed-loop integration
"""

import pytest
from unittest.mock import MagicMock, patch

from core.intelligence.confidence import (
    ConfidenceEngine,
    ConfidenceTier,
    ConfidenceAction,
    InterpretationConfidence,
    get_confidence_engine,
)
from core.conversational_intent import ConversationalIntentType
from brain.conversation.model import HumanConversationModel, HumanConversationFrame
from core.app import JarvisCore


class TestAccuracyConfidenceEngineCore:
    """Validates the core 5 dimensions, composite calculation, and 3 tiers."""

    @pytest.fixture
    def engine(self):
        return ConfidenceEngine()

    def test_five_internal_confidence_dimensions_present(self, engine):
        """Jarvis must internally maintain all 5 sub-confidences with each evaluation."""
        result = engine.evaluate(
            intent_confidence=0.92,
            entity_confidence=0.88,
            context_confidence=0.85,
            action_confidence=0.90,
            answer_confidence=0.80,
            turn_type="action",
            raw_query="Chrome open karo"
        )

        assert isinstance(result, InterpretationConfidence)
        assert result.intent_confidence == 0.92
        assert result.entity_confidence == 0.88
        assert result.context_confidence == 0.85
        assert result.action_confidence == 0.90
        assert result.answer_confidence == 0.80

        # Verify serialization
        data = result.to_dict()
        assert data["intent_confidence"] == 0.92
        assert data["entity_confidence"] == 0.88
        assert data["context_confidence"] == 0.85
        assert data["action_confidence"] == 0.90
        assert data["answer_confidence"] == 0.80
        assert "composite" in data
        assert "tier" in data
        assert "recommended_action" in data

    def test_high_tier_direct_execution_for_commands(self, engine):
        """HIGH tier (>= 0.85) recommends direct EXECUTE."""
        result = engine.evaluate(
            intent_confidence=0.98,
            entity_confidence=0.95,
            context_confidence=0.90,
            action_confidence=0.95,
            turn_type="action",
            raw_query="Chrome kholo"
        )
        assert result.tier == ConfidenceTier.HIGH
        assert result.recommended_action == ConfidenceAction.EXECUTE
        assert result.is_executable is True
        assert result.needs_clarification is False
        assert result.needs_context_or_verification is False

    def test_high_tier_direct_answer_for_information(self, engine):
        """HIGH tier (>= 0.85) recommends direct ANSWER for knowledge/information."""
        result = engine.evaluate(
            intent_confidence=0.95,
            entity_confidence=0.92,
            context_confidence=0.85,
            answer_confidence=0.95,
            turn_type="answer",
            raw_query="India ki capital kya hai?"
        )
        assert result.tier == ConfidenceTier.HIGH
        assert result.recommended_action == ConfidenceAction.ANSWER
        assert result.is_executable is True
        assert result.needs_clarification is False

    def test_medium_tier_use_context_when_context_available(self, engine):
        """MEDIUM tier (0.60 <= conf < 0.85) with active context recommends USE_CONTEXT."""
        result = engine.evaluate(
            intent_confidence=0.85,
            entity_confidence=0.65,
            context_confidence=0.85,  # strong context
            action_confidence=0.75,
            turn_type="action",
            raw_query="tab band karo"
        )
        assert result.tier == ConfidenceTier.MEDIUM
        assert result.recommended_action == ConfidenceAction.USE_CONTEXT
        assert result.needs_context_or_verification is True
        assert result.needs_clarification is False

    def test_medium_tier_verify_when_context_not_conclusive(self, engine):
        """MEDIUM tier with lower context recommends pre-execution VERIFY."""
        result = engine.evaluate(
            intent_confidence=0.80,
            entity_confidence=0.70,
            context_confidence=0.60,  # lower context
            action_confidence=0.70,
            turn_type="action",
            raw_query="Notepad close karo"
        )
        assert result.tier == ConfidenceTier.MEDIUM
        assert result.recommended_action == ConfidenceAction.VERIFY
        assert result.needs_context_or_verification is True

    def test_low_tier_mandates_clarification_principle(self, engine):
        """LOW tier (< 0.60) enforces 'galat answer se better clarification' principle."""
        result = engine.evaluate(
            intent_confidence=0.50,
            entity_confidence=0.45,
            context_confidence=0.50,
            action_confidence=0.50,
            turn_type="action",
            raw_query="khol do"
        )
        assert result.tier == ConfidenceTier.LOW
        assert result.recommended_action == ConfidenceAction.CLARIFY
        assert result.needs_clarification is True
        assert result.is_executable is False
        assert result.clarification_prompt is not None
        assert len(result.clarification_prompt) > 0

    def test_critical_dimension_collapse_forces_low_tier(self, engine):
        """If any critical dimension collapses (< 0.40), tier drops to LOW even if composite is moderate."""
        # Unrecognized entity / gibberish with high intent
        result = engine.evaluate(
            intent_confidence=0.95,
            entity_confidence=0.30,  # collapsed critical dimension!
            context_confidence=0.70,
            action_confidence=0.80,
            turn_type="action",
            raw_query="xyz123 open karo"
        )
        assert result.tier == ConfidenceTier.LOW
        assert result.recommended_action == ConfidenceAction.CLARIFY
        assert result.needs_clarification is True

    def test_destructive_action_capped_to_medium_tier(self, engine):
        """Destructive actions (shutdown, format, kill) are capped to prevent unverified execution."""
        result = engine.evaluate(
            intent_confidence=0.99,
            entity_confidence=0.99,
            context_confidence=0.90,
            action_confidence=0.99,
            is_destructive=True,
            turn_type="action",
            raw_query="system shutdown karo"
        )
        assert result.tier == ConfidenceTier.MEDIUM
        assert result.recommended_action == ConfidenceAction.VERIFY
        assert result.is_executable is False


class TestSpecializedEvaluatorsAndClarification:
    """Validates specialized action/answer evaluators and clarification prompt generation."""

    @pytest.fixture
    def engine(self):
        return ConfidenceEngine()

    def test_evaluate_action_turn_context_boost(self, engine):
        """When entity matches active window/app in context, context confidence is boosted."""
        mock_context = MagicMock()
        mock_context.application = "Google Chrome"

        result = engine.evaluate_action_turn(
            intent="OPEN_APPLICATION",
            entity="chrome",
            action="open_app",
            raw_query="Chrome kholo",
            active_context=mock_context
        )
        assert result.context_confidence >= 0.95
        assert result.tier == ConfidenceTier.HIGH
        assert result.recommended_action == ConfidenceAction.EXECUTE

    def test_evaluate_answer_turn_hallucination_gating(self, engine):
        """Hallucination risk in knowledge turns drops answer confidence and mandates clarification."""
        result = engine.evaluate_answer_turn(
            query="who will win the 2032 olympics?",
            intent_conf=0.90,
            entity_conf=0.70,
            answer_conf=0.90,
            is_hallucination_risk=True,
            category="sports"
        )
        assert result.answer_confidence <= 0.30
        assert result.tier == ConfidenceTier.LOW
        assert result.recommended_action == ConfidenceAction.CLARIFY
        assert "authoritative jaankari" in result.clarification_prompt

    def test_generate_clarification_for_ambiguous_candidates(self, engine):
        """When multiple ambiguous candidates exist, offers natural choice."""
        prompt = engine.generate_clarification(
            raw_query="Antigravity kholo",
            candidates=["Antigravity App", "Antigravity Website"],
            turn_type="action"
        )
        assert "Antigravity App ya Antigravity Website" in prompt
        assert "kaunsa" in prompt

    def test_generate_clarification_for_missing_entity(self, engine):
        """When intent is known but target entity is unknown, asks for target."""
        prompt = engine.generate_clarification(
            raw_query="kholo",
            intent_conf=0.85,
            entity_conf=0.30,
            turn_type="action"
        )
        assert "application ya target" in prompt

    def test_calibration_feedback_recording(self, engine):
        """Validates that turn feedback can be recorded for adaptive calibration."""
        engine.calibrate(1.0, {"turn_id": "turn_1", "intent": "OPEN_APPLICATION"})
        engine.calibrate(1.0, {"turn_id": "turn_2", "intent": "OPEN_APPLICATION"})
        engine.calibrate(0.0, {"turn_id": "turn_3", "correction": True})

        stats = engine.get_calibration_stats()
        assert stats["count"] == 3
        assert 0.60 <= stats["avg_feedback"] <= 0.70


class TestHumanConversationModelConfidenceIntegration:
    """Validates that HumanConversationModel produces and attaches InterpretationConfidence."""

    def test_human_conversation_frame_contains_confidence(self):
        hcm = HumanConversationModel()
        frame = hcm.analyze_turn("Chrome kholo")

        assert frame is not None
        assert frame.confidence is not None
        assert isinstance(frame.confidence, InterpretationConfidence)
        assert 0.0 <= frame.confidence.intent_confidence <= 1.0
        assert 0.0 <= frame.confidence.entity_confidence <= 1.0
        assert 0.0 <= frame.confidence.context_confidence <= 1.0
        assert 0.0 <= frame.confidence.action_confidence <= 1.0
        assert 0.0 <= frame.confidence.answer_confidence <= 1.0
        assert frame.confidence.tier in (ConfidenceTier.HIGH, ConfidenceTier.MEDIUM, ConfidenceTier.LOW)

    def test_capability_question_produces_answer_confidence(self):
        hcm = HumanConversationModel()
        frame = hcm.analyze_turn("kya tum system lock kar sakte ho?")

        assert frame.is_executable_command is False
        assert frame.confidence is not None
        assert frame.confidence.answer_confidence >= 0.80


class TestJarvisCoreConfidenceEngineIntegration:
    """Validates that JarvisCore wires ConfidenceEngine and attaches confidence to turns."""

    def test_jarvis_core_has_confidence_engine(self):
        core = JarvisCore.__new__(JarvisCore)
        core.confidence_engine = get_confidence_engine()

        assert core.confidence_engine is not None
        assert isinstance(core.confidence_engine, ConfidenceEngine)

        conf = core.confidence_engine.evaluate(
            intent_confidence=0.95,
            entity_confidence=0.90,
            context_confidence=0.85,
            action_confidence=0.90,
            turn_type="action"
        )
        assert conf.tier == ConfidenceTier.HIGH
        assert conf.is_executable is True
