# plugins/code_assistant/analyzers/duplication.py
"""
Duplicate Code Detector for the Jarvis Code Intelligence System.
Uses AST structure hashing and normalized statement sequences to detect repeated
code blocks and duplicate logic across files.
"""

import ast
import hashlib
import os
from typing import Dict, List, Optional, Set, Tuple

from ..models import DuplicateBlock, DuplicationReport


class DuplicateCodeDetector:
    """Detects duplicated code blocks and functions across the codebase."""

    def __init__(self, workspace_root: str, min_lines: int = 6):
        self.workspace_root = workspace_root
        self.min_lines = min_lines
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def _hash_ast_node(self, node: ast.AST) -> str:
        """Produces a normalized structural hash of an AST node (ignoring variable names)."""
        elements = []
        for child in ast.walk(node):
            elements.append(type(child).__name__)
        return hashlib.md5("".join(elements).encode("utf-8")).hexdigest()

    def analyze(self, target_dir: str = ".") -> DuplicationReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        seen_blocks: Dict[str, Tuple[str, int, int, str]] = {}
        duplicates: List[DuplicateBlock] = []
        total_files = 0
        total_dup_lines = 0

        for root, dirs, files in os.walk(resolved_root):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith(".")]
            if any(part.startswith(".") or part in self.ignored_dirs for part in root.split(os.sep)):
                continue

            for f in files:
                if not f.endswith(".py") or f.startswith("test_"):
                    continue

                total_files += 1
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.workspace_root)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                        lines = fp.readlines()
                    tree = ast.parse("".join(lines), filename=full_path)
                except Exception:
                    continue

                # Inspect function definitions
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start_line = node.lineno
                        end_line = getattr(node, "end_lineno", node.lineno)
                        line_count = end_line - start_line + 1

                        if line_count >= self.min_lines:
                            h = self._hash_ast_node(node)
                            snippet = "".join(lines[start_line - 1 : min(start_line + 2, end_line)]).strip()

                            if h in seen_blocks:
                                orig_file, orig_start, orig_end, orig_snip = seen_blocks[h]
                                if orig_file != rel_path or orig_start != start_line:
                                    duplicates.append(
                                        DuplicateBlock(
                                            file_path=rel_path,
                                            start_line=start_line,
                                            end_line=end_line,
                                            lines_count=line_count,
                                            duplicate_of_file=orig_file,
                                            duplicate_of_line=orig_start,
                                            similarity_pct=95,
                                            snippet=snippet,
                                        )
                                    )
                                    total_dup_lines += line_count
                            else:
                                seen_blocks[h] = (rel_path, start_line, end_line, snippet)

        dup_count = len(duplicates)
        score = max(0, min(100, 100 - (dup_count * 5)))

        lines_out = [
            "Code Duplication Report",
            f"Files Analyzed: {total_files}",
            f"Duplicate Logic Blocks: {dup_count}",
            f"Duplicate Lines Detected: {total_dup_lines}",
            f"Duplication Health Score: {score}/100",
        ]
        if dup_count > 0:
            lines_out.append("Top Duplication Candidates:")
            for d in duplicates[:3]:
                lines_out.append(f"  {d.file_path}:{d.start_line} <=> {d.duplicate_of_file}:{d.duplicate_of_line} ({d.lines_count} lines)")

        chatbox_report = "\n".join(lines_out)

        return DuplicationReport(
            total_files_analyzed=total_files,
            duplicate_blocks_count=dup_count,
            duplicate_lines_count=total_dup_lines,
            duplicates=duplicates,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
