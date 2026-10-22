# tests/test_wifi_password_intent.py
"""
Tests verifying Wi-Fi password intent recognition and disambiguation:
1. GK Engine is_knowledge_candidate correctly rejects local Wi-Fi and system credential queries.
2. Acronym full_form inference in KnowledgeRouter does not hallucinate acronym definitions for password queries.
3. ConversationalIntentClassifier correctly classifies Wi-Fi password queries as ACTION_COMMAND.
4. Capability questions ("can you tell wifi password") remain CAPABILITY_QUESTION.
5. End-to-end JarvisCore execution invokes copy_wifi_password and returns sensitive credentials.
"""

import pytest
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.knowledge import get_knowledge_engine
from core.semantic import SemanticPipelineOrchestrator


class TestWiFiPasswordIntentAndDisambiguation:
    """Tests ensuring local system Wi-Fi password queries are never hijacked by GK."""

    @pytest.mark.parametrize("query", [
        "what is wifi password of my system?",
        "mere system ka wifi password kya hai",
        "wifi password kya hai",
        "what is my wifi password",
        "system ka wifi password batao",
        "show wifi password",
        "connected wifi ka password batao",
        "wifi ka password kya hai",
    ])
    def test_is_knowledge_candidate_rejects_wifi_password_queries(self, query):
        ke = get_knowledge_engine()
        assert ke.is_knowledge_candidate(query) is False, f"Query '{query}' must NOT be treated as GK candidate"

    @pytest.mark.parametrize("query", [
        "what is wifi?",
        "what is wi-fi",
        "wifi kya hai?",
        "wifi full form",
        "wifi stands for",
    ])
    def test_is_knowledge_candidate_accepts_pure_acronym_questions(self, query):
        ke = get_knowledge_engine()
        assert ke.is_knowledge_candidate(query) is True
        res = ke.query(query)
        assert res.found is True
        assert "Wireless Fidelity" in res.answer_text

    def test_knowledge_router_never_returns_wireless_fidelity_for_password(self):
        ke = get_knowledge_engine()
        res = ke.query("what is wifi password of my system")
        # Must not claim found with "Wireless Fidelity"
        if res.found:
            assert "Wireless Fidelity" not in res.answer_text

    @pytest.mark.parametrize("query", [
        "what is wifi password of my system?",
        "mere system ka wifi password kya hai",
        "wifi password kya hai",
        "what is the wifi password",
        "show wifi password",
        "system ka wifi password",
    ])
    def test_conversational_intent_classifies_as_action_command(self, query):
        res = ConversationalIntentClassifier.classify(query)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND
        assert res.is_executable is True
        assert res.action_type == "copy_wifi_password"
        assert res.target == "network"

    @pytest.mark.parametrize("query", [
        "kya tum wifi password nikal sakte ho?",
        "can you tell wifi password?",
        "kya tum wifi password copy kar sakte ho",
    ])
    def test_capability_questions_remain_non_executable(self, query):
        res = ConversationalIntentClassifier.classify(query)
        assert res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
        assert res.is_executable is False
        assert res.natural_response is not None

    @pytest.mark.parametrize("query", [
        "what is wifi password of my system?",
        "mere system ka wifi password kya hai",
        "wifi password kya hai",
        "what is the wifi password",
    ])
    def test_semantic_pipeline_orchestrator_parses_copy_wifi_password(self, query):
        action = SemanticPipelineOrchestrator.parse(query)
        assert action is not None
        assert action.service == "network"
        assert action.action == "copy_wifi_password"
        assert action.confidence == 1.0

    def test_end_to_end_core_execution_with_mocked_network(self, monkeypatch):
        from main import create_jarvis
        from plugins.network.plugin import NetworkPlugin

        # Mock NetworkPlugin methods for deterministic test isolation
        monkeypatch.setattr(NetworkPlugin, "_get_connected_wifi_ssid", lambda self: "Test-Network-5G")
        monkeypatch.setattr(NetworkPlugin, "_get_saved_wifi_password", lambda self, ssid: "SecurePassword123")
        copied_clipboard = []
        monkeypatch.setattr(NetworkPlugin, "_copy_secret_to_clipboard", lambda self, pwd: copied_clipboard.append(pwd))

        core = create_jarvis(config_path="config.yaml")

        # Test English query
        resp_en = core.process_input("what is wifi password of my system?", source="cli")
        assert "Test-Network-5G" in resp_en
        assert "clipboard" in resp_en.lower()
        assert "Wireless Fidelity" not in resp_en
        assert copied_clipboard == ["SecurePassword123"]

        sensitive_en = core.take_sensitive_display()
        assert sensitive_en is not None
        assert sensitive_en.get("type") == "wifi_credentials"
        assert sensitive_en["items"][0]["ssid"] == "Test-Network-5G"
        assert sensitive_en["items"][0]["password"] == "SecurePassword123"

        # Test Hinglish query
        copied_clipboard.clear()
        resp_hi = core.process_input("mere system ka wifi password kya hai", source="cli")
        assert "Test-Network-5G" in resp_hi
        assert "clipboard" in resp_hi.lower()
        assert "Wireless Fidelity" not in resp_hi
        assert copied_clipboard == ["SecurePassword123"]

        sensitive_hi = core.take_sensitive_display()
        assert sensitive_hi is not None
        assert sensitive_hi["items"][0]["password"] == "SecurePassword123"
