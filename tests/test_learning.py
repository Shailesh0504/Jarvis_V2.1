# tests/test_learning.py
import os
import pytest
from core.intent import Intent, IntentType
from memory.database import DatabaseManager
from learning.learner import LearningManager


@pytest.fixture
def learner(tmp_path):
    db_file = os.path.join(tmp_path, "test_learning.db")
    db = DatabaseManager(db_path=db_file)
    return LearningManager(db=db, enabled=True)


def test_corrections_learning(learner):
    learner.register_correction("open google", "open brave")
    corrected = learner.get_correction_for("open google")
    assert corrected == "open brave"


def test_pattern_learning_and_suggestions(learner):
    intent = Intent(name="system_get_time", type=IntentType.COMMAND)
    for _ in range(4):
        learner.observe_interaction(
            raw_input="what time is it",
            normalized_input="what time is it",
            intent=intent
        )

    suggestions = learner.get_suggestions()
    assert len(suggestions) > 0
    assert "system_get_time" in suggestions[0]
