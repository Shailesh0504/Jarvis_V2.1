# plugins/code_assistant/analyzers/complexity.py
"""
Complexity Analyzer for the Jarvis Code Intelligence System.
Calculates Cyclomatic and Cognitive Complexity for every function and method.
Flags high-complexity functions exceeding maintainability thresholds.
"""

import ast
import os
from typing import List, Set

from ..models import ComplexityItem, ComplexityReport


class ComplexityAnalyzer:
    """Calculates code complexity metrics across the workspace."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Counts branching points in AST."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.Assert)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.IfExp,)):
                complexity += 1
        return complexity

    def _compute_cognitive_complexity(self, node: ast.AST, nesting_level: int = 0) -> int:
        """Recursively calculates cognitive complexity with nesting increments."""
        score = 0
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                score += 1 + nesting_level
                score += self._compute_cognitive_complexity(child, nesting_level + 1)
            elif isinstance(child, ast.Try):
                score += 1
                for handler in child.handlers:
                    score += 1 + nesting_level
                    score += self._compute_cognitive_complexity(handler, nesting_level + 1)
                score += self._compute_cognitive_complexity(child, nesting_level)
            else:
                score += self._compute_cognitive_complexity(child, nesting_level)
        return score

    def analyze(self, target_dir: str = ".") -> ComplexityReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        items: List[ComplexityItem] = []
        total_functions = 0
        total_cc = 0
        high_complexity_count = 0

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

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_functions += 1
                        cc = self._compute_cyclomatic_complexity(node)
                        cog = self._compute_cognitive_complexity(node)
                        line_count = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
                        total_cc += cc

                        risk = "LOW"
                        if cc >= 15 or line_count > 60:
                            risk = "HIGH"
                            high_complexity_count += 1
                        elif cc >= 10 or line_count > 40:
                            risk = "MEDIUM"

                        items.append(
                            ComplexityItem(
                                file_path=rel_path,
                                function_name=node.name,
                                line_number=node.lineno,
                                cyclomatic_complexity=cc,
                                cognitive_complexity=cog,
                                line_count=line_count,
                                risk_level=risk,
                            )
                        )

        avg_cc = round(total_cc / max(1, total_functions), 2)
        score = max(0, min(100, int(100 - (high_complexity_count * 3) - max(0, (avg_cc - 4) * 5))))

        # Sort items by cyclomatic complexity descending
        items.sort(key=lambda x: x.cyclomatic_complexity, reverse=True)

        lines_out = [
            "Code Complexity Analysis",
            f"Total Functions Analyzed: {total_functions:,}",
            f"Average Cyclomatic Complexity: {avg_cc}",
            f"High Complexity Functions (CC >= 15): {high_complexity_count}",
            f"Complexity Health Score: {score}/100",
        ]
        if high_complexity_count > 0:
            lines_out.append("Top Complex Functions:")
            for it in items[:4]:
                lines_out.append(f"  {it.function_name}() at {it.file_path}:{it.line_number} (CC: {it.cyclomatic_complexity}, Lines: {it.line_count})")

        chatbox_report = "\n".join(lines_out)

        return ComplexityReport(
            total_functions_analyzed=total_functions,
            avg_cyclomatic_complexity=avg_cc,
            high_complexity_count=high_complexity_count,
            items=items,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
