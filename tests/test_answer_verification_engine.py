# tests/test_answer_verification_engine.py
"""
Comprehensive test suite for the Answer Verification & Factual Grounding Engine
(`intelligence.answer_verification`).
Validates:
- Answer Source Attribution (STRUCTURED_KB, REASONING_ENGINE, IT_KNOWLEDGE, CALENDAR_ENGINE, SYSTEM_TELEMETRY, LIVE_SEARCH)
- Factual Grounding against authoritative stores
- Freshness & Currency requirements (dynamic leadership, live weather, real-time markets, tech versions)
- Contradiction & conflict detection
- Multi-tier confidence calibration & anti-hallucination refusals
- Integration with KnowledgeRouter and JarvisCore
"""

import pytest
from core.intelligence.answer_verification import (
    AnswerSource,
    GroundingStatus,
    AnswerVerificationResult,
    AnswerVerificationEngine,
    get_answer_verifier
)
from core.intelligence.confidence import ConfidenceTier
from core.knowledge import get_knowledge_engine, ConfidenceLevel


@pytest.fixture(autouse=True)
def clean_knowledge_context():
    get_knowledge_engine().clear_context()
    yield
    get_knowledge_engine().clear_context()


class TestAnswerVerificationCore:
    """Core functionality of AnswerVerificationEngine."""

    def test_singleton_accessor(self):
        v1 = get_answer_verifier()
        v2 = get_answer_verifier()
        assert v1 is v2
        assert isinstance(v1, AnswerVerificationEngine)

    def test_result_structure_and_serialization(self):
        res = AnswerVerificationResult(
            verified=True,
            grounding_status=GroundingStatus.GROUNDED,
            source=AnswerSource.STRUCTURED_KB,
            confidence=0.95,
            confidence_tier=ConfidenceTier.HIGH,
            requires_live_data=False,
            grounded_fact="New Delhi",
            suggested_response="India ki rajdhani New Delhi hai."
        )
        d = res.to_dict()
        assert d["verified"] is True
        assert d["grounding_status"] == "GROUNDED"
        assert d["source"] == "STRUCTURED_KB"
        assert d["confidence"] == 0.95
        assert d["confidence_tier"] == "HIGH"
        assert d["requires_live_data"] is False
        assert d["grounded_fact"] == "New Delhi"
        assert d["suggested_response"] == "India ki rajdhani New Delhi hai."
        assert "verified_at" in d

    def test_source_attribution(self):
        verifier = get_answer_verifier()

        # Static Entity
        src_kb = verifier.attribute_source("capital of india", "New Delhi", candidate_entity="india")
        assert src_kb == AnswerSource.STRUCTURED_KB

        # Conceptual Reasoning
        src_reason = verifier.attribute_source("why is the sky blue", "Rayleigh scattering", candidate_entity=None)
        assert src_reason == AnswerSource.REASONING_ENGINE

        # System Telemetry
        src_telem = verifier.attribute_source("what is the current time", "18:45", candidate_entity=None)
        assert src_telem == AnswerSource.SYSTEM_TELEMETRY

        # IT Knowledge
        src_it = verifier.attribute_source("how to troubleshoot rdp port 3389", "Check Windows Firewall port 3389")
        assert src_it == AnswerSource.IT_KNOWLEDGE

        # Festival Calendar
        src_cal = verifier.attribute_source("diwali kab hai", "Diwali date")
        assert src_cal == AnswerSource.CALENDAR_ENGINE


class TestFactualGrounding:
    """Validates factual grounding checks."""

    def test_grounded_static_fact_success(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="India ki capital kya hai?",
            proposed_answer="India ki capital New Delhi hai.",
            candidate_entity="india",
            candidate_property="capital",
            candidate_value="New Delhi",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.95,
            is_hindi=True
        )
        assert res.verified is True
        assert res.grounding_status == GroundingStatus.GROUNDED
        assert res.confidence_tier == ConfidenceTier.HIGH
        assert res.confidence >= 0.85
        assert res.grounded_fact == "New Delhi"

    def test_grounded_chemical_symbol(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="Gold ka chemical symbol kya hai?",
            proposed_answer="Gold ka chemical symbol Au hai.",
            candidate_entity="gold",
            candidate_property="chemical_formula",
            candidate_value="Au",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.95,
            is_hindi=True
        )
        assert res.verified is True
        assert res.grounding_status == GroundingStatus.GROUNDED
        assert "Au" in str(res.grounded_fact)

    def test_ungrounded_random_claim_rejected(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="Atlantis ka king kaun hai?",
            proposed_answer="Atlantis ka king Arthur Curry hai.",
            candidate_entity="atlantis",
            candidate_property="king",
            candidate_value="Arthur Curry",
            source=AnswerSource.UNVERIFIED_HALLUCINATION,
            raw_confidence=0.30,
            is_hindi=True
        )
        assert res.verified is False
        assert res.grounding_status in (GroundingStatus.UNGROUNDED, GroundingStatus.LOW_CONFIDENCE)
        assert res.confidence_tier == ConfidenceTier.LOW
        assert res.refusal_reason is not None
        assert "reliable" in res.suggested_response.lower() or "jaankari" in res.suggested_response.lower()


class TestFreshnessAndTimeSensitivity:
    """Validates dynamic leadership, live weather, and tech version inquiries."""

    def test_dynamic_leadership_india_pm(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="India ka PM kaun hai?",
            proposed_answer="Bharat ke vartaman Prime Minister Shri Narendra Modi hain.",
            candidate_entity="india",
            candidate_property="current_prime_minister",
            candidate_value="Narendra Modi",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.95,
            is_hindi=True
        )
        assert res.verified is True
        assert res.requires_live_data is True
        assert res.grounding_status == GroundingStatus.GROUNDED
        assert res.grounded_fact == "Narendra Modi"
        assert res.metadata.get("leadership_verified") is True

    def test_live_weather_requires_fresh_data(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="aaj weather kya hai?",
            proposed_answer="Aaj mausam 28 degree sunny hai.",  # Static guess
            candidate_entity="weather",
            candidate_property="weather",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.85,
            is_hindi=True
        )
        assert res.verified is False
        assert res.requires_live_data is True
        assert res.grounding_status == GroundingStatus.TIME_SENSITIVE_STALE
        assert "internet access" in res.suggested_response.lower() or "live" in res.suggested_response.lower()

    def test_live_financial_market_requires_fresh_data(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="Nifty ka stock price kya hai?",
            proposed_answer="Nifty 24,000 par trade kar raha hai.",
            candidate_entity="stock_market",
            candidate_property="stock_price",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.85,
            is_hindi=True
        )
        assert res.verified is False
        assert res.requires_live_data is True
        assert res.grounding_status == GroundingStatus.TIME_SENSITIVE_STALE
        assert "market" in res.suggested_response.lower() or "feed" in res.suggested_response.lower() or "live" in res.suggested_response.lower()

    def test_windows_tech_version_grounding(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="Windows ka latest version kya hai?",
            proposed_answer="Windows ka latest version Windows 11 hai.",
            candidate_entity="windows",
            candidate_property="latest_version",
            candidate_value="Windows 11",
            source=AnswerSource.STRUCTURED_KB,
            raw_confidence=0.90,
            is_hindi=True
        )
        assert res.verified is True
        assert res.grounding_status == GroundingStatus.GROUNDED
        assert "Windows 11" in str(res.grounded_fact)

    def test_historical_inquiry_not_flagged_as_freshness_requirement(self):
        verifier = get_answer_verifier()
        requires_fresh, trigger, cat = verifier.check_freshness_requirement("Who was the first prime minister of India?")
        assert requires_fresh is False
        assert trigger is None


class TestContradictionDetection:
    """Validates catching clashing or false facts against ground truth."""

    def test_contradictory_capital_detected(self):
        verifier = get_answer_verifier()
        res = verifier.verify_answer(
            query="What is the capital of India?",
            proposed_answer="Mumbai is the capital of India.",  # Contradictory assertion!
            candidate_entity="india",
            candidate_property="capital",
            candidate_value="Mumbai",
            source=AnswerSource.UNVERIFIED_HALLUCINATION,
            raw_confidence=0.85,
            is_hindi=False
        )
        assert res.verified is False
        assert res.is_contradictory is True
        assert res.grounding_status == GroundingStatus.CONTRADICTORY
        assert res.confidence_tier == ConfidenceTier.LOW
        assert "New Delhi" in str(res.contradiction_details)
        assert "Mumbai" in str(res.contradiction_details)
        assert "incorrect" in res.suggested_response.lower() or "contradiction" in res.suggested_response.lower()


class TestEndToEndKnowledgeEngineIntegration:
    """Validates end-to-end integration with KnowledgeEngine and KnowledgeRouter."""

    def test_static_fact_has_answer_verification_metadata(self):
        ke = get_knowledge_engine()
        result = ke.query("India ki capital kya hai?")
        assert result.found is True
        assert "New Delhi" in result.answer_text
        assert "answer_verification" in result.metadata
        verif = result.metadata["answer_verification"]
        assert verif["verified"] is True
        assert verif["grounding_status"] == "GROUNDED"
        assert verif["source"] == "STRUCTURED_KB"

    def test_leadership_query_has_freshness_metadata(self):
        ke = get_knowledge_engine()
        result = ke.query("India ka PM kaun hai?")
        assert result.found is True
        assert "Narendra Modi" in result.answer_text
        assert "answer_verification" in result.metadata
        verif = result.metadata["answer_verification"]
        assert verif["verified"] is True
        assert verif["requires_live_data"] is True

    def test_live_weather_refusal_is_verified_stale(self):
        ke = get_knowledge_engine()
        result = ke.query("aaj weather kya hai?")
        assert result.found is True
        assert result.needs_fresh_fetch is True
        assert "internet access" in result.answer_text.lower() or "live" in result.answer_text.lower()
        assert "answer_verification" in result.metadata
        verif = result.metadata["answer_verification"]
        assert verif["requires_live_data"] is True
        assert verif["grounding_status"] == "TIME_SENSITIVE_STALE"

    def test_windows_version_query_resolves_and_grounded(self):
        ke = get_knowledge_engine()
        result = ke.query("Windows ka latest version kya hai?")
        assert result.found is True
        assert "Windows 11" in result.answer_text
        assert "answer_verification" in result.metadata
        verif = result.metadata["answer_verification"]
        assert verif["verified"] is True
        assert verif["grounding_status"] == "GROUNDED"


class TestJarvisCoreIntegration:
    """Validates presence of AnswerVerificationEngine on JarvisCore."""

    def test_jarvis_core_has_answer_verifier(self):
        from core.app import JarvisCore
        core = JarvisCore()
        assert hasattr(core, "answer_verifier")
        assert core.answer_verifier is not None
        assert isinstance(core.answer_verifier, AnswerVerificationEngine)
