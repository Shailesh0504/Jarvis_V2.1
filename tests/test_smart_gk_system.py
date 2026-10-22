# tests/test_smart_gk_system.py
"""
Comprehensive Test Suite for Jarvis General Knowledge & Reasoning Engine.
Validates:
1. Multilingual Semantic Equivalence (Hindi, Hinglish, English variations)
2. STT Error & Phonetic Recovery
3. Simple Fact Conciseness vs Detailed Explanation
4. Polysemous Disambiguation & Contextual Resolution
5. Multi-Step Query Decomposition
6. Multi-Turn Context & Anaphora Resolution ("wahan", "unka", "iska")
7. Reasoning Capabilities (Comparative, Spatial Inversion, Mathematical Rate)
8. Capability Gating Invariance (Never executes or answers capability queries)
9. Fast Knowledge Path Sub-15ms Latency
10. User Knowledge Isolation (Sandbox integrity)
11. Strict Anti-Hallucination on Low-Confidence Inquiries
"""

import pytest
import time

from core.knowledge.engine import KnowledgeEngine, get_knowledge_engine
from core.knowledge.models import (
    ConfidenceLevel,
    GKQuestionType,
    KnowledgeSourceType
)
from core.knowledge.pipeline import (
    GKNormalizer,
    GKQuestionClassifier,
    EntityDisambiguationEngine,
    GKConfidenceEvaluator,
    FastKnowledgePath
)


@pytest.fixture
def engine():
    """Provides a freshly initialized KnowledgeEngine instance."""
    eng = KnowledgeEngine()
    eng.clear_context()
    return eng


class TestSemanticEquivalence:
    """1. Diverse phrasings must map to identical factual meaning."""

    def test_capital_of_india_variations(self, engine):
        variations = [
            "India ki capital kya hai?",
            "Bharat ki rajdhani kaun si hai?",
            "What is the capital of India?",
            "capital of India?",
            "batao na India ki capital kya hai",
            "zara batao Bharat ki rajdhani kya he",
            "India capitol city kya hai"
        ]
        for query in variations:
            res = engine.query(query)
            assert res.found is True, f"Failed on query: {query}"
            assert "New Delhi" in res.answer_text, f"Expected 'New Delhi' in answer for: {query}"
            assert res.confidence == ConfidenceLevel.HIGH

    def test_currency_of_japan_variations(self, engine):
        queries = [
            "Japan ki currency kya hai?",
            "Japan ki mudra batao",
            "What currency does Japan use?",
            "Japan currency"
        ]
        for q in queries:
            res = engine.query(q)
            assert res.found is True
            assert "Yen" in res.answer_text or "JPY" in res.answer_text


class TestSTTErrorRecovery:
    """2. Phonetic and transcription errors must be recovered."""

    def test_phonetic_normalization(self, engine):
        # "primer minister" -> "prime minister", "kon he" -> "kaun hai"
        cleaned, lang, conf = GKNormalizer.normalize("Bharat ke primer minister kon he?")
        assert "prime minister" in cleaned
        assert "kaun hai" in cleaned

        # Full resolution through engine
        res = engine.query("Bharat ke primer minister kon he?")
        assert res.found is True
        assert "Narendra Modi" in res.answer_text

    def test_earth_revolution_stt_variant(self, engine):
        # "round lagati hai" -> "chakkar lagati hai"
        res = engine.query("Prithvi suraj ka round lagati hai kitne time mein?")
        assert res.found is True
        assert "365" in res.answer_text


class TestConcisenessAndExplanation:
    """3. Simple facts produce concise answers; Why/How produce structured explanations."""

    def test_simple_fact_conciseness(self, engine):
        res = engine.query("Water ka chemical formula kya hai?")
        assert res.found is True
        assert "H2O" in res.answer_text
        # Ensure answer is concise (not a massive multi-paragraph essay)
        assert len(res.answer_text.split(".")) <= 3

    def test_why_question_explanation(self, engine):
        res = engine.query("Sky blue kyun dikhta hai?")
        assert res.found is True
        assert "scattering" in res.answer_text.lower() or "blue" in res.answer_text.lower()

    def test_how_question_rain(self, engine):
        res = engine.query("Rain kaise hoti hai?")
        assert res.found is True
        assert "water cycle" in res.answer_text.lower() or "bhaap" in res.answer_text.lower() or "evaporat" in res.answer_text.lower()


class TestMultiStepDecomposition:
    """4. Compound queries linked by conjunctions are decomposed and synthesized."""

    def test_independence_and_first_pm(self, engine):
        query = "India kab independent hua aur uske first Prime Minister kaun the?"
        res = engine.query(query)
        assert res.found is True
        assert res.question_type == GKQuestionType.MULTI_STEP
        assert "15 August 1947" in res.answer_text
        assert "Jawaharlal Nehru" in res.answer_text


class TestMultiTurnAnaphora:
    """5. Conversational context and pronouns ('wahan', 'unka') resolve to previous entities."""

    def test_location_anaphora_wahan(self, engine):
        # Turn 1: Ask about India
        res1 = engine.query("India ki capital kya hai?")
        assert res1.found is True
        assert "New Delhi" in res1.answer_text

        # Turn 2: Follow-up using 'wahan'
        res2 = engine.query("wahan ki population kitni hai?")
        assert res2.found is True
        assert "1.4 billion" in res2.answer_text or "33 million" in res2.answer_text

    def test_person_anaphora_unka(self, engine):
        # Turn 1: Ask about Einstein
        res1 = engine.query("Albert Einstein kaun the?")
        assert res1.found is True

        # Turn 2: Follow-up using 'unka'
        res2 = engine.query("unka famous theory kaun sa hai?")
        assert res2.found is True
        assert "Relativity" in res2.answer_text


class TestEntityDisambiguation:
    """6. Polysemous entities are flagged for clarification or disambiguated via cues."""

    def test_ambiguous_java_triggers_clarification(self, engine):
        res = engine.query("Java kya hai?")
        assert res.found is False
        assert res.question_type == GKQuestionType.AMBIGUOUS
        assert res.disambiguation_options is not None
        assert len(res.disambiguation_options) >= 2
        assert "programming" in res.answer_text.lower()
        assert "island" in res.answer_text.lower()

    def test_contextual_java_programming(self, engine):
        res = engine.query("Java programming language kya hai?")
        assert res.question_type != GKQuestionType.AMBIGUOUS


class TestReasoningEngines:
    """7. Comparative, Spatial, and Mathematical Rate reasoning."""

    def test_comparative_reasoning_earth_mars(self, engine):
        res = engine.query("Which planet is larger, Earth or Mars?")
        assert res.found is True
        assert res.question_type == GKQuestionType.COMPARISON
        assert "Earth" in res.answer_text
        assert "12,742" in res.answer_text
        assert "6,779" in res.answer_text

    def test_spatial_inversion_india_sri_lanka(self, engine):
        res = engine.query("If India is north of Sri Lanka, which country is south of India?")
        assert res.found is True
        assert res.question_type == GKQuestionType.SPATIAL_RELATION
        assert "Sri Lanka" in res.answer_text

    def test_math_rate_reasoning(self, engine):
        res = engine.query("If a train travels 60 km in 1 hour, how far will it travel in 3 hours?")
        assert res.found is True
        assert res.question_type == GKQuestionType.MATHEMATICAL_RATE
        assert "180 km" in res.answer_text


class TestCapabilityGating:
    """8. Capability inquiries must NEVER be claimed by Knowledge Engine."""

    def test_capability_rejected_by_candidate_filter(self, engine):
        capability_queries = [
            "kya tum system lock kar sakte ho?",
            "can you open Chrome?",
            "tum Excel chala sakte ho?",
            "kya tum computer restart kar sakte ho?"
        ]
        for q in capability_queries:
            assert engine.is_knowledge_candidate(q) is False, f"Capability query should be rejected: {q}"


class TestFastPathPerformance:
    """9. Fast knowledge path sub-15ms response retrieval."""

    def test_sub_15ms_latency(self, engine):
        query = "France ki capital kya hai?"
        # Warmup turn
        res1 = engine.query(query)
        assert res1.found is True

        # Second turn should hit FastKnowledgePath in under 15ms
        t0 = time.perf_counter()
        res2 = engine.query(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert res2.found is True
        assert "Paris" in res2.answer_text
        assert elapsed_ms < 15.0, f"Fast path latency was {elapsed_ms:.2f}ms (expected < 15ms)"


class TestUserKnowledgeIsolation:
    """10. User-taught knowledge must be sandboxed without corrupting global seed facts."""

    def test_user_taught_fact_isolation(self, engine):
        # Teach custom fact in isolated sandbox
        engine.teach_user_fact("india", "favorite_project", "Jarvis Assistant")

        res = engine.query("India ka favorite project kya hai?")
        assert res.found is True
        assert res.source_type == KnowledgeSourceType.USER_TAUGHT
        assert "Jarvis Assistant" in res.answer_text

        # Verify global seed fact is unpolluted
        seed_res = engine.query("India ki capital kya hai?")
        assert seed_res.found is True
        assert seed_res.source_type == KnowledgeSourceType.STATIC_FACT
        assert "New Delhi" in seed_res.answer_text


class TestAntiHallucination:
    """11. Strict anti-hallucination on unknown queries."""

    def test_unknown_query_honest_refusal(self, engine):
        res = engine.query("XYZ random non-existent galactic entity 9999 kya hai?")
        assert res.found is False
        assert res.confidence == ConfidenceLevel.LOW
        assert "reliable jaankari uplabdh nahi hai" in res.answer_text or "reliable information" in res.answer_text
