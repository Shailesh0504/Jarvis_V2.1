# tests/conversation/test_golden_conversations.py
"""
Golden Multi-Turn Conversation Dataset for Jarvis V2.
Validates multi-turn context preservation, reference resolution, topic tracking,
interruption returns, conversational repair, negation gating, and pragmatic reasoning.
Strictly adheres to AGENTS.md §1.1, §3, and §26-28.
"""

import pytest
from unittest.mock import MagicMock

from brain.conversation.model import HumanConversationModel, HumanConversationFrame
from core.context import ActiveTargetContext
from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
)
from core.dialogue_act import DialogueActClassifier, DialogueAct, DialogueActResult
from core.reference_resolver import ReferenceResolver
from core.topic_tracker import TopicTracker
from core.conversation_state import ConversationState


@pytest.fixture
def hcm():
    return HumanConversationModel()


class TestGoldenConversations:
    """End-to-end golden multi-turn conversation dialogues."""

    def test_flow_01_contextual_chaining_and_ellipsis(self, hcm):
        """
        Flow 1:
        User: "Chrome kholo"
        Jarvis: "Chrome open kar diya."
        User: "isko minimize karo"
        Jarvis: "Chrome minimize kar diya."
        User: "ab band karo"
        """
        ctx = ActiveTargetContext()
        recent_turns = []

        # Turn 1: Launch Chrome
        t1 = hcm.analyze_turn("Chrome kholo", active_context=ctx, recent_turns=recent_turns)
        assert t1.action == "open"
        assert t1.target == "chrome"
        assert t1.is_executable_command is True
        assert t1.decision == "EXECUTE"

        # Simulate OS activation of Chrome
        ctx.set_application("chrome", title="Google Chrome")
        recent_turns.append({"role": "user", "content": "Chrome kholo"})
        recent_turns.append({"role": "assistant", "content": "Chrome open kar diya."})

        # Turn 2: Demonstrative "isko minimize karo"
        t2 = hcm.analyze_turn("isko minimize karo", active_context=ctx, recent_turns=recent_turns)
        assert t2.action == "minimize"
        assert t2.resolved_entity.lower() == "chrome"
        assert t2.is_executable_command is True

        recent_turns.append({"role": "user", "content": "isko minimize karo"})
        recent_turns.append({"role": "assistant", "content": "Chrome minimize kar diya."})

        # Turn 3: Ellipsis "ab band karo"
        t3 = hcm.analyze_turn("ab band karo", active_context=ctx, recent_turns=recent_turns)
        assert t3.action == "close"
        assert t3.is_executable_command is True

    def test_flow_02_topic_switching_and_workflow_return(self, hcm):
        """
        Flow 2:
        User: "Excel kholo" (Excel workflow starts)
        User: "Sales wali file open karo"
        User: "Waise kal weather kaisa rahega?" (Side question interruption)
        Jarvis: "Kal mausam saaf rahega."
        User: "Achha, Excel mein wapas aao" / "return to excel"
        """
        tracker = TopicTracker()
        state = ConversationState()
        ctx = ActiveTargetContext()

        # Step 1: Start Excel workflow
        da1 = DialogueActResult(act=DialogueAct.COMMAND, topic_hint="excel", is_executable_command=True)
        tracker.track_utterance("Excel kholo", da1, state)
        ctx.set_application("excel", title="Microsoft Excel")
        assert tracker.get_active_topic() == "excel"

        # Step 2: Continue in Excel workflow
        da2 = DialogueActResult(act=DialogueAct.COMMAND, topic_hint="excel", is_executable_command=True)
        tracker.track_utterance("Sales wali file open karo", da2, state)
        assert tracker.get_active_topic() == "excel"

        # Step 3: User interrupts with side question about weather
        frame_weather = hcm.analyze_turn("Waise kal weather kaisa rahega?", active_context=ctx)
        assert frame_weather.is_executable_command is False
        assert frame_weather.decision in ("ANSWER", "CHAT")

        da3 = DialogueActResult(act=DialogueAct.QUESTION, topic_hint="weather", is_executable_command=False)
        tracker.track_utterance("Waise kal weather kaisa rahega?", da3, state)
        assert tracker.get_active_topic() == "weather"
        assert "excel" in tracker.topic_stack

        # Step 4: User finishes weather side topic and returns to previous workflow
        restored = tracker.return_to_previous_workflow(state)
        assert restored == "excel"
        assert tracker.get_active_topic() == "excel"

    def test_flow_03_tab_reference_and_conversational_repair(self, hcm):
        """
        Flow 3:
        User: "Chrome kholo"
        Jarvis: "Chrome open kar diya."
        User: "Achha ab YouTube wala tab kholo"
        User: "Nahi nahi, doosra wala" (Correction / Repair)
        User: "Haan yehi" (Confirmation)
        User: "Ab isko band kar do"
        """
        ctx = ActiveTargetContext()
        ctx.set_application("chrome", title="Google Chrome")

        # Turn 1: Specific tab request
        t1 = hcm.analyze_turn("Achha ab YouTube wala tab kholo", active_context=ctx)
        assert t1.action == "open"
        assert "youtube" in t1.target.lower()
        assert t1.is_executable_command is True

        # Turn 2: User correction "Nahi nahi, doosra wala"
        da_corr = DialogueActClassifier.classify("Nahi nahi, doosra wala")
        assert da_corr.act == DialogueAct.CORRECTION
        assert da_corr.is_executable_command is False

        # Turn 3: Confirmation "Haan yehi"
        da_conf = DialogueActClassifier.classify("Haan yehi")
        assert da_conf.act in (DialogueAct.ACKNOWLEDGEMENT, DialogueAct.CASUAL_STATEMENT)

        # Turn 4: "Ab isko band kar do"
        t4 = hcm.analyze_turn("Ab isko band kar do", active_context=ctx)
        assert t4.action == "close"
        assert t4.is_executable_command is True

    def test_flow_04_pragmatic_subtext_gating(self, hcm):
        """
        Flow 4:
        User: "Yaar bahut garmi hai."
        Jarvis: Clarifies "AC chala doon?", does NOT prematurely execute.
        User: "Haan chala do"
        Jarvis: Now executes after confirmation.
        """
        # Step 1: Indirect pragmatic remark
        t1 = hcm.analyze_turn("Yaar bahut garmi hai.")
        assert t1.pragmatic_goal == "COOL_ENVIRONMENT"
        assert t1.pragmatic_clarification == "AC chala doon?"
        assert t1.decision == "CLARIFY"
        assert t1.is_executable_command is False
        assert t1.certainty <= 0.60

        # Step 2: User confirms
        c_res = ConversationalIntentClassifier.classify("Haan chala do", has_pending_confirmation=True)
        assert c_res.intent_type == ConversationalIntentType.CONFIRMATION
        assert c_res.is_executable is True

    def test_flow_05_negation_invariant_in_conversation(self, hcm):
        """
        Flow 5:
        User: "VLC kholo"
        User: "Nahi nahi, VLC mat kholo" -> Strictly blocked!
        User: "Edge kholo" -> Executed!
        """
        ctx = ActiveTargetContext()

        # Step 1: Open VLC
        t1 = hcm.analyze_turn("VLC kholo", active_context=ctx)
        assert t1.target.lower() == "vlc"
        assert t1.is_executable_command is True

        # Step 2: Negate VLC command
        t2 = hcm.analyze_turn("Nahi nahi, VLC mat kholo", active_context=ctx)
        assert t2.is_negated is True
        assert t2.is_executable_command is False
        assert t2.decision == "ANSWER"
        assert "DO_NOT_" in t2.communicative_goal

        # Step 3: Open Edge instead
        t3 = hcm.analyze_turn("Edge kholo", active_context=ctx)
        assert t3.target.lower() == "edge"
        assert t3.is_executable_command is True
        assert t3.decision == "EXECUTE"
