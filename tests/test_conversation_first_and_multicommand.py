# tests/test_conversation_first_and_multicommand.py
"""
Tests for:
1. Day and Date Resolution ("aaj konsa din hai", "what is date today").
2. Conversation-First Behavior ("Today bahut thak gaya hoon." -> empathetic conversational reply, NO command execution).
3. Multi-Command Understanding & Distributive Conjunctions ("Chrome aur Brave kholo aur dono me YouTube open karo.").
4. Multi-App Opening ("Excel, Word aur Chrome kholo.").
"""

import os
import pytest

os.environ["JARVIS_TEST_MODE"] = "1"

from unittest.mock import patch
from core.app import JarvisCore
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.semantic.multi_entity import get_multi_entity_parser
from core.time_context import get_time_context


@pytest.fixture(scope="module")
def core():
    return JarvisCore(config_path="config.yaml")


@pytest.fixture
def parser():
    return get_multi_entity_parser()


# ===========================================================================
# 1. Day & Date Query Resolution Tests
# ===========================================================================

class TestDayAndDateQueries:
    def test_aaj_konsa_din_hai_time_context(self):
        tc = get_time_context()
        res = tc.resolve_time_query("aaj konsa din hai")
        assert res is not None
        assert "hai" in res.lower()
        assert any(d in res.lower() for d in ["somwar", "mangalwar", "budhwar", "guruwar", "shukrawar", "shaniwar", "raviwar"])

    def test_what_is_date_today_time_context(self):
        tc = get_time_context()
        res = tc.resolve_time_query("what is date today")
        assert res is not None
        assert "today is" in res.lower()

    def test_aaj_konsa_din_hai_end_to_end(self, core):
        res = core.process_input("aaj konsa din hai", source="test")
        assert res is not None
        assert "samajh nahi aayi" not in res
        assert any(d in res.lower() for d in ["somwar", "mangalwar", "budhwar", "guruwar", "shukrawar", "shaniwar", "raviwar", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])

    def test_what_is_date_today_end_to_end(self, core):
        res = core.process_input("what is date today", source="test")
        assert res is not None
        assert "not have reliable information" not in res
        assert "today is" in res.lower()

    def test_variations_day_and_date(self, core):
        for q in ["what date is today", "aaj kya din hai", "aaj ki tarikh kya hai", "what day is today"]:
            res = core.process_input(q, source="test")
            assert "samajh nahi aayi" not in res
            assert "not have reliable information" not in res


# ===========================================================================
# 2. Conversation-First Behavior Tests
# ===========================================================================

class TestConversationFirstBehavior:
    def test_fatigue_classification(self):
        res = ConversationalIntentClassifier.classify("Today bahut thak gaya hoon.")
        assert res.intent_type == ConversationalIntentType.CONVERSATION
        assert res.is_executable is False
        assert res.natural_response == "Kaafi tiring day raha lagta hai. Thoda rest kar lijiye."

    def test_fatigue_end_to_end(self, core):
        res = core.process_input("Today bahut thak gaya hoon.", source="test")
        assert res == "Kaafi tiring day raha lagta hai. Thoda rest kar lijiye."
        # Verify no app or system command was triggered
        assert "open" not in res.lower()
        assert "command" not in res.lower()

    def test_sleepiness_conversational(self, core):
        res = core.process_input("neend aa rahi hai", source="test")
        assert "aaram" in res or "thak" in res
        assert "command" not in res.lower()

    def test_hunger_conversational(self, core):
        res = core.process_input("bhookh lagi hai", source="test")
        assert "bhookh" in res.lower() or "kha" in res.lower()

    def test_small_talk_how_are_you(self, core):
        res = core.process_input("kaise ho", source="test")
        assert "theek hoon" in res.lower() or "madad" in res.lower()

    def test_greetings_warm_response(self, core):
        res = core.process_input("hello", source="test")
        assert any(g in res.lower() for g in ["namaste", "hello", "hey", "madad"])


# ===========================================================================
# 3. Multi-Command Distributive Conjunctions Tests
# ===========================================================================

class TestMultiCommandDistributiveUnderstanding:
    def test_distributive_parsing_dono_me_youtube(self, parser):
        """User: 'Chrome aur Brave kholo aur dono me YouTube open karo.'"""
        plan = parser.parse("Chrome aur Brave kholo aur dono me YouTube open karo.")
        assert plan is not None
        assert len(plan.actions) == 4

        # Action 1: Open Chrome
        assert plan.actions[0].action == "open"
        assert plan.actions[0].target == "chrome"
        assert plan.actions[0].container == ""

        # Action 2: Open Brave
        assert plan.actions[1].action == "open"
        assert plan.actions[1].target == "brave"
        assert plan.actions[1].container == ""

        # Action 3: Open YouTube in Chrome
        assert plan.actions[2].action == "open"
        assert plan.actions[2].target == "youtube"
        assert plan.actions[2].container == "chrome"

        # Action 4: Open YouTube in Brave
        assert plan.actions[3].action == "open"
        assert plan.actions[3].target == "youtube"
        assert plan.actions[3].container == "brave"

    def test_distributive_parsing_in_both(self, parser):
        """User: 'open Chrome and Brave and open YouTube in both'"""
        plan = parser.parse("open Chrome and Brave and open YouTube in both")
        assert plan is not None
        assert len(plan.actions) == 4
        targets_and_containers = [(a.target, a.container) for a in plan.actions]
        assert ("youtube", "chrome") in targets_and_containers
        assert ("youtube", "brave") in targets_and_containers

    def test_distributive_end_to_end(self, core):
        dummy_res = ExecutionResult(
            success=True, status=ExecutionState.SUCCESS, requested_action='open', executed_action='launch_application',
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type='app_launched')
        )
        with patch('core.execution.strategies.ExecutionStrategyEngine.launch_application_verified', return_value=dummy_res), \
             patch('core.execution.strategies.ExecutionStrategyEngine.open_website_verified', return_value=dummy_res):
            res = core.process_input("Chrome aur Brave kholo aur dono me YouTube open karo.", source="test")
            assert res is not None
            assert "Chrome" in res
            assert "Brave" in res
            assert "YouTube" in res


# ===========================================================================
# 4. Multi-App Opening Tests
# ===========================================================================

class TestMultiAppCommands:
    def test_three_apps_excel_word_chrome_parsing(self, parser):
        """User: 'Excel, Word aur Chrome kholo.'"""
        plan = parser.parse("Excel, Word aur Chrome kholo.")
        assert plan is not None
        assert len(plan.actions) == 3
        targets = [a.target for a in plan.actions]
        assert targets == ["excel", "word", "chrome"]

    def test_three_apps_excel_word_chrome_end_to_end(self, core):
        dummy_res = ExecutionResult(
            success=True, status=ExecutionState.SUCCESS, requested_action='open', executed_action='launch_application',
            verification_result=VerificationResult(verified=True, state=ExecutionState.SUCCESS, check_type='app_launched')
        )
        with patch('core.execution.strategies.ExecutionStrategyEngine.launch_application_verified', return_value=dummy_res):
            res = core.process_input("Excel, Word aur Chrome kholo.", source="test")
            assert "Excel" in res
            assert "Word" in res
            assert "Chrome" in res
            assert "open ho gaye" in res
