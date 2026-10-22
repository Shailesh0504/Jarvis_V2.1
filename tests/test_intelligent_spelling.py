"""
tests/test_intelligent_spelling.py
Comprehensive test suite for Intelligent Spelling Correction layer.
Verifies silent correction of high-confidence typos, natural acknowledgement
generation, personalized ambiguous clarifications, and end-to-end JarvisApp behavior.
"""

import pytest
from brain.spelling_resolver import (
    SpellingResolver,
    SpellingClarificationFormatter,
    SpellingResolution,
)
from core.app import JarvisCore


class TestIntelligentSpelling:
    """Verifies intelligent spelling correction and clarification logic."""

    # -------------------------------------------------------------------------
    # 1. High-Confidence Silent Corrections
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "typo_input,expected_corrected,expected_typo,expected_correction",
        [
            ("retstart", "restart", "retstart", "restart"),
            ("retstart the pc", "restart the pc", "retstart", "restart"),
            ("microsft", "microsoft", "microsft", "microsoft"),
            ("open excell", "open excel", "excell", "excel"),
            ("open exel", "open excel", "exel", "excel"),
            ("chrme kholo", "chrome kholo", "chrme", "chrome"),
            ("crome kholo", "chrome kholo", "crome", "chrome"),
            ("blutooth on karo", "bluetooth on karo", "blutooth", "bluetooth"),
            ("blootooth connect", "bluetooth connect", "blootooth", "bluetooth"),
        ],
    )
    def test_high_confidence_silent_corrections(
        self,
        typo_input: str,
        expected_corrected: str,
        expected_typo: str,
        expected_correction: str,
    ):
        """High-confidence typos must be silently corrected without requiring confirmation."""
        resolution = SpellingResolver.resolve(typo_input)
        assert resolution is not None, f"SpellingResolver failed to resolve: '{typo_input}'"
        assert resolution.corrected_text.lower() == expected_corrected.lower()
        assert resolution.typo.lower() == expected_typo.lower()
        assert resolution.correction.lower() == expected_correction.lower()
        assert not resolution.needs_confirmation, f"High-confidence typo '{typo_input}' should not require confirmation"
        assert resolution.confidence >= 0.85

    # -------------------------------------------------------------------------
    # 2. Natural Spoken Acknowledgement Generation
    # -------------------------------------------------------------------------
    def test_open_exel_spoken_ack(self):
        """User: 'open exel' -> Jarvis spoken ack: 'Ji, Microsoft Excel khol raha hoon.'"""
        resolution = SpellingResolver.resolve("open exel")
        assert resolution is not None
        ack = SpellingClarificationFormatter.format_auto_ack(
            typo=resolution.typo,
            correction=resolution.correction,
            original_text=resolution.original_text,
        )
        assert ack == "Ji, Microsoft Excel khol raha hoon."

    def test_chrme_kholo_spoken_ack(self):
        """User: 'chrme kholo' -> Jarvis spoken ack: 'Ji, Chrome khol raha hoon.'"""
        resolution = SpellingResolver.resolve("chrme kholo")
        assert resolution is not None
        ack = SpellingClarificationFormatter.format_auto_ack(
            typo=resolution.typo,
            correction=resolution.correction,
            original_text=resolution.original_text,
        )
        assert ack == "Ji, Chrome khol raha hoon."

    def test_blutooth_on_spoken_ack(self):
        """User: 'blutooth on karo' -> Jarvis spoken ack: 'Ji, Bluetooth enable kar raha hoon.'"""
        resolution = SpellingResolver.resolve("blutooth on karo")
        assert resolution is not None
        ack = SpellingClarificationFormatter.format_auto_ack(
            typo=resolution.typo,
            correction=resolution.correction,
            original_text=resolution.original_text,
        )
        assert ack == "Ji, Bluetooth enable kar raha hoon."

    # -------------------------------------------------------------------------
    # 3. Personalized Ambiguous / Low-Confidence Clarification
    # -------------------------------------------------------------------------
    def test_ambiguous_choice_with_user_name(self):
        """With known user_name='Shailesh', ambiguous choice yields: 'Shailesh, aap Excel keh rahe hain ya Word?'"""
        clarification = SpellingClarificationFormatter.format_clarification(
            typo="wrd",
            correction="Excel",
            original_text="open wrd",
            alt_candidate="Word",
            user_name="Shailesh",
        )
        assert clarification == "Shailesh, aap Excel keh rahe hain ya Word?"

    def test_ambiguous_choice_without_user_name(self):
        """Without user_name, ambiguous choice defaults to: 'Aap 'Excel' keh rahe hain ya 'Word', Boss?'"""
        clarification = SpellingClarificationFormatter.format_clarification(
            typo="wrd",
            correction="Excel",
            original_text="open wrd",
            alt_candidate="Word",
            user_name=None,
        )
        assert clarification == "Aap 'Excel' keh rahe hain ya 'Word', Boss?"

    def test_unknown_words_are_not_blindly_corrected(self):
        """SpellingResolver must NOT blindly autocorrect random unknown words."""
        # Non-command random strings
        assert SpellingResolver.resolve("random unknown text xyz") is None
        assert SpellingResolver.resolve("qwerty asdfgh") is None
        assert SpellingResolver.resolve("shailesh yadav") is None

    # -------------------------------------------------------------------------
    # 4. End-to-End JarvisApp Pipeline Integration
    # -------------------------------------------------------------------------
    def test_app_e2e_open_exel_natural_ack(self):
        """
        End-to-End: 'open exel' processed via JarvisCore
        Must output the natural spoken acknowledgement: 'Ji, Microsoft Excel khol raha hoon.'
        """
        from plugins.manager import PluginManager
        app = JarvisCore()
        app.plugin_manager = PluginManager(plugin_dir="plugins", config=app.config, event_bus=app.event_bus)
        app.plugin_manager.discover_and_load()
        app.state_machine.transition_to(type(app.state_machine.current_state).IDLE)

        # Mock execution so it doesn't try to actually launch external processes during test
        if hasattr(app, "execution_strategies"):
            app.execution_strategies.launch_application_verified = lambda app_name: type(
                "Result", (), {"success": True, "data": {"message": "Microsoft Excel open ho gaya, Boss."}, "reason": None}
            )()

        response = app.process_input("open exel", source="cli")
        assert response == "Ji, Microsoft Excel khol raha hoon."

    def test_app_e2e_retstart_confirmation_trigger(self):
        """
        End-to-End: 'retstart' typo processed via JarvisCore
        Must resolve 'retstart' -> 'restart' and trigger the destructive confirmation prompt.
        """
        from plugins.manager import PluginManager
        app = JarvisCore()
        app.plugin_manager = PluginManager(plugin_dir="plugins", config=app.config, event_bus=app.event_bus)
        app.plugin_manager.discover_and_load()
        app.state_machine.transition_to(type(app.state_machine.current_state).IDLE)

        response = app.process_input("retstart", source="cli")
        assert "restart" in response.lower() or "kya aap" in response.lower()
