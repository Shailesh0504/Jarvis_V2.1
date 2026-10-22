# tests/golden/test_golden_replay.py
import json
import os
import pytest
from main import create_jarvis
from core.contracts import RequestSource


@pytest.fixture(scope="module")
def jarvis_core():
    core = create_jarvis()
    return core


def test_golden_dataset_replay(jarvis_core):
    dataset_path = os.path.join(os.path.dirname(__file__), "golden_conversations.json")
    assert os.path.isfile(dataset_path), "Golden conversations dataset not found"

    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    failures = []
    for case in cases:
        case_id = case["id"]
        user_input = case["input"]
        expected_keywords = [k.lower() for k in case.get("expected_contains", [])]

        payload = jarvis_core.runtime.execute_turn(user_input, source=RequestSource.CLI)
        resp_text = (payload.text or "").lower()

        # Assert response is not empty or raw error
        if not resp_text:
            failures.append(f"[{case_id}] Empty response for '{user_input}'")
            continue

        # Check keyword match
        matched = any(kw in resp_text for kw in expected_keywords)
        if not matched:
            failures.append(
                f"[{case_id}] Input: '{user_input}' -> Response: '{payload.text}' "
                f"did not contain any expected keywords {expected_keywords}"
            )

    assert not failures, f"Golden dataset replay failures:\n" + "\n".join(failures)
