# tests/test_knowledge_engine.py
"""
Test Suite for the Jarvis General Knowledge Engine.
Validates:
1. Entity Store and multilingual attribute lookups across 16 categories
2. Synonym and phrasing normalization resolving to the same underlying facts
3. Scientific and conceptual reasoning explanations
4. Time-sensitive question gating and freshness routing
5. Anti-hallucination behavior for unknown queries
6. Complete separation of GK from capability questions and command execution
7. Dynamic learning updates
"""

import pytest
from core.knowledge import (
    get_knowledge_engine,
    ConfidenceLevel,
    KnowledgeCategory,
    KnowledgeSourceType
)
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType


@pytest.fixture
def ke():
    """Provides a fresh or singleton instance of KnowledgeEngine."""
    return get_knowledge_engine()


class TestKnowledgeFactualLookups:
    """Tests static factual knowledge across countries, capitals, states, currencies, planets, elements, etc."""

    def test_country_capitals_and_currencies(self, ke):
        # India
        res_hi = ke.query("India ki capital kya hai?")
        assert res_hi.found is True
        assert "New Delhi" in res_hi.answer_text
        assert res_hi.entity_id == "india"

        res_en = ke.query("What is the capital of India?")
        assert res_en.found is True
        assert "New Delhi" in res_en.answer_text

        res_curr = ke.query("India ka currency kya hai?")
        assert res_curr.found is True
        assert "Indian Rupee" in res_curr.answer_text

        # France
        res_fr = ke.query("France ki capital kya hai?")
        assert res_fr.found is True
        assert "Paris" in res_fr.answer_text

        # Japan
        res_jp = ke.query("Japan ki currency kya hai?")
        assert res_jp.found is True
        assert "Yen" in res_jp.answer_text

        # USA
        res_us = ke.query("What is the capital of USA?")
        assert res_us.found is True
        assert "Washington" in res_us.answer_text

    def test_phrasing_variations_resolve_to_same_fact(self, ke):
        """All variations must resolve to Entity: India, Property: capital."""
        queries = [
            "What is the capital of India?",
            "India ki capital kya hai?",
            "Bharat ki rajdhani kya hai?",
            "Tell me India's capital"
        ]
        for q in queries:
            res = ke.query(q)
            assert res.found is True, f"Failed for query: {q}"
            assert res.entity_id == "india", f"Wrong entity for query: {q}"
            assert res.property_name == "capital", f"Wrong property for query: {q}"
            assert "New Delhi" in res.answer_text, f"Wrong answer for query: {q}"

    def test_indian_states_and_capitals(self, ke):
        res_mh = ke.query("Maharashtra ki capital kya hai?")
        assert res_mh.found is True
        assert "Mumbai" in res_mh.answer_text

        res_kn = ke.query("Karnataka ki rajdhani kya hai?")
        assert res_kn.found is True
        assert "Bengaluru" in res_kn.answer_text

        res_up = ke.query("Uttar Pradesh ki capital kya hai?")
        assert res_up.found is True
        assert "Lucknow" in res_up.answer_text

    def test_planets_and_solar_system(self, ke):
        res_earth = ke.query("Earth ka closest planet kaunsa hai?")
        assert res_earth.found is True
        assert "Venus" in str(res_earth.property_value)

        res_jupiter = ke.query("Jupiter ke baare mein batao")
        assert res_jupiter.found is True
        assert "Brihaspati" in res_jupiter.answer_text or "Jupiter" in res_jupiter.answer_text

        res_light = ke.query("Speed of light kitni hoti hai?")
        assert res_light.found is True
        assert "299,792" in res_light.answer_text or "3 lakh" in res_light.answer_text

    def test_elements_and_chemistry(self, ke):
        res_water = ke.query("Water ka chemical formula kya hai?")
        assert res_water.found is True
        assert "H2O" in res_water.answer_text

        res_oxy = ke.query("Oxygen ka atomic number kya hai?")
        assert res_oxy.found is True
        assert "8" in str(res_oxy.property_value)

        res_hydro = ke.query("Hydrogen ka symbol kya hai?")
        assert res_hydro.found is True
        assert "H" in str(res_oxy.property_value) or "H" in res_hydro.answer_text

    def test_abbreviations(self, ke):
        res_cpu = ke.query("CPU ka full form kya hai?")
        assert res_cpu.found is True
        assert "Central Processing Unit" in res_cpu.answer_text

        res_ram = ke.query("RAM ka full form kya hai?")
        assert res_ram.found is True
        assert "Random Access Memory" in res_ram.answer_text

        res_isro = ke.query("ISRO ka full form kya hai?")
        assert res_isro.found is True
        assert "Indian Space Research Organisation" in res_isro.answer_text

        res_ai = ke.query("AI ka full form kya hai?")
        assert res_ai.found is True
        assert "Artificial Intelligence" in res_ai.answer_text

    def test_famous_people_and_inventions(self, ke):
        res_comp = ke.query("Computer kisne banaya tha?")
        assert res_comp.found is True
        assert "Charles Babbage" in res_comp.answer_text

        res_py = ke.query("Python kisne banaya tha?")
        assert res_py.found is True
        assert "Guido van Rossum" in res_py.answer_text

        res_bulb = ke.query("Thomas Edison ne kya banaya tha?")
        assert res_bulb.found is True
        assert "bulb" in res_bulb.answer_text.lower() or "light bulb" in res_bulb.answer_text.lower()

    def test_indian_gk(self, ke):
        res_fn = ke.query("Father of the nation kaun hain?")
        assert res_fn.found is True
        assert "Mahatma Gandhi" in res_fn.answer_text

        res_const = ke.query("Dr BR Ambedkar kaun the?")
        assert res_const.found is True
        assert "Samvidhan" in res_const.answer_text or "Constitution" in res_const.answer_text

        res_ind = ke.query("India kab aazad hua tha?")
        assert res_ind.found is True
        assert "15 August 1947" in res_ind.answer_text

        res_rep = ke.query("Republic Day kab hota hai?")
        assert res_rep.found is True
        assert "26 January 1950" in res_rep.answer_text or "26 January" in res_rep.answer_text


class TestKnowledgeReasoning:
    """Tests conceptual science explanations."""

    def test_why_sky_blue(self, ke):
        res_en = ke.query("Why does the sky appear blue?")
        assert res_en.found is True
        assert res_en.source_type == KnowledgeSourceType.REASONING
        assert "Rayleigh scattering" in res_en.answer_text or "scatter" in res_en.answer_text.lower()

        res_hi = ke.query("Aasman neela kyun dikhta hai?")
        assert res_hi.found is True
        assert "scattering" in res_hi.answer_text.lower() or "blue light" in res_hi.answer_text.lower()

    def test_photosynthesis(self, ke):
        res = ke.query("Photosynthesis kya hota hai?")
        assert res.found is True
        assert res.source_type == KnowledgeSourceType.REASONING
        assert "plants" in res.answer_text.lower() or "sunlight" in res.answer_text.lower()

    def test_gravity(self, ke):
        res = ke.query("Explain gravity simply")
        assert res.found is True
        assert res.source_type == KnowledgeSourceType.REASONING
        assert "force" in res.answer_text.lower() or "mass" in res.answer_text.lower()

    def test_stars_twinkle(self, ke):
        res = ke.query("Taare kyun timtimate hain?")
        assert res.found is True
        assert res.source_type == KnowledgeSourceType.REASONING
        assert "refraction" in res.answer_text.lower() or "atmosphere" in res.answer_text.lower()


class TestKnowledgeTimeSensitiveAndUnknowns:
    """Tests current time-sensitive queries and anti-hallucination behavior."""

    def test_current_leadership(self, ke):
        res_pm = ke.query("Who is the current Prime Minister of India?")
        assert res_pm.found is True
        assert "Narendra Modi" in res_pm.answer_text
        assert res_pm.is_time_sensitive is True

        res_pres = ke.query("Bharat ke current President kaun hain?")
        assert res_pres.found is True
        assert "Droupadi Murmu" in res_pres.answer_text

    def test_time_sensitive_fresh_requirements(self, ke):
        res_w = ke.query("Today's weather?")
        assert res_w.is_time_sensitive is True
        assert res_w.needs_fresh_fetch is True

        res_s = ke.query("Current stock price?")
        assert res_s.is_time_sensitive is True
        assert res_s.needs_fresh_fetch is True

    def test_unknown_questions_anti_hallucination(self, ke):
        """Jarvis must NEVER fabricate an answer for unknown or unverifiable queries."""
        unknown_queries = [
            "What is the capital of Atlantis?",
            "Quantum flux rate of kryptonite kya hai?",
            "What is the secret formula of xyz123?"
        ]
        for uq in unknown_queries:
            res = ke.query(uq)
            assert res.found is False
            assert res.confidence == ConfidenceLevel.LOW
            assert "reliable" in res.answer_text.lower() or "jaankari" in res.answer_text.lower()


class TestSeparationFromCommandsAndCapabilities:
    """Tests that capability questions and commands are NEVER hijacked by the GK Engine."""

    def test_capability_question_remains_capability(self):
        conv = ConversationalIntentClassifier.classify("kya tum system lock kar sakte ho?")
        assert conv.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
        assert conv.is_executable is False

        conv_chrome = ConversationalIntentClassifier.classify("can you open Chrome?")
        assert conv_chrome.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
        assert conv_chrome.is_executable is False

    def test_action_command_remains_executable(self):
        conv = ConversationalIntentClassifier.classify("system lock karo")
        assert conv.intent_type == ConversationalIntentType.ACTION_COMMAND
        assert conv.is_executable is True

    def test_router_rejects_capability_questions(self, ke):
        assert ke.is_knowledge_candidate("kya tum system lock kar sakte ho?") is False
        assert ke.is_knowledge_candidate("can you restart the computer?") is False


class TestDynamicLearningUpdates:
    """Tests that new facts can be dynamically learned and queried."""

    def test_learn_fact(self, ke):
        success = ke.learn_fact(
            entity_id="mars",
            property_name="highest_volcano",
            value="Olympus Mons (21.9 km high)",
            category=KnowledgeCategory.PLANETS
        )
        assert success is True

        # Now query the newly learned fact
        res = ke.query("Mars ka highest volcano kaunsa hai?")
        assert res.found is True
        assert "Olympus Mons" in res.answer_text
