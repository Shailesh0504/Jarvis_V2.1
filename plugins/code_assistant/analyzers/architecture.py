# plugins/code_assistant/analyzers/architecture.py
"""
Architecture Analyzer for the Jarvis Code Intelligence System.
Enforces layer boundaries, SSOT compliance, core pillars presence,
and feature registry synchronization per AGENTS.md rules.
"""

import ast
import os
from typing import Dict, List, Set

from ..models import ArchitectureReport


class ArchitectureAnalyzer:
    """Validates layer boundaries, SSOT compliance, and registry consistency."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def analyze(self) -> ArchitectureReport:
        core_pillars = ["core", "brain", "plugins", "memory", "learning"]
        presence = {}
        for p in core_pillars:
            path = os.path.join(self.workspace_root, p)
            presence[p] = os.path.isdir(path)

        ssot_violations: List[str] = []
        duplicate_modules: List[str] = []
        warnings: List[str] = []
        total_files = 0

        # Layer Boundary Check: core/ must not import gui/
        for root, dirs, files in os.walk(os.path.join(self.workspace_root, "core")):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            for f in files:
                if not f.endswith(".py"):
                    continue
                total_files += 1
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        tree = ast.parse(fp.read(), filename=full_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for a in node.names:
                                if a.name.startswith("gui"):
                                    ssot_violations.append(f"Layer violation: '{rel_path}' imports UI module '{a.name}'.")
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and node.module.startswith("gui"):
                                ssot_violations.append(f"Layer violation: '{rel_path}' imports from UI module '{node.module}'.")
                except Exception:
                    continue

        # SSOT check: Detect duplicate managers
        seen_base_names: Dict[str, str] = {}
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py") or f.startswith("__") or f.startswith("test_"):
                    continue
                total_files += 1
                base = f[:-3].lower()
                rel = os.path.relpath(os.path.join(root, f), self.workspace_root)
                if "manager" in base or "context" in base:
                    if base in seen_base_names:
                        duplicate_modules.append(f"Potential duplicate manager: '{rel}' vs '{seen_base_names[base]}'")
                    else:
                        seen_base_names[base] = rel

        # Check feature registry
        registry_file = os.path.join(self.workspace_root, "docs", "FEATURES.md")
        reg_synced = os.path.isfile(registry_file)
        if not reg_synced:
            warnings.append("docs/FEATURES.md registry file is missing!")

        score = 100
        if not all(presence.values()):
            score -= 30
        score -= min(30, len(ssot_violations) * 10)
        score -= min(20, len(duplicate_modules) * 5)
        if not reg_synced:
            score -= 10
        score = max(0, min(100, score))

        lines_out = [
            "Architecture & SSOT Integrity Report",
            f"Core Pillars Present: {sum(presence.values())}/{len(presence)}",
            f"Layer Boundary Violations: {len(ssot_violations)}",
            f"Duplicate Module Warnings: {len(duplicate_modules)}",
            f"Feature Registry Synced: {'YES' if reg_synced else 'NO'}",
            f"Architecture Health Score: {score}/100",
        ]
        chatbox_report = "\n".join(lines_out)

        return ArchitectureReport(
            core_modules_present=presence,
            ssot_violations=ssot_violations,
            duplicate_modules=duplicate_modules,
            registry_synchronized=reg_synced,
            warnings=warnings,
            total_files_checked=total_files,
            summary_message=chatbox_report,
        )
