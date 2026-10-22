# plugins/code_assistant/analyzer.py
"""
Code Analysis Engine for the Jarvis Code Assistant Plugin.
Provides AST inspection, unused function scanning, dead code detection,
architecture validation, pytest runner, git change impact assessment, and error diagnosis.
"""

import ast
import logging
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    ArchitectureReport,
    ChangeImpactReport,
    CircularDependencyReport,
    ComplexityReport,
    ComprehensiveDeadCodeReport,
    ConfidenceTier,
    CoverageReport,
    DeadCodeItem,
    DeadSymbolItem,
    DependencyReport,
    DuplicationReport,
    ErrorFixSuggestion,
    FileAnalysisResult,
    ImportAnalysisReport,
    PerformanceReport,
    ProjectHealthReport,
    PytestResult,
    SecurityReport,
    SymbolType,
    UnusedFunctionInfo,
    UnusedFunctionsReport,
)

logger = logging.getLogger("jarvis.plugins.code_assistant.analyzer")


class CodeAnalysisEngine:
    """Authoritative static analysis and developer tooling engine."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self.ignored_dirs = {
            ".venv", "venv", "__pycache__", ".git", ".pytest_cache",
            "node_modules", "logs", "data", ".gemini", ".idea", ".vscode"
        }

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self.workspace_root, path))

    # =========================================================================
    # 1. Error Finding
    # =========================================================================
    def find_errors(
        self, query: Optional[str] = None, target_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Finds errors in logs, target file, or scans recent tracebacks."""
        errors_found: List[Dict[str, Any]] = []

        # 1. If target file specified, check AST syntax
        if target_file:
            resolved = self._resolve_path(target_file)
            if os.path.isfile(resolved):
                try:
                    with open(resolved, "r", encoding="utf-8", errors="ignore") as f:
                        source = f.read()
                    ast.parse(source, filename=resolved)
                except SyntaxError as e:
                    errors_found.append({
                        "source": "syntax_check",
                        "file": resolved,
                        "line": e.lineno,
                        "offset": e.offset,
                        "message": f"SyntaxError: {e.msg} at line {e.lineno}",
                        "snippet": e.text.strip() if e.text else "",
                    })
            else:
                return {
                    "success": False,
                    "error": f"File '{target_file}' nahi mila, Boss.",
                    "errors": [],
                }

        # 2. Scan logs/jarvis.log for recent tracebacks or exceptions
        log_path = os.path.join(self.workspace_root, "logs", "jarvis.log")
        if os.path.isfile(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-400:]  # Last 400 lines

                current_tb: List[str] = []
                in_tb = False

                for line in lines:
                    if "Traceback (most recent call last):" in line:
                        in_tb = True
                        current_tb = [line.strip()]
                    elif in_tb:
                        current_tb.append(line.strip())
                        if line and not line.startswith((" ", "File", "Traceback")):
                            # End of traceback (e.g. ValueError: ...)
                            in_tb = False
                            tb_text = "\n".join(current_tb)
                            if not query or query.lower() in tb_text.lower():
                                errors_found.append({
                                    "source": "runtime_log",
                                    "error_headline": line.strip(),
                                    "traceback": tb_text,
                                })
                            current_tb = []
                    elif " ERROR " in line or " CRITICAL " in line:
                        if not query or query.lower() in line.lower():
                            errors_found.append({
                                "source": "log_error",
                                "message": line.strip(),
                            })
            except Exception as e:
                logger.warning("Error reading logs: %s", e)

        # Build summary
        count = len(errors_found)
        if count == 0:
            summary = "Jarvis code aur logs mein koi critical error nahi mila, Boss. Sab clear hai!"
        else:
            latest = errors_found[-1]
            detail = latest.get("error_headline") or latest.get("message") or "Syntax error detected."
            summary = f"Jarvis code mein {count} potential errors mile. Latest error: {detail}"

        return {
            "success": True,
            "count": count,
            "errors": errors_found[-10:],  # return up to 10 latest
            "summary_message": summary,
        }

    # =========================================================================
    # 2. File Analysis
    # =========================================================================
    def analyze_file(self, file_path: str = "main.py") -> FileAnalysisResult:
        """Performs comprehensive AST and code metrics analysis on a python file."""
        resolved = self._resolve_path(file_path)
        if not os.path.isfile(resolved):
            return FileAnalysisResult(
                file_path=file_path,
                exists=False,
                summary_message=f"File '{file_path}' nahi mila, Boss.",
            )

        try:
            with open(resolved, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            total_lines = len(lines)
            code_lines = 0
            comment_lines = 0
            blank_lines = 0

            for line in lines:
                s = line.strip()
                if not s:
                    blank_lines += 1
                elif s.startswith("#"):
                    comment_lines += 1
                else:
                    code_lines += 1

            source = "".join(lines)
            try:
                tree = ast.parse(source, filename=resolved)
                syntax_valid = True
                syntax_error = None
            except SyntaxError as se:
                syntax_valid = False
                syntax_error = f"SyntaxError at line {se.lineno}: {se.msg}"
                tree = None

            functions: List[str] = []
            classes: List[str] = []
            imports: List[str] = []

            if tree:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(node.name)
                    elif isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        for alias in node.names:
                            imports.append(f"{mod}.{alias.name}" if mod else alias.name)

            summary = (
                f"'{os.path.basename(file_path)}' analysis completed, Boss: "
                f"{total_lines} lines ({code_lines} code, {comment_lines} comments, {blank_lines} blanks), "
                f"{len(classes)} classes, {len(functions)} functions, {len(imports)} imports. "
                f"Syntax {'valid' if syntax_valid else 'INVALID: ' + str(syntax_error)}."
            )

            return FileAnalysisResult(
                file_path=file_path,
                exists=True,
                total_lines=total_lines,
                code_lines=code_lines,
                comment_lines=comment_lines,
                blank_lines=blank_lines,
                function_count=len(functions),
                class_count=len(classes),
                import_count=len(imports),
                functions=functions,
                classes=classes,
                imports=imports,
                syntax_valid=syntax_valid,
                syntax_error=syntax_error,
                summary_message=summary,
            )
        except Exception as exc:
            return FileAnalysisResult(
                file_path=file_path,
                exists=True,
                syntax_valid=False,
                syntax_error=str(exc),
                summary_message=f"File analyze karte waqt error aaya: {exc}",
            )

    # =========================================================================
    # 3. Unused Functions Finder
    # =========================================================================
    def find_unused_functions(self, target_dir: str = ".") -> List[UnusedFunctionInfo]:
        """Scans codebase for defined functions that are never called or referenced."""
        resolved_root = self._resolve_path(target_dir)
        defined_functions: Dict[str, Tuple[str, int, bool, Optional[str]]] = {}
        all_identifiers: Set[str] = set()

        ignored_methods = {
            "__init__", "__str__", "__repr__", "__call__", "__enter__", "__exit__",
            "__eq__", "__hash__", "__len__", "__getitem__", "__setitem__",
            "get_manifest", "execute", "check_dependencies", "initialize", "shutdown",
            "verify_state", "safe_execute", "parse", "resolve", "route_intent", "run"
        }

        class _SymbolVisitor(ast.NodeVisitor):
            def __init__(self, is_test: bool):
                self.is_test = is_test
                self.current_class: Optional[str] = None
                self.local_functions: List[Tuple[str, int, bool, Optional[str]]] = []
                self.local_identifiers: Set[str] = set()
                self.total_functions_count: int = 0
                self.test_functions_count: int = 0
                self.public_api_count: int = 0

            def _is_interface_method(self, node: Any) -> bool:
                for dec in getattr(node, "decorator_list", []):
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    if dec_name in ("abstractmethod", "property", "setter", "deleter", "overload", "fixture", "hookimpl"):
                        return True
                return False

            def visit_Assign(self, node: ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    self.local_identifiers.add(elt.value)
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef):
                self.local_identifiers.add(node.name)
                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self.total_functions_count += 1
                fn = node.name
                if self.is_test or fn.startswith("pytest_") or fn.startswith("test_"):
                    self.test_functions_count += 1
                elif self._is_interface_method(node) or fn in ignored_methods:
                    self.public_api_count += 1
                else:
                    if not (fn.startswith("__") and fn.endswith("__")):
                        self.local_functions.append((fn, node.lineno, self.current_class is not None, self.current_class))
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self.total_functions_count += 1
                fn = node.name
                if self.is_test or fn.startswith("pytest_") or fn.startswith("test_"):
                    self.test_functions_count += 1
                elif self._is_interface_method(node) or fn in ignored_methods:
                    self.public_api_count += 1
                else:
                    if not (fn.startswith("__") and fn.endswith("__")):
                        self.local_functions.append((fn, node.lineno, self.current_class is not None, self.current_class))
                self.generic_visit(node)

            def visit_Name(self, node: ast.Name):
                self.local_identifiers.add(node.id)

            def visit_Attribute(self, node: ast.Attribute):
                self.local_identifiers.add(node.attr)
                self.generic_visit(node)

            def visit_Constant(self, node: ast.Constant):
                if isinstance(node.value, str) and len(node.value) < 60:
                    self.local_identifiers.add(node.value)

        # Step 1: Parse all files
        total_functions_analyzed = 0
        total_test_functions = 0
        total_public_api_functions = 0

        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py"):
                    continue

                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)
                is_test_file = f.startswith("test_") or f == "conftest.py" or "tests" in rel_path.split(os.sep)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=full_path)
                except Exception:
                    continue

                visitor = _SymbolVisitor(is_test=is_test_file)
                visitor.visit(tree)

                total_functions_analyzed += visitor.total_functions_count
                total_test_functions += visitor.test_functions_count
                total_public_api_functions += visitor.public_api_count
                all_identifiers.update(visitor.local_identifiers)

                if not is_test_file:
                    for fn_name, lineno, is_method, cls_name in visitor.local_functions:
                        defined_functions[f"{rel_path}:{fn_name}"] = (
                            rel_path, lineno, is_method, cls_name
                        )

        # Step 2: Cross reference references and categorize
        high_confidence_list: List[UnusedFunctionInfo] = []
        possibly_dynamic_list: List[UnusedFunctionInfo] = []
        context_plugin_list: List[UnusedFunctionInfo] = []
        top_level_list: List[UnusedFunctionInfo] = []
        class_methods_list: List[UnusedFunctionInfo] = []
        private_helpers_list: List[UnusedFunctionInfo] = []
        module_breakdown: Dict[str, int] = {}

        for key, (rel_path, lineno, is_method, cls_name) in defined_functions.items():
            fn_name = key.split(":")[-1]
            if fn_name not in all_identifiers:
                norm_path = rel_path.replace("\\", "/").lower()
                is_context_or_plugin = any(
                    k in norm_path for k in ["context", "plugin", "memory", "session", "dialog"]
                ) or (cls_name and any(k in cls_name.lower() for k in ["context", "tracker", "session", "plugin"]))

                is_parser_or_dynamic = (
                    fn_name.startswith("_")
                    or any(k in norm_path for k in ["parser", "handler", "nlu", "route", "evaluator"])
                )

                if fn_name.startswith("_") and not fn_name.startswith("__"):
                    cat = "private_helper"
                    conf = "MEDIUM"
                elif is_method:
                    cat = "class_method"
                    conf = "LOW"
                else:
                    cat = "top_level"
                    conf = "HIGH"

                sig = f"{cls_name}.{fn_name}" if cls_name else fn_name
                info = UnusedFunctionInfo(
                    name=fn_name,
                    file_path=rel_path,
                    line_number=lineno,
                    is_method=is_method,
                    class_name=cls_name,
                    category=cat,
                    confidence=conf,
                    full_signature=sig,
                )

                mod = rel_path.split(os.sep)[0]
                module_breakdown[mod] = module_breakdown.get(mod, 0) + 1

                if cat == "top_level":
                    top_level_list.append(info)
                elif cat == "class_method":
                    class_methods_list.append(info)
                else:
                    private_helpers_list.append(info)

                if is_context_or_plugin:
                    context_plugin_list.append(info)
                elif is_parser_or_dynamic or (is_method and cat == "class_method" and fn_name not in ("decompose_complex_task",)):
                    possibly_dynamic_list.append(info)
                else:
                    high_confidence_list.append(info)

        total_count = len(top_level_list) + len(class_methods_list) + len(private_helpers_list)
        high_conf_count = len(high_confidence_list)
        dynamic_count = len(possibly_dynamic_list) + len(context_plugin_list)

        # Build clean, human-friendly multi-line chatbox response
        lines = [
            "Codebase Analysis Complete",
            "",
            f"Total functions analyzed: {total_functions_analyzed:,}",
            "",
            f"Potentially unused: {total_count}",
            f"High-confidence dead code: {high_conf_count}",
            f"Possibly dynamic: {dynamic_count}",
            f"Public/API functions: {total_public_api_functions}",
            f"Test-only functions: {total_test_functions}",
        ]

        if total_count > 0:
            lines.extend(["", "Examples:"])
            if high_confidence_list:
                lines.extend(["", "HIGH CONFIDENCE"])
                for item in high_confidence_list[:2]:
                    lines.append(f"  {item.name}()")
                    lines.append(f"  {os.path.basename(item.file_path)}:{item.line_number}")
                    lines.append("")
                if lines[-1] == "":
                    lines.pop()

            if possibly_dynamic_list:
                lines.extend(["", "POSSIBLY DYNAMIC"])
                for item in possibly_dynamic_list[:2]:
                    lines.append(f"  {item.name}()")
                    lines.append(f"  {os.path.basename(item.file_path)}:{item.line_number}")
                    lines.append("")
                if lines[-1] == "":
                    lines.pop()

            if context_plugin_list:
                lines.extend(["", "CONTEXT/PLUGIN POSSIBLE"])
                for item in context_plugin_list[:2]:
                    lines.append(f"  {item.name}()")
                    lines.append(f"  {os.path.basename(item.file_path)}:{item.line_number}")
                    lines.append("")
                if lines[-1] == "":
                    lines.pop()

            lines.extend([
                "",
                "Recommendation:",
                "",
                f"{high_conf_count} functions are safe candidates for manual review.",
                "I will NOT delete anything automatically.",
            ])
        else:
            lines.extend([
                "",
                "Recommendation:",
                "",
                "All functions are actively connected in the codebase.",
                "I will NOT delete anything automatically.",
            ])

        formatted_report = "\n".join(lines)

        return UnusedFunctionsReport(
            total_count=total_count,
            top_level_count=len(top_level_list),
            class_methods_count=len(class_methods_list),
            private_helpers_count=len(private_helpers_list),
            top_level_functions=top_level_list,
            class_methods=class_methods_list,
            private_helpers=private_helpers_list,
            module_breakdown=module_breakdown,
            summary_message=formatted_report,
            total_functions_analyzed=total_functions_analyzed,
            high_confidence_count=high_conf_count,
            possibly_dynamic_count=dynamic_count,
            public_api_count=total_public_api_functions,
            test_only_count=total_test_functions,
            formatted_chatbox_report=formatted_report,
        )

    # =========================================================================
    # 4. Project Architecture Checker
    # =========================================================================
    def check_architecture(self) -> ArchitectureReport:
        """Validates project structure, SSOT adherence, and feature registry consistency."""
        core_pillars = ["core", "brain", "plugins", "memory", "learning"]
        presence = {}
        for p in core_pillars:
            path = os.path.join(self.workspace_root, p)
            presence[p] = os.path.isdir(path)

        ssot_violations: List[str] = []
        duplicate_modules: List[str] = []
        warnings: List[str] = []

        # Check SSOT violations (e.g. duplicate context or memory managers)
        suspect_patterns = [
            ("NewContextManager", "core/"),
            ("SmartContextManager", "core/"),
            ("DuplicateExecutor", "core/"),
        ]
        for term, search_dir in suspect_patterns:
            target = os.path.join(self.workspace_root, search_dir)
            if os.path.isdir(target):
                for r, _, fs in os.walk(target):
                    for f in fs:
                        if f.endswith(".py"):
                            fp = os.path.join(r, f)
                            try:
                                with open(fp, "r", encoding="utf-8", errors="ignore") as s:
                                    if term in s.read():
                                        ssot_violations.append(f"Found suspect class '{term}' in {f}")
                            except Exception:
                                pass

        # Check registry presence
        features_md = os.path.join(self.workspace_root, "docs", "FEATURES.md")
        features_json = os.path.join(self.workspace_root, "features_registry.json")
        registry_sync = os.path.isfile(features_md) or os.path.isfile(features_json)
        if not registry_sync:
            warnings.append("Features registry (docs/FEATURES.md or features_registry.json) missing!")

        # Check total python files
        total_py = 0
        for r, dirs, fs in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            total_py += sum(1 for f in fs if f.endswith(".py"))

        all_pillars_ok = all(presence.values())
        summary = (
            f"Architecture check: Core pillars ({', '.join(core_pillars)}) are "
            f"{'ALL INTACT' if all_pillars_ok else 'INCOMPLETE'}. "
            f"Scanned {total_py} Python files. "
            f"SSOT violations: {len(ssot_violations)}. Warnings: {len(warnings)}."
        )

        return ArchitectureReport(
            core_modules_present=presence,
            ssot_violations=ssot_violations,
            duplicate_modules=duplicate_modules,
            registry_synchronized=registry_sync,
            warnings=warnings,
            total_files_checked=total_py,
            summary_message=summary,
        )

    # =========================================================================
    # 5. Pytest Runner
    # =========================================================================
    def run_pytest(
        self, test_target: Optional[str] = None, timeout: int = 45
    ) -> PytestResult:
        """Safely executes pytest and parses results."""
        target = test_target or "tests/test_code_assistant_plugin.py"
        cmd = [sys.executable, "-m", "pytest", target, "-v"]

        try:
            res = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = res.stdout or ""
            stderr = res.stderr or ""
            output = stdout + "\n" + stderr

            # Parse outcomes
            passed = 0
            failed = 0
            errors = 0
            skipped = 0
            duration = 0.0

            m_passed = re.search(r"(\d+)\s+passed", output)
            if m_passed:
                passed = int(m_passed.group(1))

            m_failed = re.search(r"(\d+)\s+failed", output)
            if m_failed:
                failed = int(m_failed.group(1))

            m_errors = re.search(r"(\d+)\s+error", output)
            if m_errors:
                errors = int(m_errors.group(1))

            m_skipped = re.search(r"(\d+)\s+skipped", output)
            if m_skipped:
                skipped = int(m_skipped.group(1))

            m_dur = re.search(r"in\s+([\d\.]+)\s*s", output)
            if m_dur:
                duration = float(m_dur.group(1))

            total = passed + failed + errors + skipped
            success = res.returncode == 0

            summary = (
                f"Pytest run completed in {duration:.2f}s: {passed} passed, "
                f"{failed} failed, {errors} errors, {skipped} skipped. "
                f"Status: {'PASSED' if success else 'FAILED'}."
            )

            return PytestResult(
                command=" ".join(cmd),
                exit_code=res.returncode,
                total_tests=total,
                passed=passed,
                failed=failed,
                errors=errors,
                skipped=skipped,
                duration_seconds=duration,
                stdout_summary=output[-800:] if len(output) > 800 else output,
                success=success,
                summary_message=summary,
            )
        except subprocess.TimeoutExpired:
            return PytestResult(
                command=" ".join(cmd),
                exit_code=-1,
                success=False,
                summary_message=f"Pytest execution timed out after {timeout} seconds, Boss.",
            )
        except Exception as exc:
            return PytestResult(
                command=" ".join(cmd),
                exit_code=-1,
                success=False,
                summary_message=f"Pytest execute karne mein error aaya: {exc}",
            )

    # =========================================================================
    # 6. Error Fix Suggestion
    # =========================================================================
    def suggest_error_fix(
        self, error_text: Optional[str] = None, file_path: Optional[str] = None
    ) -> ErrorFixSuggestion:
        """Diagnoses error and suggests a surgical fix and diff."""
        if not error_text:
            # Check latest error in logs
            errors = self.find_errors()
            if errors["errors"]:
                latest = errors["errors"][-1]
                error_text = latest.get("traceback") or latest.get("message") or latest.get("error_headline")
            else:
                error_text = "No active error found."

        # Parse error type and message
        m_err = re.search(r"([A-Za-z0-9_]+Error|Exception):\s*(.*)", error_text)
        err_type = m_err.group(1) if m_err else "RuntimeError"
        err_msg = m_err.group(2) if m_err else error_text[:120]

        # Extract target file & line if in traceback
        m_file = re.search(r'File "([^"]+)", line (\d+)', error_text)
        target_f = m_file.group(1) if m_file else file_path
        target_l = int(m_file.group(2)) if m_file else None

        # Build surgical fix advice
        root_cause = ""
        suggested_fix = ""
        diff = ""

        if "ModuleNotFoundError" in err_type or "ImportError" in err_type:
            root_cause = f"Module ya import dependency missing hai: {err_msg}"
            suggested_fix = "Module ko install karein (`pip install`) ya relative import path check karein."
        elif "AttributeError" in err_type:
            root_cause = f"Object par requested attribute/method exist nahi karta: {err_msg}"
            suggested_fix = "Attribute name spelling check karein ya `hasattr()` ya optional chaining use karein."
        elif "KeyError" in err_type:
            root_cause = f"Dictionary key missing hai: {err_msg}"
            suggested_fix = "Direct key access `d[k]` ki jagah `d.get(k, default)` use karein."
        elif "TypeError" in err_type:
            root_cause = f"Function arguments ya data type mismatch: {err_msg}"
            suggested_fix = "Function signature aur argument types check karein."
        elif "SyntaxError" in err_type:
            root_cause = f"Python syntax rule violation: {err_msg}"
            suggested_fix = "Line ke end par colon, unclosed parentheses, ya indentation check karein."
        else:
            root_cause = f"Exception encountered: {err_msg}"
            suggested_fix = "Traceback ko trace karein aur input parameters validate karein."

        diff = (
            f"--- a/{target_f or 'target.py'}\n"
            f"+++ b/{target_f or 'target.py'}\n"
            f"@@ -{target_l or 1},1 +{target_l or 1},1 @@\n"
            f"- # Suspect line causing {err_type}\n"
            f"+ # Recommended: {suggested_fix}\n"
        )

        summary = (
            f"Error Fix Suggestion for {err_type}: Root cause: {root_cause}. "
            f"Recommended Fix: {suggested_fix}"
        )

        return ErrorFixSuggestion(
            error_type=err_type,
            error_message=err_msg,
            target_file=target_f,
            target_line=target_l,
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            diff=diff,
            patch_applied=False,
            summary_message=summary,
        )

    # =========================================================================
    # 7. Git Change Impact Assessment
    # =========================================================================
    def analyze_change_impact(self) -> ChangeImpactReport:
        """Analyzes git status/diff, determines modified components, and assigns Risk Tier."""
        modified_files: List[str] = []
        untracked_files: List[str] = []
        affected_components: Set[str] = set()

        try:
            # 1. git status
            st_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in (st_res.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                status_code = line[:2]
                file_name = line[3:].strip()
                if status_code.startswith("??"):
                    untracked_files.append(file_name)
                else:
                    modified_files.append(file_name)

            # 2. If no working tree changes, check last commit
            if not modified_files:
                diff_res = subprocess.run(
                    ["git", "diff", "HEAD~1", "--name-only"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for line in (diff_res.stdout or "").splitlines():
                    f = line.strip()
                    if f:
                        modified_files.append(f)

            # 3. Classify affected components
            for f in modified_files + untracked_files:
                if f.startswith("core/router") or f.startswith("core/intent") or "semantic_executor" in f:
                    affected_components.add("router_and_execution")
                elif f.startswith("core/"):
                    affected_components.add("core_subsystem")
                elif f.startswith("plugins/"):
                    parts = f.split("/")
                    plugin_name = parts[1] if len(parts) > 1 else "plugin"
                    affected_components.add(f"plugin_{plugin_name}")
                elif f.startswith("brain/"):
                    affected_components.add("brain_nlu")
                elif f.startswith("memory/"):
                    affected_components.add("memory_system")
                elif f.startswith("tests/"):
                    affected_components.add("test_suite")

            # 4. Determine Risk Tier according to AGENTS.md §7
            risk_tier = "LOW"
            rationale = "Localized changes with minimal side effects."
            if "router_and_execution" in affected_components:
                risk_tier = "HIGH"
                rationale = "Shared routing and execution layer modified; high regression risk."
            elif "core_subsystem" in affected_components or "brain_nlu" in affected_components:
                risk_tier = "MEDIUM"
                rationale = "Core or brain components modified; regression testing required."

            # 5. Recommend tests
            recommended_tests = []
            if "router_and_execution" in affected_components:
                recommended_tests.extend([
                    "tests/test_universal_verification_layer.py",
                    "tests/test_conversational_response_policy.py"
                ])
            if any(c.startswith("plugin_") for c in affected_components):
                recommended_tests.append("tests/test_plugins_advanced.py")
            recommended_tests.append("tests/test_code_assistant_plugin.py")

            summary = (
                f"Change Impact Analysis: {len(modified_files)} modified, {len(untracked_files)} untracked. "
                f"Risk Tier: {risk_tier} ({rationale}). "
                f"Recommended test run: {', '.join(recommended_tests[:2])}."
            )

            return ChangeImpactReport(
                modified_files=modified_files,
                untracked_files=untracked_files,
                affected_components=sorted(list(affected_components)),
                risk_tier=risk_tier,
                risk_rationale=rationale,
                recommended_tests=recommended_tests,
                summary_message=summary,
            )
        except Exception as exc:
            return ChangeImpactReport(
                summary_message=f"Change impact analyze karne mein error: {exc}"
            )

    # =========================================================================
    # 8. Dead Code Finder
    # =========================================================================
    def find_dead_code(self, target_dir: str = ".") -> List[DeadCodeItem]:
        """Detects unreachable code blocks (after return/raise/break) and unused imports."""
        resolved_root = self._resolve_path(target_dir)
        dead_items: List[DeadCodeItem] = []

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

                # Check for unreachable statements in functions/blocks
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        terminated = False
                        for stmt in node.body:
                            if terminated:
                                dead_items.append(
                                    DeadCodeItem(
                                        file_path=rel_path,
                                        line_number=stmt.lineno,
                                        item_type="unreachable_code",
                                        description=f"Unreachable code after terminal statement in function '{node.name}'",
                                    )
                                )
                                break
                            if isinstance(stmt, (ast.Return, ast.Raise)):
                                terminated = True

        return dead_items

    # =========================================================================
    # 9. Comprehensive Multi-Symbol Dead Code Analyzer (11 Categories)
    # =========================================================================
    def analyze_all_dead_code(self, target_dir: str = ".") -> ComprehensiveDeadCodeReport:
        """
        Comprehensive multi-symbol dead code analyzer covering 11 symbol categories:
        FUNCTION, CLASS, METHOD, IMPORT, VARIABLE, MODULE, PLUGIN, ROUTE,
        CLI_COMMAND, EVENT_HANDLER, DECORATOR.
        Categorizes findings into 4 strict confidence tiers (95-100%, 80-94%, 50-79%, <50%).
        """
        resolved_root = self._resolve_path(target_dir)
        ignored_names = {
            "__init__", "__str__", "__repr__", "__call__", "__enter__", "__exit__",
            "__eq__", "__hash__", "__len__", "__getitem__", "__setitem__",
            "get_manifest", "execute", "check_dependencies", "initialize", "shutdown",
            "verify_state", "safe_execute", "parse", "resolve", "route_intent", "run"
        }

        all_workspace_identifiers: Set[str] = set()
        all_imported_modules: Set[str] = set()
        all_emitted_events: Set[str] = set()
        all_decorators_used: Set[str] = set()
        all_workspace_files: List[str] = []

        # Intermediate file records
        file_data: Dict[str, Dict[str, Any]] = {}
        total_symbols_analyzed = 0

        class _ComprehensiveVisitor(ast.NodeVisitor):
            def __init__(self, is_test: bool):
                self.is_test = is_test
                self.current_class: Optional[str] = None
                self.imports: List[Tuple[str, int]] = []
                self.assigned_vars: List[Tuple[str, int]] = []
                self.defined_classes: List[Tuple[str, int]] = []
                self.defined_functions: List[Tuple[str, int, bool, Optional[str]]] = []
                self.unreachable_blocks: List[Tuple[int, str]] = []
                self.decorators_defined: List[Tuple[str, int]] = []
                self.event_subscriptions: List[Tuple[str, int]] = []
                self.file_identifiers: Set[str] = set()
                self.export_all: Set[str] = set()
                self.symbols_count = 0

            def visit_Import(self, node: ast.Import):
                for alias in node.names:
                    self.symbols_count += 1
                    name_to_track = alias.asname or alias.name.split(".")[0]
                    self.imports.append((name_to_track, node.lineno))
                    all_imported_modules.add(alias.name.split(".")[0])
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom):
                if node.module:
                    all_imported_modules.add(node.module.split(".")[0])
                for alias in node.names:
                    self.symbols_count += 1
                    if alias.name == "*":
                        continue
                    name_to_track = alias.asname or alias.name
                    self.imports.append((name_to_track, node.lineno))
                self.generic_visit(node)

            def visit_Assign(self, node: ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "__all__":
                            if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                        self.export_all.add(elt.value)
                                        self.file_identifiers.add(elt.value)
                        elif self.current_class is None:  # module level
                            self.symbols_count += 1
                            self.assigned_vars.append((target.id, node.lineno))
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef):
                self.symbols_count += 1
                self.defined_classes.append((node.name, node.lineno))
                self.file_identifiers.add(node.name)
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        all_decorators_used.add(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        all_decorators_used.add(dec.attr)
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            all_decorators_used.add(dec.func.id)
                        elif isinstance(dec.func, ast.Attribute):
                            all_decorators_used.add(dec.func.attr)

                prev = self.current_class
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = prev

            def _handle_func_def(self, node: Any):
                self.symbols_count += 1
                is_method = self.current_class is not None
                fn_name = node.name
                self.defined_functions.append((fn_name, node.lineno, is_method, self.current_class))

                # Check if this function defines a decorator (accepts func as first arg or wraps)
                if any(arg.arg in ("func", "fn", "target", "f") for arg in getattr(node.args, "args", [])):
                    self.decorators_defined.append((fn_name, node.lineno))

                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        all_decorators_used.add(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        all_decorators_used.add(dec.attr)
                    elif isinstance(dec, ast.Call):
                        if isinstance(dec.func, ast.Name):
                            all_decorators_used.add(dec.func.id)
                        elif isinstance(dec.func, ast.Attribute):
                            all_decorators_used.add(dec.func.attr)

                # Check unreachable code
                terminated = False
                for stmt in node.body:
                    if terminated:
                        self.unreachable_blocks.append(
                            (stmt.lineno, f"Unreachable statement after terminal statement in '{fn_name}'")
                        )
                        break
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        terminated = True

            def visit_FunctionDef(self, node: ast.FunctionDef):
                self._handle_func_def(node)
                self.generic_visit(node)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                self._handle_func_def(node)
                self.generic_visit(node)

            def visit_Call(self, node: ast.Call):
                # Detect EventBus calls
                fn_name = ""
                if isinstance(node.func, ast.Attribute):
                    fn_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    fn_name = node.func.id

                if fn_name in ("emit", "publish") and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        all_emitted_events.add(node.args[0].value)
                elif fn_name in ("subscribe", "listen", "on") and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        self.event_subscriptions.append((node.args[0].value, node.lineno))

                self.generic_visit(node)

            def visit_Name(self, node: ast.Name):
                self.file_identifiers.add(node.id)
                self.generic_visit(node)

            def visit_Attribute(self, node: ast.Attribute):
                self.file_identifiers.add(node.attr)
                self.generic_visit(node)

            def visit_Constant(self, node: ast.Constant):
                if isinstance(node.value, str) and len(node.value) < 60:
                    self.file_identifiers.add(node.value)

        # Step 1: Scan all files
        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py"):
                    continue

                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)
                all_workspace_files.append(rel_path)
                is_test = f.startswith("test_") or "tests" in rel_path.split(os.sep)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=full_path)
                except Exception:
                    continue

                visitor = _ComprehensiveVisitor(is_test=is_test)
                visitor.visit(tree)

                total_symbols_analyzed += visitor.symbols_count
                all_workspace_identifiers.update(visitor.file_identifiers)
                file_data[rel_path] = {
                    "is_test": is_test,
                    "imports": visitor.imports,
                    "assigned_vars": visitor.assigned_vars,
                    "defined_classes": visitor.defined_classes,
                    "defined_functions": visitor.defined_functions,
                    "unreachable_blocks": visitor.unreachable_blocks,
                    "decorators_defined": visitor.decorators_defined,
                    "event_subscriptions": visitor.event_subscriptions,
                    "file_identifiers": visitor.file_identifiers,
                    "export_all": visitor.export_all,
                }

        # Step 2: Cross-reference across 11 Symbol Categories
        dead_symbols: List[DeadSymbolItem] = []

        for rel_path, data in file_data.items():
            if data["is_test"]:
                continue

            # 1. Unreachable blocks (FUNCTION / unreachable code)
            for lineno, desc in data["unreachable_blocks"]:
                dead_symbols.append(
                    DeadSymbolItem(
                        name="unreachable_block",
                        file_path=rel_path,
                        line_number=lineno,
                        symbol_type=SymbolType.FUNCTION,
                        confidence_pct=100,
                        confidence_tier=ConfidenceTier.VERY_LIKELY_DEAD,
                        rationale=desc,
                    )
                )

            # 2. Unused Imports (IMPORT)
            for imp_name, lineno in data["imports"]:
                if (
                    imp_name not in data["file_identifiers"]
                    and imp_name not in data["export_all"]
                    and not imp_name.startswith("_")
                ):
                    dead_symbols.append(
                        DeadSymbolItem(
                            name=imp_name,
                            file_path=rel_path,
                            line_number=lineno,
                            symbol_type=SymbolType.IMPORT,
                            confidence_pct=96,
                            confidence_tier=ConfidenceTier.VERY_LIKELY_DEAD,
                            rationale=f"Imported symbol '{imp_name}' is never referenced in '{rel_path}' body.",
                        )
                    )

            # 3. Unused Module Variables (VARIABLE)
            for var_name, lineno in data["assigned_vars"]:
                if (
                    var_name not in data["export_all"]
                    and var_name not in all_workspace_identifiers
                    and not var_name.startswith("_")
                    and not var_name.isupper()
                ):
                    dead_symbols.append(
                        DeadSymbolItem(
                            name=var_name,
                            file_path=rel_path,
                            line_number=lineno,
                            symbol_type=SymbolType.VARIABLE,
                            confidence_pct=85,
                            confidence_tier=ConfidenceTier.PROBABLY_UNUSED,
                            rationale=f"Module variable '{var_name}' is assigned but unreferenced across codebase.",
                        )
                    )

            # 4. Unused Classes (CLASS)
            for cls_name, lineno in data["defined_classes"]:
                if (
                    cls_name not in all_workspace_identifiers
                    and cls_name not in data["export_all"]
                    and not cls_name.startswith("_")
                ):
                    dead_symbols.append(
                        DeadSymbolItem(
                            name=cls_name,
                            file_path=rel_path,
                            line_number=lineno,
                            symbol_type=SymbolType.CLASS,
                            confidence_pct=88,
                            confidence_tier=ConfidenceTier.PROBABLY_UNUSED,
                            rationale=f"Class '{cls_name}' is defined but has zero references across workspace.",
                        )
                    )

            # 5. Functions & Methods (FUNCTION, METHOD)
            for fn_name, lineno, is_method, cls_name in data["defined_functions"]:
                if (
                    fn_name not in all_workspace_identifiers
                    and fn_name not in data["export_all"]
                    and not (fn_name.startswith("__") and fn_name.endswith("__"))
                    and fn_name not in ignored_names
                ):
                    if is_method:
                        dead_symbols.append(
                            DeadSymbolItem(
                                name=f"{cls_name}.{fn_name}" if cls_name else fn_name,
                                file_path=rel_path,
                                line_number=lineno,
                                symbol_type=SymbolType.METHOD,
                                confidence_pct=65,
                                confidence_tier=ConfidenceTier.NEEDS_REVIEW,
                                rationale="Class method has no direct calls; may be invoked dynamically or via interface.",
                            )
                        )
                    elif not fn_name.startswith("_"):
                        dead_symbols.append(
                            DeadSymbolItem(
                                name=fn_name,
                                file_path=rel_path,
                                line_number=lineno,
                                symbol_type=SymbolType.FUNCTION,
                                confidence_pct=95,
                                confidence_tier=ConfidenceTier.VERY_LIKELY_DEAD,
                                rationale="Standalone top-level function is never called or referenced.",
                            )
                        )
                    else:
                        dead_symbols.append(
                            DeadSymbolItem(
                                name=fn_name,
                                file_path=rel_path,
                                line_number=lineno,
                                symbol_type=SymbolType.FUNCTION,
                                confidence_pct=55,
                                confidence_tier=ConfidenceTier.NEEDS_REVIEW,
                                rationale="Private helper function has no local references in file.",
                            )
                        )

            # 6. Unused Custom Decorators (DECORATOR)
            for deco_name, lineno in data["decorators_defined"]:
                if deco_name not in all_decorators_used and deco_name not in all_workspace_identifiers:
                    dead_symbols.append(
                        DeadSymbolItem(
                            name=deco_name,
                            file_path=rel_path,
                            line_number=lineno,
                            symbol_type=SymbolType.DECORATOR,
                            confidence_pct=82,
                            confidence_tier=ConfidenceTier.PROBABLY_UNUSED,
                            rationale=f"Decorator '@{deco_name}' is defined but never applied to functions/classes.",
                        )
                    )

            # 7. Unmatched Event Handlers (EVENT_HANDLER)
            for topic, lineno in data["event_subscriptions"]:
                if topic not in all_emitted_events:
                    dead_symbols.append(
                        DeadSymbolItem(
                            name=topic,
                            file_path=rel_path,
                            line_number=lineno,
                            symbol_type=SymbolType.EVENT_HANDLER,
                            confidence_pct=72,
                            confidence_tier=ConfidenceTier.NEEDS_REVIEW,
                            rationale=f"Event handler listens for '{topic}', but matching event is never emitted.",
                        )
                    )

        # 8. Unreferenced Modules (MODULE)
        for rel_f in all_workspace_files:
            base = os.path.basename(rel_f)
            mod_name, _ = os.path.splitext(base)
            if (
                base not in ("main.py", "conftest.py", "setup.py", "__init__.py")
                and not base.startswith("test_")
                and "plugins" not in rel_f
                and mod_name not in all_imported_modules
                and mod_name not in all_workspace_identifiers
            ):
                dead_symbols.append(
                    DeadSymbolItem(
                        name=mod_name,
                        file_path=rel_f,
                        line_number=1,
                        symbol_type=SymbolType.MODULE,
                        confidence_pct=84,
                        confidence_tier=ConfidenceTier.PROBABLY_UNUSED,
                        rationale=f"Module file '{base}' appears to have zero imports across workspace.",
                    )
                )

        # Step 3: Group & Calculate Metrics
        by_symbol_type: Dict[str, int] = {}
        v_dead = 0
        p_unused = 0
        n_review = 0
        p_dynamic = 0

        for sym in dead_symbols:
            stype = sym.symbol_type.value if hasattr(sym.symbol_type, "value") else str(sym.symbol_type)
            by_symbol_type[stype] = by_symbol_type.get(stype, 0) + 1

            if sym.confidence_tier == ConfidenceTier.VERY_LIKELY_DEAD:
                v_dead += 1
            elif sym.confidence_tier == ConfidenceTier.PROBABLY_UNUSED:
                p_unused += 1
            elif sym.confidence_tier == ConfidenceTier.NEEDS_REVIEW:
                n_review += 1
            else:
                p_dynamic += 1

        total_dead = len(dead_symbols)

        # Step 4: Build Formatted Chatbox Report
        lines = [
            "Comprehensive Dead Code Analysis Complete",
            "",
            f"Total symbols analyzed: {total_symbols_analyzed:,}",
            f"Potentially unused symbols: {total_dead}",
            "",
            "Confidence Breakdown:",
            f"  Very Likely Dead (95-100%): {v_dead}",
            f"  Probably Unused (80-94%):   {p_unused}",
            f"  Needs Review (50-79%):      {n_review}",
            f"  Possibly Dynamic (<50%):    {p_dynamic}",
            "",
            "Symbol Types Detected:",
        ]
        for st, cnt in sorted(by_symbol_type.items()):
            lines.append(f"  {st.capitalize()}s: {cnt}")

        if total_dead > 0:
            lines.extend(["", "Top High-Confidence Candidates:"])
            high_candidates = [s for s in dead_symbols if s.confidence_pct >= 95][:4]
            for s in high_candidates:
                lines.append(f"  [{s.symbol_type.value}] {s.name}")
                lines.append(f"    {os.path.basename(s.file_path)}:{s.line_number} (Confidence: {s.confidence_pct}%)")

            lines.extend([
                "",
                "Recommendation:",
                f"{v_dead} symbols are high-confidence candidates for safe manual review.",
                "Automatic deletion is strictly guarded; no code has been modified.",
            ])
        else:
            lines.extend([
                "",
                "Recommendation:",
                "Zero dead code detected. All symbols are actively connected.",
            ])

        chatbox_report = "\n".join(lines)

        return ComprehensiveDeadCodeReport(
            total_symbols_analyzed=total_symbols_analyzed,
            potentially_unused_count=total_dead,
            very_likely_dead_count=v_dead,
            probably_unused_count=p_unused,
            needs_review_count=n_review,
            possibly_dynamic_count=p_dynamic,
            by_symbol_type=by_symbol_type,
            symbols=dead_symbols,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )

    # =========================================================================
    # 10. Code Intelligence & Holistic Project Health Audit
    # =========================================================================
    def run_health_audit(self, target_dir: str = ".") -> ProjectHealthReport:
        """Executes holistic 10-pillar code health audit across the project."""
        from .analyzers.health_audit import HealthAuditEngine
        engine = HealthAuditEngine(self.workspace_root)
        return engine.run_audit(target_dir=target_dir)

    def analyze_dependencies(self) -> DependencyReport:
        """Analyzes requirements.txt against active environment packages."""
        from .analyzers.dependency import DependencyAnalyzer
        analyzer = DependencyAnalyzer(self.workspace_root)
        return analyzer.analyze()

    def analyze_imports(self, target_dir: str = ".") -> ImportAnalysisReport:
        """Analyzes import hygiene, wildcards, and out-of-order imports."""
        from .analyzers.imports import ImportAnalyzer
        analyzer = ImportAnalyzer(self.workspace_root, ignored_dirs=self.ignored_dirs)
        return analyzer.analyze(target_dir=target_dir)

    def detect_duplication(self, target_dir: str = ".") -> DuplicationReport:
        """Detects duplicated logic blocks and repeated function bodies."""
        from .analyzers.duplication import DuplicateCodeDetector
        detector = DuplicateCodeDetector(self.workspace_root)
        return detector.analyze(target_dir=target_dir)

    def analyze_complexity(self, target_dir: str = ".") -> ComplexityReport:
        """Calculates cyclomatic and cognitive complexity metrics."""
        from .analyzers.complexity import ComplexityAnalyzer
        analyzer = ComplexityAnalyzer(self.workspace_root)
        return analyzer.analyze(target_dir=target_dir)

    def detect_circular_dependencies(self, target_dir: str = ".") -> CircularDependencyReport:
        """Detects circular import dependency cycles across internal modules."""
        from .analyzers.circular import CircularDependencyDetector
        detector = CircularDependencyDetector(self.workspace_root)
        return detector.analyze(target_dir=target_dir)

    def scan_security(self, target_dir: str = ".") -> SecurityReport:
        """Scans for static vulnerabilities, eval/exec, shell=True, and secrets."""
        from .analyzers.security import SecurityScanner
        scanner = SecurityScanner(self.workspace_root)
        return scanner.analyze(target_dir=target_dir)

    def analyze_performance(self, target_dir: str = ".") -> PerformanceReport:
        """Detects blocking async calls, uncompiled regex in loops, and I/O risks."""
        from .analyzers.performance import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer(self.workspace_root)
        return analyzer.analyze(target_dir=target_dir)

    def analyze_coverage(self, target_dir: str = ".") -> CoverageReport:
        """Maps project source modules to test suites and evaluates test coverage."""
        from .analyzers.coverage import CoverageAnalyzer
        analyzer = CoverageAnalyzer(self.workspace_root)
        return analyzer.analyze(target_dir=target_dir)

