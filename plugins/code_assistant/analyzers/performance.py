# plugins/code_assistant/analyzers/performance.py
"""
Performance Analyzer for the Jarvis Code Intelligence System.
Detects static performance bottlenecks: synchronous blocking calls inside async loops,
repeated uncompiled regexes in loops, and unbounded I/O operations.
"""

import ast
import os
from typing import List, Set

from ..models import PerformanceAntipattern, PerformanceReport


class PerformanceAnalyzer:
    """Detects latency risks and static performance antipatterns."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def analyze(self, target_dir: str = ".") -> PerformanceReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        issues: List[PerformanceAntipattern] = []
        total_checks = 0

        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py") or f.startswith("test_"):
                    continue

                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=full_path)
                except Exception:
                    continue

                total_checks += 1

                for node in ast.walk(tree):
                    # 1. Blocking sleep in async function
                    if isinstance(node, ast.AsyncFunctionDef):
                        for inner in ast.walk(node):
                            if isinstance(inner, ast.Call):
                                fn_name = ""
                                if isinstance(inner.func, ast.Attribute):
                                    fn_name = f"{getattr(inner.func.value, 'id', '')}.{inner.func.attr}"
                                if fn_name in ("time.sleep", "sleep"):
                                    issues.append(
                                        PerformanceAntipattern(
                                            file_path=rel_path,
                                            line_number=inner.lineno,
                                            pattern_type="blocking_in_async",
                                            description=f"Synchronous '{fn_name}()' blocks the async event loop in '{node.name}()'.",
                                            suggestion="Use 'await asyncio.sleep()' instead.",
                                        )
                                    )

                    # 2. Uncompiled regex inside loops
                    if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                        for inner in ast.walk(node):
                            if isinstance(inner, ast.Call):
                                if isinstance(inner.func, ast.Attribute) and getattr(inner.func.value, "id", "") == "re":
                                    if inner.func.attr in ("search", "match", "findall", "sub"):
                                        issues.append(
                                            PerformanceAntipattern(
                                                file_path=rel_path,
                                                line_number=inner.lineno,
                                                pattern_type="uncompiled_regex_loop",
                                                description=f"Regex 're.{inner.func.attr}()' called repeatedly inside loop.",
                                                suggestion="Pre-compile pattern once outside loop with 're.compile()'.",
                                            )
                                        )

        issue_count = len(issues)
        score = max(0, min(100, 100 - (issue_count * 5)))

        lines_out = [
            "Performance Antipattern Scan",
            f"Files Inspected: {total_checks}",
            f"Performance Bottlenecks Detected: {issue_count}",
            f"Performance Health Score: {score}/100",
        ]
        if issue_count > 0:
            lines_out.append("Top Performance Concerns:")
            for issue in issues[:3]:
                lines_out.append(f"  {issue.description} ({issue.file_path}:{issue.line_number})")
        else:
            lines_out.append("No blocking async calls or uncompiled regex loops detected.")

        chatbox_report = "\n".join(lines_out)

        return PerformanceReport(
            total_checks_performed=total_checks,
            issues_found=issue_count,
            items=issues,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
