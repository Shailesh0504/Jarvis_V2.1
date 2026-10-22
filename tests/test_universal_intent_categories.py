"""
Tests for Semantic Meaning Normalization and 15 Universal Intent Categories.

Validates:
1. Meaning, Not Words: 7 variations of Chrome opening all resolve to:
   intent = OPEN_APPLICATION, entity = chrome
2. 15 Universal Intent Categories distinguished at minimum:
   COMMAND, QUESTION, INFORMATION_REQUEST, GENERAL_CONVERSATION, FOLLOW_UP,
   CORRECTION, CONFIRMATION, REJECTION, CANCELLATION, TROUBLESHOOTING,
   REQUEST_FOR_CLARIFICATION, SYSTEM_INFORMATION, ACTION_RESULT, COMPLAINT, SMALL_TALK
3. Extensibility: Registering new semantic categories without duplicating the intent system.
4. Backwards compatibility: intent == "OPEN_APP" remains True.
"""

import pytest

from brain.conversation.model import HumanConversationModel
from brain.semantic_parser import HinglishNLUParser
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.intent import UniversalCategoryRegistry, UniversalIntentCategory
from core.semantic.orchestrator import SemanticPipelineOrchestrator


class TestMeaningNotWordsAppOpening:
    """Validates that diverse phrasings resolve to canonical intent = OPEN_APPLICATION, entity = chrome."""

    @pytest.mark.parametrize("phrase", [
        "Chrome kholo",
        "Chrome open karo",
        "Bhai Chrome chala de",
        "Chrome start kar",
        "Can you open Chrome?",
        "Please launch Chrome",
        "Chrome khol do",
    ])
    def test_all_phrases_resolve_to_open_application_and_chrome(self, phrase):
        action = SemanticPipelineOrchestrator.parse(phrase)
        assert action is not None, f"Failed to parse phrase: '{phrase}'"

        # Canonical Intent & Entity
        assert action.intent == "OPEN_APPLICATION", (
            f"Expected intent == 'OPEN_APPLICATION' for '{phrase}', got {action.intent}"
        )
        assert action.entity == "chrome", (
            f"Expected entity == 'chrome' for '{phrase}', got {action.entity}"
        )

        # Backwards compatibility invariant: legacy tests checking "OPEN_APP" must still pass
        assert action.intent == "OPEN_APP", (
            f"Expected backwards compatibility equality for 'OPEN_APP' for '{phrase}'"
        )

    def test_hinglish_nlu_parser_facade_matches_orchestrator(self):
        for phrase in ["Chrome kholo", "Please launch Chrome", "Can you open Chrome?"]:
            action = HinglishNLUParser.parse(phrase)
            assert action is not None
            assert action.intent == "OPEN_APPLICATION"
            assert action.entity == "chrome"


class TestUniversalIntentCategories:
    """Validates that Jarvis distinguishes at minimum all 15 Universal Intent Categories."""

    @pytest.mark.parametrize("query,expected_cat", [
        # 1. COMMAND
        ("Chrome kholo", UniversalIntentCategory.COMMAND),
        ("volume 50 karo", UniversalIntentCategory.COMMAND),
        ("lock system", UniversalIntentCategory.COMMAND),
        ("Please launch Chrome", UniversalIntentCategory.COMMAND),

        # 2. QUESTION
        ("Can you open Chrome?", UniversalIntentCategory.QUESTION),
        ("kya tum system lock kar sakte ho?", UniversalIntentCategory.QUESTION),
        ("kya tum screen dekh sakte ho?", UniversalIntentCategory.QUESTION),

        # 3. INFORMATION_REQUEST
        ("what is DNS?", UniversalIntentCategory.INFORMATION_REQUEST),
        ("India ki capital kya hai?", UniversalIntentCategory.INFORMATION_REQUEST),
        ("explain photosynthesis", UniversalIntentCategory.INFORMATION_REQUEST),

        # 4. GENERAL_CONVERSATION
        ("aap kaise ho?", UniversalIntentCategory.GENERAL_CONVERSATION),
        ("Jarvis tell me about yourself", UniversalIntentCategory.GENERAL_CONVERSATION),

        # 5. FOLLOW_UP
        ("aur uske baad?", UniversalIntentCategory.FOLLOW_UP),
        ("what about tomorrow?", UniversalIntentCategory.FOLLOW_UP),
        ("and chrome also?", UniversalIntentCategory.FOLLOW_UP),

        # 6. CORRECTION
        ("nahi, chrome nahi edge", UniversalIntentCategory.CORRECTION),
        ("maine 50 bola tha", UniversalIntentCategory.CORRECTION),
        ("no, i meant notepad", UniversalIntentCategory.CORRECTION),

        # 7. CONFIRMATION
        ("haan", UniversalIntentCategory.CONFIRMATION),
        ("yes", UniversalIntentCategory.CONFIRMATION),
        ("theek hai kar do", UniversalIntentCategory.CONFIRMATION),
        ("proceed", UniversalIntentCategory.CONFIRMATION),

        # 8. REJECTION
        ("nahi chahiye", UniversalIntentCategory.REJECTION),
        ("no thanks", UniversalIntentCategory.REJECTION),
        ("no don't do that", UniversalIntentCategory.REJECTION),
        ("bilkul nahi", UniversalIntentCategory.REJECTION),

        # 9. CANCELLATION
        ("cancel karo", UniversalIntentCategory.CANCELLATION),
        ("rehne do", UniversalIntentCategory.CANCELLATION),
        ("stop it", UniversalIntentCategory.CANCELLATION),
        ("abort", UniversalIntentCategory.CANCELLATION),
        ("terminate task", UniversalIntentCategory.CANCELLATION),

        # 10. TROUBLESHOOTING
        ("Chrome open kyun nahi ho raha?", UniversalIntentCategory.TROUBLESHOOTING),
        ("wifi connect kyun nahi ho raha?", UniversalIntentCategory.TROUBLESHOOTING),

        # 11. REQUEST_FOR_CLARIFICATION
        ("kya matlab?", UniversalIntentCategory.REQUEST_FOR_CLARIFICATION),
        ("what do you mean?", UniversalIntentCategory.REQUEST_FOR_CLARIFICATION),
        ("samjha nahi", UniversalIntentCategory.REQUEST_FOR_CLARIFICATION),

        # 12. SYSTEM_INFORMATION
        ("cpu usage kitna hai?", UniversalIntentCategory.SYSTEM_INFORMATION),
        ("battery percentage kya hai?", UniversalIntentCategory.SYSTEM_INFORMATION),
        ("system status batao", UniversalIntentCategory.SYSTEM_INFORMATION),

        # 13. ACTION_RESULT
        ("Chrome open hua?", UniversalIntentCategory.ACTION_RESULT),
        ("system lock ho gaya kya?", UniversalIntentCategory.ACTION_RESULT),
        ("did it open yet?", UniversalIntentCategory.ACTION_RESULT),

        # 14. COMPLAINT
        ("tum sun nahi rahe ho", UniversalIntentCategory.COMPLAINT),
        ("galat kar diya tumne", UniversalIntentCategory.COMPLAINT),
        ("you made a mistake", UniversalIntentCategory.COMPLAINT),

        # 15. SMALL_TALK
        ("shukriya", UniversalIntentCategory.SMALL_TALK),
        ("thank you", UniversalIntentCategory.SMALL_TALK),
        ("good morning", UniversalIntentCategory.SMALL_TALK),
        ("nice job", UniversalIntentCategory.SMALL_TALK),
        ("tell me a joke", UniversalIntentCategory.SMALL_TALK),
    ])
    def test_universal_categories_classification(self, query, expected_cat):
        res = ConversationalIntentClassifier.classify(query)
        assert res.universal_category == expected_cat, (
            f"Query '{query}' expected universal_category={expected_cat.value}, got {res.universal_category.value} (type={res.intent_type.value})"
        )


class TestUniversalCategoryRegistryExtensibility:
    """Validates that new semantic categories can be added dynamically without duplicating the intent system."""

    def test_extensible_category_registration(self):
        # Verify default 15 categories are present
        default_cats = UniversalCategoryRegistry.list_categories()
        assert len(default_cats) >= 15
        for cat in UniversalIntentCategory:
            assert UniversalCategoryRegistry.is_registered(cat.value)

        # Register a new domain category
        new_cat = UniversalCategoryRegistry.register_category(
            name="EMERGENCY_OVERRIDE",
            description="High-priority emergency override category",
            default_executable=True,
            aliases=["PANIC", "EMERGENCY"]
        )
        assert new_cat == "EMERGENCY_OVERRIDE"
        assert UniversalCategoryRegistry.is_registered("EMERGENCY_OVERRIDE")

        descriptor = UniversalCategoryRegistry.get_category("EMERGENCY_OVERRIDE")
        assert descriptor is not None
        assert descriptor.default_executable is True
        assert "PANIC" in descriptor.aliases


class TestHumanConversationModelFrameUniversalCategory:
    """Validates that HumanConversationModel attaches universal_category to conversation frames."""

    def test_frame_contains_universal_category(self):
        hcm = HumanConversationModel()
        frame_cmd = hcm.analyze_turn("Chrome open karo")
        assert frame_cmd.universal_category == UniversalIntentCategory.COMMAND

        frame_q = hcm.analyze_turn("Can you open Chrome?")
        assert frame_q.universal_category == UniversalIntentCategory.QUESTION

        frame_complaint = hcm.analyze_turn("tum sun nahi rahe ho")
        assert frame_complaint.universal_category == UniversalIntentCategory.COMPLAINT
