# tests/test_future_intention_understanding.py
"""
Unit and Integration Tests for Jarvis Future Intention & Scheduled Plan Understanding.

Verifies:
1. Speech-Act Classification distinguishing:
   - FUTURE_INTENTION ("Mujhe 1:30 PM pe khana khane jaana hai.")
   - FUTURE_EVENT ("Kal 3 baje presentation hai.")
   - EXPLICIT_REMINDER_REQUEST ("1:30 PM pe mujhe yaad dilana.")
   - INFORMATION_QUESTION ("1:30 PM pe mujhe jaana hai kya?")
   - STATEMENT ("Lunch time achha hota hai.")
2. Temporal Anchor Extraction:
   - 12-hour AM/PM formats ("1:30 PM", "1 30 pm", "4 PM")
   - Hinglish period + baje formats ("shaam 6 baje", "dopahar 1:30", "kal subah 10 baje")
3. Turn N+1 Multi-Turn Affirmation / Cancellation via DialogManager:
   - "haan" creates reminder using authoritative ReminderPlugin
   - "nahi" gracefully cancels without creating a reminder
   - Topic switch clears the pending reminder offer
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
)
from core.dialog_manager import (
    DialogManager,
    PendingReminderOffer,
)


class TestFutureIntentionClassification:
    """Tests for conversational intent classification of future intentions and events."""

    def test_future_intention_queries(self):
        queries = [
            ("Mujhe 1:30 PM pe khana khane jaana hai.", "1:30 PM", "GO_TO_EAT"),
            ("mujhe kal subah 10 baje doctor ke paas jana hai", "10 baje", "DOCTOR_APPOINTMENT"),
            ("shaam 6 baje gym jana hai", "shaam 6 baje", "GYM_WORKOUT"),
            ("I have to leave for lunch at 1:30 PM", "1:30 PM", "GO_TO_EAT"),
            ("dopahar 2 baje meeting attend karni hai", "dopahar 2 baje", "ATTEND_MEETING"),
        ]

        for text, expected_time_sub, expected_goal in queries:
            res = ConversationalIntentClassifier.classify(text)
            assert res.intent_type == ConversationalIntentType.FUTURE_INTENTION, (
                f"Query '{text}' should be FUTURE_INTENTION, got {res.intent_type}"
            )
            assert res.is_executable is False, (
                f"FUTURE_INTENTION query '{text}' must NOT be executable"
            )
            assert res.parameters.get("reminder_candidate") is True
            assert res.parameters.get("goal") == expected_goal
            assert expected_time_sub.lower() in res.parameters.get("time_display", "").lower()
            assert res.natural_response is not None
            assert "yaad dila du" in res.natural_response or "remind" in res.natural_response.lower()

    def test_go_home_and_custom_task_extraction(self):
        """Verifies natural utterances like 'mujhe 7 PM pe ghar jaana hai' extract real task instead of 'Scheduled task'."""
        text = "mujhe 7 PM pe ghar jaana hai"
        res = ConversationalIntentClassifier.classify(text)
        assert res.intent_type == ConversationalIntentType.FUTURE_INTENTION
        assert res.parameters.get("goal") == "GO_HOME"
        assert res.parameters.get("description") == "Ghar jaana"
        assert "7 PM" in res.parameters.get("time_display", "")

        text2 = "7 baje assignment submit karna hai"
        res2 = ConversationalIntentClassifier.classify(text2)
        assert res2.intent_type == ConversationalIntentType.FUTURE_INTENTION
        assert res2.parameters.get("description") == "Assignment submit karna"

    def test_future_event_queries(self):
        queries = [
            ("Kal 3 baje team meeting hai.", "meeting"),
            ("dopahar 2 baje exam hai", "exam"),
            ("tomorrow at 4 PM is the project demo", "demo"),
        ]

        for text, _ in queries:
            res = ConversationalIntentClassifier.classify(text)
            assert res.intent_type == ConversationalIntentType.FUTURE_EVENT, (
                f"Query '{text}' should be FUTURE_EVENT, got {res.intent_type}"
            )
            assert res.is_executable is False
            assert res.parameters.get("reminder_candidate") is True

    def test_explicit_reminder_request(self):
        explicit_queries = [
            "1:30 PM pe mujhe yaad dilana.",
            "mujhe 4 baje yaad dilana ki call karna hai",
            "remind me at 5 PM to submit report",
            "shaam 6 baje reminder set karo",
        ]

        for text in explicit_queries:
            res = ConversationalIntentClassifier.classify(text)
            assert res.intent_type == ConversationalIntentType.ACTION_COMMAND, (
                f"Query '{text}' must be an ACTION_COMMAND, got {res.intent_type}"
            )
            assert res.is_executable is True, (
                f"Explicit reminder query '{text}' MUST be executable"
            )

    def test_information_question_gating(self):
        question_queries = [
            "1:30 PM pe mujhe jaana hai kya?",
            "kya kal 2 baje meeting hai?",
            "do I have a meeting at 4 PM?",
            "kya mujhe 1 baje nikalna hai?",
        ]

        for text in question_queries:
            res = ConversationalIntentClassifier.classify(text)
            assert res.intent_type in (
                ConversationalIntentType.QUESTION,
                ConversationalIntentType.INFORMATION_QUESTION,
                ConversationalIntentType.STATUS_QUESTION,
                ConversationalIntentType.CAPABILITY_QUESTION,
            ), f"Query '{text}' should be a QUESTION, got {res.intent_type}"
            assert res.is_executable is False

    def test_general_statement_gating(self):
        statement_queries = [
            "lunch time pe sab khana khate hain",
            "health ke liye walk karna accha hota hai",
            "khana time pe khana chahiye",
        ]

        for text in statement_queries:
            res = ConversationalIntentClassifier.classify(text)
            # Should NOT be classified as FUTURE_INTENTION with reminder candidate
            assert res.parameters.get("reminder_candidate") is not True


class TestDialogManagerTurnNPlus1:
    """Tests for multi-turn confirmation and cancellation flow."""

    def setup_method(self):
        self.dm = DialogManager()

    def test_affirmation_creates_reminder(self):
        offer = PendingReminderOffer(
            title="Khana khane jaana",
            remind_time="2026-09-17T13:30:00+05:30",
            time_display="1:30 PM",
            goal="GO_TO_EAT",
        )
        self.dm.set_pending_reminder_offer(offer)
        assert self.dm.has_pending_reminder_offer() is True

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.data = {"message": "Reminder set kar diya hai: 'Khana khane jaana' 1:30 PM ke liye, Boss. ⏰"}
        mock_plugin = MagicMock()
        mock_plugin.return_value.execute.return_value = mock_result

        with patch("plugins.reminder.plugin.ReminderPlugin", mock_plugin):
            handled, response = self.dm.process_reminder_offer_turn("haan")
            assert handled is True
            assert response is not None
            assert "1:30 PM" in response
            assert "set kar diya" in response or "yaad dila dunga" in response
            assert self.dm.has_pending_reminder_offer() is False
            mock_plugin.return_value.execute.assert_called_once()

    def test_cancellation_discards_reminder(self):
        offer = PendingReminderOffer(
            title="Khana khane jaana",
            remind_time="2026-09-17T13:30:00+05:30",
            time_display="1:30 PM",
            goal="GO_TO_EAT",
        )
        self.dm.set_pending_reminder_offer(offer)
        assert self.dm.has_pending_reminder_offer() is True

        handled, response = self.dm.process_reminder_offer_turn("nahi mat karo")
        assert handled is True
        assert response is not None
        assert "nahi kiya" in response or "theek hai" in response.lower()
        assert self.dm.has_pending_reminder_offer() is False

    def test_topic_switch_clears_reminder_offer(self):
        offer = PendingReminderOffer(
            title="Khana khane jaana",
            remind_time="2026-09-17T13:30:00+05:30",
            time_display="1:30 PM",
            goal="GO_TO_EAT",
        )
        self.dm.set_pending_reminder_offer(offer)

        # User asks unrelated command instead of confirming
        handled, response = self.dm.process_reminder_offer_turn("Chrome khol do")
        assert handled is False  # False indicates DialogManager passes query to normal pipeline
        assert self.dm.has_pending_reminder_offer() is False  # Offer cleared on topic switch
