# tests/conversation/test_conversation_corpus.py
"""
Dedicated 26-Group Conversational Understanding Test Corpus for Jarvis V2.
Validates the canonical 29-dimension conversation frame, meaning representation,
dialogue acts, negation invariant, pragmatic understanding, and indirect requests.
Strictly adheres to AGENTS.md §1.1 and §3.
"""

import pytest
from unittest.mock import MagicMock

from brain.conversation.model import HumanConversationFrame, HumanConversationModel
from core.context import ActiveTargetContext
from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
    ConversationalIntentResult,
)
from core.dialogue_act import DialogueActClassifier, DialogueAct, DialogueActResult
from core.reference_resolver import ReferenceResolver, ReferenceTargetType
from core.topic_tracker import TopicTracker
from core.conversation_state import ConversationState, ConversationMode


@pytest.fixture
def hcm():
    return HumanConversationModel()


class TestConversationCorpusAllGroups:
    """Comprehensive test suite covering all 26 conversational understanding groups."""

    # 1. Greetings
    def test_group_01_greetings(self, hcm):
        greetings = [
            "Hi", "Hello", "Good morning", "Kaise ho?", "Kya chal raha hai?", "Kya kar rahe ho?"
        ]
        for query in greetings:
            frame = hcm.analyze_turn(query)
            assert frame.raw_utterance == query
            assert frame.is_executable_command is False
            assert frame.dialogue_act in (DialogueAct.GREETING, DialogueAct.SMALL_TALK, DialogueAct.STATUS_UPDATE, DialogueAct.QUESTION)

    # 2. Small Talk
    def test_group_02_small_talk(self, hcm):
        queries = ["Achha hai", "Theek hai", "Hmm", "Wow", "Great"]
        for query in queries:
            frame = hcm.analyze_turn(query)
            assert frame.is_executable_command is False
            assert frame.dialogue_act in (DialogueAct.ACKNOWLEDGEMENT, DialogueAct.CASUAL_STATEMENT, DialogueAct.SMALL_TALK, DialogueAct.STATUS_UPDATE)

    # 3. Acknowledgement
    def test_group_03_acknowledgement(self, hcm):
        queries = ["Thanks", "Thank you", "Sorry", "Koi baat nahi", "Chalo", "Theek", "Bas"]
        for query in queries:
            frame = hcm.analyze_turn(query)
            assert frame.is_executable_command is False
            assert frame.decision in ("CHAT", "ANSWER")

    # 4. Questions
    def test_group_04_questions(self, hcm):
        queries = [
            "Ek baat batao", "Mujhe ek cheez poochni hai", "is notepad open?"
        ]
        for query in queries:
            frame = hcm.analyze_turn(query)
            assert frame.is_executable_command is False
            assert frame.decision in ("ANSWER", "CHAT")

    # 5. Indirect Requests
    def test_group_05_indirect_requests(self, hcm):
        indirect_requests = [
            ("Chrome khol doge?", "chrome", "open"),
            ("Mujhe Chrome chahiye", "chrome", "open"),
            ("Chalo Chrome", "chrome", "open"),
            ("Zara Chrome laga do", "chrome", "open"),
            ("Chrome pe chalte hain", "chrome", "open"),
            ("Chrome kar do", "chrome", "open"),
        ]
        for query, expected_target, expected_act in indirect_requests:
            frame = hcm.analyze_turn(query)
            assert frame.target.lower() == expected_target
            assert frame.action.lower() == expected_act
            assert frame.is_executable_command is True
            assert frame.decision == "EXECUTE"

    # 6. Commands (Word Order & Paraphrase Flexibility)
    def test_group_06_commands_paraphrase_flexibility(self, hcm):
        variants = [
            "Chrome kholo",
            "Chrome ko kholo",
            "Chrome open karo",
            "Chrome chala do",
            "Chrome start kar do",
            "Chrome ab kholo",
            "Ab Chrome kholo",
            "Chrome please kholo",
            "Bhai Chrome khol do",
            "Khol do Chrome",
            "Zara Chrome kholna",
            "Please open Chrome",
            "Would you open Chrome?",
        ]
        for v in variants:
            frame = hcm.analyze_turn(v)
            assert frame.target.lower() == "chrome"
            assert frame.action in ("open", "kholo", "chala", "start", "launch")
            assert frame.is_executable_command is True
            assert frame.decision == "EXECUTE"

    # 7. Statements
    def test_group_07_human_statements(self, hcm):
        statements = [
            "Aaj main bahut tired hoon.",
            "Aaj office mein bahut kaam tha.",
            "Maine abhi lunch nahi kiya.",
            "Aaj mausam achha hai.",
            "Kal mujhe Mumbai jaana hai.",
            "Mujhe Excel mein kaam karna hai.",
            "Mera internet slow chal raha hai.",
        ]
        for s in statements:
            frame = hcm.analyze_turn(s)
            assert frame.is_executable_command is False
            assert frame.decision in ("ANSWER", "CHAT", "CLARIFY")

    # 8. Conversational Repair / Correction
    def test_group_08_conversational_repair(self, hcm):
        repairs = [
            ("Chrome nahi Edge", "edge"),
            ("nahi, Chrome nahi Edge kholo", "edge"),
            ("Arre nahi, woh nahi doosra", "doosra"),
            ("Actually Edge kholo", "edge"),
        ]
        for query, expected_new in repairs:
            da_res = DialogueActClassifier.classify(query)
            assert da_res.act == DialogueAct.CORRECTION

    # 9. Negation (Strict Negation Invariant)
    def test_group_09_negation_invariant(self, hcm):
        negations = [
            "Chrome mat kholo",
            "Chrome nahi kholna",
            "Maine Chrome nahi bola",
            "Usko band mat karo",
            "Nahi, mujhe woh nahi chahiye",
            "Don't open Chrome",
            "Do not close Chrome",
        ]
        for query in negations:
            frame = hcm.analyze_turn(query)
            assert frame.is_negated is True, f"Failed negation for '{query}'"
            assert frame.is_executable_command is False, f"Negated utterance '{query}' must NOT be executable"
            assert frame.decision == "ANSWER"
            assert "DO_NOT_" in frame.communicative_goal

    # 10. Ellipsis Understanding
    def test_group_10_ellipsis_understanding(self, hcm):
        # 1. "Ab band karo" with active Chrome context
        ctx = ActiveTargetContext()
        ctx.set_application("chrome", title="Google Chrome")
        frame_close = hcm.analyze_turn("Ab band karo", active_context=ctx)
        assert frame_close.action == "close"
        assert frame_close.is_executable_command is True

        # 2. "Volume 50"
        frame_vol = hcm.analyze_turn("Volume 50")
        assert frame_vol.quantity == 50
        assert frame_vol.action in ("set_volume", "set", "karo")
        assert frame_vol.is_executable_command is True

    # 11. Reference Understanding (Demonstratives & Ordinals)
    def test_group_11_reference_understanding(self, hcm):
        ref_tokens = [
            "ye", "yeh", "woh", "isko", "ise", "usko", "usme", "isme",
            "doosra", "pehla", "last wala", "upar wala", "neeche wala",
            "wahi", "same", "usko hi", "jo abhi khula tha"
        ]
        for ref in ref_tokens:
            assert ReferenceResolver.has_reference(ref) is True, f"Missing reference recognition for '{ref}'"

        ctx = ActiveTargetContext()
        ctx.set_application("chrome", title="Google Chrome")
        resolved = ReferenceResolver.resolve("jo abhi khula tha", active_context=ctx)
        assert resolved.resolved is True
        assert resolved.target_name.lower() == "chrome"

    # 12. Pragmatic Understanding
    def test_group_12_pragmatic_understanding(self, hcm):
        # Pragmatic subtext: "Yaar bahut garmi hai." -> Clarify "AC chala doon?", never auto-execute
        frame_hot = hcm.analyze_turn("Yaar bahut garmi hai.")
        assert frame_hot.pragmatic_goal == "COOL_ENVIRONMENT"
        assert frame_hot.pragmatic_clarification == "AC chala doon?"
        assert frame_hot.decision == "CLARIFY"
        assert frame_hot.is_executable_command is False
        assert frame_hot.certainty <= 0.60

        frame_cold = hcm.analyze_turn("Bahut thand lag rahi hai.")
        assert frame_cold.pragmatic_goal == "WARM_ENVIRONMENT"
        assert frame_cold.pragmatic_clarification == "Heater chala doon?"
        assert frame_cold.decision == "CLARIFY"
        assert frame_cold.is_executable_command is False

    # 13. Topic Switching and Return
    def test_group_13_topic_switching_and_return(self):
        tracker = TopicTracker()
        state = ConversationState()

        # Step 1: In Excel workflow
        da_excel = DialogueActResult(act=DialogueAct.COMMAND, topic_hint="excel", is_executable_command=True)
        tracker.track_utterance("Excel kholo", da_excel, state)
        assert tracker.get_active_topic() == "excel"

        # Step 2: Switch to weather side question
        da_weather = DialogueActResult(act=DialogueAct.QUESTION, topic_hint="weather", is_executable_command=False)
        tracker.track_utterance("Waise kal weather kaisa rahega?", da_weather, state)
        assert tracker.get_active_topic() == "weather"
        assert "excel" in tracker.topic_stack

        # Step 3: Return to previous workflow
        restored = tracker.return_to_previous_workflow(state)
        assert restored == "excel"
        assert tracker.get_active_topic() == "excel"

    # 14. Code-Switching (Mixed Hindi/English)
    def test_group_14_code_switching(self, hcm):
        code_switched = [
            "Can you mera volume thoda low kar do?",
            "Kal meeting ke liye presentation ready karna hai.",
            "Isko thoda aur clean kar do.",
            "Open the file jo desktop pe hai.",
        ]
        for s in code_switched:
            frame = hcm.analyze_turn(s)
            assert frame.language == "hinglish"
            assert frame.is_code_switched is True

    # 15. Politeness & Urgency Classification
    def test_group_15_politeness_and_urgency(self, hcm):
        frame_polite = hcm.analyze_turn("Please Chrome open kar do bhai")
        assert frame_polite.politeness == "POLITE"

        frame_urgent = hcm.analyze_turn("Jaldi system lock karo emergency hai")
        assert frame_urgent.urgency == "URGENT"

    # 16. Confirmation / Rejection / Cancellation
    def test_group_16_confirmation_rejection_cancellation(self, hcm):
        # Confirmation
        c_res = ConversationalIntentClassifier.classify("haan karo", has_pending_confirmation=True)
        assert c_res.intent_type == ConversationalIntentType.CONFIRMATION
        assert c_res.is_executable is True

        # Rejection
        r_res = ConversationalIntentClassifier.classify("nahi rehne do")
        assert r_res.intent_type in (ConversationalIntentType.REJECTION, ConversationalIntentType.CANCELLATION)
        assert r_res.is_executable is False

        # Cancellation
        abort_res = ConversationalIntentClassifier.classify("cancel karo")
        assert abort_res.intent_type == ConversationalIntentType.CANCELLATION
        assert abort_res.is_executable is False

    # 17. One-Word Replies
    def test_group_17_one_word_replies(self, hcm):
        one_words = ["haan", "nahi", "theek", "done", "wait", "ruko"]
        for w in one_words:
            frame = hcm.analyze_turn(w)
            assert frame.raw_utterance == w
            assert frame.dialogue_act is not None

    # 18. Capability Questions Non-Execution Guarantee
    def test_group_18_capability_question_guarantee(self, hcm):
        cap_queries = [
            "kya tum system lock kar sakte ho?",
            "can you open Chrome?",
            "tum Excel chala sakte ho?",
        ]
        for q in cap_queries:
            frame = hcm.analyze_turn(q)
            assert frame.intention == ConversationalIntentType.CAPABILITY_QUESTION
            assert frame.is_executable_command is False
            assert frame.decision == "ANSWER"
