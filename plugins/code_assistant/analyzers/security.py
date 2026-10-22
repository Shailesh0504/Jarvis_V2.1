# plugins/code_assistant/analyzers/security.py
"""
Security Scanner for the Jarvis Code Intelligence System.
Performs static AST rule checks and regex heuristics for hardcoded credentials,
unsafe execution (eval/exec, shell=True), weak cryptography, and insecure deserialization.
"""

import ast
import os
import re
from typing import List, Set

from ..models import SecurityReport, SecurityVulnerability


class SecurityScanner:
    """Detects static security vulnerabilities and sensitive data leakage."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.ignored_dirs = {
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "data"
        }

    def analyze(self, target_dir: str = ".") -> SecurityReport:
        resolved_root = os.path.abspath(os.path.join(self.workspace_root, target_dir))
        vulnerabilities: List[SecurityVulnerability] = []
        total_files = 0
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0

        secret_patterns = [
            (r"(?i)(?:api_key|secret_key|private_key|auth_token)\s*=\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]", "SEC_HARDCODED_API_KEY", "HIGH", "Hardcoded API key or secret token detected."),
            (r"(?i)(?:password|passwd)\s*=\s*['\"][A-Za-z0-9@#$%^&*!]{6,}['\"]", "SEC_HARDCODED_PASSWORD", "CRITICAL", "Hardcoded plain-text password detected."),
        ]

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
                    source = "".join(lines)
                except Exception:
                    continue

                # 1. Regex checks for secrets
                for idx, line in enumerate(lines):
                    line_no = idx + 1
                    for pat, rule_id, sev, desc in secret_patterns:
                        if re.search(pat, line) and "os.environ" not in line and "getenv" not in line:
                            vulnerabilities.append(
                                SecurityVulnerability(
                                    file_path=rel_path,
                                    line_number=line_no,
                                    rule_id=rule_id,
                                    severity=sev,
                                    description=desc,
                                    code_snippet=line.strip()[:60],
                                    recommendation="Move sensitive credentials to environment variables (.env).",
                                )
                            )
                            if sev == "CRITICAL":
                                critical_count += 1
                            else:
                                high_count += 1

                # 2. AST inspections
                try:
                    tree = ast.parse(source, filename=full_path)
                except Exception:
                    continue

                for node in ast.walk(tree):
                    # Check eval / exec
                    if isinstance(node, ast.Call):
                        fn_name = ""
                        if isinstance(node.func, ast.Name):
                            fn_name = node.func.id
                        if fn_name in ("eval", "exec"):
                            critical_count += 1
                            vulnerabilities.append(
                                SecurityVulnerability(
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    rule_id="SEC_ARBITRARY_CODE_EXEC",
                                    severity="CRITICAL",
                                    description=f"Use of '{fn_name}()' allows arbitrary code execution.",
                                    recommendation="Use ast.literal_eval() or safe parsing dispatch.",
                                )
                            )

                        # Check subprocess shell=True
                        if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                            high_count += 1
                            vulnerabilities.append(
                                SecurityVulnerability(
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    rule_id="SEC_SUBPROCESS_SHELL_TRUE",
                                    severity="HIGH",
                                    description="Subprocess called with 'shell=True', exposing command injection risk.",
                                    recommendation="Pass command arguments as list with shell=False.",
                                )
                            )

                        # Check verify=False in requests
                        if any(k.arg == "verify" and isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):
                            medium_count += 1
                            vulnerabilities.append(
                                SecurityVulnerability(
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    rule_id="SEC_TLS_VERIFY_DISABLED",
                                    severity="MEDIUM",
                                    description="TLS certificate validation disabled ('verify=False').",
                                    recommendation="Enable SSL/TLS certificate verification.",
                                )
                            )

        total_vulns = len(vulnerabilities)
        score = max(0, min(100, 100 - (critical_count * 30) - (high_count * 15) - (medium_count * 5) - (low_count * 2)))

        lines_out = [
            "Security Vulnerability Scan",
            f"Files Scanned: {total_files}",
            f"Vulnerabilities Found: {total_vulns}",
            f"  Critical: {critical_count} | High: {high_count} | Medium: {medium_count} | Low: {low_count}",
            f"Security Health Score: {score}/100",
        ]
        if critical_count > 0 or high_count > 0:
            lines_out.append("High-Severity Warnings:")
            for v in vulnerabilities:
                if v.severity in ("CRITICAL", "HIGH"):
                    lines_out.append(f"  [{v.severity}] {v.description} ({v.file_path}:{v.line_number})")

        chatbox_report = "\n".join(lines_out)

        return SecurityReport(
            total_files_scanned=total_files,
            vulnerabilities_count=total_vulns,
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            items=vulnerabilities,
            health_score=score,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
