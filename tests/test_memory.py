# tests/test_memory.py
import os
import pytest
from memory.database import DatabaseManager
from memory.memory_manager import MemoryManager


@pytest.fixture
def memory_mgr(tmp_path):
    db_file = os.path.join(tmp_path, "test_jarvis.db")
    return MemoryManager(db_path=db_file)


def test_semantic_memory_store_and_get(memory_mgr):
    memory_mgr.store_fact(key="favorite_editor", value="VSCode", category="preferences")
    fact = memory_mgr.get_fact("favorite_editor")
    assert fact is not None
    assert fact["value"] == "VSCode"
    assert fact["category"] == "preferences"


def test_semantic_memory_search(memory_mgr):
    memory_mgr.store_fact(key="car", value="Tesla Model 3")
    memory_mgr.store_fact(key="bike", value="Ducati")

    results = memory_mgr.search_memories("Tesla")
    assert len(results) == 1
    assert results[0]["key"] == "car"


def test_preferences_memory(memory_mgr):
    memory_mgr.set_preference("dark_mode", True)
    memory_mgr.set_preference("volume", 80)

    assert memory_mgr.get_preference("dark_mode") is True
    assert memory_mgr.get_preference("volume") == 80


def test_episodic_memory_recording(memory_mgr):
    memory_mgr.record_interaction(
        user_input="Hello Jarvis",
        response="Hello Boss",
        intent="chat",
        source="cli"
    )
    recent = memory_mgr.get_recent_interactions(limit=5)
    assert len(recent) == 1
    assert recent[0]["user_input"] == "Hello Jarvis"
    assert recent[0]["assistant_response"] == "Hello Boss"


def test_federated_search_canonical_precedence_and_deduplication(memory_mgr):
    from core.memory.retrieval import ConversationMemoryRetriever

    # 1. Store a fact purely through canonical store_fact
    memory_mgr.store_fact("user_city", "Pune", category="user_profile")

    # 2. Store a fact through legacy store_conversation_fact
    memory_mgr.store_conversation_fact("legacy_framework", "FastAPI", category="tech")

    # 3. Store duplicate logical fact in both tables with different values
    memory_mgr.store_conversation_fact("editor_choice", "SublimeText", category="preferences")
    memory_mgr.store_fact("editor_choice", "VSCode", category="preferences")

    # Verify search_conversation_facts directly
    res = memory_mgr.search_conversation_facts("user_city")
    assert len(res) == 1
    assert res[0]["value"] == "Pune"
    assert res[0]["source_store"] == "canonical_memories"

    res_legacy = memory_mgr.search_conversation_facts("legacy_framework")
    assert len(res_legacy) == 1
    assert res_legacy[0]["value"] == "FastAPI"
    assert res_legacy[0]["source_store"] == "semantic_memory"

    # Verify deduplication and canonical precedence
    res_dedup = memory_mgr.search_conversation_facts("editor_choice")
    assert len(res_dedup) == 1
    assert res_dedup[0]["value"] == "VSCode"
    assert res_dedup[0]["source_store"] == "canonical_memories"

    # 4. Verify retrieval through ConversationMemoryRetriever
    retriever = ConversationMemoryRetriever(memory_manager=memory_mgr)
    retrieved = retriever.retrieve("user_city Pune", limit=5)
    city_mems = [r for r in retrieved if r.source == "semantic" and "user_city" in r.content]
    assert len(city_mems) == 1
    assert city_mems[0].content == "user_city = Pune"

    # Verify legacy retrieval through ConversationMemoryRetriever
    retrieved_legacy = retriever.retrieve("legacy_framework FastAPI", limit=5)
    legacy_mems = [r for r in retrieved_legacy if r.source == "semantic" and "legacy_framework" in r.content]
    assert len(legacy_mems) == 1
    assert legacy_mems[0].content == "legacy_framework = FastAPI"

    # Verify deduplicated retrieval through ConversationMemoryRetriever
    retrieved_dedup = retriever.retrieve("editor_choice", limit=5)
    dedup_mems = [r for r in retrieved_dedup if r.source == "semantic" and "editor_choice" in r.content]
    assert len(dedup_mems) == 1
    assert dedup_mems[0].content == "editor_choice = VSCode"

