# tests/test_universal_window_resolver.py
"""
Comprehensive Test Matrix for Universal Application & Window Resolution Engine.
Validates:
1. Normalization & Noise Stripping (Anti Gravity, Anti-Gravity, Anti Gravity ID, Chrome Browser, etc.)
2. Multi-signal matching across processes, window titles, and token sets.
3. Antigravity variations ('antigravity minimise karo', 'anti gravity ID ko minimise karo', etc.)
4. Chrome variations ('chrome', 'google chrome', 'chrome browser')
5. VS Code variations ('vs code', 'visual studio code', 'vscode')
6. Demonstratives & Deictic Pronouns ('yah window', 'yeh', 'this window', 'isko')
7. Conversational context inheritance ('AntiGravity open karo' -> 'isko minimise karo')
8. State-aware operations ('already minimized hai', 'already maximized hai')
9. Distinguishing process running without window vs not open at all
10. End-to-end NLU and execution verification
"""

import pytest
from unittest.mock import patch, MagicMock

from core.universal_window_resolver import (
    UniversalAppNormalizer,
    UniversalWindowResolver,
    normalize_application_name,
    get_universal_window_resolver
)
from plugins.windows.window_manager import WindowInfo, WindowManager
from core.semantic.parsers.windows import parse_window_control
from core.target_engine import TargetRequest, UniversalTargetDiscoveryEngine, ActionOutcome


# ==============================================================================
# 1. Normalization & Noise Suffix Stripping Unit Tests
# ==============================================================================
def test_universal_app_normalizer():
    # AntiGravity variations
    assert normalize_application_name("Anti Gravity") == "antigravity"
    assert normalize_application_name("Anti-Gravity") == "antigravity"
    assert normalize_application_name("Anti Gravity ID") == "antigravity"
    assert normalize_application_name("Anti Gravity IDE") == "antigravity"
    assert normalize_application_name("AntiGravity") == "antigravity"
    assert normalize_application_name("antigravity app") == "antigravity"

    # Browser variations
    assert normalize_application_name("Google Chrome Browser") == "google chrome"
    assert normalize_application_name("Chrome Browser") == "chrome"
    assert normalize_application_name("Brave Browser") == "brave"

    # Editor variations
    assert normalize_application_name("Visual Studio Code") == "visual studio code"
    assert normalize_application_name("VS Code") == "vs code"
    assert normalize_application_name("vscode") == "vscode"

    # Preserves single token even if it looks like a noise word when standalone
    assert normalize_application_name("window") == "window"
    assert normalize_application_name("browser") == "browser"


def test_universal_deictic_identification():
    assert UniversalAppNormalizer.is_relative_target("yah window") is True
    assert UniversalAppNormalizer.is_relative_target("yah") is True
    assert UniversalAppNormalizer.is_relative_target("yeh window") is True
    assert UniversalAppNormalizer.is_relative_target("yeh") is True
    assert UniversalAppNormalizer.is_relative_target("ye window") is True
    assert UniversalAppNormalizer.is_relative_target("ye") is True
    assert UniversalAppNormalizer.is_relative_target("this window") is True
    assert UniversalAppNormalizer.is_relative_target("this") is True
    assert UniversalAppNormalizer.is_relative_target("current") is True
    assert UniversalAppNormalizer.is_relative_target("isko") is True
    assert UniversalAppNormalizer.is_relative_target("ise") is True
    assert UniversalAppNormalizer.is_relative_target("chrome") is False
    assert UniversalAppNormalizer.is_relative_target("antigravity") is False


# ==============================================================================
# 2. Window Resolution Multi-Signal Matching Tests
# ==============================================================================
def test_resolve_antigravity_variations():
    """Verify all variations of AntiGravity resolve to the open Antigravity IDE window."""
    resolver = UniversalWindowResolver()
    antigravity_win = WindowInfo(
        hwnd=1001,
        title="Jarvis_19-09-2026 - Antigravity IDE - main.py",
        process_name="Antigravity IDE.exe",
        pid=5500
    )
    other_win = WindowInfo(hwnd=2001, title="Untitled - Notepad", process_name="notepad.exe", pid=6600)
    windows = [antigravity_win, other_win]

    variations = [
        "antigravity",
        "anti gravity",
        "anti-gravity",
        "anti gravity id",
        "anti gravity ide",
        "antigravity ide",
        "anti gravity app",
    ]

    for var in variations:
        res = resolver.resolve_window(var, windows)
        assert res is not None, f"Failed to resolve variation: {var}"
        assert res.hwnd == 1001
        assert res.process_name == "Antigravity IDE.exe"


def test_resolve_chrome_variations():
    resolver = UniversalWindowResolver()
    chrome_win = WindowInfo(hwnd=3001, title="GitHub - Google Chrome", process_name="chrome.exe", pid=7700)
    windows = [chrome_win]

    variations = ["chrome", "google chrome", "chrome browser", "google chrome browser"]
    for var in variations:
        res = resolver.resolve_window(var, windows)
        assert res is not None, f"Failed to resolve variation: {var}"
        assert res.hwnd == 3001


def test_resolve_vscode_variations():
    resolver = UniversalWindowResolver()
    vscode_win = WindowInfo(hwnd=4001, title="main.py - Visual Studio Code", process_name="Code.exe", pid=8800)
    windows = [vscode_win]

    variations = ["vs code", "visual studio code", "vscode", "code"]
    for var in variations:
        res = resolver.resolve_window(var, windows)
        assert res is not None, f"Failed to resolve variation: {var}"
        assert res.hwnd == 4001


# ==============================================================================
# 3. NLU Semantic Parser Tests for Window Commands
# ==============================================================================
def test_parse_window_control_matrix():
    cases = [
        ("antigravity minimise karo", "antigravity", "minimize"),
        ("anti gravity minimise karo", "antigravity", "minimize"),
        ("anti-gravity minimise karo", "antigravity", "minimize"),
        ("anti gravity id minimise karo", "antigravity", "minimize"),
        ("antigravity ko minimize karo", "antigravity", "minimize"),
        ("anti gravity ko minimise karo", "antigravity", "minimize"),
        ("chrome minimise karo", "chrome", "minimize"),
        ("google chrome minimise karo", "chrome", "minimize"),
        ("chrome browser minimise karo", "chrome", "minimize"),
        ("vs code minimise karo", "code", "minimize"),
        ("visual studio code minimise karo", "code", "minimize"),
        ("vscode minimise karo", "code", "minimize"),
        ("yah window minimise karo", "current", "minimize"),
        ("this window minimise karo", "current", "minimize"),
        ("yeh window band karo", "current", "close"),
        ("notepad ko maximize karo", "notepad", "maximize"),
    ]

    for text, expected_app, expected_op in cases:
        action = parse_window_control(text, text.lower())
        assert action is not None, f"Parser returned None for: {text}"
        assert action.parameters.get("operation") == expected_op, f"Wrong op for: {text}"
        assert action.parameters.get("app_name") == expected_app, f"Wrong app for: {text}"


# ==============================================================================
# 4. Context & Pronoun Resolution Tests ('AntiGravity open karo' -> 'isko minimise karo')
# ==============================================================================
def test_conversational_context_resolution():
    resolver = get_universal_window_resolver()
    antigravity_win = WindowInfo(
        hwnd=9999,
        title="Jarvis_19-09-2026 - Antigravity IDE - main.py",
        process_name="Antigravity IDE.exe",
        pid=5500
    )
    other_win = WindowInfo(hwnd=8888, title="Calculator", process_name="Calculator.exe", pid=2200)
    windows = [antigravity_win, other_win]

    # 1. User previously interacted with Antigravity
    resolver.update_context(
        app_name="AntiGravity",
        window_title="Jarvis_19-09-2026 - Antigravity IDE - main.py",
        hwnd=9999,
        process_name="Antigravity IDE.exe",
        action="open"
    )

    # 2. User says 'isko minimise karo' -> target is 'isko'
    resolved = resolver.resolve_window("isko", windows)
    assert resolved is not None
    assert resolved.hwnd == 9999
    assert resolved.process_name == "Antigravity IDE.exe"

    # 3. User says 'yah window' when no foreground mock is active -> resolves to recent context
    resolved_yah = resolver.resolve_window("yah window", windows)
    assert resolved_yah is not None
    assert resolved_yah.hwnd == 9999


# ==============================================================================
# 5. WindowManager State-Aware Operations & Verification
# ==============================================================================
def test_window_manager_already_minimized_state():
    wm = WindowManager()
    minimized_win = WindowInfo(
        hwnd=1111,
        title="Google - Google Chrome",
        process_name="chrome.exe",
        pid=3333,
        is_minimized=True
    )

    with patch.object(wm, "find_windows_for_app", return_value=[minimized_win]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("minimize", "chrome")
        assert res["success"] is True
        assert res.get("already") is True
        assert "already minimized" in res["message"]


def test_window_manager_already_maximized_state():
    wm = WindowManager()
    maximized_win = WindowInfo(
        hwnd=2222,
        title="Google - Google Chrome",
        process_name="chrome.exe",
        pid=3333,
        is_maximized=True
    )

    with patch.object(wm, "find_windows_for_app", return_value=[maximized_win]), \
         patch.object(wm, "_user32") as mock_u32:
        res = wm.execute_operation("maximize", "chrome")
        assert res["success"] is True
        assert res.get("already") is True
        assert "already maximized" in res["message"]


def test_window_manager_process_running_without_visible_window():
    wm = WindowManager()

    # When no windows are discovered, but psutil shows process is active
    with patch.object(wm, "find_windows_for_app", return_value=[]), \
         patch.object(wm, "is_process_running", return_value=(True, [4444])), \
         patch.object(wm, "_get_hwnds_for_pids", return_value=[]):
        res = wm.execute_operation("minimize", "antigravity")
        assert res["success"] is False
        assert res.get("running") is True
        assert "background process chal rahi hai" in res["message"]


def test_window_manager_not_running_at_all():
    wm = WindowManager()

    with patch.object(wm, "find_windows_for_app", return_value=[]), \
         patch.object(wm, "is_process_running", return_value=(False, [])):
        res = wm.execute_operation("minimize", "unknown_app_xyz")
        assert res["success"] is False
        assert res.get("running") is False
        assert "open nahi hai (already band hai)" in res["message"]


# ==============================================================================
# 6. TargetEngine End-to-End Resolution & Execution
# ==============================================================================
def test_target_engine_anti_gravity_id_resolution():
    wm = WindowManager()
    antigravity_win = WindowInfo(
        hwnd=7777,
        title="Jarvis_19-09-2026 - Antigravity IDE - main.py",
        process_name="Antigravity IDE.exe",
        pid=5500
    )

    engine = UniversalTargetDiscoveryEngine(window_manager=wm)

    with patch.object(wm, "list_all_windows", return_value=[antigravity_win]), \
         patch.object(wm, "find_windows_for_app", return_value=[antigravity_win]), \
         patch.object(wm, "_user32") as mock_u32:
        outcome = engine.execute(TargetRequest(target="anti gravity ID", action="minimize"))
        assert outcome.success is True
        assert "minimize" in outcome.message
        assert outcome.verified is True
