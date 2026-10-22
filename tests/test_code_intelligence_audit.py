# tests/test_code_intelligence_audit.py
"""Comprehensive test suite for the 10-Pillar Code Intelligence System and Project Health Audit."""

import os
import tempfile
import pytest

from brain.semantic_parser import HinglishNLUParser
from plugins.code_assistant.analyzer import CodeAnalysisEngine
from plugins.code_assistant.analyzers.architecture import ArchitectureAnalyzer
from plugins.code_assistant.analyzers.circular import CircularDependencyDetector
from plugins.code_assistant.analyzers.complexity import ComplexityAnalyzer
from plugins.code_assistant.analyzers.coverage import CoverageAnalyzer
from plugins.code_assistant.analyzers.dead_code import DeadCodeAnalyzer
from plugins.code_assistant.analyzers.dependency import DependencyAnalyzer
from plugins.code_assistant.analyzers.duplication import DuplicateCodeDetector
from plugins.code_assistant.analyzers.health_audit import HealthAuditEngine
from plugins.code_assistant.analyzers.imports import ImportAnalyzer
from plugins.code_assistant.analyzers.performance import PerformanceAnalyzer
from plugins.code_assistant.analyzers.security import SecurityScanner
from plugins.code_assistant.plugin import CodeAssistantPlugin


@pytest.fixture
def plugin():
    return CodeAssistantPlugin()


@pytest.fixture
def workspace_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# =====================================================================
# 1. Dependency Analyzer
# =====================================================================
def test_dependency_analyzer(workspace_root):
    analyzer = DependencyAnalyzer(workspace_root)
    rep = analyzer.analyze()
    assert rep.total_dependencies > 0
    assert 0 <= rep.health_score <= 100
    assert "Dependency Health Report" in rep.formatted_chatbox_report


# =====================================================================
# 2. Import Analyzer
# =====================================================================
def test_import_analyzer_wildcards_and_order(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "bad_import.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                "print('executable statement first')\n"
                "from math import *\n"  # wildcard and out of order
                "import os\n"
            )

        analyzer = ImportAnalyzer(temp_dir)
        rep = analyzer.analyze()
        assert rep.wildcard_count >= 1
        assert rep.out_of_order_count >= 1
        assert rep.health_score < 100


# =====================================================================
# 3. Duplicate Code Detector
# =====================================================================
def test_duplicate_code_detector(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        f1 = os.path.join(temp_dir, "module_a.py")
        f2 = os.path.join(temp_dir, "module_b.py")
        dup_code = (
            "def compute_hash_data(a, b, c):\n"
            "    x = a + b\n"
            "    y = x * c\n"
            "    z = y - 10\n"
            "    w = z ** 2\n"
            "    return w + 42\n"
        )
        with open(f1, "w", encoding="utf-8") as fp:
            fp.write(dup_code)
        with open(f2, "w", encoding="utf-8") as fp:
            fp.write(dup_code)

        detector = DuplicateCodeDetector(temp_dir, min_lines=5)
        rep = detector.analyze()
        assert rep.duplicate_blocks_count >= 1
        assert any(d.duplicate_of_file.endswith("module_a.py") or d.file_path.endswith("module_b.py") for d in rep.duplicates)


# =====================================================================
# 4. Complexity Analyzer
# =====================================================================
def test_complexity_analyzer(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        f = os.path.join(temp_dir, "complex.py")
        with open(f, "w", encoding="utf-8") as fp:
            fp.write(
                "def deeply_nested(x, y, z):\n"
                "    if x > 0:\n"
                "        for i in range(10):\n"
                "            if y and z:\n"
                "                while i < 5:\n"
                "                    if i % 2 == 0:\n"
                "                        return 1\n"
                "    return 0\n"
            )

        analyzer = ComplexityAnalyzer(temp_dir)
        rep = analyzer.analyze()
        assert rep.total_functions_analyzed == 1
        assert rep.items[0].cyclomatic_complexity >= 5
        assert rep.items[0].cognitive_complexity >= 5


# =====================================================================
# 5. Circular Dependency Detector
# =====================================================================
def test_circular_dependency_detector(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create module_x importing module_y, and module_y importing module_x
        f_x = os.path.join(temp_dir, "pkg_x.py")
        f_y = os.path.join(temp_dir, "pkg_y.py")
        with open(f_x, "w", encoding="utf-8") as fp:
            fp.write("import pkg_y\n")
        with open(f_y, "w", encoding="utf-8") as fp:
            fp.write("import pkg_x\n")

        detector = CircularDependencyDetector(temp_dir)
        rep = detector.analyze()
        assert rep.cycles_found >= 1
        assert rep.health_score < 100


# =====================================================================
# 6. Security Scanner
# =====================================================================
def test_security_scanner(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        f = os.path.join(temp_dir, "vuln.py")
        with open(f, "w", encoding="utf-8") as fp:
            fp.write(
                "import subprocess\n"
                "cmd = 'ls'\n"
                "subprocess.run(cmd, shell=True)\n"  # shell=True
                "eval('2 + 2')\n"                    # eval
                "api_key = 'test_" + "secret_" * 3 + "value_1234567890'\n" # synthetic secret
            )

        scanner = SecurityScanner(temp_dir)
        rep = scanner.analyze()
        assert rep.vulnerabilities_count >= 3
        assert rep.critical_count >= 1  # eval
        assert rep.high_count >= 2     # shell=True + api_key
        assert rep.health_score <= 50


# =====================================================================
# 7. Performance Analyzer
# =====================================================================
def test_performance_analyzer(workspace_root):
    with tempfile.TemporaryDirectory() as temp_dir:
        f = os.path.join(temp_dir, "slow.py")
        with open(f, "w", encoding="utf-8") as fp:
            fp.write(
                "import asyncio, time, re\n"
                "async def fetch_data():\n"
                "    time.sleep(1)\n"  # blocking in async
                "\n"
                "def regex_in_loop(items):\n"
                "    for it in items:\n"
                "        re.search(r'\\d+', it)\n"  # uncompiled regex
            )

        analyzer = PerformanceAnalyzer(temp_dir)
        rep = analyzer.analyze()
        assert rep.issues_found >= 2
        assert any(i.pattern_type == "blocking_in_async" for i in rep.items)
        assert any(i.pattern_type == "uncompiled_regex_loop" for i in rep.items)


# =====================================================================
# 8. Coverage Analyzer
# =====================================================================
def test_coverage_analyzer(workspace_root):
    analyzer = CoverageAnalyzer(workspace_root)
    rep = analyzer.analyze()
    assert rep.total_source_modules > 0
    assert rep.tested_modules > 0
    assert 0 <= rep.overall_coverage_pct <= 100


# =====================================================================
# 9. Holistic Health Audit Engine
# =====================================================================
def test_health_audit_engine(workspace_root):
    engine = HealthAuditEngine(workspace_root)
    report = engine.run_audit()

    assert 0 <= report.overall_score <= 100
    assert report.letter_grade in ("A+", "A", "B+", "B", "C", "D", "F")
    assert len(report.pillar_scores) == 10
    assert len(report.top_recommendations) >= 1
    assert "PROJECT HEALTH AUDIT REPORT" in report.formatted_chatbox_report
    assert "Overall Health Score:" in report.formatted_chatbox_report
    assert "Pillar Breakdown:" in report.formatted_chatbox_report


def test_plugin_execute_health_audit(plugin):
    res = plugin.execute("run_health_audit", {})
    assert res.success is True
    data = res.data
    assert "overall_score" in data
    assert "letter_grade" in data
    assert "pillar_scores" in data
    assert len(data["pillar_scores"]) == 10
    assert "summary_message" in data


# =====================================================================
# 10. End-to-End NLU Routing for Code Intelligence Commands
# =====================================================================
@pytest.mark.parametrize(
    "utterance,expected_action",
    [
        ("Jarvis, mere pure project ka health audit karo", "run_health_audit"),
        ("mere pure project ka health audit karo", "run_health_audit"),
        ("project health audit karo", "run_health_audit"),
        ("code health audit", "run_health_audit"),
        ("dependency analyze karo", "analyze_dependencies"),
        ("dependencies check karo", "analyze_dependencies"),
        ("imports analyze karo", "analyze_imports"),
        ("wildcard imports check karo", "analyze_imports"),
        ("duplicate code find karo", "detect_duplication"),
        ("code complexity check karo", "analyze_complexity"),
        ("circular dependencies check karo", "detect_circular_dependencies"),
        ("security scan karo", "scan_security"),
        ("performance analyze karo", "analyze_performance"),
        ("test coverage check karo", "analyze_coverage"),
    ],
)
def test_code_intelligence_nlu_routing(utterance, expected_action):
    action = HinglishNLUParser.parse(utterance)
    assert action is not None, f"Query '{utterance}' did not parse into SemanticAction"
    assert action.service == "code_assistant", f"Expected service 'code_assistant', got '{action.service}'"
    assert action.action == expected_action, f"Expected action '{expected_action}', got '{action.action}'"
