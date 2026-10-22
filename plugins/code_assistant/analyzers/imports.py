# plugins/code_assistant/analyzers/imports.py
"""
Import Analyzer for the Jarvis Code Intelligence System.
Detects wildcard imports, unused imports, out-of-order imports, and deprecated module imports.
"""

import ast
import os
from typing import List, Optional, Set

from ..models import ImportAnalysisReport, ImportIssue


class ImportAnalyzer:
    """Performs static AST inspection on workspace imports for clean hygiene and PEP-8 standards."""

    def __init__(self, workspace_root: str, ignored_dirs: Optional[Set[str]] = None):
        self.workspace_root = workspace_root
        self.ignored_dirs = ignored_dirs or {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def analyze(self, target_dir: str = ".") -> ImportAnalysisReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        issues: List[ImportIssue] = []
        total_imports = 0
        wildcard_count = 0
        unused_count = 0
        out_of_order_count = 0

        deprecated_modules = {"distutils", "imp", "optparse", "formatter", "symbol", "parser"}

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

                # Collect all identifiers in file
                file_identifiers: Set[str] = set()
                export_all: Set[str] = set()
                imports_in_file = []
                seen_non_import_statement = False

                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        file_identifiers.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        file_identifiers.add(node.attr)

                # Check __all__
                for stmt in tree.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and target.id == "__all__":
                                if isinstance(stmt.value, (ast.List, ast.Tuple, ast.Set)):
                                    for elt in stmt.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                            export_all.add(elt.value)

                # Inspect top-level statements for order and wildcards
                for stmt in tree.body:
                    if isinstance(stmt, ast.Import):
                        if seen_non_import_statement:
                            out_of_order_count += 1
                            issues.append(
                                ImportIssue(
                                    file_path=rel_path,
                                    line_number=stmt.lineno,
                                    module_name=", ".join([a.name for a in stmt.names]),
                                    issue_type="out_of_order",
                                    recommendation="Move import to top of the file before executable statements.",
                                )
                            )
                        for alias in stmt.names:
                            total_imports += 1
                            mod_base = alias.name.split(".")[0]
                            if mod_base in deprecated_modules:
                                issues.append(
                                    ImportIssue(
                                        file_path=rel_path,
                                        line_number=stmt.lineno,
                                        module_name=alias.name,
                                        issue_type="deprecated",
                                        recommendation=f"Module '{alias.name}' is deprecated in modern Python.",
                                    )
                                )
                            track_name = alias.asname or mod_base
                            imports_in_file.append((track_name, stmt.lineno))

                    elif isinstance(stmt, ast.ImportFrom):
                        if seen_non_import_statement:
                            out_of_order_count += 1
                            issues.append(
                                ImportIssue(
                                    file_path=rel_path,
                                    line_number=stmt.lineno,
                                    module_name=stmt.module or "from",
                                    issue_type="out_of_order",
                                    recommendation="Move import to top of the file.",
                                )
                            )
                        if stmt.module and stmt.module.split(".")[0] in deprecated_modules:
                            issues.append(
                                ImportIssue(
                                    file_path=rel_path,
                                    line_number=stmt.lineno,
                                    module_name=stmt.module,
                                    issue_type="deprecated",
                                    recommendation=f"Module '{stmt.module}' is deprecated.",
                                )
                            )

                        for alias in stmt.names:
                            total_imports += 1
                            if alias.name == "*":
                                wildcard_count += 1
                                issues.append(
                                    ImportIssue(
                                        file_path=rel_path,
                                        line_number=stmt.lineno,
                                        module_name=f"from {stmt.module} import *",
                                        issue_type="wildcard",
                                        recommendation=f"Replace wildcard import 'from {stmt.module} import *' with explicit imports.",
                                    )
                                )
                            else:
                                track_name = alias.asname or alias.name
                                imports_in_file.append((track_name, stmt.lineno))

                    else:
                        is_docstring = isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
                        is_pass = isinstance(stmt, ast.Pass)
                        is_meta_assign = isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("__doc__", "__all__", "__version__") for t in stmt.targets)
                        if not (is_docstring or is_pass or is_meta_assign):
                            seen_non_import_statement = True

                # Check unused imports
                for imp_name, lineno in imports_in_file:
                    if (
                        imp_name not in file_identifiers
                        and imp_name not in export_all
                        and not imp_name.startswith("_")
                    ):
                        unused_count += 1
                        if len(issues) < 200:  # Cap details
                            issues.append(
                                ImportIssue(
                                    file_path=rel_path,
                                    line_number=lineno,
                                    module_name=imp_name,
                                    issue_type="unused",
                                    recommendation=f"Remove unreferenced import '{imp_name}'.",
                                )
                            )

        # Health score: 100 - (wildcard * 15) - (out_of_order * 2) - (unused / 20)
        score = max(0, min(100, int(100 - (wildcard_count * 15) - (out_of_order_count * 2) - (unused_count * 0.05))))

        lines_out = [
            "Import Hygiene Analysis",
            f"Total Imports Checked: {total_imports:,}",
            f"Wildcard Imports (import *): {wildcard_count}",
            f"Unused Imports: {unused_count}",
            f"Out-of-Order Imports: {out_of_order_count}",
            f"Import Hygiene Score: {score}/100",
        ]
        if wildcard_count > 0:
            lines_out.append("WARNING: Wildcard imports detected! Explicit imports recommended.")

        chatbox_report = "\n".join(lines_out)

        return ImportAnalysisReport(
            total_imports_checked=total_imports,
            wildcard_count=wildcard_count,
            unused_count=unused_count,
            out_of_order_count=out_of_order_count,
            issues=issues,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
