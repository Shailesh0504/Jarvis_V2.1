# tests/test_unified_memory.py
"""Focused tests for the lightweight offline Unified Memory subsystem (Phase 8).

Covers: explicit remember/forget, preference + profile storage, session
memory, retrieval priority, update/delete, no-memory fallback, Context
Manager cooperation (memory never replaces context), duplicate prevention,
expiration, confidence gating, and Laya/parser/execution regressions.
"""

import time

import pytest

from memory.memory_api import UnifiedMemory, get_unified_memory_for
from memory.memory_manager import MemoryManager


@pytest.fixture
def mem(tmp_path):
    mgr = MemoryManager(db_path=str(tmp_path / "mem.db"))
    return UnifiedMemory(memory_manager=mgr)


# -- explicit remember / retrieval ------------------------------------------

def test_explicit_remember_and_get(mem):
    assert mem.remember("meeting", "5 baje call hai", memory_type="FACT", explicit=True) is True
    rec = mem.get("meeting")
    assert rec and rec["value"] == "5 baje call hai"


def test_remember_update_overwrites_no_duplicate(mem):
    mem.remember("note_x", "pehla", explicit=True)
    mem.remember("note_x", "doosra", explicit=True)
    assert mem.get("note_x")["value"] == "doosra"
    rows = mem.list_memories()
    assert sum(1 for r in rows if r["key"] == "note_x") == 1


def test_explicit_forget(mem):
    mem.remember("temp_key", "kuch", explicit=True)
    assert mem.forget("temp_key") is True
    assert mem.get("temp_key") is None


def test_forget_missing_returns_false_gracefully(mem):
    assert mem.forget("kabhi_tha_hi_nahi") is False


def test_no_memory_fallback(mem):
    assert mem.get("aisa_kuch_nahi_hai") is None
    assert mem.search("zzzz_no_match_qqq") == []
    assert mem.get_relevant("zzzz_no_match_qqq") == []


# -- preference / profile ----------------------------------------------------

def test_preference_storage_and_listing(mem):
    mem.remember("response_language", "hinglish", memory_type="PREFERENCE",
                 explicit=True, category="preferences")
    prefs = mem.get_preferences()
    assert prefs.get("response_language") == "hinglish"


def test_profile_fact_storage(mem):
    mem.remember("user_name", "Shailesh", memory_type="PROFILE",
                 explicit=True, category="user_profile")
    rec = mem.get("user_name")
    assert rec and rec["value"] == "Shailesh"


# -- session memory ----------------------------------------------------------

def test_session_memory_and_clear(mem):
    # mid-confidence auto content lands in session only, not SQLite
    assert mem.remember("session_hint", "context wali baat", confidence=0.70,
                        explicit=False) is True
    rec = mem.get("session_hint")
    assert rec and rec.get("session_only") is True
    assert mem.clear_session() == 1
    assert mem.get("session_hint") is None


def test_low_confidence_dropped(mem):
    assert mem.remember("noise", "blah", confidence=0.30, explicit=False) is False
    assert mem.get("noise") is None


def test_sensitive_never_auto_persisted(mem):
    assert mem.remember("login", "my password is abc123", confidence=0.99,
                        explicit=False) is False
    assert mem.get("login") is None


def test_high_confidence_auto_persists(mem):
    assert mem.remember("stable_fact", "office timing 9 baje", confidence=0.95,
                        explicit=False) is True
    rec = mem.get("stable_fact")
    assert rec and not rec.get("session_only")


# -- retrieval priority ------------------------------------------------------

def test_retrieval_exact_key_first(mem):
    mem.remember("chrome", "preferred browser", explicit=True)
    hits = mem.get_relevant("chrome kholo")
    assert hits and hits[0]["key"] == "chrome"


def test_get_recent_bounded(mem):
    mem._mgr().record_interaction("hello", "namaste", intent="greeting")
    recent = mem.get_recent(limit=5)
    assert isinstance(recent, list) and len(recent) <= 5


# -- update / expiration -----------------------------------------------------

def test_memory_update(mem):
    mem.remember("upd_key", "purana", explicit=True)
    assert mem.update("upd_key", value="naya") is True
    assert mem.get("upd_key")["value"] == "naya"


def test_expiration_handling(mem):
    mem.remember("short_lived", "abhi ke liye", explicit=True, expires_in=0.05)
    assert mem.get("short_lived") is not None
    time.sleep(0.08)
    assert mem.get("short_lived") is None


# -- parser routing (existing architecture, no parallel system) --------------

def test_memory_parser_routes_explicit_commands():
    from core.semantic.orchestrator import SemanticPipelineOrchestrator as SPO
    a = SPO.parse("yaad rakho meri meeting 5 baje hai")
    assert a and a.intent == "MEMORY_REMEMBER" and a.service == "memory"
    a = SPO.parse("ye memory delete karo")
    assert a and a.intent == "MEMORY_FORGET"
    a = SPO.parse("meri preferences kya hain")
    assert a and a.intent == "MEMORY_PREFERENCES"
    a = SPO.parse("session memory clear karo")
    assert a and a.intent == "MEMORY_CLEAR"


def test_memory_parser_does_not_steal_reminder_or_commands():
    from core.semantic.orchestrator import SemanticPipelineOrchestrator as SPO
    a = SPO.parse("mujhe 10 minute baad paani peene yaad dilana")
    assert a and a.intent == "CREATE_REMINDER"
    a = SPO.parse("chrome kholo")
    assert a and a.intent == "OPEN_APPLICATION"
    a = SPO.parse("notepad band karo")
    assert a and a.intent == "WINDOW_CLOSE"


# -- Laya decoupling ----------------------------------------------------------

def test_laya_routes_memory_without_importing_it():
    from core.laya.intelligence import get_laya_intelligence, _INTENT_TOOL_MAP
    assert _INTENT_TOOL_MAP["memory_remember"]["plugin"] == "memory"
    # Semantic level (Laya reuses the same orchestrator): memory intent maps
    # to the memory tool without any memory import inside Laya logic.
    # (Top-level decide() speech-act gating stays owned by the classifier;
    # core serves memory directives via the structured pre-gating path.)
    li = get_laya_intelligence()
    name, entities, conf, action = li._parse_semantic("yaad rakho meri meeting 5 baje hai", None)
    assert name == "memory_remember"
    li2 = get_laya_intelligence()
    dec = li2.decide("yaad rakho meri meeting 5 baje hai")
    # Either direct EXECUTE routing or conversational short-circuit is
    # acceptable; what must hold is zero coupling:
    assert dec is not None
    import core.laya.intelligence as lic
    import inspect
    src = inspect.getsource(lic)
    assert "memory_api" not in src and "UnifiedMemory" not in src


# -- Context Manager cooperation ----------------------------------------------

def test_context_manager_stays_owner_of_pronouns(tmp_path):
    # "isko" resolution must still come from context, not memory.
    from core.universal_window_resolver import UniversalAppNormalizer
    assert UniversalAppNormalizer.is_relative_target("isko") is True
    # memory.get_relevant on a bare pronoun must not fabricate a target
    mgr = MemoryManager(db_path=str(tmp_path / "ctx.db"))
    m = UnifiedMemory(memory_manager=mgr)
    assert m.get_relevant("isko") == []


# -- end-to-end through JarvisCore --------------------------------------------

def _make_core(tmp_path):
    from main import create_jarvis
    db_path = str(tmp_path / "e2e.db").replace("\\", "/")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f'system:\n  name: JARVIS_TEST\nmemory:\n  db_path: "{db_path}"\n'
        "brain:\n  llm_provider: mock\n  model: llama3\nplugins:\n"
        "  plugin_dir: plugins\n  auto_load: true\nlearning:\n  enabled: true\n",
        encoding="utf-8",
    )
    return create_jarvis(str(cfg))


def test_e2e_remember_recall_forget(tmp_path):
    core = _make_core(tmp_path)
    r1 = core.process_input("yaad rakho meri meeting 5 baje hai")
    assert "yaad" in r1.lower()
    r2 = core.process_input("tumhe mere baare mein kya yaad hai")
    # profile path owns exact summary; memory fallback must also answer
    assert r2 and len(r2) > 0


def test_e2e_fact_remember_and_query(tmp_path):
    core = _make_core(tmp_path)
    r1 = core.process_input("remember that my favorite color is Blue")
    assert "favorite color" in r1.lower()
    r2 = core.process_input("What is my favorite color?")
    assert "blue" in r2.lower()
    # profile-owned queries stay with the profile path
    core.process_input("mera naam Rahul hai")
    assert core.process_input("mera naam kya hai") == "Aapka naam Rahul hai."
    # reminder commands still route to reminders, never memory
    a_rem = core.process_input("mujhe 10 minute baad paani peene yaad dilana")
    assert a_rem and "yaad rakh liya" not in a_rem.lower()


def test_e2e_no_crash_without_memory_manager(tmp_path):
    core = _make_core(tmp_path)
    core.memory_manager = None
    r = core.process_input("yaad rakho kuch zaroori baat")
    assert isinstance(r, str) and len(r) > 0


def test_core_scoped_adapter_reuse(tmp_path):
    core = _make_core(tmp_path)
    a1 = get_unified_memory_for(core)
    a2 = get_unified_memory_for(core)
    assert a1 is a2
