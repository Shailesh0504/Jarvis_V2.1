# tests/test_identity_queries.py
"""Human-like user-profile and Jarvis self-identity query tests."""

import pytest

from main import create_jarvis


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_path = str(tmp_path / "identity.db").replace("\\", "/")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
system:
  name: JARVIS_TEST
memory:
  db_path: "{db_path}"
brain:
  llm_provider: mock
  model: llama3
plugins:
  plugin_dir: plugins
  auto_load: true
learning:
  enabled: true
""",
        encoding="utf-8",
    )
    return create_jarvis(str(config_path))


def test_user_name_unknown_then_remembered(jarvis_gui_core):
    unknown = jarvis_gui_core.process_input("mera naam kya hai")
    assert "nahi bataya" in unknown

    stored = jarvis_gui_core.process_input("mera naam Rahul hai")
    assert "Rahul" in stored and "yaad" in stored

    recalled = jarvis_gui_core.process_input("mera naam kya hai")
    assert recalled == "Aapka naam Rahul hai."


def test_jarvis_name_and_model_are_answered_correctly(jarvis_gui_core):
    assert "Mera naam JARVIS hai" in jarvis_gui_core.process_input("tumhara naam kya hai")
    assert "built-in conversational engine" in jarvis_gui_core.process_input("tumhara AI model kya hai")


def test_bare_model_query_asks_what_kind(jarvis_gui_core):
    response = jarvis_gui_core.process_input("model")
    assert "AI model" in response and "laptop" in response


@pytest.mark.parametrize(
    "statement",
    [
        "mera naam Shailesh hai",
        "main Shailesh hoon",
        "my name is Shailesh",
        "mujhe Shailesh bulao",
        "mera naam Shailesh hai yaad rakhna",
    ],
)
def test_explicit_name_variants_are_profile_memory(jarvis_gui_core, statement):
    response = jarvis_gui_core.process_input(statement)

    assert response == "Samajh gaya, Shailesh. Main aapka naam yaad rakhunga."
    assert jarvis_gui_core.memory_manager.get_fact("user_name")["value"] == "Shailesh"
    assert not any(word in response.lower() for word in ("sales", "excel", "youtube"))


@pytest.mark.parametrize(
    "question",
    [
        "mera naam kya hai",
        "mera naam kya hai?",
        "maine tumhe apna naam kya bataya tha",
    ],
)
def test_name_queries_retrieve_profile_memory(jarvis_gui_core, question):
    jarvis_gui_core.process_input("mera naam Shailesh hai")

    assert jarvis_gui_core.process_input(question) == "Aapka naam Shailesh hai."


@pytest.mark.parametrize("prefix", ["nahi", "galat", "no", "mera matlab"])
def test_contextual_name_correction_replaces_previous_value(jarvis_gui_core, prefix):
    jarvis_gui_core.process_input("mera naam Rahul hai")

    response = jarvis_gui_core.process_input(f"{prefix}, Shailesh hai")

    assert response == "Theek hai, aapka naam Shailesh hai. Main ise yaad rakhunga."
    assert jarvis_gui_core.process_input("mera naam kya hai") == "Aapka naam Shailesh hai."


@pytest.mark.parametrize("statement,question,key,value", [
    ("main Pune mein rehta hoon", "main kahan rehta hoon", "user_city", "Pune"),
    ("mujhe coding pasand hai", "mujhe kya pasand hai", "user_interest", "coding"),
    ("mera pasandida khana dosa hai", "mera pasandida khana kya hai", "favorite_food", "dosa"),
    ("meri hobby photography hai", "meri hobby kya hai", "user_hobby", "photography"),
    ("main Jarvis par kaam kar raha hoon", "mera current project kya hai", "current_project", "Jarvis"),
    ("I live in New Delhi", "where do I live", "user_city", "New Delhi"),
    ("remember that my current project is Atlas", "what am I working on", "current_project", "Atlas"),
])
def test_personal_facts_recall_after_memory_reopen(jarvis_gui_core, statement, question, key, value):
    from memory.memory_manager import MemoryManager
    core = jarvis_gui_core
    response = core.process_input(statement)
    assert "yaad" in response or "remember" in response
    assert core.memory_manager.get_fact(key)["value"] == value
    core.memory_manager = MemoryManager(core.memory_manager.db.db_path)
    assert value in core.process_input(question)


@pytest.mark.parametrize("text", [
    "I am tired", "main thak gaya hoon", "mujhe coding pasand nahi hai",
    "agar main Pune mein rehta hoon", "kya main Pune mein rehta hoon?",
    "mera project kholo", "main Pune mein rehta hoon aur Chrome open karo",
    "mujhe 10 minute baad paani peene yaad dilana",
    "my current project is password secret", "my name is not Rahul",
])
def test_profile_does_not_store_moods_questions_commands_or_secrets(text):
    from brain.personal_profile import PersonalProfileExtractor
    assert PersonalProfileExtractor.extract(text) is None


def test_memory_failure_never_claims_success(jarvis_gui_core, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("unavailable")
    monkeypatch.setattr(jarvis_gui_core.memory_manager, "store_fact", fail)
    response = jarvis_gui_core.process_input("mera project Atlas hai")
    assert "save nahi" in response
    assert jarvis_gui_core.memory_manager.get_fact("current_project") is None


def test_profile_correction_does_not_leak_across_unrelated_turns(jarvis_gui_core):
    jarvis_gui_core.process_input("mera naam Rahul hai")
    jarvis_gui_core.process_input("hello")
    jarvis_gui_core.process_input("nahi, mushkil hai")
    assert jarvis_gui_core.memory_manager.get_fact("user_name")["value"] == "Rahul"


def test_personal_project_callback_is_grounded_and_not_repeated(jarvis_gui_core):
    core = jarvis_gui_core
    core.process_input("mera naam Rahul hai")
    core.process_input("mera project Atlas hai")
    greeting = core.process_input("hello")
    assert "Rahul" in greeting and "Atlas" in greeting
    assert "Atlas" not in core.process_input("hello")


def test_support_conversation_reaches_engine_from_core(jarvis_gui_core):
    core = jarvis_gui_core
    first = core.process_input("aaj mera mood kharab hai")
    assert "sunun" in first
    assert "sun raha" in core.process_input("bas suno")
    assert "deadline" in core.process_input("office mein deadline hai").lower()
    assert core.memory_manager.get_fact("user_name") is None


def test_memory_summary_only_uses_saved_personal_facts(jarvis_gui_core):
    core = jarvis_gui_core
    core.process_input("mera naam Rahul hai")
    core.process_input("mujhe coding pasand hai")
    core.memory_manager.store_fact("unrelated", "do not include", category="facts")
    response = core.process_input("mere baare mein kya yaad hai")
    assert "Rahul" in response and "coding" in response
    assert "do not include" not in response


def test_project_correction_updates_one_canonical_fact(jarvis_gui_core):
    core = jarvis_gui_core
    core.process_input("mera project Atlas hai")
    core.process_input("nahi, mera project Orion hai")
    assert core.memory_manager.get_fact("current_project")["value"] == "Orion"
    assert "Atlas" not in core.process_input("mera project kya hai")
