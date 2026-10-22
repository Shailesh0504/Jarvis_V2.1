# tests/test_greeting_typo_tolerance.py
"""
Unit and End-to-End Tests for Greeting Typo-Tolerance and Social Word Handling.
Validates:
1. Common misspellings and abbreviations (moring, mornig, mornin, gud, gm, helo, etc.) resolve to GREETING.
2. Social vocatives and fillers (dear, sir, bro, buddy, yaar, ji, etc.) are tolerated without destroying intent.
3. Negative and edge cases (meaning queries, message generation, capability questions) do NOT become GREETING.
4. Real end-to-end execution in JarvisCore returns natural greetings without clarification requests.
"""

import pytest
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.dialogue_act import DialogueActClassifier, DialogueAct
from core.app import JarvisCore


class TestGreetingTypoTolerance:
    """Validates normalization and conversational intent classification for greetings."""

    @pytest.mark.parametrize("phrase", [
        "good morning",
        "good moring",
        "good mornig",
        "good mornin",
        "gud morning",
        "gud moring",
        "good morning dear",
        "good moring dear",
        "good morning sir",
        "good morning bro",
        "gud morning ji",
        "good mrng dear",
        "gm dear",
        "morning dear",
        "hey good morning",
        "hello good morning",
        "hello dear",
        "hi dear",
        "suprabhat",
        "subah bakhair",
    ])
    def test_greeting_phrases_classified_as_greeting(self, phrase):
        # 1. DialogueAct check
        da_res = DialogueActClassifier.classify(phrase)
        assert da_res.act == DialogueAct.GREETING, f"DialogueAct failed for {phrase}: {da_res.act}"

        # 2. ConversationalIntent check
        intent_res = ConversationalIntentClassifier.classify(phrase)
        assert intent_res.intent_type == ConversationalIntentType.GREETING, (
            f"ConversationalIntent failed for {phrase}: {intent_res.intent_type}"
        )
        assert intent_res.is_executable is False

    @pytest.mark.parametrize("phrase,expected_not_greeting", [
        ("good morning ka meaning kya hai", ConversationalIntentType.GREETING),
        ("good morning message likho", ConversationalIntentType.GREETING),
        ("can you say good morning", ConversationalIntentType.GREETING),
        ("kya tum good morning bol sakte ho", ConversationalIntentType.GREETING),
    ])
    def test_unrelated_queries_do_not_become_greeting(self, phrase, expected_not_greeting):
        intent_res = ConversationalIntentClassifier.classify(phrase)
        assert intent_res.intent_type != expected_not_greeting, (
            f"Phrase '{phrase}' was unexpectedly classified as GREETING"
        )


class TestGreetingEndToEndJarvisCore:
    """Validates real end-to-end execution of greetings in JarvisCore."""

    @pytest.fixture(scope="class")
    @classmethod
    def core_instance(cls):
        core = JarvisCore(config_path="config.yaml")
        return core

    @pytest.mark.parametrize("phrase", [
        "good moring dear",
        "good morning dear",
        "good mornig sir",
        "gud morning",
        "hello dear",
        "hey good morning",
    ])
    def test_real_jarvis_e2e_greeting_response(self, core_instance, phrase):
        response = core_instance.process_input(phrase, source="test")
        low = response.lower()

        # Must NOT request clarification
        assert "what are you referring to" not in low, f"Got clarification for '{phrase}': {response}"
        assert "context chahiye" not in low, f"Got clarification for '{phrase}': {response}"
        assert "takneeki samasya" not in low, f"Got technical error for '{phrase}': {response}"

        # Must contain greeting content (morning, hello, etc.)
        greeting_markers = ["morning", "hello", "hi", "hey", "namaste", "prabhat", "systems operational", "aage kya", "help", "good"]
        assert any(m in low for m in greeting_markers), (
            f"Response for '{phrase}' did not appear to be a greeting: {response}"
        )
