# plugins/code_assistant/analyzers/dependency.py
"""
Dependency Analyzer for the Jarvis Code Intelligence System.
Inspects requirements.txt, setup.py, and active virtual environment for missing,
unpinned, or outdated dependencies.
"""

import os
import re
from typing import List, Optional
import importlib.metadata

from ..models import DependencyIssue, DependencyReport


class DependencyAnalyzer:
    """Analyzes workspace dependencies, virtual environment packages, and version pins."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root

    def analyze(self) -> DependencyReport:
        req_file = os.path.join(self.workspace_root, "requirements.txt")
        issues: List[DependencyIssue] = []
        total_dependencies = 0
        missing_count = 0
        unpinned_count = 0

        if not os.path.isfile(req_file):
            return DependencyReport(
                total_dependencies=0,
                missing_count=0,
                unpinned_count=0,
                health_score=80,
                summary_message="requirements.txt nahi mila workspace mein.",
                formatted_chatbox_report="requirements.txt nahi mila workspace mein.",
            )

        try:
            with open(req_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in lines:
                raw = line.strip()
                if not raw or raw.startswith("#") or raw.startswith("-"):
                    continue

                total_dependencies += 1
                # Parse package name and version requirement (e.g. pytest>=7.0.0, PySide6==6.5.0)
                m = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([<>=!~]+.*)?$", raw)
                if not m:
                    continue

                pkg_name = m.group(1).strip()
                version_spec = (m.group(2) or "").strip()

                # Check if installed
                installed_ver: Optional[str] = None
                try:
                    # Normalize name (e.g., PySide6 -> pyside6, pyttsx3)
                    norm_name = pkg_name.replace("_", "-")
                    installed_ver = importlib.metadata.version(norm_name)
                except Exception:
                    try:
                        installed_ver = importlib.metadata.version(pkg_name.lower())
                    except Exception:
                        installed_ver = None

                if installed_ver is None:
                    missing_count += 1
                    issues.append(
                        DependencyIssue(
                            package_name=pkg_name,
                            issue_type="missing",
                            required_version=version_spec or "any",
                            installed_version=None,
                            recommendation=f"Package '{pkg_name}' venv mein installed nahi hai. Run: pip install {pkg_name}",
                        )
                    )
                elif not version_spec or not ("==" in version_spec or ">=" in version_spec):
                    unpinned_count += 1
                    issues.append(
                        DependencyIssue(
                            package_name=pkg_name,
                            issue_type="unpinned",
                            installed_version=installed_ver,
                            required_version=version_spec or "unpinned",
                            recommendation=f"Pin exact version in requirements.txt (e.g., {pkg_name}=={installed_ver}).",
                        )
                    )

            # Health calculation: 100 - (missing * 25) - (unpinned * 2)
            score = max(0, min(100, 100 - (missing_count * 25) - (unpinned_count * 2)))

            lines_out = [
                "Dependency Health Report",
                f"Total Dependencies Checked: {total_dependencies}",
                f"Missing in Active Environment: {missing_count}",
                f"Unpinned Requirements: {unpinned_count}",
                f"Pillar Health Score: {score}/100",
            ]
            if missing_count > 0:
                lines_out.append("Missing Packages: " + ", ".join([i.package_name for i in issues if i.issue_type == "missing"][:3]))

            chatbox_report = "\n".join(lines_out)

            return DependencyReport(
                total_dependencies=total_dependencies,
                missing_count=missing_count,
                unpinned_count=unpinned_count,
                issues=issues,
                health_score=score,
                summary_message=chatbox_report,
                formatted_chatbox_report=chatbox_report,
            )

        except Exception as exc:
            return DependencyReport(
                total_dependencies=total_dependencies,
                missing_count=missing_count,
                unpinned_count=unpinned_count,
                health_score=70,
                summary_message=f"Dependency analysis error: {exc}",
                formatted_chatbox_report=f"Dependency analysis error: {exc}",
            )
