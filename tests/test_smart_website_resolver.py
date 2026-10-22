"""Regression coverage for persistent, user-learned website resolution."""

import pytest
from unittest.mock import MagicMock, patch

from brain.semantic_parser import HinglishNLUParser
from core.app import JarvisCore
from core.website_knowledge import WebsiteKnowledgeStore
from core.target_engine import TargetRequest, UniversalTargetDiscoveryEngine
from plugins.manifest import PluginResult
from plugins.browser.website_resolver import AmbiguousWebsiteError, UnknownWebsiteError, WebsiteResolver


@pytest.fixture
def website_store(tmp_path):
    store = WebsiteKnowledgeStore(str(tmp_path / "website_knowledge.db"))
    WebsiteResolver.configure_knowledge_store(store)
    yield store
    WebsiteResolver.configure_knowledge_store(None)


def test_learned_website_resolves_exact_hinglish_natural_and_stt_variants(website_store):
    website_store.learn("human 3d", "https://www.zygotebody.com/")

    for request in (
        "open human 3d",
        "human 3d kholo",
        "human body ka 3d wala site open karo",
        "3d human body wala site open karo",
        "human 3d type kholo",
    ):
        resolution = WebsiteResolver.resolve(request)
        assert resolution.final_url == "https://www.zygotebody.com/"
        assert resolution.source == "user_learned"
        assert resolution.confidence >= 0.90


def test_unknown_phrase_never_becomes_an_invented_domain(website_store):
    with pytest.raises(UnknownWebsiteError):
        WebsiteResolver.resolve("xyz portal")


def test_learning_persists_and_explicit_correction_updates_the_same_mapping(tmp_path):
    db_path = str(tmp_path / "website_knowledge.db")
    first_store = WebsiteKnowledgeStore(db_path)
    first_store.learn("human 3d", "https://www.zygotebody.com/")
    first_store.learn("human 3d", "https://example.com/new-body")

    restarted_store = WebsiteKnowledgeStore(db_path)
    WebsiteResolver.configure_knowledge_store(restarted_store)
    try:
        resolution = WebsiteResolver.resolve("human 3d wali website kholo")
        assert resolution.final_url == "https://example.com/new-body"
        assert len(restarted_store.list_entries()) == 1
    finally:
        WebsiteResolver.configure_knowledge_store(None)


def test_close_learned_mappings_are_reported_as_ambiguous(website_store):
    website_store.learn("alpha beta gamma", "https://first.example.com")
    website_store.learn("alpha beta delta", "https://second.example.com")

    with pytest.raises(AmbiguousWebsiteError):
        WebsiteResolver.resolve("open alpha beta")


def test_multiword_teaching_command_is_parsed_without_hardcoded_site_rules():
    action = HinglishNLUParser.parse(
        "jab bhi main xyz portal bolun to https://example.com open karna"
    )
    assert action is not None
    assert action.action == "learn_alias"
    assert action.parameters == {
        "alias": "xyz portal",
        "target": "https://example.com",
        "action_type": "OPEN_WEBSITE",
    }


def test_unknown_request_then_url_reply_teaches_the_active_website_workflow(tmp_path):
    core = JarvisCore()
    store = WebsiteKnowledgeStore(str(tmp_path / "website_knowledge.db"))
    core.website_knowledge = store
    WebsiteResolver.configure_knowledge_store(store)
    try:
        prompt = core.process_input("open human 3d", source="test")
        assert "kis webpage" in prompt

        learned = core.process_input("https://www.zygotebody.com/", source="test")
        assert "human 3d" in learned.lower()
        assert WebsiteResolver.resolve("3d human body wala site open karo").final_url == "https://www.zygotebody.com/"
    finally:
        WebsiteResolver.configure_knowledge_store(None)


def test_resolved_url_is_the_only_value_sent_to_browser_and_launch_success_is_reported():
    plugin_manager = MagicMock()
    plugin_manager.execute_action.return_value = PluginResult(
        success=True,
        data={"status": "opened", "url": "https://www.zygotebody.com/", "verification": "unknown"},
    )
    verifier = MagicMock()
    verifier.verify_browser_opened.return_value = MagicMock(verified=False)
    engine = UniversalTargetDiscoveryEngine(plugin_manager=plugin_manager, verifier=verifier)

    outcome = engine.execute(TargetRequest(
        target="open human 3d view",
        action="open",
        resolved_url="https://www.zygotebody.com/",
        display_name="Human 3D View",
    ))

    assert outcome.success is True
    assert outcome.status == "verification_unknown"
    assert outcome.url == "https://www.zygotebody.com/"
    assert outcome.verification == "unknown"
    assert outcome.message == "Opening Human 3D View."
    assert plugin_manager.execute_action.call_args.args == (
        "browser", "open_website", {"site": "https://www.zygotebody.com/"},
    )


def test_actual_browser_launch_failure_is_reported_as_failed():
    plugin_manager = MagicMock()
    plugin_manager.execute_action.return_value = PluginResult(success=False, error="Browser rejected navigation")
    engine = UniversalTargetDiscoveryEngine(plugin_manager=plugin_manager)

    outcome = engine.execute(TargetRequest(
        target="open human 3d view",
        action="open",
        resolved_url="https://www.zygotebody.com/",
    ))

    assert outcome.success is False
    assert outcome.status == "failed"
    assert outcome.url == "https://www.zygotebody.com/"


def test_core_reports_opening_after_a_learned_alias_launches(tmp_path):
    core = JarvisCore()
    store = WebsiteKnowledgeStore(str(tmp_path / "website_knowledge.db"))
    core.website_knowledge = store
    WebsiteResolver.configure_knowledge_store(store)
    try:
        assert "kis webpage" in core.process_input("open human 3d view", source="test")
        core.process_input("https://www.zygotebody.com/", source="test")
        with patch("webbrowser.open", return_value=True) as opened:
            response = core.process_input("open human 3d view", source="test")

        opened.assert_called_once_with("https://www.zygotebody.com/")
        assert response == "Opening Human 3D View."
        assert core.last_execution_result.success is True
        assert core.last_execution_result.verification_result.state.value == "UNVERIFIED"
    finally:
        WebsiteResolver.configure_knowledge_store(None)
