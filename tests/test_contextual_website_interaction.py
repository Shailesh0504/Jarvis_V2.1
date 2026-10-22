# tests/test_contextual_website_interaction.py
"""
Regression and integration tests for Contextual Website Interaction & ActiveTargetContext.
Verifies that after opening a website, natural follow-up requests operate on that active
website without generic conversation fallback or "aage kya karna hai?" prompts.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.app import JarvisCore
from core.context import ActiveTargetContext
from core.contextual_resolver import ContextualActionResolver, ContextualActionResult
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager


@pytest.fixture
def jarvis_core(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_context.db")
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


def test_flipkart_open_then_shoes_dikhao(jarvis_core):
    """
    Test 1: User opens Flipkart, then asks 'shoes dikhao'.
    Must resolve as a search for 'shoes' on Flipkart.
    """
    with patch("webbrowser.open") as mock_open:
        # Turn 1: Open Flipkart
        resp1 = jarvis_core.process_input("Flipkart open karo")
        assert "Flipkart" in resp1 or "open" in resp1.lower()
        assert jarvis_core.active_context.website == "flipkart"

        # Turn 2: Follow-up query
        resp2 = jarvis_core.process_input("shoes dikhao")
        assert "Flipkart" in resp2
        assert "Shoes" in resp2
        assert "search kar diya" in resp2
        assert jarvis_core.active_context.last_search_query == "shoes"
        assert jarvis_core.active_context.last_action == "search_products"
        mock_open.assert_called()


def test_flipkart_open_then_compound_conversational_shoes(jarvis_core, caplog):
    """
    Test 2: User opens Flipkart, then says 'mujhe ek shoes lena hai to shoes dikhao'.
    Must normalize Hinglish preamble and search for 'shoes' on Flipkart.
    """
    caplog.set_level("INFO")
    with patch("webbrowser.open") as mock_open:
        jarvis_core.process_input("Flipkart open karo")
        assert jarvis_core.active_context.website == "flipkart"

        resp = jarvis_core.process_input("mujhe ek shoes lena hai to shoes dikhao")
        assert "Flipkart" in resp
        assert "Shoes" in resp
        assert jarvis_core.active_context.last_search_query == "shoes"

        # Verify structured logs
        logs = caplog.text
        assert "ACTIVE_CONTEXT" in logs
        assert "CONTEXT_RESOLUTION" in logs
        assert "CONTEXT_TARGET website=flipkart" in logs
        assert "CONTEXTUAL_INTENT" in logs
        assert "ENTITY_EXTRACTED" in logs
        assert "PLUGIN_SELECTED" in logs
        assert "ACTION_EXECUTED" in logs
        assert "RESULT_VERIFIED" in logs


def test_amazon_open_then_running_shoes(jarvis_core):
    """
    Test 3: User opens Amazon, then says 'mujhe running shoes dikhao'.
    Must search 'running shoes' on Amazon.
    """
    with patch("webbrowser.open") as mock_open:
        jarvis_core.process_input("Amazon open karo")
        assert jarvis_core.active_context.website == "amazon"

        resp = jarvis_core.process_input("mujhe running shoes dikhao")
        assert "Amazon" in resp
        assert "Running Shoes" in resp
        assert jarvis_core.active_context.last_search_query == "running shoes"


def test_youtube_open_then_arijit_singh_song(jarvis_core):
    """
    Test 4: User opens YouTube, then says 'Arijit Singh ka gana chalao'.
    Must execute media playback / search on YouTube.
    """
    with patch("webbrowser.open") as mock_open:
        jarvis_core.process_input("YouTube open karo")
        assert jarvis_core.active_context.website == "youtube"

        resp = jarvis_core.process_input("Arijit Singh ka gana chalao")
        assert "YouTube" in resp
        assert "Arijit Singh" in resp
        assert jarvis_core.active_context.last_action == "play_video"


def test_google_open_then_weather_search(jarvis_core):
    """
    Test 5: User opens Google, then says 'weather search karo'.
    Must search Google for weather.
    """
    with patch("webbrowser.open") as mock_open:
        jarvis_core.process_input("Google open karo")
        assert jarvis_core.active_context.website == "google"

        resp = jarvis_core.process_input("weather search karo")
        assert "Google" in resp
        assert "Weather" in resp
        assert jarvis_core.active_context.last_search_query == "weather"


def test_context_persistence_across_multiple_turns_and_replacement(jarvis_core):
    """
    Test 6: Multi-turn persistence across multiple searches, and replacement when switching target.
    """
    with patch("webbrowser.open"):
        # 1. Open Flipkart
        jarvis_core.process_input("Flipkart open karo")
        assert jarvis_core.active_context.website == "flipkart"

        # 2. Search 1 on Flipkart
        resp1 = jarvis_core.process_input("laptop dikhao")
        assert "Flipkart" in resp1 and "Laptop" in resp1
        assert jarvis_core.active_context.last_search_query == "laptop"

        # 3. Search 2 on Flipkart (same active context preserved)
        resp2 = jarvis_core.process_input("isme wireless mouse search karo")
        assert "Flipkart" in resp2 and "Wireless Mouse" in resp2
        assert jarvis_core.active_context.last_search_query == "wireless mouse"

        # 4. Explicitly switch target to YouTube
        jarvis_core.process_input("YouTube open karo")
        assert jarvis_core.active_context.website == "youtube"

        # 5. Follow-up operates on the new active target (YouTube)
        resp3 = jarvis_core.process_input("Python tutorial search karo")
        assert "YouTube" in resp3 or "Python Tutorial" in resp3


def test_navigation_and_cart_actions_on_active_website(jarvis_core):
    """
    Test 7: Navigation follow-ups like 'ye wala kholo' or 'isey cart mein daalo'.
    """
    with patch("webbrowser.open"):
        jarvis_core.active_context.set_website("flipkart")
        
        resp_nav = jarvis_core.process_input("ye wala kholo")
        assert "Flipkart" in resp_nav and "pehla result" in resp_nav

        resp_cart = jarvis_core.process_input("isey cart mein daalo")
        assert "Flipkart" in resp_cart and "cart" in resp_cart.lower()


def test_generic_custom_domain_contextual_search():
    """
    Test 8: Generic custom website domain support.
    """
    context = ActiveTargetContext()
    context.set_website("github", domain="github.com")

    with patch("webbrowser.open") as mock_open:
        result = ContextualActionResolver.resolve("react repositories dikhao", context)
        assert result.handled is True
        assert result.target == "github"
        assert "Github" in result.response_message or "github.com" in result.response_message
        mock_open.assert_called()
