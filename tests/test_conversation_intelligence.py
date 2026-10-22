# tests/test_conversation_intelligence.py
"""
Tests for Conversation Intelligence Layer and Hinglish Conversational AI Engine.
Covers multi-turn context, response-awareness, conversational repair, topic switching,
personality tones, compound commands, and structured metrics.
"""

import pytest
from brain.conversation_engine import (
    ConversationClassifier,
    ConversationEngine,
    ConversationalIntent,
    ConversationIntent,
    ConversationNormalizer,
    ContextResolver,
    PersonalityConfig,
    PersonaTone,
    ResponseStrategy,
    StrategySelector,
    ConversationMetricsLogger
)
from brain.llm import MockLLMProvider


def test_local_support_remembers_listening_choice():
    engine = ConversationEngine()
    assert "sunun" in engine.process_conversation_turn("aaj mera mood kharab hai")[1]
    assert "sun raha" in engine.process_conversation_turn("bas suno")[1]
    assert "deadline" in engine.process_conversation_turn("office mein deadline hai")[1].lower()
    assert "control" in engine.process_conversation_turn("solution do")[1]
    engine.process_conversation_turn("nahi")
    assert engine.context_tracker.state.support_mode is None


def test_context_expiration_drops_stale_question_and_entity():
    import time
    engine = ConversationEngine()
    engine.context_tracker.state.ttl_seconds = 20
    engine.context_tracker.update_user_turn("India", ConversationalIntent.GENERAL_CHAT, {"place": "India"})
    engine.context_tracker.state.last_updated_time = time.time() - 30
    engine.process_conversation_turn("hello")
    assert engine.context_tracker.state.ttl_seconds == 20
    assert engine.context_tracker.resolver.get_last_entity() is None


def test_provider_receives_bounded_history_and_persona():
    class Provider:
        def chat(self, messages):
            self.messages = messages
            return "Let's think about your idea."
    provider = Provider()
    engine = ConversationEngine(llm_provider=provider)
    engine.process_conversation_turn("I had an unusual idea today")
    engine.process_conversation_turn("it involves paper birds")
    assert provider.messages[0]["role"] == "system"
    assert "Never invent" in provider.messages[0]["content"]
    assert any(m["content"] == "I had an unusual idea today" for m in provider.messages)
    assert provider.messages[-1] == {"role": "user", "content": "it involves paper birds"}


def test_support_does_not_swallow_commands_or_reminders():
    engine = ConversationEngine()
    engine.process_conversation_turn("aaj mera mood kharab hai")
    assert engine.process_conversation_turn("Chrome kholo")[0] is False
    assert engine.context_tracker.state.support_mode is None
    assert engine.process_conversation_turn("mujhe 10 minute baad paani peene yaad dilana")[0] is False


def test_provider_failure_keeps_local_conversation_available():
    class OfflineProvider:
        def chat(self, messages):
            raise OSError("offline")
    engine = ConversationEngine(llm_provider=OfflineProvider())
    handled, response, _ = engine.process_conversation_turn("I had an unusual idea today")
    assert handled and response
    assert "samajh gaya" not in response.lower()


def test_recall_previous_user_statement():
    engine = ConversationEngine()
    engine.process_conversation_turn("hello")
    handled, response, _ = engine.process_conversation_turn("maine abhi kya kaha tha")
    assert handled and "hello" in response.lower()
from core.app import JarvisCore


@pytest.fixture
def conv_engine():
    llm = MockLLMProvider()
    return ConversationEngine(llm_provider=llm)


def test_conversation_classification_intents():
    """Verify classification of conversational intents vs commands."""
    # Commands
    assert ConversationClassifier.classify("Chrome kholo") == ConversationalIntent.COMMAND
    assert ConversationClassifier.classify("Volume 50 karo") == ConversationalIntent.COMMAND
    assert ConversationClassifier.classify("YouTube par gaana chalao") == ConversationalIntent.COMMAND

    # Casual
    assert ConversationClassifier.classify("Kya kar rahe ho?") == ConversationalIntent.STATUS_CHECK
    assert ConversationClassifier.classify("Hi jarvis") == ConversationalIntent.GREETING

    # Emotional
    assert ConversationClassifier.classify("Yaar aaj mood kharab hai") == ConversationalIntent.EMOTIONAL_MOOD
    assert ConversationClassifier.classify("Aaj main bohot sad hoon") == ConversationalIntent.EMOTIONAL_MOOD

    # Joke / Fun
    assert ConversationClassifier.classify("Koi funny joke suna") == ConversationalIntent.JOKE
    assert ConversationClassifier.classify("Ek achha chutkula batao") == ConversationalIntent.JOKE

    # Advice / Opinion
    assert ConversationClassifier.classify("Mujhe kya karna chahiye?") == ConversationalIntent.OPINION_REQUEST
    assert ConversationClassifier.classify("Tumhare hisaab se kaunsa better hai?") == ConversationalIntent.OPINION_REQUEST

    # Correction
    assert ConversationClassifier.classify("Nahi, mera matlab Excel wali file thi") == ConversationalIntent.CORRECTION

    # Interruption
    assert ConversationClassifier.classify("Ruk ek minute") == ConversationalIntent.INTERRUPTION_WAIT
    assert ConversationClassifier.classify("Wait") == ConversationalIntent.INTERRUPTION_WAIT


def test_casual_conversation_flow(conv_engine):
    """Verify the exact multi-turn Hinglish dialogue flow requested by user."""
    # Turn 1
    handled, resp1, _ = conv_engine.process_conversation_turn("Jarvis, kya kar raha hai?")
    assert handled is True
    assert "tumhara wait kar raha tha" in resp1.lower() or "wait" in resp1.lower()

    # Turn 2
    handled, resp2, _ = conv_engine.process_conversation_turn("Kuch nahi yaar.")
    assert handled is True
    assert "kabhi-kabhi" in resp2.lower() or "theek hai" in resp2.lower()

    # Turn 3
    handled, resp3, _ = conv_engine.process_conversation_turn("Achha ek baat bata.")
    assert handled is True
    assert "haan bolo" in resp3.lower()

    # Turn 4
    handled, resp4, _ = conv_engine.process_conversation_turn("Agar main tumhe kuch sikhau to yaad rakhoge?")
    assert handled is True
    assert "remember" in resp4.lower() or "yaad" in resp4.lower()

    # Turn 5
    handled, resp5, _ = conv_engine.process_conversation_turn("Jaise?")
    assert handled is True
    assert "workflow" in resp5.lower() or "settings" in resp5.lower()


def test_human_smalltalk_does_not_echo_previous_greeting(conv_engine):
    handled, greeting1, _ = conv_engine.process_conversation_turn("hi")
    assert handled is True

    handled, greeting2, _ = conv_engine.process_conversation_turn("hello")
    assert handled is True
    assert greeting2 != greeting1

    handled, wellbeing, intent = conv_engine.process_conversation_turn("kaise ho")
    assert handled is True
    assert intent == ConversationalIntent.HOW_ARE_YOU
    assert "kyunki" not in wellbeing.lower()
    assert "theek" in wellbeing.lower()

    handled, status, intent = conv_engine.process_conversation_turn("kya ho raha hai")
    assert handled is True
    assert intent == ConversationalIntent.STATUS_CHECK
    assert "kyunki" not in status.lower()
    assert greeting1.lower() not in status.lower()


def test_multi_turn_anaphora_and_entity_followup(conv_engine):
    """
    Verify multi-turn factual/entity flow:
    Turn 1: 'India ki capital kya hai?' (tracks active entity India)
    Turn 2: 'Achha wahan ka weather kaisa hai?' (wahan -> India)
    Turn 3: 'Uski population kitni hai?' (uski -> India)
    """
    # Turn 1: Seed entity context
    conv_engine.context_tracker.update_user_turn("India ki capital kya hai?", ConversationalIntent.QUESTION_WH, entities={"place": "India"})
    conv_engine.context_tracker.update_assistant_turn("India ki capital New Delhi hai.", ConversationalIntent.EXPLANATION_REQUEST)

    # Turn 2: Follow-up with spatial pronoun 'wahan'
    h2, r2, _ = conv_engine.process_conversation_turn("Achha wahan ka weather kaisa hai?")
    assert h2 is True
    assert "india" in r2.lower() or "weather" in r2.lower() or "mausam" in r2.lower()

    # Turn 3: Follow-up with pronoun 'uski'
    h3, r3, _ = conv_engine.process_conversation_turn("Uski population kitni hai?")
    assert h3 is True
    assert "140 crore" in r3.lower() or "population" in r3.lower()


def test_response_awareness_queries(conv_engine):
    """
    Verify response-awareness where Jarvis knows what it just said:
    - 'kyun?' / 'kaise?'
    - 'example do'
    - 'short mein batao'
    - 'detail mein samjhao'
    - 'dobara bolo'
    """
    # Seed a response
    conv_engine.process_conversation_turn("Jarvis, kya kar raha hai?")

    # 1. Repeat
    h1, r1, _ = conv_engine.process_conversation_turn("Dobara bolo")
    assert h1 is True
    assert "maine kaha tha" in r1.lower()

    # 2. Short version
    h2, r2, _ = conv_engine.process_conversation_turn("Short mein batao")
    assert h2 is True
    assert "short me" in r2.lower()

    # 3. Examples
    h3, r3, _ = conv_engine.process_conversation_turn("Example do")
    assert h3 is True
    assert "jaise" in r3.lower()


def test_conversational_repair(conv_engine):
    """Verify conversational repair when user clarifies or corrects intent."""
    handled, resp, intent = conv_engine.process_conversation_turn("Nahi, mera matlab Brave browser tha")
    assert handled is True
    assert intent == ConversationalIntent.CORRECTION
    assert "brave" in resp.lower()
    assert "samajh gaya" in resp.lower()


def test_topic_switching_and_return(conv_engine):
    """Verify topic change and return via 'wapis usi baat par aao'."""
    conv_engine.context_tracker.set_topic("Machine Learning")
    assert conv_engine.context_tracker.get_topic() == "Machine Learning"

    # Switch topic
    conv_engine.context_tracker.set_topic("Cricket")
    assert conv_engine.context_tracker.get_topic() == "Cricket"

    # Return to previous topic
    h, resp, _ = conv_engine.process_conversation_turn("Wapis usi baat par aao")
    assert h is True
    assert "machine learning" in resp.lower() or "wapis" in resp.lower()


def test_personality_tone_adaptation(conv_engine):
    """Verify personality configuration changes tone without changing logic."""
    # Concise Tone
    conv_engine.set_tone("concise")
    assert conv_engine.get_tone() == "concise"
    h1, r1, _ = conv_engine.process_conversation_turn("Hi jarvis")
    assert h1 is True
    assert len(r1.split(".")) <= 2

    # Humorous Tone
    conv_engine.set_tone("humorous")
    assert conv_engine.get_tone() == "humorous"
    h2, r2, _ = conv_engine.process_conversation_turn("thanks jarvis")
    assert h2 is True
    assert any(emoji in r2 for emoji in ["😄", "😎", "🙌"])

    # Reset to Natural
    conv_engine.set_tone("natural")
    assert conv_engine.get_tone() == "natural"


def test_compound_command_extraction():
    """Verify compound commands (conversational prefix + actionable command) are extracted."""
    chat, cmd = ConversationClassifier.extract_compound_command("achha weather to theek hai par Chrome khol do")
    assert chat is not None and "weather" in chat.lower()
    assert cmd is not None and "chrome khol do" in cmd.lower()

    res = ConversationClassifier.classify_detailed("achha weather to theek hai par Chrome khol do")
    assert res.is_command is True
    assert res.actionable_command == "Chrome khol do"


def test_conversation_metrics_logging(conv_engine):
    """Verify quality metrics logger records turns and generates summary."""
    conv_engine.process_conversation_turn("Hi jarvis")
    conv_engine.process_conversation_turn("Kya kar rahe ho?")
    summary = conv_engine.get_metrics_summary()
    assert summary["total_turns"] >= 2
    assert summary["avg_confidence"] > 0.0


def test_context_resolver_anaphora():
    """Verify anaphora resolution ('usko', 'wahi') with previous turns."""
    resolver = ContextResolver()

    class MockTurn:
        def __init__(self, raw):
            self.raw_input = raw
            self.entities = {}

    recent_turns = [MockTurn("Chrome open karo")]
    resolved, entity = resolver.resolve("Usko open kar do", recent_turns)
    assert entity == "chrome"
    assert "chrome" in resolved.lower()


def test_advanced_conversational_intents(conv_engine):
    """Comprehensive test covering all conversational categories and edge cases."""
    # 1. Activity Update
    handled1, resp1, int1 = conv_engine.process_conversation_turn("main abhi khana khane ja raha hoon")
    assert handled1 is True
    assert int1 == ConversationalIntent.ACTIVITY_UPDATE
    assert any(w in resp1.lower() for w in ["khana", "araam", "yahi hoon"])

    # 2. Listening Check
    handled2, resp2, int2 = conv_engine.process_conversation_turn("kya tum meri baat sun rahe ho?")
    assert handled2 is True
    assert int2 == ConversationalIntent.LISTENING_CHECK
    assert any(w in resp2.lower() for w in ["sun raha hoon", "active", "attention"])

    # 3. Help Inquiry
    handled3, resp3, int3 = conv_engine.process_conversation_turn("kya tum meri help kar sakte ho?")
    assert handled3 is True
    assert int3 == ConversationalIntent.HELP_INQUIRY
    assert any(w in resp3.lower() for w in ["help", "madad", "ready"])

    # 4. Gratitude & Politeness
    handled4, resp4, int4 = conv_engine.process_conversation_turn("thanks a lot jarvis")
    assert handled4 is True
    assert int4 == ConversationalIntent.GRATITUDE
    assert any(w in resp4.lower() for w in ["swagat", "mention not", "anytime", "welcome"])

    # 5. Apology & Politeness
    handled5, resp5, int5 = conv_engine.process_conversation_turn("sorry galti ho gayi")
    assert handled5 is True
    assert int5 == ConversationalIntent.APOLOGY
    assert any(w in resp5.lower() for w in ["koi baat nahi", "chill", "tension", "problem", "don't worry", "theek hai"])

    # 6. Farewell
    handled6, resp6, int6 = conv_engine.process_conversation_turn("good night jarvis")
    assert handled6 is True
    assert int6 == ConversationalIntent.FAREWELL
    assert any(w in resp6.lower() for w in ["good night", "araam", "standby", "alvida"])

    # 7. Topic Change
    handled7, resp7, int7 = conv_engine.process_conversation_turn("topic change karo")
    assert handled7 is True
    assert int7 == ConversationalIntent.TOPIC_CHANGE
    assert any(w in resp7.lower() for w in ["topic", "naye", "discuss"])

    # 8. Dismissal
    handled8, resp8, int8 = conv_engine.process_conversation_turn("bas rehne do")
    assert handled8 is True
    assert int8 == ConversationalIntent.DISMISSAL_CANCEL
    assert any(w in resp8.lower() for w in ["cancel", "drop", "rehne"])

    # 9. Follow-up Continuation
    handled9, resp9, int9 = conv_engine.process_conversation_turn("achha phir kya hua?")
    assert handled9 is True
    assert int9 == ConversationalIntent.FOLLOW_UP_CONTINUATION


def test_transliteration_and_stt_robustness():
    """Verify normalizer handles colloquial spellings and repeated characters."""
    assert ConversationNormalizer.clean("accha") == "achha"
    assert ConversationNormalizer.clean("haaaan") == "haan"
    assert ConversationNormalizer.clean("kyuuu?") == "kyun"
    assert ConversationNormalizer.clean("thik hai bhai") == "theek hai bhai"
    assert ConversationNormalizer.clean("thnx jarvis") == "thanks jarvis"
    assert ConversationNormalizer.clean("sooooorry", remove_fillers=True) == "sorry"


def test_dynamic_phrase_registration(conv_engine):
    """Verify runtime registration of custom approved user phrases without modifying code."""
    conv_engine.register_custom_phrase("chai peene chalte hain", ConversationalIntent.ACTIVITY_UPDATE)
    handled, resp, intent = conv_engine.process_conversation_turn("chai peene chalte hain")
    assert handled is True
    assert intent == ConversationalIntent.ACTIVITY_UPDATE


def test_end_to_end_core_conversation(tmp_path):
    """Verify end-to-end processing in JarvisCore pipeline."""
    core = JarvisCore()
    from memory.memory_manager import MemoryManager
    from brain.response import ResponseGenerator
    from brain.llm import MockLLMProvider
    from plugins.manager import PluginManager

    db_path = str(tmp_path / "test_jarvis.db")
    mem = MemoryManager(db_path=db_path)
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")

    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen
    )

    # 1. Casual talk
    resp = core.process_input("Jarvis, kya kar raha hai?")
    assert any(w in resp.lower() for w in ["wait", "bolo", "intezar", "ready", "command"])

    # 2. Emotional talk
    resp_mood = core.process_input("Yaar aaj mood kharab hai")
    assert any(w in resp_mood.lower() for w in ["kya hua", "break", "chill", "relax", "sunun"])

    # 3. Interruption
    resp_stop = core.process_input("Ruk ek minute")
    assert "ruk gaya" in resp_stop.lower() or "bataiye" in resp_stop.lower()

    # 4. Activity Update via Core pipeline
    resp_activity = core.process_input("Jarvis main abhi khana khane ja raha hoon")
    assert any(w in resp_activity.lower() for w in ["khana", "araam", "yahi hoon"])

    # 5. Listening Complaint & Feedback
    resp_complaint = core.process_input("Pehle kyon nahi listen kar rahi thi? Kab se bol raha tha listen kar, listen karna nonsense.")
    assert "sorry" in resp_complaint.lower() or "maaf" in resp_complaint.lower()
    assert any(w in resp_complaint.lower() for w in ["voice", "baat", "detect", "pick", "sun", "listening"])
    assert "aage kya karna hai?" not in resp_complaint.lower()
    assert "bataiye iske baare mein kya karna hai" not in resp_complaint.lower()


def test_listening_complaint_classification_and_response(conv_engine):
    """
    Verifies that complaints / criticisms about previous listening behavior
    are recognized as USER_COMPLAINT_FEEDBACK and responded to with natural apology.
    """
    phrases = [
        "Pehle kyon nahi listen kar rahi thi? Kab se bol raha tha listen kar, listen karna nonsense.",
        "sun kyon nahi raha tha?",
        "kab se bol raha tha sun nahi raha",
        "why were you not listening?",
        "listen karna nonsense",
        "itni der se bol raha hoon response nahi diya"
    ]
    for p in phrases:
        handled, resp, intent = conv_engine.process_conversation_turn(p)
        assert handled is True, f"Failed to handle complaint phrase: {p}"
        assert intent in (
            ConversationalIntent.USER_COMPLAINT_FEEDBACK,
            ConversationalIntent.CRITICISM_LISTENING,
            ConversationalIntent.COMPLAINT
        ), f"Incorrect intent {intent} for phrase: {p}"
        assert any(w in resp.lower() for w in ["sorry", "maaf"]), f"Missing apology in response: {resp}"
        assert any(w in resp.lower() for w in ["detect", "pick", "voice", "sun", "listening"]), f"Missing listening context in response: {resp}"
