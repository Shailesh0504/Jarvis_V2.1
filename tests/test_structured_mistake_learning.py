# tests/test_structured_mistake_learning.py
"""
Unit and integration tests for Structured Mistake Logging,
Automated JSONL Log Digestion, and Conversational Reflection.
"""

import json
import os
import pytest
from unittest.mock import MagicMock

from core.logger import (
    MistakeCategory,
    MistakeRecord,
    MistakeLogWriter,
    log_mistake,
    get_mistake_logger
)
from core.experience.log_learner import LogLearningEngine
from core.experience.models import MemoryType
from core.experience.storage import ExperienceStorageManager
from core.experience.evaluator import OutcomeEvaluator
from core.experience.system import ExperienceLearningSystem


@pytest.fixture
def temp_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)


@pytest.fixture
def temp_db_path(tmp_path):
    db_file = tmp_path / "test_experience.db"
    return str(db_file)


def test_mistake_record_serialization():
    """Verifies that MistakeRecord converts to and from dict faithfully."""
    rec = MistakeRecord(
        log_id="err-1234",
        timestamp="2026-09-19T23:50:00",
        category=MistakeCategory.TARGET_RESOLUTION_ERROR.value,
        user_query="close chrome",
        normalized_query="close chrome",
        turn_id="turn-42",
        intent="close_app",
        attempted_action="close",
        error_type="ProcessLookupError",
        error_message="Chrome process was not found",
        failing_module="window_manager",
        diagnosis="Chrome window was not running",
        anti_pattern="Trying to close unverified process",
        recommended_fix="Check if process is running before sending close signal"
    )
    d = rec.to_dict()
    assert d["log_id"] == "err-1234"
    assert d["category"] == "target_resolution_error"
    assert d["error_type"] == "ProcessLookupError"

    rec2 = MistakeRecord.from_dict(d)
    assert rec2.log_id == "err-1234"
    assert rec2.user_query == "close chrome"
    assert rec2.recommended_fix == "Check if process is running before sending close signal"
    assert rec2.learned_status == "PENDING"


def test_mistake_log_writer_and_sanitization(temp_log_dir):
    """Verifies that MistakeLogWriter redacts secrets and appends valid JSONL lines."""
    writer = MistakeLogWriter(log_dir=temp_log_dir)

    rec = MistakeRecord(
        log_id="err-secret-test",
        timestamp="2026-09-19T23:51:00",
        category=MistakeCategory.TOOL_FAILURE.value,
        user_query="set api key sk-1234567890abcdef12345678",
        error_message="Failed connecting with token Bearer abc123def456ghi789",
        action_parameters={"password": "supersecretpassword123"}
    )
    log_id = writer.write_mistake(rec)
    assert log_id == "err-secret-test"

    # Read back file directly
    log_path = writer.log_file
    assert os.path.exists(log_path)

    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["log_id"] == "err-secret-test"
    # Verify sensitive data was redacted
    assert "sk-1234567890abcdef12345678" not in entry["user_query"]
    assert "[REDACTED_API_KEY]" in entry["user_query"]
    assert "abc123def456ghi789" not in entry["error_message"]
    assert "[REDACTED_TOKEN]" in entry["error_message"]
    assert "supersecretpassword123" not in str(entry["action_parameters"])


def test_log_learner_digests_mistakes_into_experience(temp_log_dir, temp_db_path):
    """Verifies that LogLearningEngine digests pending mistakes into Experience Memory."""
    writer = MistakeLogWriter(log_dir=temp_log_dir)

    # 1. Write 2 mistake entries
    writer.write_mistake(MistakeRecord(
        log_id="err-01",
        timestamp="2026-09-19T23:52:00",
        category=MistakeCategory.VERIFICATION_FAILURE.value,
        user_query="open chrome",
        attempted_action="launch",
        failing_module="browser",
        error_type="TimeoutError",
        error_message="Browser window did not appear within 2.5s",
        diagnosis="Cold launch took longer than verification timeout",
        anti_pattern="Short timeout on cold launch",
        recommended_fix="Increase verification retries for first browser launch"
    ))
    writer.write_mistake(MistakeRecord(
        log_id="err-02",
        timestamp="2026-09-19T23:52:30",
        category=MistakeCategory.TARGET_RESOLUTION_ERROR.value,
        user_query="excel maximize karo",
        attempted_action="maximize",
        failing_module="window_manager",
        error_type="WindowNotFoundError",
        error_message="Excel window handle is invalid",
        diagnosis="Excel was minimized to tray",
        anti_pattern="Blind maximize on unmapped hwnd",
        recommended_fix="Restore from tray before maximizing"
    ))

    storage = ExperienceStorageManager(db_or_path=temp_db_path)
    engine = LogLearningEngine(storage=storage, log_writer=writer)

    # Check unlearned count before digestion
    unlearned_before = writer.get_unlearned_mistakes()
    assert len(unlearned_before) == 2

    # Digest
    digested = engine.digest_mistakes(limit=10)
    assert len(digested) == 2

    # Check that entries in log are now marked DIGESTED
    unlearned_after = writer.get_unlearned_mistakes()
    assert len(unlearned_after) == 0

    all_logs = writer.get_all_mistakes()
    assert all(l["learned_status"] == "DIGESTED" for l in all_logs)

    # Check that ExperienceStorageManager now contains the Failure memories
    failures = storage.get_active_items(memory_type=MemoryType.FAILURE)
    assert len(failures) == 2

    # Verify summary generation
    summary = engine.get_learned_mistakes_summary()
    assert summary["digested_mistakes_count"] == 2
    assert summary["pending_unlearned_count"] == 0
    assert len(summary["lessons"]) == 2
    assert "Boss, maine recent logs se 2 galtiyan analyze ki hain" in summary["spoken_summary"]


def test_experience_learning_system_integration(temp_log_dir, temp_db_path):
    """Verifies ExperienceLearningSystem integrates LogLearningEngine seamlessly."""
    writer = MistakeLogWriter(log_dir=temp_log_dir)
    writer.write_mistake(MistakeRecord(
        log_id="err-sys-01",
        timestamp="2026-09-19T23:53:00",
        category=MistakeCategory.TOOL_FAILURE.value,
        user_query="screenshot lo",
        attempted_action="capture",
        failing_module="screen",
        error_type="DisplayError",
        error_message="DirectX surface lock failed",
        diagnosis="GPU driver mode switch in progress",
        anti_pattern="Instant screenshot during display mode switch",
        recommended_fix="Retry capture after 200ms debounce"
    ))

    system = ExperienceLearningSystem(db_or_path=temp_db_path)
    # Inject our isolated writer
    system.log_learner.log_writer = writer

    digested = system.digest_log_mistakes()
    assert len(digested) == 1
    assert digested[0].memory_type == MemoryType.FAILURE
    assert "screenshot lo" in digested[0].query_pattern

    summary = system.get_lessons_learned_summary()
    assert summary["digested_mistakes_count"] == 1
    assert "screenshot lo" in summary["spoken_summary"]


def test_fast_path_mistake_inquiry():
    """Verifies that asking 'tumne apni galtiyon se kya seekha' triggers Section 12 fast path."""
    from core.execution.fast_path import FastPathEngine

    mock_core = MagicMock()
    mock_core.dialog_manager = None
    mock_exp = MagicMock()
    mock_exp.get_lessons_learned_summary.return_value = {
        "spoken_summary": "Boss, maine pichhli galtiyon se seekha hai ki window verify karne ke baad hi confirm karna chahiye."
    }
    mock_core.experience_system = mock_exp
    mock_core._finalize_fast_turn = lambda turn, resp, st, tr, intent, src: resp

    engine = FastPathEngine(core=mock_core)

    turn = MagicMock()
    res = engine.try_handle(
        raw_text="tumne apni galtiyon se kya seekha?",
        normalized_input="tumne apni galtiyon se kya seekha",
        turn=turn,
        start_time=0.0,
        tracker=None,
        source="cli"
    )
    assert res is not None
    assert "pichhli galtiyon se seekha hai" in res
    assert mock_exp.digest_log_mistakes.called
