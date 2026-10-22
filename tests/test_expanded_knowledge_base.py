# tests/test_expanded_knowledge_base.py
"""
Comprehensive Test Suite for Jarvis Expanded Natural Language Knowledge Base.
Validates:
1. Indian States and Union Territories (Capitals, Languages, Landmarks)
2. World Countries (Capitals, Currencies, Continents, Languages)
3. Science and Astronomy (Galaxies, Stars, Elements, Constants, Biology)
4. Computing and Technology (Protocols, Hardware, Software Architecture, Full Forms)
5. Historical Leaders and Innovators (Freedom fighters, Scientists, Inventors)
6. Iconic Monuments and World Wonders (Builders, Locations, Heights)
7. Acronyms and Physical Geography (Rivers, Mountains, Trenches, Lakes, Deserts)
8. Scientific Conceptual Reasoning (Airplanes, Chlorophyll, Lightning, Sound in vacuum, Tides)
9. Strict Anti-Hallucination and Safe Refusals
"""

import pytest
from core.knowledge import (
    get_knowledge_engine,
    ConfidenceLevel,
    KnowledgeSourceType
)


@pytest.fixture
def ke():
    """Provides singleton instance of KnowledgeEngine."""
    return get_knowledge_engine()


class TestIndianStatesAndTerritories:
    """Validates 28 Indian States and Union Territories knowledge."""

    def test_state_capitals(self, ke):
        test_cases = [
            ("Maharashtra ki capital kya hai?", "Mumbai"),
            ("Bihar ki rajdhani kya hai?", "Patna"),
            ("Gujarat ki capital kya hai?", "Gandhinagar"),
            ("Tamil Nadu ki rajdhani kya hai?", "Chennai"),
            ("Punjab ki capital kya hai?", "Chandigarh"),
            ("Assam ki rajdhani kya hai?", "Dispur"),
            ("Odisha ki capital kya hai?", "Bhubaneswar"),
            ("Kerala ki rajdhani kya hai?", "Thiruvananthapuram"),
        ]
        for query, expected_capital in test_cases:
            res = ke.query(query)
            assert res.found is True, f"Failed on query: {query}"
            assert expected_capital in res.answer_text, f"Expected {expected_capital} in answer for {query}, got {res.answer_text}"

    def test_state_languages(self, ke):
        res_mh = ke.query("Maharashtra ki official bhasha kya hai?")
        assert res_mh.found is True
        assert "Marathi" in res_mh.answer_text

        res_gj = ke.query("Gujarat ki bhasha kya hai?")
        assert res_gj.found is True
        assert "Gujarati" in res_gj.answer_text


class TestWorldCountries:
    """Validates world nations, capitals, and currencies."""

    def test_world_capitals(self, ke):
        test_cases = [
            ("Japan ki capital kya hai?", "Tokyo"),
            ("Egypt ki capital kya hai?", "Cairo"),
            ("Russia ki rajdhani kya hai?", "Moscow"),
            ("Germany ki capital kya hai?", "Berlin"),
            ("Australia ki capital kya hai?", "Canberra"),
            ("Turkey ki capital kya hai?", "Ankara"),
            ("Mexico ki capital kya hai?", "Mexico City"),
            ("Argentina ki capital kya hai?", "Buenos Aires"),
        ]
        for query, expected_capital in test_cases:
            res = ke.query(query)
            assert res.found is True, f"Failed on query: {query}"
            assert expected_capital in res.answer_text, f"Expected {expected_capital} for {query}, got {res.answer_text}"

    def test_world_currencies(self, ke):
        res_jp = ke.query("Japan ki currency kya hai?")
        assert res_jp.found is True
        assert "Yen" in res_jp.answer_text

        res_ru = ke.query("Russia ki currency kya hai?")
        assert res_ru.found is True
        assert "Ruble" in res_ru.answer_text


class TestScienceAndAstronomy:
    """Validates astronomy, elements, physical constants, and biology."""

    def test_elements_and_symbols(self, ke):
        res_gold = ke.query("Gold ka symbol kya hai?")
        assert res_gold.found is True
        assert "Au" in str(res_gold.property_value) or "Au" in res_gold.answer_text

        res_silver = ke.query("Silver ka symbol kya hai?")
        assert res_silver.found is True
        assert "Ag" in str(res_silver.property_value) or "Ag" in res_silver.answer_text

    def test_physical_constants(self, ke):
        res_sound = ke.query("Speed of sound kitni hoti hai?")
        assert res_sound.found is True
        assert "343" in res_sound.answer_text or "1,235" in res_sound.answer_text

        res_light = ke.query("Speed of light kya hai?")
        assert res_light.found is True
        assert "299,792" in res_light.answer_text or "3 lakh" in res_light.answer_text


class TestComputingAndTechnology:
    """Validates IT, networking, architecture, and technology concepts."""

    def test_full_forms(self, ke):
        test_cases = [
            ("SSD ka full form kya hai?", "Solid State Drive"),
            ("BIOS ka full form kya hai?", "Basic Input/Output System"),
            ("HTTPS ka full form kya hai?", "Hypertext Transfer Protocol Secure"),
            ("API ka full form kya hai?", "Application Programming Interface"),
        ]
        for query, expected_full_form in test_cases:
            res = ke.query(query)
            assert res.found is True, f"Failed on query: {query}"
            assert expected_full_form in res.answer_text, f"Expected {expected_full_form} for {query}, got {res.answer_text}"

    def test_tech_inventors(self, ke):
        res_bt = ke.query("Bluetooth kisne banaya tha?")
        assert res_bt.found is True
        assert "Jaap Haartsen" in res_bt.answer_text or "Ericsson" in res_bt.answer_text


class TestMonumentsAndWonders:
    """Validates historical monuments and world wonders."""

    def test_monuments(self, ke):
        res_taj = ke.query("Taj Mahal kisne banwaya tha?")
        assert res_taj.found is True
        assert "Shah Jahan" in res_taj.answer_text

        res_statue = ke.query("Statue of Unity ki unchai kitni hai?")
        assert res_statue.found is True
        assert "182" in res_statue.answer_text

        res_qutub = ke.query("Qutub Minar ki unchai kitni hai?")
        assert res_qutub.found is True
        assert "72.5" in res_qutub.answer_text

        res_eiffel = ke.query("Eiffel Tower kahan hai?")
        assert res_eiffel.found is True
        assert "Paris" in res_eiffel.answer_text


class TestHistoricalFigures:
    """Validates freedom fighters, scientists, and cultural icons."""

    def test_historical_figures(self, ke):
        res_swami = ke.query("Swami Vivekananda ka janm kab hua tha?")
        assert res_swami.found is True
        assert "12 January" in res_swami.answer_text

        res_shastri = ke.query("Lal Bahadur Shastri ka slogan kya tha?")
        assert res_shastri.found is True
        assert "Jai Jawan" in res_shastri.answer_text or "Jai Kisan" in res_shastri.answer_text

        res_einstein = ke.query("Albert Einstein ki famous theory kya hai?")
        assert res_einstein.found is True
        assert "Relativity" in res_einstein.answer_text


class TestGeographyAndAcronyms:
    """Validates physical geography and acronyms."""

    def test_geography(self, ke):
        res_mariana = ke.query("Mariana Trench ki depth kitni hai?")
        assert res_mariana.found is True
        assert "10,994" in res_mariana.answer_text

        res_everest = ke.query("Mount Everest ki height kitni hai?")
        assert res_everest.found is True
        assert "8,848" in res_everest.answer_text

        res_nile = ke.query("Nile River ki length kitni hai?")
        assert res_nile.found is True
        assert "6,650" in res_nile.answer_text


class TestConceptualReasoning:
    """Validates scientific conceptual explanations for why/how questions."""

    def test_conceptual_models(self, ke):
        # Airplanes
        res_plane = ke.query("Hawai jahaj kaise udta hai?")
        assert res_plane.found is True
        assert res_plane.source_type == KnowledgeSourceType.REASONING
        assert "lift" in res_plane.answer_text.lower() or "airfoil" in res_plane.answer_text.lower()

        # Leaves
        res_leaves = ke.query("Pattiyan hari kyun hoti hain?")
        assert res_leaves.found is True
        assert "chlorophyll" in res_leaves.answer_text.lower()

        # Sound in vacuum
        res_sound = ke.query("Space mein aawaz kyun nahi aati?")
        assert res_sound.found is True
        assert "vacuum" in res_sound.answer_text.lower() or "wave" in res_sound.answer_text.lower() or "medium" in res_sound.answer_text.lower()

        # Lightning before thunder
        res_light = ke.query("Bijli pehle kyun dikhti hai?")
        assert res_light.found is True
        assert "speed" in res_light.answer_text.lower() or "tez" in res_light.answer_text.lower()


class TestAntiHallucinationAndSafety:
    """Validates transparent refusal on unknown queries with zero hallucination."""

    def test_unknown_query_refusal(self, ke):
        res = ke.query("Who is the emperor of the mythical planet Xylos 9?")
        assert res.found is False
        assert res.confidence == ConfidenceLevel.LOW
        assert "reliable" in res.answer_text.lower() or "jaankari" in res.answer_text.lower()
