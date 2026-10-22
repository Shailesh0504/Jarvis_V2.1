# tests/test_generic_conversational_typo_tolerance.py
"""Comprehensive tests for Generic Typo-Tolerant Conversational & Command Normalization."""

import pytest
from core.semantic.normalizer import HinglishNormalizer
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from main import create_jarvis


class TestGenericConversationalTypoTolerance:
    """Validates multi-tier generic normalization across SMS, phonetic shorthand, and command typos."""

    @pytest.mark.parametrize("query,expected_substring", [
        ("how are yu", "how are you"),
        ("how r u", "how are you"),
        ("hw r u", "how are you"),
        ("who r u", "who are you"),
        ("what is yu name", "what is your name"),
        ("tum kya kr skte ho", "tum kya kar sakte ho"),
        ("kya tum ye kr skte ho", "kya tum ye kar sakte ho"),
        ("open chorme", "open chrome"),
        ("systm restart karo", "system restart karo"),
        ("shudown pc", "shutdown pc"),
        ("clse chrome", "close chrome"),
        ("brwoser kholo", "browser kholo"),
        ("opn notepad", "open notepad"),
        ("kese ho bhai", "kaise ho bhai"),
        ("kya kr rhe ho", "kya kar rahe ho"),
        ("wht r u doing", "what are you doing"),
        ("plz open chrome", "please open chrome"),
        ("thx jarvis", "thanks jarvis"),
    ])
    def test_generic_normalization_transforms(self, query: str, expected_substring: str):
        normalized = HinglishNormalizer.normalize_text(query)
        assert expected_substring in normalized, f"Expected '{expected_substring}' in '{normalized}' for query '{query}'"

    def test_preserved_non_typos_and_numbers(self):
        """Ensures valid words, numbers, and technical terms are never corrupted."""
        assert HinglishNormalizer.normalize_text("2 plus 2") == "2 plus 2"
        assert HinglishNormalizer.normalize_text("bappa drawing banao") == "bappa drawing banao"
        assert HinglishNormalizer.normalize_text("shailesh yadav") == "shailesh yadav"
        assert HinglishNormalizer.normalize_text("good morning ka meaning kya hai") == "good morning ka meaning kya hai"

    @pytest.mark.parametrize("query,expected_speech_act", [
        ("how are yu", ConversationalIntentType.CONVERSATION),
        ("how r u", ConversationalIntentType.CONVERSATION),
        ("tum kya kr skte ho", ConversationalIntentType.CAPABILITY_QUESTION),
        ("kya tum chrome khol skte ho", ConversationalIntentType.CAPABILITY_QUESTION),
        ("open chorme", ConversationalIntentType.ACTION_COMMAND),
        ("clse chrome", ConversationalIntentType.ACTION_COMMAND),
        ("systm restart karo", ConversationalIntentType.ACTION_COMMAND),
        ("shudown pc", ConversationalIntentType.ACTION_COMMAND),
    ])
    def test_conversational_intent_classification_on_typos(self, query: str, expected_speech_act: ConversationalIntentType):
        normalized = HinglishNormalizer.normalize_text(query)
        res = ConversationalIntentClassifier.classify(normalized)
        assert res.intent_type == expected_speech_act, f"Expected {expected_speech_act} for '{query}' (normalized: '{normalized}'), got {res.intent_type}"


class TestEndToEndGenericTypoTolerance:
    """End-to-end pipeline verification using create_jarvis()."""

    @pytest.fixture(scope="class")
    def jarvis(self):
        return create_jarvis()

    def test_how_are_yu(self, jarvis):
        resp = jarvis.process_input("how are yu")
        assert any(term in resp.lower() for term in ["theek", "fine", "good", "badhiya", "chal raha"])
        assert "context" not in resp.lower()

    def test_who_r_u(self, jarvis):
        resp = jarvis.process_input("who r u")
        assert "jarvis" in resp.lower()

    def test_what_is_yu_name(self, jarvis):
        resp = jarvis.process_input("what is yu name")
        assert "jarvis" in resp.lower()

    def test_tum_kya_kr_skte_ho(self, jarvis):
        resp = jarvis.process_input("tum kya kr skte ho")
        assert any(term in resp.lower() for term in ["sakta hoon", "kar sakta", "applications", "help"])
        assert "context" not in resp.lower()

    def test_open_chorme(self, jarvis):
        resp = jarvis.process_input("open chorme")
        assert any(term in resp.lower() for term in ["chrome", "open", "khol"])

    def test_systm_restart_karo(self, jarvis):
        resp = jarvis.process_input("systm restart karo")
        assert any(term in resp.lower() for term in ["restart", "confirm", "sach me"])

    def test_shudown_pc(self, jarvis):
        resp = jarvis.process_input("shudown pc")
        assert any(term in resp.lower() for term in ["shutdown", "band", "confirm"])

    def test_clse_chrome(self, jarvis):
        resp = jarvis.process_input("clse chrome")
        assert any(term in resp.lower() for term in ["chrome", "band", "close"])

    def test_brwoser_kholo(self, jarvis):
        resp = jarvis.process_input("brwoser kholo")
        assert any(term in resp.lower() for term in ["browser", "open", "khol", "brave", "chrome"])

    def test_opn_notepad(self, jarvis):
        resp = jarvis.process_input("opn notepad")
        assert any(term in resp.lower() for term in ["notepad", "open", "khol"])
