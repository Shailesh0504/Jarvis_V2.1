"""
tests/test_vocabulary_lexicon_engine.py
Comprehensive test suite for Local Vocabulary / Lexicon Intelligence Layer.
Verifies English/Hindi/Hinglish phrase recognition, synonym mapping,
contextuality invariants, and target resolution without keyword brittleness.
"""

import pytest
from core.semantic.lexicon import (
    LexiconEngine,
    ActionConcept,
    TargetDomain,
    get_lexicon_engine,
)
from core.semantic.parsers.system import parse_system_control
from core.semantic.parsers.windows import parse_universal_target_action
from core.semantic.orchestrator import SemanticPipelineOrchestrator


class TestVocabularyLexiconEngine:
    """Verifies Vocabulary & Lexicon Intelligence features."""

    @pytest.fixture
    def engine(self) -> LexiconEngine:
        return get_lexicon_engine()

    # -------------------------------------------------------------------------
    # 1. System Restart Invariants
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "query",
        [
            "restart",
            "reboot",
            "restart the PC",
            "reboot my computer",
            "system ko restart karo",
            "PC dobara start karo",
        ],
    )
    def test_all_restart_phrases_resolve_to_system_restart(self, engine: LexiconEngine, query: str):
        """All variations of restart (English, Hindi, Hinglish) must resolve to SYSTEM_RESTART."""
        # 1. Lexicon check
        assert engine.is_system_restart_utterance(query), f"Failed lexicon restart check for: '{query}'"

        # 2. System parser check
        lowered = query.lower().strip()
        action = parse_system_control(query, lowered)
        assert action is not None, f"parse_system_control returned None for: '{query}'"
        assert action.intent == "SYSTEM_RESTART", f"Expected SYSTEM_RESTART, got {action.intent} for: '{query}'"
        assert action.service == "system"
        assert action.parameters.get("restart") is True

    # -------------------------------------------------------------------------
    # 2. Open Verbs & Application Target Resolution
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "verb,app_target",
        [
            ("open", "chrome"),
            ("launch", "excel"),
            ("start", "notepad"),
            ("chalao", "calculator"),
            ("khol do", "vlc"),
        ],
    )
    def test_open_verbs_map_to_open_target_with_entity(self, engine: LexiconEngine, verb: str, app_target: str):
        """Open verbs ('open', 'launch', 'start', 'chalao', 'khol do') map to OPEN action when paired with an app."""
        # Prefix phrasing: e.g. "open chrome", "khol do vlc"
        phrase1 = f"{verb} {app_target}"
        analysis1 = engine.analyze(phrase1)
        assert analysis1.action_concept == ActionConcept.OPEN_APPLICATION, f"Action OPEN_APPLICATION missing in analysis for: '{phrase1}'"

        # Suffix phrasing: e.g. "chrome open", "vlc khol do", "chrome chalao"
        phrase2 = f"{app_target} {verb}"
        analysis2 = engine.analyze(phrase2)
        assert analysis2.action_concept == ActionConcept.OPEN_APPLICATION, f"Action OPEN_APPLICATION missing in analysis for: '{phrase2}'"

    @pytest.mark.parametrize(
        "phrase",
        [
            "chrome open karo",
            "excel launch karo",
            "notepad start karo",
            "chrome chalao",
            "chrome khol do",
            "vlc khol de",
            "calculator kholo",
        ],
    )
    def test_open_commands_resolve_in_orchestrator(self, phrase: str):
        """Verify that open variations resolve to OPEN_APP in SemanticPipelineOrchestrator."""
        action = SemanticPipelineOrchestrator.parse(phrase)
        assert action is not None, f"Failed to parse open command for: '{phrase}'"
        assert action.intent == "OPEN_APP", f"Intent should be OPEN_APP for: '{phrase}', got {action.intent}"
        assert action.action in ("open", "launch", "launch_app"), f"Action should be open/launch for: '{phrase}'"

    # -------------------------------------------------------------------------
    # 3. Contextuality Invariant: Lexicon helps understanding but does NOT decide intent
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "bare_verb",
        [
            "open",
            "launch",
            "start",
            "chalao",
            "khol do",
            "kholo",
        ],
    )
    def test_bare_verbs_without_context_do_not_trigger_final_intent(self, bare_verb: str):
        """
        CRITICAL INVARIANT: The vocabulary layer must help understanding
        but must NOT itself decide the final intent without context.
        Bare verbs without entities/targets must NOT trigger app launch or media play.
        """
        # Orchestrator parsing must NOT treat bare 'open', 'chalao', etc. as an executable action
        action = SemanticPipelineOrchestrator.parse(bare_verb)
        if action is not None:
            # If any action is returned, it must require clarification, not execute blindly
            assert action.needs_clarification, f"Bare verb '{bare_verb}' executed without context or clarification!"

    # -------------------------------------------------------------------------
    # 4. Synonym and Abbreviation Detection
    # -------------------------------------------------------------------------
    def test_abbreviations_expansion(self, engine: LexiconEngine):
        """Verify common tech abbreviations are understood by LexiconEngine."""
        assert engine.expand_abbreviation("pc") == "computer"
        assert engine.expand_abbreviation("bt") == "bluetooth"
        assert engine.expand_abbreviation("calc") == "calculator"
        assert engine.expand_abbreviation("microsft") == "microsoft"

    def test_synonym_normalization(self, engine: LexiconEngine):
        """Verify synonyms for system verbs and states."""
        assert engine.get_canonical_term("dobara start") == "restart"
        assert engine.get_canonical_term("reboot") == "restart"
        assert engine.get_canonical_term("chalao") == "open"
        assert engine.get_canonical_term("khol do") == "open"
        assert engine.get_canonical_term("band karo") == "close"
