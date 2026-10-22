"""
Adversarial Natural-Language Intelligence Test Suite for Jarvis V2.1.
Directly exercises the real repository implementation to evaluate semantic understanding,
anti-guessing boundaries, context inheritance, conversational repair, multi-command parsing,
speech-act gating, and unseen phrase generalization.
"""

import pytest
from unittest.mock import MagicMock

from core.capabilities import get_capability_registry
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.context import ActiveTargetContext
from core.semantic.goal_resolver import UniversalGoalResolver
from core.semantic.resolution import ResolutionDecision
from brain.semantic_parser import HinglishNLUParser
from core.semantic.multi_entity import get_multi_entity_parser
from brain.spelling_resolver import SpellingResolver


# ==============================================================================
# SECTION 3: ADVERSARIAL PARAPHRASES, HINGLISH, INDIRECT & CONVERSATIONAL
# ==============================================================================

@pytest.mark.parametrize("phrase", [
    # A. Direct paraphrases
    "temp file clear karo",
    "clear temp file",
    "temp files clean karo",
    "temporary files delete kar do",
    "temporary files hata do",
    # B. Hinglish
    "temp bhi clean kar do",
    "temp file bhi clear karo",
    "bhai temp hata de",
    "temporary wala saaf kar do",
    "computer ka temp clean kar",
    # C. Indirect requests with temp evidence
    "system se temporary garbage hata do",
    "jo temp junk pada hai use clean kar do",
    # D. Natural conversational phrasing
    "bhai woh temporary cheezein jo pada rehti hain na unko saaf kar de",
    "computer mein jo unnecessary temp stuff jama hai use hata de",
    "system mein jo temporary kachra hai usko clean kar",
])
def test_adversarial_temp_cleanup_resolution(phrase):
    """Verifies that varied Hinglish and conversational phrasings resolve to TEMP_FILE_CLEANUP."""
    res = UniversalGoalResolver.resolve(phrase)
    assert res.goal == "TEMP_FILE_CLEANUP", f"Expected TEMP_FILE_CLEANUP for '{phrase}', got {res.goal}"
    assert res.decision == ResolutionDecision.EXECUTE
    assert res.capability_available is True
    assert res.confidence >= 0.85


# ==============================================================================
# SECTION 4: CONTEXT & MULTI-TURN CONVERSATIONS
# ==============================================================================

def test_context_chrome_then_youtube_in_container():
    """
    Test 1:
    User: Chrome kholo
    User: isme YouTube kholo
    Expected: OPEN_APPLICATION(chrome) -> OPEN_WEBSITE(youtube, context=chrome)
    """
    ctx = ActiveTargetContext()
    # Turn 1
    res1 = UniversalGoalResolver.resolve("Chrome kholo", context=ctx)
    assert res1.goal == "OPEN_APPLICATION"
    assert res1.entities.get("app_name") == "chrome"
    ctx.set_application("chrome")

    # Turn 2
    res2 = UniversalGoalResolver.resolve("isme YouTube kholo", context=ctx)
    assert res2.goal == "OPEN_WEBSITE"
    assert "youtube" in res2.entities.get("entity", "").lower()
    assert res2.entities.get("container") == "chrome"
    assert res2.decision == ResolutionDecision.EXECUTE


def test_context_brave_gmail_close_pronoun():
    """
    Test 2:
    User: Brave kholo
    User: isme Gmail kholo
    User: ab isko band karo
    Expected: pronoun 'isko' resolves to active target.
    """
    ctx = ActiveTargetContext()
    # Turn 1
    res1 = UniversalGoalResolver.resolve("Brave kholo", context=ctx)
    assert res1.goal == "OPEN_APPLICATION"
    ctx.set_application("brave")

    # Turn 2
    res2 = UniversalGoalResolver.resolve("isme Gmail kholo", context=ctx)
    assert res2.goal == "OPEN_WEBSITE"
    ctx.set_website("gmail", container="brave")

    # Turn 3: "ab isko band karo"
    res3 = UniversalGoalResolver.resolve("ab isko band karo", context=ctx)
    assert res3.goal == "CLOSE_APPLICATION"
    # Should resolve pronoun to active target (gmail or brave)
    assert res3.entities.get("app_name") in ("gmail", "brave")
    assert res3.decision == ResolutionDecision.EXECUTE


def test_context_temp_cleanup_phir_se_repeat():
    """
    Test 3:
    User: temp cleanup karo
    User: phir se karo
    User: same kaam ek baar aur
    All three must resolve to TEMP_FILE_CLEANUP.
    """
    ctx = ActiveTargetContext()
    res1 = UniversalGoalResolver.resolve("temp cleanup karo", context=ctx)
    assert res1.goal == "TEMP_FILE_CLEANUP"
    ctx.update_command_context(
        intent="TEMP_FILE_CLEANUP",
        action="clear_temp_files",
        entities={"target": "temp_files"},
        service="system",
        raw_command="temp cleanup karo",
        success=True,
    )

    res2 = UniversalGoalResolver.resolve("phir se karo", context=ctx)
    assert res2.goal == "TEMP_FILE_CLEANUP"
    assert res2.parameters.get("modifier") == "REPEAT"
    assert res2.decision == ResolutionDecision.EXECUTE

    res3 = UniversalGoalResolver.resolve("same kaam ek baar aur", context=ctx)
    assert res3.goal == "TEMP_FILE_CLEANUP"
    assert res3.decision == ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 5: EXPLICIT TARGET MUST OVERRIDE CONTEXT
# ==============================================================================

def test_explicit_target_overrides_previous_context():
    """
    User: Recycle Bin clear karo
    User: temp bhi clear karo
    Expected: Second command targets temp_files, NOT recycle_bin!
    """
    ctx = ActiveTargetContext()
    res1 = UniversalGoalResolver.resolve("Recycle Bin clear karo", context=ctx)
    assert res1.goal == "RECYCLE_BIN_CLEANUP"
    ctx.update_command_context(
        intent="RECYCLE_BIN_CLEANUP",
        action="empty_recycle_bin",
        entities={"target": "recycle_bin"},
        service="system",
        raw_command="Recycle Bin clear karo",
        success=True,
    )

    res2 = UniversalGoalResolver.resolve("temp bhi clear karo", context=ctx)
    assert res2.goal == "TEMP_FILE_CLEANUP"
    assert res2.entities.get("target") == "temp_files"
    assert res2.parameters.get("modifier") == "ALSO"
    assert res2.decision == ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 6 & 7: INDIRECT GOAL TESTS & UNSEEN GENERALIZATION
# ==============================================================================

def test_indirect_cleanup_without_context_asks_clarification():
    """General ambiguous cleanup without context triggers clarification rather than blind guessing."""
    res = UniversalGoalResolver.resolve("computer ko thoda fresh kar do")
    # Candidates are temp files vs recycle bin
    assert res.decision == ResolutionDecision.ASK_PRECISE_CLARIFICATION
    assert res.clarification_prompt or res.response_text


def test_indirect_cleanup_with_context_infers_goal():
    """Indirect cleanup with active temp context resolves safely without asking."""
    ctx = ActiveTargetContext()
    ctx.update_command_context(
        intent="TEMP_FILE_CLEANUP",
        action="clear_temp_files",
        entities={"target": "temp_files"},
        service="system",
        raw_command="temp file clear karo",
        success=True,
    )
    res = UniversalGoalResolver.resolve("computer ko thoda halka kar do", context=ctx)
    assert res.goal == "TEMP_FILE_CLEANUP"
    assert res.decision == ResolutionDecision.EXECUTE


@pytest.mark.parametrize("unseen_phrase", [
    "computer mein jo temporary clutter jama hai, usko nikaal do",
    "system se faltu temporary kooda nikal do",
    "disk par jitna temporary trash hai sab remove kar",
    "machine se temporary kachra saaf karna hai",
])
def test_unseen_phrase_generalization(unseen_phrase):
    """
    CRITICAL TEST: Unseen paraphrases not in predefined alias lists
    must resolve via semantic meaning and entity extraction.
    """
    res = UniversalGoalResolver.resolve(unseen_phrase)
    assert res.goal == "TEMP_FILE_CLEANUP", f"Failed for unseen phrase: {unseen_phrase}"
    assert res.decision == ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 8: CAPABILITY-AWARE RESOLUTION (AVAILABLE VS HONEST REFUSAL)
# ==============================================================================

def test_capability_available_resolves_and_executes():
    res = UniversalGoalResolver.resolve("clear temp file")
    assert res.capability_available is True
    assert res.decision == ResolutionDecision.EXECUTE


@pytest.mark.parametrize("unsupported_query", [
    "mere Windows ka pura registry optimize kar do",
    "hack wifi password of my neighbor",
    "overclock my CPU to 6GHz",
    "compile linux kernel on this pc",
])
def test_capability_unavailable_returns_honest_refusal(unsupported_query):
    """System must NOT hallucinate execution for unsupported capabilities."""
    res = UniversalGoalResolver.resolve(unsupported_query)
    assert res.capability_available is False
    assert res.decision == ResolutionDecision.CAPABILITY_UNAVAILABLE
    assert "nahi" in res.response_text.lower() or "not supported" in res.response_text.lower() or "unsupported" in res.response_text.lower()


# ==============================================================================
# SECTION 9: CONFIDENCE TESTING
# ==============================================================================

def test_high_confidence_direct_execution():
    res = UniversalGoalResolver.resolve("temp files clean kar do")
    assert res.confidence >= 0.85
    assert res.decision == ResolutionDecision.EXECUTE


def test_medium_confidence_with_and_without_context():
    # Without context -> clarify
    res_no_ctx = UniversalGoalResolver.resolve("computer thoda clean kar do")
    assert res_no_ctx.decision == ResolutionDecision.ASK_PRECISE_CLARIFICATION

    # With context -> execute
    ctx = ActiveTargetContext()
    ctx.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"}, service="system", raw_command="clear temp file", success=True)
    res_with_ctx = UniversalGoalResolver.resolve("computer thoda clean kar do", context=ctx)
    assert res_with_ctx.decision == ResolutionDecision.EXECUTE


def test_low_confidence_ambiguity_never_guesses():
    res = UniversalGoalResolver.resolve("woh kar do")
    # Low confidence without antecedent must never guess a destructive or random action
    assert res.decision == ResolutionDecision.ASK_PRECISE_CLARIFICATION


# ==============================================================================
# SECTION 10: SEMANTIC EQUIVALENCE ACROSS 10 CAPABILITY GROUPS
# ==============================================================================

SEMANTIC_EQUIVALENCE_GROUPS = [
    (
        "TEMP_FILE_CLEANUP",
        [
            "temp file clear karo",
            "temporary files hata do",
            "computer ka temp clean kar",
            "temp wala kachra saaf kar do",
            "system se temporary clutter nikaal do",
        ],
    ),
    (
        "OPEN_APPLICATION",
        [
            "Chrome kholo",
            "launch Google Chrome",
            "Chrome start kar do",
            "Chrome chalao",
            "bhai Chrome open karo",
        ],
    ),
    (
        "CLOSE_APPLICATION",
        [
            "Chrome band karo",
            "close Chrome",
            "Chrome exit kar do",
            "Chrome ko shut kar do",
            "Chrome hata do",
        ],
    ),
    (
        "OPEN_WEBSITE",
        [
            "YouTube website kholo",
            "open YouTube website",
            "YouTube open karo",
            "browser mein YouTube khol do",
            "YouTube site par jao",
        ],
    ),
    (
        "PLAY_MEDIA",
        [
            "YouTube par play karo lofi beats",
            "lofi beats song YouTube par chalao",
            "play lofi beats on youtube",
            "YouTube par gaana baja do lofi beats",
        ],
    ),
    (
        "RECYCLE_BIN_CLEANUP",
        [
            "Recycle Bin clear karo",
            "empty Recycle Bin",
            "Recycle Bin khali kar do",
            "trash can empty karo",
            "Recycle Bin saaf karo",
        ],
    ),
    (
        "LOCK_SYSTEM",
        [
            "system lock karo",
            "pc lock kar do",
            "lock computer",
            "screen lock karo",
        ],
    ),
    (
        "VOLUME_UP",
        [
            "volume badhao",
            "awaz badhao",
            "volume up karo",
            "sound badhao",
        ],
    ),
    (
        "VOLUME_DOWN",
        [
            "volume kam karo",
            "awaz kam karo",
            "volume down karo",
            "sound kam karo",
        ],
    ),
]


@pytest.mark.parametrize("expected_goal, phrases", SEMANTIC_EQUIVALENCE_GROUPS)
def test_semantic_equivalence_groups(expected_goal, phrases):
    for phrase in phrases:
        res = UniversalGoalResolver.resolve(phrase)
        assert res.goal == expected_goal, f"Phrase '{phrase}' expected goal '{expected_goal}', but got '{res.goal}'"
        assert res.decision == ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 11: CORRECTION & CONVERSATIONAL REPAIR
# ==============================================================================

def test_conversational_repair_replace_application_target():
    """
    User: Chrome kholo
    Jarvis: ...
    User: nahi, Brave kholo
    Expected: Brave replaces previous target Chrome.
    """
    ctx = ActiveTargetContext()
    res1 = UniversalGoalResolver.resolve("Chrome kholo", context=ctx)
    assert res1.entities.get("app_name") == "chrome"
    ctx.set_application("chrome")

    # User corrects: "nahi, Brave kholo"
    res2 = UniversalGoalResolver.resolve("nahi, Brave kholo", context=ctx)
    assert res2.goal == "OPEN_APPLICATION"
    assert res2.entities.get("app_name") == "brave"
    assert res2.decision == ResolutionDecision.EXECUTE


def test_conversational_repair_update_container_retain_entity():
    """
    User: YouTube Brave mein kholo
    User: nahi, Chrome mein
    Expected: Container updated to Chrome, website entity YouTube retained.
    """
    ctx = ActiveTargetContext()
    res1 = UniversalGoalResolver.resolve("YouTube Brave mein kholo", context=ctx)
    ctx.set_website("youtube", container="brave")

    res2 = UniversalGoalResolver.resolve("nahi, Chrome mein", context=ctx)
    assert res2.goal == "OPEN_WEBSITE"
    assert "youtube" in str(res2.entities.get("entity", "")).lower()
    assert res2.entities.get("container") == "chrome"


# ==============================================================================
# SECTION 12: SPEECH-ACT GATING (QUESTIONS VS COMMANDS)
# ==============================================================================

def test_speech_act_capability_question_does_not_execute():
    """'kya tum Chrome khol sakte ho?' is a CAPABILITY_QUESTION; MUST NOT EXECUTE."""
    res = UniversalGoalResolver.resolve("kya tum Chrome khol sakte ho?")
    assert res.speech_act == "CAPABILITY_QUESTION"
    assert res.decision != ResolutionDecision.EXECUTE
    assert res.decision == ResolutionDecision.ANSWER
    assert "haan" in res.response_text.lower()


def test_speech_act_action_command_executes():
    """'Chrome kholo' is an ACTION_COMMAND; EXECUTES."""
    res = UniversalGoalResolver.resolve("Chrome kholo")
    assert res.speech_act == "ACTION_COMMAND"
    assert res.decision == ResolutionDecision.EXECUTE


def test_speech_act_status_question_inspects_state():
    """'Chrome khula hai kya?' is a STATUS_QUESTION; DOES NOT ALTER STATE."""
    res = UniversalGoalResolver.resolve("Chrome khula hai kya?")
    assert res.speech_act in ("STATUS_QUESTION", "STATUS_QUERY")
    assert res.decision != ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 13: MULTI-COMMAND TESTING
# ==============================================================================

def test_multi_command_parsing():
    """
    Multi-command requests:
    'Chrome kholo aur YouTube chalao.'
    'Temp files clean kar do aur Recycle Bin bhi empty kar dena.'
    """
    parser = get_multi_entity_parser()

    plan1 = parser.parse("Chrome kholo aur YouTube chalao")
    assert plan1 is not None
    assert len(plan1.actions) >= 2

    plan2 = parser.parse("Temp files clean kar do aur Recycle Bin bhi empty kar dena")
    assert plan2 is not None
    assert len(plan2.actions) >= 2


# ==============================================================================
# SECTION 14: ASR & TYPO ROBUSTNESS
# ==============================================================================

@pytest.mark.parametrize("typo_phrase, expected_goal", [
    ("tem file clear karo", "TEMP_FILE_CLEANUP"),
    ("chrme kholo", "OPEN_APPLICATION"),
    ("braev kholo", "OPEN_APPLICATION"),
    ("youtub kholo", "OPEN_WEBSITE"),
    ("excel chalao", "OPEN_APPLICATION"),
])
def test_asr_typo_robustness(typo_phrase, expected_goal):
    """ASR typos must resolve to the intended canonical goal."""
    res = UniversalGoalResolver.resolve(typo_phrase)
    assert res.goal == expected_goal, f"Typo '{typo_phrase}' resolved to '{res.goal}', expected '{expected_goal}'"
    assert res.decision == ResolutionDecision.EXECUTE


# ==============================================================================
# SECTION 15: HUMAN-LIKE RESPONSE (NO ROBOTIC LEAKS)
# ==============================================================================

def test_human_like_response_contains_no_internal_debug_leaks():
    res = UniversalGoalResolver.resolve("temp file clear karo")
    debug_str = res.to_debug_string()
    # Debug string is for internal telemetry, not spoken response
    assert "TEMP_FILE_CLEANUP" in debug_str
    assert "EXECUTE" in debug_str

    # Any spoken response generated must never contain raw process names or handle brackets
    if res.response_text:
        assert ".exe" not in res.response_text.lower()
        assert "hwnd" not in res.response_text.lower()
        assert "('title')" not in res.response_text.lower()


# ==============================================================================
# SECTION 16: FURTHER UNSEEN PARAPHRASES & COMPREHENSIVE RECOVERY
# ==============================================================================

@pytest.mark.parametrize("phrase", [
    "laptop se faltu temp files saaf kar de",
    "hard disk se temporary junk delete karna hai",
    "system ki temp directory ko empty kar do",
    "pc se jo extra temporary files padi hain unhe nikal do",
])
def test_further_unseen_paraphrases(phrase):
    res = UniversalGoalResolver.resolve(phrase)
    assert res.goal == "TEMP_FILE_CLEANUP", f"Unseen paraphrase '{phrase}' failed to resolve."
    assert res.decision == ResolutionDecision.EXECUTE


def test_speech_act_status_after_action_and_troubleshooting():
    """Verify STATUS_AFTER_ACTION and TROUBLESHOOTING speech-acts."""
    res_after = UniversalGoalResolver.resolve("temp file clean hua kya?")
    assert res_after.speech_act in ("STATUS_AFTER_ACTION", "STATUS_QUESTION")
    assert res_after.decision != ResolutionDecision.EXECUTE

    res_trouble = UniversalGoalResolver.resolve("temp files delete kyun nahi ho rahi?")
    assert res_trouble.speech_act == "TROUBLESHOOTING"
    assert res_trouble.decision != ResolutionDecision.EXECUTE


def test_conversational_repair_app_target_switch():
    """
    User: Brave kholo
    User: nahi, Notepad open karo
    Expected: Notepad replaces previous target Brave.
    """
    ctx = ActiveTargetContext()
    res1 = UniversalGoalResolver.resolve("Brave kholo", context=ctx)
    ctx.set_application("brave")

    res2 = UniversalGoalResolver.resolve("nahi, Notepad open karo", context=ctx)
    assert res2.goal == "OPEN_APPLICATION"
    assert res2.entities.get("app_name") == "notepad"
    assert res2.decision == ResolutionDecision.EXECUTE


def test_compound_three_command_parsing():
    """Verify parsing of 3-command compound instruction."""
    parser = get_multi_entity_parser()
    plan = parser.parse("Chrome aur Brave kholo aur YouTube chalao")
    assert plan is not None
    assert len(plan.actions) >= 2

