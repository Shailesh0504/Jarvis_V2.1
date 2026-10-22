# tests/test_negative_constraint_cleanup.py
"""
Tests for Negative Constraints & Safety Restrictors in System Cleanup:
Validates that user utterances containing negative safety constraints
(e.g., 'Mujhe thoda system cleanup chahiye, lekin meri personal files ko touch mat karna')
resolve cleanly to safe system maintenance (TEMP_FILE_CLEANUP), execute clear_temp_files,
provide explicit reassurance about personal files, and never collide with Knowledge Engine entities.
"""

import pytest
from core.semantic.goal_resolver import UniversalGoalResolver
from core.semantic.resolution import ResolutionDecision
from brain.semantic_parser import HinglishNLUParser
from core.knowledge import get_knowledge_engine
from core.natural_responses import NaturalResponseSynthesizer


@pytest.mark.parametrize(
    "phrase,expected_goal,expected_action",
    [
        (
            "Mujhe thoda system cleanup chahiye, lekin meri personal files ko touch mat karna",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "System clean kar do par personal documents delete mat karna",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "Clear temp files but don't touch personal files",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "computer clean karo par personal data mat chhedna",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "system clean kar do bina meri personal files ko touch kiye",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "clear temporary files without deleting personal data",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
        (
            "thoda computer saaf kar do par meri personal files ko touch mat karna",
            "TEMP_FILE_CLEANUP",
            "clear_temp_files",
        ),
    ],
)
def test_negative_constraint_cleanup_resolution(phrase, expected_goal, expected_action):
    """Verifies cleanup with negative constraints resolves safely to TEMP_FILE_CLEANUP."""
    res = UniversalGoalResolver.resolve(phrase)
    assert res.goal == expected_goal, f"Failed for '{phrase}': got {res.goal}"
    assert res.decision == ResolutionDecision.EXECUTE
    assert res.capability_required == "system.maintenance.temp_cleanup"
    assert res.parameters.get("exclude_personal_files") is True
    assert res.action_plan["action"] == expected_action
    assert res.action_plan["parameters"].get("exclude_personal_files") is True

    # Check facade parser
    act = HinglishNLUParser.parse(phrase)
    assert act is not None
    assert act.action == expected_action
    assert act.parameters.get("exclude_personal_files") is True


def test_recycle_bin_with_negative_constraint():
    """Verifies recycle bin with negative constraint preserves safety parameter."""
    phrase = "recycle bin empty kar do par personal files ko chhedna mat"
    res = UniversalGoalResolver.resolve(phrase)
    assert res.goal == "RECYCLE_BIN_CLEANUP"
    assert res.decision == ResolutionDecision.EXECUTE
    assert res.capability_required == "system.maintenance.recycle_bin"
    assert res.parameters.get("exclude_personal_files") is True
    assert res.action_plan["action"] == "empty_recycle_bin"


def test_knowledge_engine_never_matches_personal_files_as_gold():
    """
    Guarantees word-boundary entity matching:
    The word 'personal' contains substring 'sona', but MUST NEVER match the Gold entity.
    """
    ke = get_knowledge_engine()
    query = "Mujhe thoda system cleanup chahiye, lekin meri personal files ko touch mat karna"

    # Must not be a knowledge candidate
    assert ke.is_knowledge_candidate(query) is False

    # search_entities must not return gold
    matched = ke.entity_store.search_entities(query)
    gold_matches = [ent for ent, conf in matched if ent.entity_id == "gold"]
    assert len(gold_matches) == 0, f"Gold falsely matched inside 'personal': {gold_matches}"

    # Querying should not return gold fact
    res = ke.query(query)
    assert res.found is False or res.entity_name != "Gold"
    assert "parmanu sankhya 79" not in (res.answer_text or "")


def test_legitimate_gold_queries_still_succeed():
    """Ensures legitimate questions about Gold / Sona continue to work."""
    ke = get_knowledge_engine()
    res_hi = ke.query("sona kya hota hai")
    assert res_hi.found is True
    assert "Gold" in res_hi.entity_name or "Sona" in res_hi.answer_text

    res_en = ke.query("what is gold")
    assert res_en.found is True
    assert "Gold" in res_en.entity_name


def test_natural_response_safety_reassurance():
    """Verifies that system maintenance returns reassuring message when safety constraint is present."""
    resp_hi = NaturalResponseSynthesizer.system_maintenance(
        "clear_temp_files",
        target="temp",
        is_repeat=False,
        language="hi",
        safety_reassurance=True,
    )
    assert "personal files" in resp_hi.lower()
    assert "safe" in resp_hi.lower()

    resp_en = NaturalResponseSynthesizer.system_maintenance(
        "clear_temp_files",
        target="temp",
        is_repeat=False,
        language="en",
        safety_reassurance=True,
    )
    assert "personal files" in resp_en.lower()
    assert "safe" in resp_en.lower()
