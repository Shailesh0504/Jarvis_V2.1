# tests/test_web_product_search.py
"""
Tests for Generic Web Search & Product Discovery capability in Jarvis V2.
Verifies NLU entity extraction (site, query, price filters), site-aware URL generation,
browser launch verification, structured results, and end-to-end task planner execution.
"""

from unittest.mock import MagicMock, patch
import pytest

from brain.semantic_parser import HinglishNLUParser, SemanticAction
from core.app import JarvisCore
from core.intent import Intent, IntentType
from core.planner import TaskPlanner
from core.executor import PlanExecutor
from memory.memory_manager import MemoryManager
from brain.response import ResponseGenerator
from brain.llm import MockLLMProvider
from plugins.manager import PluginManager
from plugins.browser.plugin import BrowserPlugin
from plugins.browser.search_adapters import (
    BaseSearchAdapter,
    SearchSiteRegistry,
    SearchUrlResult
)


@pytest.fixture
def jarvis_core(tmp_path):
    core = JarvisCore()
    db_path = str(tmp_path / "test_search.db")
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


class TestNLUProductDiscoveryParser:
    """Test suite for Hinglish, Hindi, and English product discovery intent parsing."""

    def test_hindi_flipkart_shoes(self):
        act = HinglishNLUParser.parse("mujhe Flipkart pe ek shoes dikhao")
        assert act is not None
        assert act.intent == "WEB_SEARCH"
        assert act.service == "browser"
        assert act.action == "search_website"
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "shoes"

    def test_hindi_amazon_mobile(self):
        act = HinglishNLUParser.parse("Amazon pe mobile dikhao")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "mobile"

    def test_hindi_blinkit_milk(self):
        act = HinglishNLUParser.parse("Blinkit pe milk dikhao")
        assert act is not None
        assert act.parameters["site"] == "blinkit"
        assert act.parameters["query"] == "milk"

    def test_hindi_flipkart_nike_shoes_search_karo(self):
        act = HinglishNLUParser.parse("Flipkart pe Nike shoes search karo")
        assert act is not None
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "Nike shoes"

    def test_hindi_amazon_par_laptop_dikhao(self):
        act = HinglishNLUParser.parse("Amazon par laptop dikhao")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "laptop"

    def test_hinglish_price_filter_ke_andar(self):
        act = HinglishNLUParser.parse("Amazon pe 50000 ke andar laptop dikhao")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "laptop"
        assert act.parameters["filters"]["max_price"] == 50000
        assert act.parameters["max_price"] == 50000

    def test_hinglish_price_filter_ke_niche_phone(self):
        act = HinglishNLUParser.parse("Flipkart par 20000 ke niche phone search karo")
        assert act is not None
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "phone"
        assert act.parameters["filters"]["max_price"] == 20000

    def test_hinglish_k_suffix_price(self):
        act = HinglishNLUParser.parse("Amazon pe 50k ke andar laptop dikhao")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "laptop"
        assert act.parameters["filters"]["max_price"] == 50000

    def test_hinglish_min_price_se_upar(self):
        act = HinglishNLUParser.parse("Amazon par 1500 se upar headphones dikhao")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "headphones"
        assert act.parameters["filters"]["min_price"] == 1500

    def test_english_show_shoes_on_flipkart(self):
        act = HinglishNLUParser.parse("show shoes on Flipkart")
        assert act is not None
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "shoes"

    def test_english_search_milk_on_blinkit(self):
        act = HinglishNLUParser.parse("search milk on Blinkit")
        assert act is not None
        assert act.parameters["site"] == "blinkit"
        assert act.parameters["query"] == "milk"

    def test_english_find_laptop_under_60000_on_amazon(self):
        act = HinglishNLUParser.parse("find laptop under 60000 on Amazon")
        assert act is not None
        assert act.parameters["site"] == "amazon"
        assert act.parameters["query"] == "laptop"
        assert act.parameters["filters"]["max_price"] == 60000

    def test_query_first_site_last(self):
        act = HinglishNLUParser.parse("shoes dikhao Flipkart pe")
        assert act is not None
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "shoes"

    def test_multi_word_query(self):
        act = HinglishNLUParser.parse("Flipkart pe Nike running shoes dikhao")
        assert act is not None
        assert act.parameters["site"] == "flipkart"
        assert act.parameters["query"] == "Nike running shoes"

    def test_unknown_website_target(self):
        act = HinglishNLUParser.parse("Croma pe OLED TV dikhao")
        assert act is not None
        assert act.parameters["site"] == "croma"
        assert act.parameters["query"] == "OLED TV"

    def test_desktop_system_not_mistaken_as_website(self):
        # Must not be parsed as WEB_SEARCH
        act = HinglishNLUParser.parse("desktop pe test naam ka folder banao")
        if act is not None:
            assert act.intent != "WEB_SEARCH"


class TestSearchSiteRegistryAndAdapters:
    """Test site-specific URL adapters, encoding, and filters."""

    def test_flipkart_url_adapter(self):
        res = SearchSiteRegistry.build_search_url("flipkart", "Nike shoes")
        assert res.site_name == "Flipkart"
        assert "https://www.flipkart.com/search?q=Nike+shoes" in res.url

    def test_flipkart_with_max_price(self):
        res = SearchSiteRegistry.build_search_url("flipkart", "shoes", filters={"max_price": 2000})
        assert "https://www.flipkart.com/search?q=shoes" in res.url
        assert "facets.price_range.to" in res.url

    def test_amazon_url_adapter(self):
        res = SearchSiteRegistry.build_search_url("amazon", "laptop")
        assert res.site_name == "Amazon"
        assert "https://www.amazon.in/s?k=laptop" in res.url

    def test_amazon_with_max_price_paise(self):
        res = SearchSiteRegistry.build_search_url("amazon", "laptop", filters={"max_price": 50000})
        assert "https://www.amazon.in/s?k=laptop" in res.url
        # 50000 INR = 5000000 paise
        assert "5000000" in res.url

    def test_blinkit_url_adapter(self):
        res = SearchSiteRegistry.build_search_url("blinkit", "milk")
        assert res.site_name == "Blinkit"
        assert "https://blinkit.com/s/?q=milk" in res.url

    def test_unknown_site_fallback(self):
        res = SearchSiteRegistry.build_search_url("croma", "TV")
        assert res.adapter_used == "fallback_google"
        assert "google.com/search" in res.url
        assert "site:croma.com" in res.url
        assert "TV" in res.url

    def test_dynamic_custom_site_registration(self):
        class CustomStoreAdapter(BaseSearchAdapter):
            def build_search_url(self, query, filters=None):
                return SearchUrlResult(
                    site_key="customstore",
                    site_name="CustomStore",
                    url=f"https://customstore.com/find?item={query}",
                    adapter_used="specific",
                    query=query,
                    filters=filters or {}
                )

        SearchSiteRegistry.register_adapter("customstore", CustomStoreAdapter(), aliases=["mycustomshop"])
        res = SearchSiteRegistry.build_search_url("mycustomshop", "watch")
        assert res.site_name == "CustomStore"
        assert res.url == "https://customstore.com/find?item=watch"


class TestBrowserPluginExecutionAndVerification:
    """Test BrowserPlugin search_website execution and navigation verification."""

    def test_search_website_success(self):
        plugin = BrowserPlugin()
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = plugin.execute("search_website", {
                "site": "flipkart",
                "query": "shoes"
            })
            assert result.success is True
            assert mock_open.called
            data = result.data
            assert data["site"] == "Flipkart"
            assert data["query"] == "shoes"
            assert "https://www.flipkart.com/search?q=shoes" in data["url"]
            assert data["success"] is True
            assert data["error"] is None
            assert "results dikha diye hain" in data["message"]

    def test_search_website_failure_verification(self):
        plugin = BrowserPlugin()
        # Mock browser failing to launch
        with patch("webbrowser.open", return_value=False) as mock_open:
            result = plugin.execute("search_website", {
                "site": "flipkart",
                "query": "shoes"
            })
            assert result.success is False
            assert "mana kar diya" in result.error
            # Never say "dikha diya" on failure
            assert "results dikha diye hain" not in (result.data.get("message") or "")


class TestTaskPlannerAndCoreIntegration:
    """Test end-to-end integration via TaskPlanner, Executor, and JarvisCore."""

    def test_task_planner_and_executor(self):
        plugins = PluginManager(plugin_dir="plugins")
        plugins.discover_and_load()
        planner = TaskPlanner()
        executor = PlanExecutor(plugin_manager=plugins)

        intent = Intent(
            name="web_search",
            type=IntentType.COMMAND,
            target_plugin="browser",
            target_action="search_website",
            entities={"site": "amazon", "query": "laptop", "max_price": 50000}
        )
        plan = planner.create_plan_from_intent(intent)
        assert len(plan.steps) == 1
        assert plan.steps[0].plugin_name == "browser"
        assert plan.steps[0].action_name == "search_website"

        with patch("webbrowser.open", return_value=True) as mock_open:
            results = executor.execute_plan(plan)
            assert len(results) == 1
            assert results[0].success is True
            assert mock_open.called
            assert "laptop" in results[0].data["query"]

    def test_jarvis_core_process_input_flipkart_shoes(self, jarvis_core):
        with patch("webbrowser.open", return_value=True) as mock_open:
            response = jarvis_core.process_input("mujhe Flipkart pe ek shoes dikhao")
            assert mock_open.called
            assert "Flipkart" in response
            assert "shoes" in response.lower()
            assert "dikha diye hain" in response
            # Active context updated
            assert jarvis_core.active_context.website == "flipkart"
            assert jarvis_core.active_context.last_search_query == "shoes"
            assert jarvis_core.active_context.last_action == "search_products"

    def test_jarvis_core_process_input_amazon_laptop_with_price(self, jarvis_core):
        with patch("webbrowser.open", return_value=True) as mock_open:
            response = jarvis_core.process_input("Amazon pe 50000 ke andar laptop dikhao")
            assert mock_open.called
            assert "Amazon" in response
            assert "laptop" in response.lower()
            assert "50000 ke andar" in response
            assert "dikha diye hain" in response
            assert jarvis_core.active_context.website == "amazon"

    def test_jarvis_core_process_input_blinkit_milk(self, jarvis_core):
        with patch("webbrowser.open", return_value=True) as mock_open:
            response = jarvis_core.process_input("Blinkit pe milk dikhao")
            assert mock_open.called
            assert "Blinkit" in response
            assert "milk" in response.lower()
            assert jarvis_core.active_context.website == "blinkit"

    def test_jarvis_core_navigation_failure_never_claims_success(self, jarvis_core):
        with patch("webbrowser.open", return_value=False):
            response = jarvis_core.process_input("Flipkart pe shoes dikhao")
            assert "dikha diye hain" not in response
            assert "mana kar diya" in response or "failed" in response.lower()
