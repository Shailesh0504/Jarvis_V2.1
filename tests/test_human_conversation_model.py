# tests/test_human_conversation_model.py
"""
Comprehensive test suite for the Human Conversation Model in Jarvis V2.
Verifies the 7 core dimensions of human communication:
1. Words: Phrasing, normalization, Hinglish understanding.
2. Context: Active app, website, window, entity.
3. Intention: Speech-act classification (Command vs Question vs Troubleshooting).
4. Emotion: Affective state detection (Anger, Fatigue, Joy, Anxiety, Calm) & intensity.
5. Previous Conversation: Multi-turn history, anaphora resolution ("isme", "usko").
6. Correction: Conversational repair detection and preference assignment.
7. Situation: Time-of-day awareness, night mode, focus context.

Strictly adheres to the No-Duplicate-Implementation Rule (AGENTS.md §1.1).
"""

import os
import tempfile
import pytest

from brain.conversation.intents import ConversationalIntent
from brain.conversation.model import EmotionAnalyzer, HumanConversationFrame, HumanConversationModel
from brain.conversation.response_generator import ConversationResponseGenerator
from core.context import ActiveTargetContext, TurnContext
from core.conversational_intent import ConversationalIntentType
from core.semantic.hindi_vocab import EmotionConcept
from learning.learner import LearningManager
from memory.database import DatabaseManager


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    yield db
    if os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


@pytest.fixture
def human_model(temp_db):
    learn_mgr = LearningManager(db=temp_db, enabled=True)
    return HumanConversationModel(learning_manager=learn_mgr)


class TestHumanConversationModel:
    """Tests the 7 dimensions of the Human Conversation Model."""

    # -------------------------------------------------------------------------
    # 1. Words & Intention (Speech-Act Gating)
    # -------------------------------------------------------------------------
    def test_intention_speech_act_gating(self, human_model):
        """Differentiates Action Commands from Capability & Status Questions."""
        # 1. Action Command
        frame_cmd = human_model.analyze_turn("system lock karo")
        assert frame_cmd.intention == ConversationalIntentType.ACTION_COMMAND
        assert frame_cmd.is_executable_command is True

        # 2. Capability Question
        frame_cap = human_model.analyze_turn("kya tum system lock kar sakte ho?")
        assert frame_cap.intention == ConversationalIntentType.CAPABILITY_QUESTION
        assert frame_cap.is_executable_command is False
        assert frame_cap.suggested_tone == "informative_direct"

        # 3. Status Question
        frame_stat = human_model.analyze_turn("Chrome open hai kya?")
        assert frame_stat.intention == ConversationalIntentType.STATUS_QUESTION
        assert frame_stat.is_executable_command is False

        # 4. Troubleshooting Inquiry
        frame_trouble = human_model.analyze_turn("Chrome open kyun nahi ho raha?")
        assert frame_trouble.intention == ConversationalIntentType.TROUBLESHOOTING
        assert frame_trouble.is_executable_command is False
        assert frame_trouble.suggested_tone == "calm_empathy"

    # -------------------------------------------------------------------------
    # 2. Context & Anaphora Resolution ("isme", "usko")
    # -------------------------------------------------------------------------
    def test_context_and_anaphora_resolution(self, human_model):
        """Resolves 'isme' and 'usko' using active desktop context."""
        active_ctx = ActiveTargetContext()
        active_ctx.set_application("chrome", title="Google Chrome")

        frame = human_model.analyze_turn(
            "isme YouTube kholo",
            active_context=active_ctx
        )

        assert frame.context["application"] == "chrome"
        assert frame.resolved_entity == "chrome"
        assert "chrome" in frame.resolved_utterance.lower()

    # -------------------------------------------------------------------------
    # 3. Emotion Detection & Affective Cues
    # -------------------------------------------------------------------------
    def test_emotion_detection_frustration_and_anger(self, human_model):
        """Detects frustration/anger and triggers calm_empathy response tone."""
        utterance = "arrey yaar dimag kharab ho gaya ye kaam kyun nahi kar raha"
        frame = human_model.analyze_turn(utterance)

        assert frame.emotion == EmotionConcept.ANGER
        assert frame.emotion_intensity >= 0.70
        assert frame.is_frustrated_or_angry is True
        assert frame.suggested_tone == "calm_empathy"

    def test_emotion_detection_fatigue_and_tiredness(self, human_model):
        """Detects fatigue and triggers supportive_care response tone."""
        utterance = "aaj bohot zyada thak gaya hoon yaar sir dard ho raha hai"
        frame = human_model.analyze_turn(utterance)

        assert frame.emotion == EmotionConcept.FATIGUE
        assert frame.emotion_intensity >= 0.70
        assert frame.suggested_tone == "supportive_care"

    def test_emotion_detection_joy_and_celebration(self, human_model):
        """Detects joy and excitement and triggers enthusiastic response tone."""
        utterance = "aaj maza aa gaya mera project pass ho gaya!"
        frame = human_model.analyze_turn(utterance)

        assert frame.emotion == EmotionConcept.JOY
        assert frame.emotion_intensity >= 0.70
        assert frame.suggested_tone == "enthusiastic"

    def test_emotion_detection_anxiety_and_stress(self, human_model):
        """Detects stress/tension and flags anxiety state."""
        utterance = "badi tension ho rahi hai urgent problem ho gayi"
        frame = human_model.analyze_turn(utterance)

        assert frame.emotion == EmotionConcept.ANXIETY
        assert frame.emotion_intensity >= 0.75

    # -------------------------------------------------------------------------
    # 4. Correction Integration (Conversational Repair)
    # -------------------------------------------------------------------------
    def test_correction_detection_with_context_target(self, human_model):
        """Detects conversational repair and infers target from active context."""
        active_ctx = ActiveTargetContext()
        active_ctx.set_website("youtube")

        frame = human_model.analyze_turn(
            "nahi, brave mein open karo",
            active_context=active_ctx
        )

        assert frame.is_correction is True
        assert frame.is_executable_command is False  # Corrections handled by repair logic
        assert frame.correction_details is not None
        assert frame.correction_details["preferred_container"] == "brave"
        assert frame.correction_details["target"] == "youtube"
        assert frame.suggested_tone == "receptive_repair"

    # -------------------------------------------------------------------------
    # 5. Situation & Environmental Awareness (Late Night / Work Hours)
    # -------------------------------------------------------------------------
    def test_situation_awareness_late_night(self, human_model):
        """Adapts response tone to concise_quiet during late night hours."""
        late_night_situation = {
            "hour": 2,
            "day_part": "night",
            "is_late_night": True,
            "is_work_hours": False,
            "timestamp": 123456789.0
        }

        frame = human_model.analyze_turn(
            "kya haal hai",
            situation_override=late_night_situation
        )

        assert frame.situation["is_late_night"] is True
        assert frame.suggested_tone == "concise_quiet"

    # -------------------------------------------------------------------------
    # 6. Empathetic Response Generation with HumanConversationFrame
    # -------------------------------------------------------------------------
    def test_response_generator_empathy_adaptation(self, human_model):
        """ConversationResponseGenerator generates empathetic response based on frame."""
        resp_gen = ConversationResponseGenerator()

        # 1. Frustration / Anger empathy
        frame_frustrated = human_model.analyze_turn("arrey yaar dimag kharab ho gaya ye chal kyun nahi raha")
        resp_frustrated = resp_gen.generate(
            raw_text="arrey yaar dimag kharab ho gaya ye chal kyun nahi raha",
            normalized_text="arrey yaar dimag kharab ho gaya ye chal kyun nahi raha",
            intent=ConversationalIntent.COMPLAINT,
            conversation_frame=frame_frustrated
        )
        assert any(w in resp_frustrated.lower() for w in ["samajh", "frustrating", "pareshan mat", "check"])

        # 2. Fatigue empathy
        frame_tired = human_model.analyze_turn("aaj main bohot thak gaya hoon sir dard ho raha hai")
        resp_tired = resp_gen.generate(
            raw_text="aaj main bohot thak gaya hoon sir dard ho raha hai",
            normalized_text="aaj main bohot thak gaya hoon sir dard ho raha hai",
            intent=ConversationalIntent.EMOTIONAL_MOOD,
            conversation_frame=frame_tired
        )
        assert any(w in resp_tired.lower() for w in ["thake", "aaram", "sambhal", "load"])

        # 3. Joy empathy
        frame_joy = human_model.analyze_turn("aaj bohot khush hoon maza aa gaya!")
        resp_joy = resp_gen.generate(
            raw_text="aaj bohot khush hoon maza aa gaya!",
            normalized_text="aaj bohot khush hoon maza aa gaya!",
            intent=ConversationalIntent.EMOTIONAL_MOOD,
            conversation_frame=frame_joy
        )
        assert any(w in resp_joy.lower() for w in ["badhiya", "khushi", "achha", "mast"])

    # -------------------------------------------------------------------------
    # 7. Closed-Loop Integration with JarvisCore
    # -------------------------------------------------------------------------
    def test_jarvis_core_attaches_conversation_frame(self, temp_db):
        """JarvisCore._process_input attaches HumanConversationFrame to turn metadata."""
        from core.app import JarvisCore
        from memory.memory_manager import MemoryManager

        core = JarvisCore(config_path="config.yaml")
        mem_mgr = MemoryManager(db_path=temp_db.db_path)
        learn_mgr = LearningManager(db=temp_db, enabled=True)

        core.initialize_subsystems(
            memory_manager=mem_mgr,
            learning_manager=learn_mgr
        )

        # Run an interaction through JarvisCore
        core.process_input("hello jarvis, kaise ho?", source="cli")

        turn = core.conversation_manager.session.get_current_turn()
        assert turn is not None
        assert "conversation_frame" in turn.metadata
        frame = turn.metadata["conversation_frame"]
        assert isinstance(frame, HumanConversationFrame)
        assert frame.words == "hello jarvis, kaise ho?"
        assert frame.intention is not None
        assert frame.emotion is not None
