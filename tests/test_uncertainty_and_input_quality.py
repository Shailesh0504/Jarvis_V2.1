# tests/test_uncertainty_and_input_quality.py
"""
Comprehensive test suite for Incomplete, Garbled & Uncertain Input Handling
(`nlp.uncertainty_and_input_recovery`).

Validates:
- InputQualityEvaluator classification (CLEAN, INCOMPLETE_FRAGMENT, UNINTELLIGIBLE, AMBIGUOUS, EMPTY)
- Zero False Intent Forcing (garbled inputs never classified as COMMAND, GK, SEARCH, or APPLICATION)
- ContextualRecoveryEngine (fragment recovery 'clo' -> 'close chrome', acoustic 'grave' -> 'Brave')
- Non-aggressive autocorrect (ordinary words in neutral context preserved)
- Ambiguous pronoun handling ('open it' prompts for target or resolves from recent file)
- NaturalUncertaintyResponder (non-repetitive rotating responses)
- Learning integration (evidence threshold >= 3 before promotion)
- End-to-end JarvisCore integration and 7-field telemetry diagnostics recording
"""

import pytest
from core.speech_understanding import (
    InputQuality,
    InputQualityEvaluator,
    ContextualRecoveryEngine,
    NaturalUncertaintyResponder,
    SpeechDecision,
    SpeechUnderstandingEngine,
    ConfidenceScores,
)
from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType,
)
from core.intent import UniversalIntentCategory, UniversalCategoryRegistry
from core.context import ActiveTargetContext


class MockTurn:
    def __init__(self, raw_input: str = "", response: str = ""):
        self.raw_input = raw_input
        self.response = response


class TestInputQualityEvaluator:
    """Validates lexical quality categorization across edge cases."""

    def test_unintelligible_inputs(self):
        garbled_cases = [
            "-[p-o0p-\\",
            r"!@#$%^&*()",
            "asdfghjkl",
            "zxcvbnm",
            "p-o0p-\\",
            "~~~~~",
            "???!!!!!###",
        ]
        for inp in garbled_cases:
            quality, conf, meta = InputQualityEvaluator.evaluate_quality(inp, inp)
            assert quality == InputQuality.UNINTELLIGIBLE, f"Failed for {inp!r}: got {quality}"
            assert conf <= 0.10

    def test_incomplete_fragment_inputs(self):
        fragment_cases = [
            "clo",
            "wha",
            "pla",
            "can you please",
            "chrome ko",
            "kripya",
        ]
        for inp in fragment_cases:
            quality, conf, meta = InputQualityEvaluator.evaluate_quality(inp, inp)
            assert quality == InputQuality.INCOMPLETE_FRAGMENT, f"Failed for {inp!r}: got {quality}"
            assert conf <= 0.30

    def test_ambiguous_pronoun_commands(self):
        ambiguous_cases = [
            "open it",
            "close that",
            "start it",
            "khol do ise",
            "use band karo",
            "ise open karo",
            "launch it",
        ]
        for inp in ambiguous_cases:
            quality, conf, meta = InputQualityEvaluator.evaluate_quality(inp, inp)
            assert quality == InputQuality.AMBIGUOUS, f"Failed for {inp!r}: got {quality}"
            assert conf <= 0.50

    def test_clean_meaningful_inputs(self):
        clean_cases = [
            "open chrome",
            "kya haal hai",
            "what is the capital of India",
            "volume 50 percent karo",
            "tell me a joke",
            "close this tab",
            "save the grave danger",
        ]
        for inp in clean_cases:
            quality, conf, meta = InputQualityEvaluator.evaluate_quality(inp, inp)
            assert quality == InputQuality.CLEAN, f"Failed for {inp!r}: got {quality}"
            assert conf >= 0.85

    def test_empty_and_whitespace_inputs(self):
        empty_cases = ["", "   ", "\t\n", "....", ",,,"]
        for inp in empty_cases:
            quality, conf, meta = InputQualityEvaluator.evaluate_quality(inp, inp)
            assert quality == InputQuality.EMPTY, f"Failed for {inp!r}: got {quality}"
            assert conf == 0.0


class TestContextualRecoveryEngine:
    """Validates meaning reconstruction from context, conversation, and workflows."""

    def test_fragment_recovery_with_active_app(self):
        ctx = ActiveTargetContext()
        ctx.set_application("chrome", action="open")

        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="clo",
            quality=InputQuality.INCOMPLETE_FRAGMENT,
            active_context=ctx
        )
        assert recovered is True
        assert reconstructed == "close chrome"
        assert "chrome" in ctx_used
        assert conf >= 0.85

    def test_fragment_recovery_with_recent_turn(self):
        recent_turns = [
            MockTurn(raw_input="open notepad", response="Notepad open kar diya."),
        ]
        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="clo",
            quality=InputQuality.INCOMPLETE_FRAGMENT,
            recent_turns=recent_turns
        )
        assert recovered is True
        assert reconstructed == "close notepad"
        assert conf >= 0.85

    def test_unrecoverable_fragment_without_context(self):
        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="clo",
            quality=InputQuality.INCOMPLETE_FRAGMENT,
            active_context=None,
            recent_turns=[]
        )
        assert recovered is False
        assert reconstructed is None
        assert conf == 0.0

    def test_acoustic_confusion_recovery_in_browser_context(self):
        ctx = ActiveTargetContext()
        ctx.set_application("chrome", action="open")

        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="open grave",
            quality=InputQuality.CLEAN,
            active_context=ctx
        )
        assert recovered is True
        assert reconstructed == "open Brave"
        assert "browser_context_acoustic" in ctx_used
        assert conf >= 0.85

    def test_non_aggressive_autocorrect_outside_browser_context(self):
        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="save the grave",
            quality=InputQuality.CLEAN,
            active_context=None,
            recent_turns=[]
        )
        assert recovered is False
        assert reconstructed is None

    def test_ambiguous_pronoun_recovery_with_recent_entity(self):
        recent_turns = [
            MockTurn(raw_input="check document.pdf", response="Document ready."),
        ]
        recovered, reconstructed, ctx_used, conf = ContextualRecoveryEngine.attempt_recovery(
            text="open it",
            quality=InputQuality.AMBIGUOUS,
            recent_turns=recent_turns
        )
        assert recovered is True
        assert reconstructed == "open document.pdf"
        assert "document.pdf" in ctx_used
        assert conf >= 0.85

    def test_learning_evidence_promotion_threshold(self):
        pattern = "custom_test_shortcut"
        target = "test_app"

        assert ContextualRecoveryEngine.is_pattern_promoted(pattern, target) is False

        # Observation 1
        ContextualRecoveryEngine._record_observation(pattern, target)
        assert ContextualRecoveryEngine.get_pattern_observation_count(pattern, target) == 1
        assert ContextualRecoveryEngine.is_pattern_promoted(pattern, target) is False

        # Observation 2
        ContextualRecoveryEngine._record_observation(pattern, target)
        assert ContextualRecoveryEngine.get_pattern_observation_count(pattern, target) == 2
        assert ContextualRecoveryEngine.is_pattern_promoted(pattern, target) is False

        # Observation 3 -> Meets threshold!
        ContextualRecoveryEngine._record_observation(pattern, target)
        assert ContextualRecoveryEngine.get_pattern_observation_count(pattern, target) == 3
        assert ContextualRecoveryEngine.is_pattern_promoted(pattern, target) is True


class TestNaturalUncertaintyResponder:
    """Validates non-repetitive rotating responses."""

    def test_unintelligible_rotation(self):
        responses = [NaturalUncertaintyResponder.get_unintelligible_response() for _ in range(10)]
        assert len(set(responses)) > 1
        # No consecutive duplicates
        for i in range(len(responses) - 1):
            assert responses[i] != responses[i + 1]

    def test_incomplete_rotation(self):
        responses = [NaturalUncertaintyResponder.get_incomplete_response() for _ in range(8)]
        assert len(set(responses)) > 1
        for i in range(len(responses) - 1):
            assert responses[i] != responses[i + 1]

    def test_ambiguous_rotation(self):
        responses = [NaturalUncertaintyResponder.get_ambiguous_response() for _ in range(8)]
        assert len(set(responses)) > 1
        for i in range(len(responses) - 1):
            assert responses[i] != responses[i + 1]


class TestConversationalIntentGating:
    """Validates conversational speech-act gating with input quality."""

    def test_unintelligible_classified_as_unknown(self):
        res = ConversationalIntentClassifier.classify("-[p-o0p-\\")
        assert res.intent_type == ConversationalIntentType.UNKNOWN
        assert res.confidence <= 0.10
        assert res.is_executable is False
        assert res.natural_response is not None
        assert any(term in res.natural_response for term in ("capture", "adhura", "boliye", "aaya", "repeat"))

    def test_ambiguous_classified_as_ambiguous(self):
        res = ConversationalIntentClassifier.classify("open it")
        assert res.intent_type == ConversationalIntentType.AMBIGUOUS
        assert res.confidence <= 0.50
        assert res.is_executable is False
        assert res.natural_response is not None
        assert any(term in res.natural_response for term in ("application", "target", "file", "cheez"))

    def test_never_forces_into_command_or_gk(self):
        for garbled in ["-[p-o0p-\\", "!@#$%", "asdfghjkl"]:
            res = ConversationalIntentClassifier.classify(garbled)
            assert res.intent_type not in (
                ConversationalIntentType.ACTION_COMMAND,
                ConversationalIntentType.COMMAND,
                ConversationalIntentType.INFORMATION_QUESTION,
                ConversationalIntentType.INFORMATION_REQUEST,
            )
            assert res.is_executable is False


class TestJarvisCoreIntegration:
    """End-to-end integration with JarvisCore pipeline and 7-field telemetry."""

    def test_garbled_input_handling_and_diagnostics(self):
        from core.app import JarvisCore
        core = JarvisCore()
        resp = core.process_input("-[p-o0p-\\", source="cli")
        assert resp
        assert any(w in resp for w in ("capture", "adhura", "boliye", "samajh", "repeat"))

        # Inspect turn telemetry
        last_turn = core.conversation_manager.get_history()[-1]
        diag = last_turn.metadata.get("speech_diagnostics")
        assert diag is not None
        assert diag["raw_input"] == "-[p-o0p-\\"
        assert diag["input_quality"] == "unintelligible"
        assert diag["detected_intent"] == "unknown"
        assert diag["confidence"] <= 0.10
        assert diag["recovered_interpretation"] is None

    def test_isolated_incomplete_fragment_prompt(self):
        from core.app import JarvisCore
        core = JarvisCore()
        resp = core.process_input("clo", source="cli")
        assert resp
        assert any(w in resp for w in ("adhura", "adhuri", "poora", "repeat", "cut off", "boliye"))

    def test_isolated_ambiguous_command_prompt(self):
        from core.app import JarvisCore
        core = JarvisCore()
        resp = core.process_input("open it", source="cli")
        assert resp
        assert any(w in resp for w in ("application", "file", "target", "referring"))

    def test_contextual_fragment_recovery_execution(self):
        from core.app import JarvisCore
        core = JarvisCore()
        # Step 1: Open chrome
        r_open = core.process_input("open chrome", source="cli")
        assert "open" in r_open.lower() or "chrome" in r_open.lower()

        # Step 2: Say 'clo' -> Reconstructs to close chrome
        r_close = core.process_input("clo", source="cli")
        assert "chrome" in r_close.lower() or "band" in r_close.lower() or "close" in r_close.lower()

        last_turn = core.conversation_manager.get_history()[-1]
        diag = last_turn.metadata.get("speech_diagnostics")
        assert diag["recovered_interpretation"] == "close chrome"
        assert "active_context" in diag["context_used"]

    def test_contextual_acoustic_recovery_execution(self):
        from core.app import JarvisCore
        core = JarvisCore()
        core.process_input("open chrome", source="cli")

        # In browser context, 'open grave' recovers to 'open Brave'
        r_grave = core.process_input("open grave", source="cli")
        assert "brave" in r_grave.lower()

        last_turn = core.conversation_manager.get_history()[-1]
        diag = last_turn.metadata.get("speech_diagnostics")
        assert diag["recovered_interpretation"] == "open Brave"
