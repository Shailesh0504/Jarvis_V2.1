# plugins/code_assistant/analyzers/coverage.py
"""
Test Coverage Analyzer for the Jarvis Code Intelligence System.
Maps project source modules to test suites (tests/test_*.py), identifies untested
components, and calculates structural test coverage metrics.
"""

import ast
import os
from typing import Dict, List, Set

from ..models import CoverageReport, ModuleCoverageItem


class CoverageAnalyzer:
    """Evaluates test suite completeness and module coverage across the project."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def analyze(self, target_dir: str = ".") -> CoverageReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        source_modules: List[str] = []
        test_files: Dict[str, int] = {}  # test_file_rel -> test_func_count

        # 1. Discover all test files and count test functions
        tests_dir = os.path.join(self.workspace_root, "tests")
        if os.path.isdir(tests_dir):
            for f in os.listdir(tests_dir):
                if f.startswith("test_") and f.endswith(".py"):
                    full_test = os.path.join(tests_dir, f)
                    try:
                        with open(full_test, "r", encoding="utf-8", errors="ignore") as fp:
                            tree = ast.parse(fp.read(), filename=full_test)
                        cnt = sum(1 for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))
                        test_files[f] = max(1, cnt)
                    except Exception:
                        test_files[f] = 1

        # 2. Discover all primary source modules in core, brain, plugins
        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            rel_root = os.path.relpath(root, self.workspace_root)
            if not any(rel_root.startswith(p) for p in ("core", "brain", "plugins", "memory", "learning")):
                continue

            for f in files:
                if not f.endswith(".py") or f.startswith("__") or f.startswith("test_"):
                    continue
                source_modules.append(os.path.join(rel_root, f))

        # 3. Map sources to tests
        items: List[ModuleCoverageItem] = []
        tested_count = 0

        for sm in source_modules:
            base = os.path.splitext(os.path.basename(sm))[0]
            matched_test = None
            test_funcs = 0

            # Heuristic match: test_<base>.py or test_<component>.py
            possible_names = [f"test_{base}.py"]
            if "/" in sm or "\\" in sm:
                pkg_name = sm.replace("\\", "/").split("/")[0]
                possible_names.append(f"test_{pkg_name}.py")

            for p in possible_names:
                if p in test_files:
                    matched_test = f"tests/{p}"
                    test_funcs = test_files[p]
                    break

            has_test = matched_test is not None
            if has_test:
                tested_count += 1

            cov_pct = min(100, test_funcs * 12) if has_test else 0

            items.append(
                ModuleCoverageItem(
                    module_path=sm,
                    has_test_file=has_test,
                    test_file_path=matched_test,
                    estimated_coverage_pct=cov_pct,
                    test_functions_count=test_funcs,
                )
            )

        total_sources = len(source_modules)
        untested_count = total_sources - tested_count
        overall_cov = round((tested_count / max(1, total_sources)) * 100)
        score = max(0, min(100, int(overall_cov * 1.05)))

        lines_out = [
            "Test Suite Coverage Analysis",
            f"Primary Source Modules: {total_sources}",
            f"Tested Modules: {tested_count}",
            f"Untested Modules: {untested_count}",
            f"Active Test Files: {len(test_files)}",
            f"Coverage Health Score: {score}/100 ({overall_cov}% mapped)",
        ]
        if untested_count > 0:
            lines_out.append(f"Untested Sample: {', '.join([i.module_path for i in items if not i.has_test_file][:3])}")

        chatbox_report = "\n".join(lines_out)

        return CoverageReport(
            total_source_modules=total_sources,
            tested_modules=tested_count,
            untested_modules=untested_count,
            overall_coverage_pct=overall_cov,
            items=items,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
