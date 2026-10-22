"""
tests/test_claude_negation_search_recovery.py
Verifies:
1. Resolution of modern AI websites (Claude, Claude AI, Cloude, Gemini, Perplexity)
2. Spelling resolution of "cloude" to "claude" rather than false-positive "code"
3. Negation command recovery: "nahi cloude search karo google par" clears pending spelling rejection
   and passes through to execute the command rather than getting trapped in anchorless clarification loops.
"""

import pytest
from plugins.browser.website_resolver import WebsiteResolver
from brain.spelling_resolver import SpellingResolver
from core.pipeline.input_pipeline import _maybe_start_compose_workflow
import types
from core.conversational_intent import ConversationalIntentClassifier


def test_website_resolver_modern_ai_sites():
    """Claude and modern AI platforms must resolve directly without UnknownWebsiteError."""
    for query in ["cloude ai", "cloude", "claude", "claude ai", "claudeai", "cloud ai"]:
        res = WebsiteResolver.resolve(query)
        assert res.resolved_url == "https://claude.ai/", f"Failed for query '{query}': got {res.resolved_url}"

    gemini_res = WebsiteResolver.resolve("gemini")
    assert gemini_res.resolved_url == "https://gemini.google.com/"

    perplexity_res = WebsiteResolver.resolve("perplexity")
    assert perplexity_res.resolved_url == "https://www.perplexity.ai/"


def test_spelling_resolver_cloude_not_code():
    """'cloude' should resolve to 'claude' (silent high-confidence or explicit), never 'code'."""
    res = SpellingResolver.resolve("cloude")
    if res is not None:
        assert res.correction.lower() == "claude"
        assert res.correction.lower() != "code"


def test_negation_command_recovery():
    """
    When a pending spelling exists and user says 'nahi cloude search karo google par',
    it must reject the spelling candidate and fall through to execution (returning None)
    with normalized_input rewritten to 'cloude search karo google par'.
    """
    class MockDialogManager:
        def __init__(self):
            self.pending_spelling = {"typo": "cloude", "correction": "code", "corrected_text": "code"}

        def has_active_lock(self):
            return False

        def has_pending_system_action(self):
            return False

    class MockCore:
        def __init__(self):
            self.dialog_manager = MockDialogManager()
            self._rejected_fuzzy_candidates = set()
            self.active_context = None

        def reject_fuzzy_candidate(self, typo: str, rejected_candidate: str):
            self._rejected_fuzzy_candidates.add((typo.lower().strip(), rejected_candidate.lower().strip()))

    mock_core = MockCore()
    turn = types.SimpleNamespace(
        raw_input="nahi cloude search karo google par",
        normalized_input="nahi cloude search karo google par",
        turn_id="t_neg_1",
        metadata={}
    )
    conv_intent = ConversationalIntentClassifier.classify(turn.normalized_input)

    resp = _maybe_start_compose_workflow(mock_core, conv_intent, turn, turn.raw_input)

    # Must return None to fall through to command execution (NOT "Samajh gaya — kuch correct karna hai...")
    assert resp is None
    # Must clear pending spelling
    assert mock_core.dialog_manager.pending_spelling is None
    # Must record rejected candidate ("cloude", "code") so it's never repeated
    assert ("cloude", "code") in mock_core._rejected_fuzzy_candidates
    # Normalized input must be stripped of negation
    assert turn.normalized_input == "cloude search karo google par"
