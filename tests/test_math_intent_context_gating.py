# tests/test_math_intent_context_gating.py
"""Regression tests for reported 05:48/05:49 failures + negation guard.

Covers:
- "2+2=?" must NOT be UNINTELLIGIBLE (math whitelist in InputQuality).
- "2+2 kitana hota hai?" (STT variant) must calculate, not chitchat.
- "nahi" must survive HinglishNormalizer (was fuzzy-corrected to "rahi",
  breaking troubleshooting/correction/negation intents).
- "system lock kyun nahi ho raha?" must stay TROUBLESHOOTING end-to-end.
- Laya rescue_intent deterministic math pre-check (no model download needed).
"""

from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.conversation import TextNormalizer
from core.semantic.normalizer import HinglishNormalizer
from core.speech_understanding import (
    InputQuality,
    InputQualityEvaluator,
    SpeechDecision,
    SpeechUnderstandingEngine,
)
from plugins.math.calculator import SpokenMathNormalizer


import pytest


@pytest.fixture
def core_app(tmp_path):
    from brain.llm import MockLLMProvider
    from brain.response import ResponseGenerator
    from core.app import JarvisCore
    from memory.memory_manager import MemoryManager
    from plugins.manager import PluginManager

    core = JarvisCore()
    mem = MemoryManager(db_path=str(tmp_path / "test_math_gating.db"))
    llm = MockLLMProvider()
    resp_gen = ResponseGenerator(llm_provider=llm)
    plugins = PluginManager(plugin_dir="plugins")
    plugins.discover_and_load()
    core.initialize_subsystems(
        memory_manager=mem,
        learning_manager=None,
        brain=resp_gen,
        classifier=None,
        plugin_manager=plugins,
        response_generator=resp_gen,
    )
    return core


def test_math_short_expression_is_clean_quality():
    for q in ("2+2=?", "2+2", "10/2"):
        quality, score, meta = InputQualityEvaluator.evaluate_quality(q, q, False)
        assert quality == InputQuality.CLEAN, (q, quality, meta)
        assert score >= 0.90


def test_math_speech_decision_executes():
    for q in ("2+2=?", "2+2 kitana hota hai?", "2+2 kitna hota hai"):
        res = SpeechUnderstandingEngine.process_speech_input(q)
        assert res.input_quality == InputQuality.CLEAN
        assert res.decision == SpeechDecision.EXECUTE_VERIFIED, (q, res.decision)
        assert res.confidence.combined >= 0.70


def test_math_conversational_intent_is_action_command():
    for q in ("2+2=?", "2+2 kitana hota hai?", "25 mein 15 jod do"):
        res = ConversationalIntentClassifier.classify(q)
        assert res.intent_type == ConversationalIntentType.ACTION_COMMAND, (q, res.intent_type)
        assert res.is_executable is True


def test_negation_survives_normalization():
    assert HinglishNormalizer.normalize_text("system lock kyun nahi ho raha?") == "system lock kyun nahi ho raha?"
    assert HinglishNormalizer.normalize_text("chrome nahi brave kholo") == "chrome nahi brave kholo"
    assert TextNormalizer.normalize("system lock kyun nahi ho raha?") == "system lock kyun nahi ho raha?"


def test_troubleshooting_after_normalization():
    normalized = TextNormalizer.normalize("system lock kyun nahi ho raha?")
    res = ConversationalIntentClassifier.classify(normalized)
    assert res.intent_type == ConversationalIntentType.TROUBLESHOOTING, res.intent_type


def test_kitana_variant_calculates():
    from plugins.math.calculator import MathEngine
    for q in ("2+2 kitana hota hai?", "2+2 kitna hota hai?", "2+2 kya hota hai"):
        engine_res = MathEngine().calculate(q)
        assert engine_res.success is True, (q, engine_res.formatted_answer)
        assert "4" in engine_res.formatted_answer


def test_laya_rescue_deterministic_math_without_model():
    from core.laya import get_laya_manager
    from core.laya.manager import LayaModelManager
    LayaModelManager.reset_instance()
    mgr = get_laya_manager(config={"enabled": True, "use_for_intent_routing": False})
    rescue = mgr.rescue_intent("2+2 kitana hota hai?")
    assert rescue is not None
    assert rescue["choice"] == "calculation"
    assert rescue["confidence"] >= 0.90
    LayaModelManager.reset_instance()


def test_end_to_end_reported_cases(core_app):
    assert "4" in core_app.process_input("2+2=?", source="cli")
    assert "4" in core_app.process_input("2+2 kitana hota hai?", source="cli")
    resp = core_app.process_input("system lock kyun nahi ho raha?", source="cli")
    assert ("reasons" in resp.lower() or "policy" in resp.lower()), resp
