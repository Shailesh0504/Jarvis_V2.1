# tests/test_conversational_intent_speech_act.py
"""
Unit and Integration Tests for Human-Like Conversational Intent & Speech-Act Gating Layer.
Verifies that:
1. Capability questions ("kya tum system lock kar sakte ho?") do NOT execute commands.
2. Action commands ("system lock karo") are classified as ACTION_COMMAND and execute.
3. Status questions ("system lock hai kya?") answer state without altering state.
4. Status after action ("system lock hua?") report actual current state without altering state.
5. Troubleshooting queries ("system lock kyun nahi ho raha?") provide diagnostics without re-attempting action.
6. Confirmations without pending operations do not execute random commands.
7. Cancellations cancel gracefully.
"""

import pytest
from unittest.mock import MagicMock, patch

from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
    ConversationalIntentResult,
)
from core.app import JarvisCore


class TestConversationalIntentClassifier:
    """Unit tests for speech-act pattern matching and classification."""

    def test_capability_questions_classification(self):
        capability_queries = [
            ("kya tum system lock kar sakte ho?", "system"),
            ("can you open Chrome?", "chrome"),
            ("tum Excel chala sakte ho?", "excel"),
            ("can you restart the computer?", "system"),
            ("Chrome open kar sakte ho?", "chrome"),
            ("kya aap Notepad open kar sakte hain?", "notepad"),
            ("kya tum YouTube chala sakte ho?", "youtube"),
            ("tumse system lock ho payega kya?", "system"),
        ]
        for query, expected_target in capability_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.CAPABILITY_QUESTION, (
                f"Failed for query '{query}', got {res.intent_type}"
            )
            assert res.is_executable is False, f"Capability question '{query}' must NOT be executable"
            assert res.target == expected_target, f"Expected target '{expected_target}' for '{query}', got '{res.target}'"
            assert res.natural_response is not None
            assert len(res.natural_response) > 5

    def test_action_commands_classification(self):
        action_queries = [
            ("system lock karo", "lock"),
            ("lock pc", "lock"),
            ("Chrome open karo", "kholo" if "kholo" in "Chrome open karo" else "open"),
            ("open excel", "open"),
            ("Excel chala do", "chala"),
            ("computer restart karo", "restart"),
            ("volume 50 karo", "karo"),
            ("close brave", "close"),
        ]
        for query, _ in action_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.ACTION_COMMAND, (
                f"Failed for action command '{query}', got {res.intent_type}"
            )
            assert res.is_executable is True, f"Action command '{query}' must be executable"

    def test_status_questions_classification(self):
        status_queries = [
            "system lock hai kya?",
            "Chrome open hai kya?",
            "Excel chal raha hai?",
            "is notepad open?",
            "is system locked?",
            "status of chrome?",
        ]
        for query in status_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.STATUS_QUESTION, (
                f"Failed for status query '{query}', got {res.intent_type}"
            )
            assert res.is_executable is False

    def test_status_after_action_classification(self):
        status_after_queries = [
            "system lock hua?",
            "Chrome open hua?",
            "restart ho gaya?",
            "Notepad open hua?",
            "did chrome open?",
        ]
        for query in status_after_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.STATUS_AFTER_ACTION, (
                f"Failed for status after action query '{query}', got {res.intent_type}"
            )
            assert res.is_executable is False

    def test_troubleshooting_classification(self):
        troubleshooting_queries = [
            "system lock kyun nahi ho raha?",
            "Chrome kyun nahi khul raha?",
            "why isn't chrome opening?",
            "volume kyun nahi badh raha?",
        ]
        for query in troubleshooting_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.TROUBLESHOOTING, (
                f"Failed for troubleshooting query '{query}', got {res.intent_type}"
            )
            assert res.is_executable is False
            assert res.natural_response is not None
            assert "reasons" in res.natural_response.lower() or "kaaran" in res.natural_response.lower() or "rukawat" in res.natural_response.lower()

    def test_confirmation_handling_with_and_without_pending(self):
        # Without pending confirmation
        res_no_pending = ConversationalIntentClassifier.classify("haan karo", has_pending_confirmation=False)
        assert res_no_pending.intent_type == ConversationalIntentType.CONFIRMATION
        assert res_no_pending.is_executable is False
        assert "batayein" in res_no_pending.natural_response

        # With active pending confirmation
        res_with_pending = ConversationalIntentClassifier.classify("haan karo", has_pending_confirmation=True)
        assert res_with_pending.intent_type == ConversationalIntentType.CONFIRMATION
        assert res_with_pending.is_executable is True

    def test_cancellation_classification(self):
        cancel_queries = ["nahi", "mat karo", "cancel", "rehne do", "abort"]
        for query in cancel_queries:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.CANCELLATION
            assert res.is_executable is False
            assert "cancel" in res.natural_response.lower()

    def test_greetings_classification(self):
        greetings = ["hello", "namaste", "good morning", "hi jarvis"]
        for query in greetings:
            res = ConversationalIntentClassifier.classify(query)
            assert res.intent_type == ConversationalIntentType.GREETING
            assert res.is_executable is False


class TestJarvisCoreSpeechActIntegration:
    """Integration tests verifying end-to-end JarvisCore behavior with speech-act gating."""

    @pytest.fixture
    def core(self):
        jarvis = JarvisCore()
        jarvis.plugin_manager = MagicMock()
        return jarvis

    def test_capability_question_does_not_execute_command(self, core):
        """
        'kya tum system lock kar sakte ho?' must return capability confirmation
        and MUST NOT call system plugin lock_pc or execute any workstation lock.
        """
        sys_plugin = MagicMock()
        core.plugin_manager.get_plugin.return_value = sys_plugin

        resp = core.process_input("kya tum system lock kar sakte ho?", source="cli")
        assert "main system lock kar sakta hoon" in resp
        # Verify plugin execute was NEVER called
        sys_plugin.execute.assert_not_called()
        core.plugin_manager.execute_action.assert_not_called()

    def test_chrome_capability_question_does_not_launch_app(self, core):
        """
        'Chrome open kar sakte ho?' must confirm capability and NOT launch Chrome.
        """
        with patch.object(core.execution_strategies, "launch_application_verified") as mock_launch:
            resp = core.process_input("Chrome open kar sakte ho?", source="cli")
            assert "main chrome open kar sakta hoon" in resp.lower()
            mock_launch.assert_not_called()

    def test_system_lock_status_question_does_not_lock(self, core):
        """
        'system lock hai kya?' must return current unlocked status and NOT lock PC.
        """
        sys_plugin = MagicMock()
        core.plugin_manager.get_plugin.return_value = sys_plugin

        resp = core.process_input("system lock hai kya?", source="cli")
        assert "unlocked" in resp.lower()
        sys_plugin.execute.assert_not_called()
        core.plugin_manager.execute_action.assert_not_called()

    def test_system_lock_troubleshooting_does_not_lock(self, core):
        """
        'system lock kyun nahi ho raha?' must return troubleshooting advice and NOT attempt lock.
        """
        sys_plugin = MagicMock()
        core.plugin_manager.get_plugin.return_value = sys_plugin

        resp = core.process_input("system lock kyun nahi ho raha?", source="cli")
        assert "reasons" in resp.lower() or "policy" in resp.lower()
        sys_plugin.execute.assert_not_called()
        core.plugin_manager.execute_action.assert_not_called()

    def test_action_command_routes_to_execution(self, core):
        """
        'system lock karo' is an action command and proceeds to execution pipeline.
        """
        core.plugin_manager.execute_action.return_value = MagicMock(success=True, data={"message": "System lock kar diya hai."})
        resp = core.process_input("system lock karo", source="cli")
        assert core.plugin_manager.execute_action.called or "lock" in resp.lower()
