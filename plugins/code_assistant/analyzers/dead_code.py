# plugins/code_assistant/analyzers/dead_code.py
"""
Dead Code Analyzer for the Jarvis Code Intelligence System.
Detects uncalled functions, unused imports, unreachable code blocks,
and dead symbols across 11 symbol categories with 4 confidence tiers.
"""

import ast
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models import (
    ComprehensiveDeadCodeReport,
    ConfidenceTier,
    DeadCodeItem,
    DeadSymbolItem,
    SymbolType,
    UnusedFunctionInfo,
    UnusedFunctionsReport,
)


class DeadCodeAnalyzer:
    """Detects unreferenced functions, unreachable blocks, and dead symbols."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }
        self.ignored_names = {
            "__init__", "__str__", "__repr__", "__call__", "__enter__", "__exit__",
            "__eq__", "__hash__", "__len__", "__getitem__", "__setitem__",
            "get_manifest", "execute", "check_dependencies", "initialize", "shutdown",
            "verify_state", "safe_execute", "parse", "resolve", "route_intent", "run"
        }

    def find_unused_functions(self, target_dir: str = ".") -> UnusedFunctionsReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        defined_functions: Dict[str, Tuple[str, int, bool, Optional[str]]] = {}
        all_identifiers: Set[str] = set()

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
                elif self._is_interface_method(node) or fn in self.ignored_names:
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
                elif self._is_interface_method(node) or fn in self.ignored_names:
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

        _SymbolVisitor.ignored_names = self.ignored_names

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

    def analyze_all_dead_code(self, target_dir: str = ".") -> ComprehensiveDeadCodeReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        all_workspace_identifiers: Set[str] = set()
        all_imported_modules: Set[str] = set()
        all_emitted_events: Set[str] = set()
        all_decorators_used: Set[str] = set()
        all_workspace_files: List[str] = []

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
                        elif self.current_class is None:
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

        dead_symbols: List[DeadSymbolItem] = []

        for rel_path, data in file_data.items():
            if data["is_test"]:
                continue

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

            for fn_name, lineno, is_method, cls_name in data["defined_functions"]:
                if (
                    fn_name not in all_workspace_identifiers
                    and fn_name not in data["export_all"]
                    and not (fn_name.startswith("__") and fn_name.endswith("__"))
                    and fn_name not in self.ignored_names
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
