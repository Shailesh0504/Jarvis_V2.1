# tests/test_windows_app_resolver.py
"""
Comprehensive test suite for Windows Application Resolver & Alias System.
Validates:
1. Microsoft Store recognition including typo ("microsft store") without "storage" misclassification.
2. English, Hindi, and Hinglish open/close phrasing.
3. Common Windows 11 apps resolution and process termination mappings.
4. Distinguishing Application vs Website.
5. Multi-application commands.
6. Contextual disambiguation for bare words vs unambiguous requests.
7. User-learned alias persistence and resolution.
8. Structured execution result contracts.
"""

import pytest
from core.windows_app_resolver import WindowsAppResolver, WindowsAppMatch, WindowsAppSpec
from brain.spelling_resolver import SpellingResolver
from core.semantic.parsers.windows import parse_service_open, parse_app_close
from core.semantic.parsers.aliases import parse_alias_management, parse_custom_alias_execution
from core.alias_manager import CustomAliasManager
from core.execution.strategies import ExecutionStrategyEngine


@pytest.fixture
def resolver():
    return WindowsAppResolver.get_instance()


# ---------------------------------------------------------------------------
# 1. Primary Bug Verification: Microsoft Store & Typos
# ---------------------------------------------------------------------------

def test_microsoft_store_exact_resolution(resolver):
    match = resolver.resolve_app("microsoft store")
    assert match is not None
    assert match.canonical_id == "store"
    assert match.display_name == "Microsoft Store"
    assert match.launch_strategy == "protocol"
    assert match.launch_target == "ms-windows-store:"
    assert "WinStore.App.exe" in match.process_names


def test_microsoft_store_typo_microsft_store(resolver):
    # Minor STT typo: "microsft store"
    match = resolver.resolve_app("microsft store")
    assert match is not None
    assert match.canonical_id == "store"
    assert match.display_name == "Microsoft Store"


def test_spelling_resolver_does_not_suggest_storage_for_store():
    # User saying "open microsft store"
    # Previously, SpellingResolver intercepted "store" -> "storage" with needs_confirmation=True.
    correction = SpellingResolver.resolve("open microsft store")
    # Entity-aware resolver should correct "microsft store" directly to "Microsoft Store"
    # without asking "Kya aap 'storage' kehna chahte hain?"
    assert correction is not None
    assert correction.needs_confirmation is False
    assert correction.correction == "Microsoft Store"
    assert correction.corrected_text == "open Microsoft Store"


def test_open_storage_negative_guard(resolver):
    # Negative test: "storage" must NOT resolve to Microsoft Store
    match = resolver.resolve_app("storage")
    assert match is None or match.canonical_id != "store"

    # In spelling resolver, "open storage" must not be corrupted
    spelling = SpellingResolver.resolve("open storage")
    assert spelling is None  # "storage" is in IGNORE_WORDS and valid term


# ---------------------------------------------------------------------------
# 2. English, Hindi, Hinglish Open / Close Commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command,expected_intent,expected_app", [
    ("open microsoft store", "OPEN_APP", "store"),
    ("open microsft store", "OPEN_APP", "store"),
    ("microsoft store kholo", "OPEN_APP", "store"),
    ("microsoft store open karo", "OPEN_APP", "store"),
    ("close microsoft store", "WINDOW_CLOSE", "store"),
    ("microsoft store band karo", "WINDOW_CLOSE", "store"),
    ("microsoft store close kar do", "WINDOW_CLOSE", "store"),
])
def test_multilingual_open_close_commands(command, expected_intent, expected_app):
    lowered = command.lower()
    if "close" in lowered or "band" in lowered:
        act = parse_app_close(command, lowered)
    else:
        act = parse_service_open(command, lowered)

    assert act is not None, f"Failed to parse: {command}"
    assert act.intent == expected_intent
    assert act.parameters.get("app_name") == expected_app


# ---------------------------------------------------------------------------
# 3. 15+ Common Windows 11 Applications
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected_id,expected_strategy", [
    ("settings", "settings", "protocol"),
    ("calculator", "calc", "protocol"),
    ("task manager", "taskmgr", "executable"),
    ("file explorer", "explorer", "executable"),
    ("notepad", "notepad", "executable"),
    ("paint", "paint", "executable"),
    ("snipping tool", "snipping_tool", "protocol"),
    ("terminal", "terminal", "protocol"),
    ("camera", "camera", "protocol"),
    ("edge", "edge", "protocol"),
    ("word", "word", "protocol"),
    ("excel", "excel", "protocol"),
    ("chrome", "chrome", "protocol"),
    ("brave", "brave", "executable"),
    ("control panel", "control_panel", "executable"),
])
def test_common_windows_applications(resolver, query, expected_id, expected_strategy):
    match = resolver.resolve_app(query)
    assert match is not None, f"Failed to resolve app: {query}"
    assert match.canonical_id == expected_id
    assert match.launch_strategy == expected_strategy
    assert len(match.process_names) > 0


# ---------------------------------------------------------------------------
# 4. Safe Process Closing Mapping
# ---------------------------------------------------------------------------

def test_process_names_for_uwp_and_win32(resolver):
    # Store runs under WinStore.App.exe, NOT store.exe
    store_procs = resolver.get_process_names("store")
    assert "WinStore.App.exe" in store_procs

    # Settings runs under SystemSettings.exe
    settings_procs = resolver.get_process_names("settings")
    assert "SystemSettings.exe" in settings_procs

    # Calculator runs under CalculatorApp.exe or Calculator.exe
    calc_procs = resolver.get_process_names("calculator")
    assert any("calculator" in p.lower() for p in calc_procs)


# ---------------------------------------------------------------------------
# 5. Distinguish Application vs Website
# ---------------------------------------------------------------------------

def test_app_vs_website_distinction(resolver):
    # Applications
    assert resolver.is_application("chrome") is True
    assert resolver.is_application("brave") is True
    assert resolver.is_application("microsoft store") is True
    assert resolver.is_application("excel") is True

    # Websites must NOT be resolved as desktop apps
    assert resolver.resolve_app("youtube") is None
    assert resolver.resolve_app("google") is None
    assert resolver.resolve_app("wikipedia") is None


# ---------------------------------------------------------------------------
# 6. Multi-Application Commands
# ---------------------------------------------------------------------------

def test_multi_app_entity_extraction():
    from core.entities.knowledge import EntityKnowledgeBase
    kb = EntityKnowledgeBase.get_instance()

    # "open excel chrome brave word"
    found = kb.extract_entities_from_text("open excel chrome brave word")
    canonical_apps = [ent.entity_id for ent, start, end in found]
    assert "excel" in canonical_apps
    assert "chrome" in canonical_apps
    assert "brave" in canonical_apps
    assert "word" in canonical_apps

    # "open calculator notepad paint"
    found2 = kb.extract_entities_from_text("open calculator notepad paint")
    canonical_apps2 = [ent.entity_id for ent, start, end in found2]
    assert "calc" in canonical_apps2
    assert "notepad" in canonical_apps2
    assert "paint" in canonical_apps2


# ---------------------------------------------------------------------------
# 7. Contextual Disambiguation for Bare Words
# ---------------------------------------------------------------------------

def test_disambiguation_for_bare_store(resolver):
    # Bare word "store" is ambiguous
    match_bare = resolver.resolve_app("store")
    assert match_bare is not None
    assert match_bare.is_ambiguous is True
    assert match_bare.clarification is not None
    assert "Microsoft Store" in match_bare.clarification

    # Specific phrase "microsoft store" is NOT ambiguous
    match_specific = resolver.resolve_app("microsoft store")
    assert match_specific is not None
    assert match_specific.is_ambiguous is False
    assert match_specific.clarification is None


# ---------------------------------------------------------------------------
# 8. User-Learned Application Aliases & Persistence
# ---------------------------------------------------------------------------

def test_user_learned_alias_parsing_and_resolution(tmp_path):
    # Test Hindi meaning pattern: "store se mera matlab Microsoft Store hai"
    cmd1 = "store se mera matlab Microsoft Store hai"
    act1 = parse_alias_management(cmd1, cmd1.lower())
    assert act1 is not None
    assert act1.intent == "LEARN_ALIAS"
    assert act1.parameters.get("alias") == "store"
    assert act1.parameters.get("target") == "Microsoft Store"
    assert act1.parameters.get("action_type") == "OPEN_APPLICATION"

    # Test future alias pattern: "jab main 'store' bolun to Microsoft Store open karna"
    cmd2 = "jab main 'store' bolun to Microsoft Store open karna"
    act2 = parse_alias_management(cmd2, cmd2.lower())
    assert act2 is not None
    assert act2.intent == "LEARN_ALIAS"
    assert act2.parameters.get("alias") == "store"
    assert act2.parameters.get("target") == "Microsoft Store"
    assert act2.parameters.get("action_type") == "OPEN_APPLICATION"

    # Save alias in custom database
    test_db = str(tmp_path / "test_jarvis.db")
    alias_mgr = CustomAliasManager(db_path=test_db)
    alias_mgr.add_alias(
        alias="store",
        target="Microsoft Store",
        action_type="OPEN_APPLICATION"
    )

    # Verify retrieval
    entry = alias_mgr.get_alias("store")
    assert entry is not None
    assert entry["target"] == "Microsoft Store"
    assert entry["action_type"] == "OPEN_APPLICATION"


# ---------------------------------------------------------------------------
# 9. Structured Execution Result Contracts
# ---------------------------------------------------------------------------

def test_execution_result_contract(monkeypatch):
    strategies = ExecutionStrategyEngine()

    from core.execution.models import ExecutionState, VerificationResult
    monkeypatch.setattr(strategies, "_dispatch_app_strategy", lambda **kwargs: (True, None))
    monkeypatch.setattr(
        strategies.verifier,
        "verify_application_running",
        lambda app, should_run=True: VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="app_running",
            expected=True,
            actual=True
        )
    )

    # Launch contract for known app
    res = strategies.launch_application_verified("store", is_new=False)
    assert res.success is True
    assert res.data.get("application") == "Microsoft Store"
    assert res.data.get("canonical_id") == "store"
    assert res.data.get("launch_target") == "ms-windows-store:"

    # Close contract check
    monkeypatch.setattr(
        strategies.verifier,
        "verify_window_operation",
        lambda target, op, hwnd=None: VerificationResult(
            verified=True,
            state=ExecutionState.SUCCESS,
            check_type="window_close",
            expected="closed",
            actual="closed"
        )
    )
    monkeypatch.setattr(strategies.verifier.window_manager, "execute_operation", lambda op, target: {"success": True})

    close_res = strategies.close_target_verified("store")
    assert close_res.success is True
    assert close_res.data.get("application") == "Microsoft Store"
    assert "WinStore.App.exe" in close_res.data.get("process_names", [])
