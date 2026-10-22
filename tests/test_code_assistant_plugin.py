# tests/test_code_assistant_plugin.py
"""Comprehensive test suite for Developer Code Assistant Plugin."""

import os
import tempfile
import pytest

from brain.semantic_parser import HinglishNLUParser
from plugins.code_assistant.analyzer import CodeAnalysisEngine
from plugins.code_assistant.models import AssistantMode
from plugins.code_assistant.plugin import CodeAssistantPlugin
from plugins.manifest import PluginResult


@pytest.fixture
def plugin():
    return CodeAssistantPlugin()


@pytest.fixture
def analyzer():
    return CodeAnalysisEngine()


# =====================================================================
# 1. Plugin Lifecycle and Manifest
# =====================================================================
def test_plugin_discovery_and_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "code_assistant"
    assert manifest.version == "1.0.0"
    assert "filesystem" in manifest.permissions
    assert "process" in manifest.permissions

    action_names = {a.name for a in manifest.actions}
    expected = {
        "find_errors",
        "analyze_file",
        "find_unused_functions",
        "check_architecture",
        "run_pytest",
        "suggest_error_fix",
        "analyze_change_impact",
        "find_dead_code",
        "get_mode",
        "set_mode",
    }
    assert expected.issubset(action_names)


# =====================================================================
# 2. Strict Safety Invariants & Mode Enforcement
# =====================================================================
def test_default_mode_is_read_only(plugin):
    assert plugin.mode == AssistantMode.READ_ONLY
    res = plugin.execute("get_mode", {})
    assert res.success is True
    assert res.data["mode"] == "READ_ONLY"
    assert "strictly prohibited" in res.data["message"]


def test_file_modification_blocked_in_read_only(plugin):
    plugin.mode = AssistantMode.READ_ONLY
    res = plugin.execute("apply_patch", {"target_file": "main.py", "confirm": True})
    assert res.success is False
    assert "blocked" in res.error.lower()
    assert "read_only" in res.error.lower()


def test_file_modification_blocked_in_suggest_mode(plugin):
    plugin.execute("set_mode", {"mode": "SUGGEST"})
    assert plugin.mode == AssistantMode.SUGGEST

    res = plugin.execute("auto_fix", {"target_file": "main.py", "confirm": True})
    assert res.success is False
    assert "blocked" in res.error.lower()
    assert "suggest" in res.error.lower()


def test_direct_automatic_modification_blocked_without_confirmation(plugin):
    # Even in AUTO_FIX mode, direct unprompted modification without explicit confirm is blocked
    plugin.execute("set_mode", {"mode": "AUTO_FIX"})
    assert plugin.mode == AssistantMode.AUTO_FIX

    res = plugin.execute("auto_fix", {"target_file": "main.py"})
    assert res.success is False
    assert "Safety Guard" in res.error
    assert res.data.get("requires_confirmation") is True


def test_mode_switching(plugin):
    for m in [AssistantMode.SUGGEST, AssistantMode.PATCH, AssistantMode.AUTO_FIX, AssistantMode.READ_ONLY]:
        res = plugin.execute("set_mode", {"mode": m.value})
        assert res.success is True
        assert plugin.mode == m


# =====================================================================
# 3. File Analysis
# =====================================================================
def test_analyze_file_main_py(plugin):
    res = plugin.execute("analyze_file", {"file_path": "main.py"})
    assert res.success is True
    data = res.data
    assert data["exists"] is True
    assert data["total_lines"] > 50
    assert data["code_lines"] > 30
    assert data["syntax_valid"] is True
    assert "main.py" in data["summary_message"]


def test_analyze_file_temporary_script(analyzer):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write("class Demo:\n    def hello(self):\n        pass\n")
        temp_path = tf.name

    try:
        res = analyzer.analyze_file(temp_path)
        assert res.exists is True
        assert res.class_count == 1
        assert "Demo" in res.classes
        assert "hello" in res.functions
        assert res.syntax_valid is True
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# =====================================================================
# 4. Error Finding & Diagnosis
# =====================================================================
def test_find_errors_syntax_check(analyzer):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write("def broken(\n    pass\n")  # Syntax error: unclosed parenthesis
        temp_path = tf.name

    try:
        res = analyzer.find_errors(target_file=temp_path)
        assert res["success"] is True
        assert res["count"] >= 1
        assert any(e.get("source") == "syntax_check" for e in res["errors"])
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_suggest_error_fix(plugin):
    sample_error = (
        'Traceback (most recent call last):\n'
        '  File "core/test.py", line 42, in run\n'
        'TypeError: unsupported operand type(s) for +: int and str'
    )
    res = plugin.execute("suggest_error_fix", {"error_text": sample_error})
    assert res.success is True
    data = res.data
    assert data["error_type"] == "TypeError"
    assert data["target_line"] == 42
    assert "Function signature" in data["suggested_fix"]
    assert "diff" in data


# =====================================================================
# 5. Unused Functions & Dead Code
# =====================================================================
def test_find_dead_code_unreachable(analyzer):
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "sample.py")
        with open(test_file, "w", encoding="utf-8") as tf:
            tf.write(
                "def test_foo():\n"
                "    return 1\n"
                "    print('unreachable')\n"
            )

        items = analyzer.find_dead_code(target_dir=temp_dir)
        assert any(d.item_type == "unreachable_code" for d in items)


def test_find_unused_functions(plugin):
    res = plugin.execute("find_unused_functions", {"target_dir": "plugins/code_assistant"})
    assert res.success is True
    assert "count" in res.data
    assert "summary_message" in res.data
    report_text = res.data["summary_message"]
    # Verify exact user chatbox structure
    assert "Codebase Analysis Complete" in report_text
    assert "Total functions analyzed:" in report_text
    assert "Potentially unused:" in report_text
    assert "High-confidence dead code:" in report_text
    assert "Possibly dynamic:" in report_text
    assert "Public/API functions:" in report_text
    assert "Test-only functions:" in report_text
    assert "Recommendation:" in report_text
    assert "I will NOT delete anything automatically." in report_text


def test_analyze_all_dead_code_comprehensive(analyzer):
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "sample_module.py")
        with open(test_file, "w", encoding="utf-8") as tf:
            tf.write(
                "import math\n"            # unused import
                "unused_var = 123\n"        # unused var
                "def dead_func():\n"        # unused function
                "    return 1\n"
                "    print('dead')\n"       # unreachable code
                "class UnusedDemo:\n"       # unused class
                "    def uncalled(self):\n" # unused method
                "        pass\n"
            )

        report = analyzer.analyze_all_dead_code(target_dir=temp_dir)
        assert report.total_symbols_analyzed >= 5
        assert report.potentially_unused_count >= 3
        assert report.very_likely_dead_count >= 1
        assert "Comprehensive Dead Code Analysis Complete" in report.formatted_chatbox_report
        assert "Automatic deletion is strictly guarded; no code has been modified." in report.formatted_chatbox_report


def test_safe_cleanup_5_stage_guarded_workflow(plugin):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(
            "def active():\n"
            "    return True\n"
            "\n"
            "def dead_func():\n"
            "    return False\n"
        )
        temp_file = tf.name

    try:
        # Stage 1: Blocked in READ_ONLY
        plugin.mode = AssistantMode.READ_ONLY
        res = plugin.execute("safe_cleanup", {"target_file": temp_file, "confirm": True})
        assert res.success is False
        assert "blocked" in res.error.lower()

        # Switch to AUTO_FIX
        plugin.mode = AssistantMode.AUTO_FIX

        # Stage 2: Blocked without confirm=True
        res = plugin.execute("safe_cleanup", {"target_file": temp_file, "confirm": False})
        assert res.success is False
        assert res.data.get("requires_confirmation") is True

        # Stage 3, 4, 5: Confirmed safe cleanup with backup
        res = plugin.execute("safe_cleanup", {
            "target_file": temp_file,
            "symbol_name": "dead_func",
            "confirm": True,
            "verify_tests": False,
        })
        assert res.success is True
        assert os.path.isfile(f"{temp_file}.bak")

        # Verify target file has dead code commented out and syntax is valid
        with open(temp_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "DEAD_CODE_REMOVED" in content
        assert "def active():" in content

        # Test Auto-Rollback on Syntax Error
        res_bad = plugin.execute("safe_cleanup", {
            "target_file": temp_file,
            "patch_content": "def broken(\n",  # syntax error
            "confirm": True,
            "verify_tests": False,
        })
        assert res_bad.success is False
        assert res_bad.data.get("rolled_back") is True
        # Content rolled back safely
        with open(temp_file, "r", encoding="utf-8") as f:
            rb_content = f.read()
        assert rb_content == content

    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(f"{temp_file}.bak"):
            os.remove(f"{temp_file}.bak")


# =====================================================================
# 6. Architecture & SSOT Check
# =====================================================================
def test_check_architecture(plugin):
    res = plugin.execute("check_architecture", {})
    assert res.success is True
    data = res.data
    assert data["core_modules_present"]["core"] is True
    assert data["core_modules_present"]["brain"] is True
    assert data["core_modules_present"]["plugins"] is True
    assert data["total_files_checked"] > 100
    assert "Architecture check" in data["summary_message"]


# =====================================================================
# 7. Change Impact Assessment & Pytest Runner
# =====================================================================
def test_analyze_change_impact(plugin):
    res = plugin.execute("analyze_change_impact", {})
    assert res.success is True
    data = res.data
    assert data["risk_tier"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert "summary_message" in data


def test_run_pytest_scoped(plugin):
    # Run a fast scoped test (this file itself or a single quick test)
    res = plugin.execute("run_pytest", {
        "test_target": "tests/test_code_assistant_plugin.py::test_default_mode_is_read_only",
        "timeout": 30
    })
    assert res.success is True
    data = res.data
    assert data["passed"] >= 1
    assert data["failed"] == 0
    assert "Pytest run completed" in data["summary_message"]


# =====================================================================
# 8. End-to-End NLU Command Routing (All 8 Commands + Modes)
# =====================================================================
@pytest.mark.parametrize(
    "utterance,expected_action",
    [
        ("Jarvis code mein ye error find karo", "find_errors"),
        ("main.py analyze karo", "analyze_file"),
        ("unused functions find karo", "find_unused_functions"),
        ("project architecture check karo", "check_architecture"),
        ("pytest run karo", "run_pytest"),
        ("error fix suggest karo", "suggest_error_fix"),
        ("last change ka impact batao", "analyze_change_impact"),
        ("dead code find karo", "find_dead_code"),
        ("code assistant mode check karo", "get_mode"),
        ("code assistant mode set karo AUTO_FIX", "set_mode"),
        ("code assistant mode set karo SUGGEST", "set_mode"),
        ("code assistant mode set karo READ_ONLY", "set_mode"),
    ],
)
def test_nlu_command_routing(utterance, expected_action):
    action = HinglishNLUParser.parse(utterance)
    assert action is not None, f"Query '{utterance}' did not parse into SemanticAction"
    assert action.service == "code_assistant", f"Expected service 'code_assistant', got '{action.service}' for '{utterance}'"
    assert action.action == expected_action, f"Expected action '{expected_action}', got '{action.action}' for '{utterance}'"

