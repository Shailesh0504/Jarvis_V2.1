# tests/test_exit_and_bye_behavior.py
"""
Unit and Integration tests for Exit and Bye Command Behavior in Jarvis V2.
Validates:
1. 'exit', 'bye', 'quit', 'goodbye', 'alvida', 'terminate', 'band karo jarvis', etc.:
   - Classified as ACTION_COMMAND with action='shutdown' and target='jarvis'.
   - Trigger immediate clean lifecycle shutdown: SystemState.SHUTDOWN.
   - Return appropriate farewell response containing 'Shutting down Jarvis'.
   - Emit 'system.shutdown' event on EventBus.
2. Speech-act safety invariant:
   - Capability inquiries ('can you exit?', 'kya tum shutdown kar sakte ho?')
     must NEVER trigger shutdown and must be classified as CAPABILITY_QUESTION.
3. Conversational turns (empathy, fatigue, small-talk) remain unhindered:
   - 'Today bahut thak gaya hoon' returns empathetic rest response, NOT shutdown.
"""

import os
import pytest

os.environ["JARVIS_TEST_MODE"] = "1"

from core.app import JarvisCore
from core.state import SystemState
from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
)


@pytest.fixture
def core_instance():
    core = JarvisCore(config_path="config.yaml")
    return core


class TestExitAndByeIntentClassification:
    """Validates NLP and speech-act classification of exit/bye commands."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "exit",
            "bye",
            "bye bye",
            "bye-bye",
            "quit",
            "goodbye",
            "alvida",
            "terminate",
            "exit jarvis",
            "quit jarvis",
            "shutdown jarvis",
            "bye jarvis",
            "goodbye jarvis",
            "alvida jarvis",
            "jarvis exit",
            "jarvis quit",
            "jarvis shutdown",
            "jarvis bye",
            "jarvis goodbye",
            "jarvis alvida",
            "band karo jarvis",
            "jarvis band karo",
            "jarvis ko band karo",
            "jarvis close karo",
            "close jarvis",
        ],
    )
    def test_exit_phrases_classified_as_action_command(self, phrase):
        res = ConversationalIntentClassifier.classify(phrase)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND
        assert res.is_executable is True
        assert res.target == "jarvis"
        assert res.action_type == "shutdown"

    @pytest.mark.parametrize(
        "query",
        [
            "kya tum shutdown kar sakte ho?",
            "can you exit?",
            "kya aap jarvis ko exit kar sakte ho?",
            "are you able to shutdown?",
        ],
    )
    def test_capability_questions_do_not_classify_as_action_command(self, query):
        res = ConversationalIntentClassifier.classify(query)
        assert res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
        assert res.is_executable is False


class TestExitAndByeEndToEndExecution:
    """Validates end-to-end shutdown behavior in JarvisCore."""

    @pytest.mark.parametrize(
        "exit_cmd",
        [
            "exit",
            "bye",
            "quit",
            "goodbye",
            "alvida",
            "terminate",
            "exit jarvis",
            "jarvis band karo",
            "band karo jarvis",
        ],
    )
    def test_exit_commands_trigger_shutdown(self, core_instance, exit_cmd):
        events_emitted = []
        core_instance.event_bus.subscribe("system.shutdown", lambda e: events_emitted.append(e))

        response = core_instance.process_input(exit_cmd, source="cli")

        assert response is not None
        assert "shutting down jarvis" in response.lower()
        assert core_instance.state_machine.current_state == SystemState.SHUTDOWN
        assert len(events_emitted) == 1
        assert events_emitted[0].data.get("reason") == "user_command"

    def test_capability_question_does_not_shutdown_core(self, core_instance):
        events_emitted = []
        core_instance.event_bus.subscribe("system.shutdown", lambda e: events_emitted.append(e))

        response = core_instance.process_input("kya tum shutdown kar sakte ho?", source="cli")

        assert response is not None
        assert "shutting down jarvis" not in response.lower()
        assert core_instance.state_machine.current_state != SystemState.SHUTDOWN
        assert len(events_emitted) == 0

    def test_empathetic_turn_preserved_without_fallback_loop(self, core_instance):
        response = core_instance.process_input("Today bahut thak gaya hoon.", source="cli")

        assert response is not None
        assert "rest" in response.lower() or "thak" in response.lower()
        assert core_instance.state_machine.current_state != SystemState.SHUTDOWN
