# plugins/code_assistant/analyzers/circular.py
"""
Circular Dependency Detector for the Jarvis Code Intelligence System.
Builds internal module import graphs and uses cycle detection algorithms (DFS)
to identify circular import loops that cause silent runtime initialization errors.
"""

import ast
import os
from typing import Dict, List, Set

from ..models import CircularDependencyCycle, CircularDependencyReport


class CircularDependencyDetector:
    """Constructs module dependency graphs and finds circular dependency cycles."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def _file_to_module_name(self, rel_path: str) -> str:
        clean = rel_path.replace("\\", "/").replace(".py", "")
        if clean.endswith("/__init__"):
            clean = clean[:-9]
        return clean.replace("/", ".")

    def analyze(self, target_dir: str = ".") -> CircularDependencyReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        graph: Dict[str, Set[str]] = {}

        # 1. Build import graph for internal modules
        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py") or f.startswith("test_"):
                    continue

                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)
                mod_name = self._file_to_module_name(rel_path)
                graph[mod_name] = set()

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                    tree = ast.parse(content, filename=full_path)
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            graph[mod_name].add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            graph[mod_name].add(node.module)

        # 2. Filter graph to internal modules only
        internal_modules = set(graph.keys())
        filtered_graph: Dict[str, Set[str]] = {}
        for mod, targets in graph.items():
            filtered_graph[mod] = set()
            for tgt in targets:
                if tgt in internal_modules:
                    filtered_graph[mod].add(tgt)
                else:
                    parts = tgt.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        parent = ".".join(parts[:i])
                        if parent in internal_modules:
                            filtered_graph[mod].add(parent)
                            break

        # 3. Detect cycles using DFS
        visited: Set[str] = set()
        rec_stack: List[str] = []
        raw_cycles: List[List[str]] = []

        def dfs(node: str):
            visited.add(node)
            rec_stack.append(node)

            for neighbor in filtered_graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    idx = rec_stack.index(neighbor)
                    cycle = rec_stack[idx:] + [neighbor]
                    raw_cycles.append(cycle)

            rec_stack.pop()

        for mod in list(filtered_graph.keys()):
            if mod not in visited:
                dfs(mod)

        # Deduplicate cycles
        unique_cycles: List[CircularDependencyCycle] = []
        seen_cycle_keys: Set[str] = set()
        for c in raw_cycles:
            norm_cycle = tuple(sorted(set(c)))
            key = ",".join(norm_cycle)
            if key not in seen_cycle_keys and len(c) > 2:
                seen_cycle_keys.add(key)
                unique_cycles.append(CircularDependencyCycle(cycle_path=c, cycle_length=len(c) - 1))

        cycles_count = len(unique_cycles)
        score = max(0, min(100, 100 - (cycles_count * 25)))

        lines_out = [
            "Circular Dependency Detection",
            f"Internal Modules Analyzed: {len(filtered_graph)}",
            f"Circular Import Cycles Found: {cycles_count}",
            f"Dependency Graph Score: {score}/100",
        ]
        if cycles_count > 0:
            lines_out.append("Detected Cycles:")
            for cyc in unique_cycles[:3]:
                lines_out.append("  " + " -> ".join(cyc.cycle_path))
        else:
            lines_out.append("No circular dependency loops detected. Clean acyclic import hierarchy.")

        chatbox_report = "\n".join(lines_out)

        return CircularDependencyReport(
            total_modules_analyzed=len(filtered_graph),
            cycles_found=cycles_count,
            cycles=unique_cycles,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
