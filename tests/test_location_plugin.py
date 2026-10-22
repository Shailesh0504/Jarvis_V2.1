# tests/test_location_plugin.py
"""
Comprehensive Unit and Regression Tests for Jarvis Location & Universal Geography Plugin.
Validates:
- Universal worldwide place resolution (not hardcoded to Mumbai)
- Country, state, and continent hierarchical relationships
- Great-circle distance calculations via Haversine formula
- Zero-API web map and driving direction URL generation
- Nearby POI search query generation
- Natural Hindi, Hinglish, and English queries
- End-to-end integration with JarvisCore and semantic routing
"""

import os
import pytest
from plugins.location.database import LocationDatabase
from plugins.location.resolver import LocationResolver
from plugins.location.plugin import LocationPlugin
from core.app import JarvisCore
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def loc_resolver(tmp_path):
    db_path = str(tmp_path / "test_geo.db")
    db = LocationDatabase(db_path=db_path)
    return LocationResolver(db=db)


@pytest.fixture
def loc_plugin(tmp_path):
    return LocationPlugin()


@pytest.fixture
def core_app(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_location_app.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )
    return core


def test_worldwide_city_resolution(loc_resolver):
    """Verifies that place resolution works universally for international and Indian cities."""
    # 1. Mumbai
    mumbai = loc_resolver.get_location_info("Mumbai")
    assert mumbai.success is True
    assert mumbai.location.state_name == "Maharashtra"
    assert mumbai.location.country_name == "India"

    # 2. London
    london = loc_resolver.get_location_info("London")
    assert london.success is True
    assert london.location.country_name == "United Kingdom"
    assert london.location.continent == "Europe"

    # 3. Tokyo
    tokyo = loc_resolver.get_location_info("Tokyo")
    assert tokyo.success is True
    assert tokyo.location.country_name == "Japan"
    assert tokyo.location.continent == "Asia"

    # 4. Paris
    paris = loc_resolver.get_location_info("Paris")
    assert paris.success is True
    assert paris.location.country_name == "France"
    assert paris.location.continent == "Europe"


def test_landmarks_and_mountains(loc_resolver):
    """Verifies mountains and landmarks worldwide."""
    # Mount Everest
    everest = loc_resolver.get_location_info("Mount Everest")
    assert everest.success is True
    assert "Nepal" in everest.location.country_name

    # Taj Mahal
    taj = loc_resolver.get_location_info("Taj Mahal")
    assert taj.success is True
    assert taj.location.district_name == "Agra"
    assert taj.location.state_name == "Uttar Pradesh"


def test_country_info_and_capitals(loc_resolver):
    """Verifies country details including capital, continent, and state counts."""
    # India
    ind = loc_resolver.get_country_info("India")
    assert ind.success is True
    assert "New Delhi" in ind.formatted_answer

    # France
    fra = loc_resolver.get_country_info("France")
    assert fra.success is True
    assert "Paris" in fra.formatted_answer

    # USA states
    usa = loc_resolver.get_country_info("USA")
    assert usa.success is True
    assert "50 states" in usa.formatted_answer


def test_haversine_distance_calculation(loc_resolver):
    """Verifies great-circle spherical distance calculations."""
    # New York to Boston (approx 306 km / 190 miles)
    ny_bos = loc_resolver.calculate_distance("New York", "Boston")
    assert ny_bos.success is True
    dist_km = ny_bos.distance_info.distance_km
    assert 280 < dist_km < 340
    assert "maps/dir" in ny_bos.distance_info.directions_url

    # Delhi to Mumbai (approx 1148 km)
    del_mum = loc_resolver.calculate_distance("Delhi", "Mumbai")
    assert del_mum.success is True
    dist_del_mum = del_mum.distance_info.distance_km
    assert 1100 < dist_del_mum < 1200


def test_zero_api_map_and_direction_urls(loc_resolver):
    """Verifies zero-API Google Maps URL generation."""
    map_res = loc_resolver.open_map_in_browser("Paris")
    assert "google.com/maps/search/?api=1&query=Paris" in map_res.map_url

    dir_res = loc_resolver.open_directions_in_browser("Delhi", "Mumbai")
    assert "origin=Delhi" in dir_res.map_url
    assert "destination=Mumbai" in dir_res.map_url

    nearby_res = loc_resolver.search_nearby("restaurant")
    assert "restaurant+near+me" in nearby_res.map_url or "restaurant" in nearby_res.map_url


def test_end_to_end_location_queries(core_app):
    """Verifies end-to-end Hindi/Hinglish natural language routing through JarvisCore."""
    # 1. Mumbai kaha hai
    resp1 = core_app.process_input("Jarvis, Mumbai kaha hai?")
    assert "Maharashtra" in resp1
    assert "India" in resp1
    assert "Main samajh gaya Boss! Bataiye" not in resp1

    # 2. Delhi kis state mein hai
    resp2 = core_app.process_input("Jarvis, Delhi kis state mein hai?")
    assert "Delhi" in resp2
    assert "India" in resp2

    # 3. London kis country mein hai
    resp3 = core_app.process_input("Jarvis, London kis country mein hai?")
    assert "United Kingdom" in resp3

    # 4. India ki capital kya hai
    resp4 = core_app.process_input("Jarvis, India ki capital kya hai?")
    assert "New Delhi" in resp4

    # 5. Mount Everest kaha hai
    resp5 = core_app.process_input("Jarvis, Mount Everest kaha hai?")
    assert "Nepal" in resp5

    # 6. Distance query
    resp6 = core_app.process_input("Jarvis, New York se Boston kitna door hai?")
    assert "km" in resp6 or "miles" in resp6


def test_location_question_and_automatic_map_action(core_app):
    """
    Verifies that when asking location questions:
    1. A short, natural conversational spoken answer is given (without bulky cards/raw URLs).
    2. Google Maps is automatically opened/focused.
    3. Ambiguous queries (e.g. Washington) prompt for clarification and do NOT open the browser.
    """
    from unittest.mock import patch, MagicMock

    # 1. Mumbai
    with patch("webbrowser.open") as mock_open:
        resp_mumbai = core_app.process_input("Mumbai kaha hai?")
        assert "Maharashtra" in resp_mumbai
        assert "map" in resp_mumbai.lower()
        mock_open.assert_called_once()
        args, _ = mock_open.call_args
        assert "maps" in args[0].lower()
        assert "mumbai" in args[0].lower()

    # 2. Pune
    with patch("webbrowser.open") as mock_open:
        resp_pune = core_app.process_input("Pune kaha hai?")
        assert "Maharashtra" in resp_pune
        assert "map" in resp_pune.lower()
        mock_open.assert_called_once()
        args, _ = mock_open.call_args
        assert "maps" in args[0].lower()
        assert "pune" in args[0].lower()

    # 3. Goa
    with patch("webbrowser.open") as mock_open:
        resp_goa = core_app.process_input("Goa kaha hai?")
        assert "Goa" in resp_goa
        assert "map" in resp_goa.lower()
        mock_open.assert_called_once()
        args, _ = mock_open.call_args
        assert "maps" in args[0].lower()
        assert "goa" in args[0].lower()

    # 4. Ambiguous location: Washington
    with patch("webbrowser.open") as mock_open:
        resp_wash = core_app.process_input("Washington kaha hai?")
        assert "Washington, D.C." in resp_wash or "Washington State" in resp_wash
        # Browser must NOT be opened when clarification is required
        mock_open.assert_not_called()

