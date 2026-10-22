# plugins/code_assistant/analyzers/health_audit.py
"""
Project Health Audit Engine for the Jarvis Code Intelligence System.
Aggregates findings from all 10 specialized analyzers into a single unified health score (0-100),
letter grade (A-F), pillar breakdown, and actionable prioritized recommendations.
"""

import os
from typing import List

from ..models import PillarScore, ProjectHealthReport
from .architecture import ArchitectureAnalyzer
from .circular import CircularDependencyDetector
from .complexity import ComplexityAnalyzer
from .coverage import CoverageAnalyzer
from .dead_code import DeadCodeAnalyzer
from .dependency import DependencyAnalyzer
from .duplication import DuplicateCodeDetector
from .imports import ImportAnalyzer
from .performance import PerformanceAnalyzer
from .security import SecurityScanner


class HealthAuditEngine:
    """Coordinates all 10 static analyzers and computes the overall Project Health Audit."""

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.dead_code_analyzer = DeadCodeAnalyzer(workspace_root)
        self.dependency_analyzer = DependencyAnalyzer(workspace_root)
        self.import_analyzer = ImportAnalyzer(workspace_root)
        self.duplication_analyzer = DuplicateCodeDetector(workspace_root)
        self.complexity_analyzer = ComplexityAnalyzer(workspace_root)
        self.architecture_analyzer = ArchitectureAnalyzer(workspace_root)
        self.circular_analyzer = CircularDependencyDetector(workspace_root)
        self.security_scanner = SecurityScanner(workspace_root)
        self.performance_analyzer = PerformanceAnalyzer(workspace_root)
        self.coverage_analyzer = CoverageAnalyzer(workspace_root)

    def run_audit(self, target_dir: str = ".") -> ProjectHealthReport:
        # 1. Run all 10 analyzers concurrently for maximum speed
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=6) as executor:
            fut_dead = executor.submit(self.dead_code_analyzer.analyze_all_dead_code, target_dir)
            fut_dep = executor.submit(self.dependency_analyzer.analyze)
            fut_imp = executor.submit(self.import_analyzer.analyze, target_dir)
            fut_dup = executor.submit(self.duplication_analyzer.analyze, target_dir)
            fut_comp = executor.submit(self.complexity_analyzer.analyze, target_dir)
            fut_arch = executor.submit(self.architecture_analyzer.analyze)
            fut_circ = executor.submit(self.circular_analyzer.analyze, target_dir)
            fut_sec = executor.submit(self.security_scanner.analyze, target_dir)
            fut_perf = executor.submit(self.performance_analyzer.analyze, target_dir)
            fut_cov = executor.submit(self.coverage_analyzer.analyze, target_dir)

            dead_rep = fut_dead.result()
            dep_rep = fut_dep.result()
            imp_rep = fut_imp.result()
            dup_rep = fut_dup.result()
            comp_rep = fut_comp.result()
            arch_rep = fut_arch.result()
            circ_rep = fut_circ.result()
            sec_rep = fut_sec.result()
            perf_rep = fut_perf.result()
            cov_rep = fut_cov.result()

        # 2. Compute individual pillar scores and weights
        # Dead code score: 100 - (v_dead * 0.05)
        dead_score = max(50, min(100, int(100 - (dead_rep.very_likely_dead_count * 0.05))))

        pillars = [
            PillarScore(
                pillar_name="Dead Code",
                score=dead_score,
                weight=0.10,
                details=f"{dead_rep.very_likely_dead_count} very likely dead, {dead_rep.probably_unused_count} probably unused",
                critical_issues_count=dead_rep.very_likely_dead_count,
            ),
            PillarScore(
                pillar_name="Dependency Health",
                score=dep_rep.health_score,
                weight=0.10,
                details=f"{dep_rep.missing_count} missing, {dep_rep.unpinned_count} unpinned",
                critical_issues_count=dep_rep.missing_count,
            ),
            PillarScore(
                pillar_name="Import Hygiene",
                score=imp_rep.health_score,
                weight=0.10,
                details=f"{imp_rep.wildcard_count} wildcards, {imp_rep.unused_count} unused imports",
                critical_issues_count=imp_rep.wildcard_count,
            ),
            PillarScore(
                pillar_name="Code Duplication",
                score=dup_rep.health_score,
                weight=0.10,
                details=f"{dup_rep.duplicate_blocks_count} duplicate blocks ({dup_rep.duplicate_lines_count} lines)",
                critical_issues_count=dup_rep.duplicate_blocks_count,
            ),
            PillarScore(
                pillar_name="Cyclomatic Complexity",
                score=comp_rep.health_score,
                weight=0.10,
                details=f"Avg CC: {comp_rep.avg_cyclomatic_complexity}, {comp_rep.high_complexity_count} complex functions",
                critical_issues_count=comp_rep.high_complexity_count,
            ),
            PillarScore(
                pillar_name="Architecture & SSOT",
                score=arch_rep.warnings and 80 or (len(arch_rep.ssot_violations) == 0 and 95 or 85),
                weight=0.15,
                details=f"{sum(arch_rep.core_modules_present.values())}/5 pillars, {len(arch_rep.ssot_violations)} violations",
                critical_issues_count=len(arch_rep.ssot_violations),
            ),
            PillarScore(
                pillar_name="Circular Dependencies",
                score=circ_rep.health_score,
                weight=0.10,
                details=f"{circ_rep.cycles_found} circular import cycles",
                critical_issues_count=circ_rep.cycles_found,
            ),
            PillarScore(
                pillar_name="Security & Secrets",
                score=sec_rep.health_score,
                weight=0.15,
                details=f"{sec_rep.critical_count} critical, {sec_rep.high_count} high vulnerabilities",
                critical_issues_count=sec_rep.critical_count + sec_rep.high_count,
            ),
            PillarScore(
                pillar_name="Performance Patterns",
                score=perf_rep.health_score,
                weight=0.10,
                details=f"{perf_rep.issues_found} latency risks detected",
                critical_issues_count=perf_rep.issues_found,
            ),
            PillarScore(
                pillar_name="Test Coverage",
                score=cov_rep.health_score,
                weight=0.10,
                details=f"{cov_rep.overall_coverage_pct}% modules mapped to tests",
                critical_issues_count=cov_rep.untested_modules,
            ),
        ]

        # 3. Overall Weighted Score Calculation
        weighted_sum = sum(p.score * p.weight for p in pillars)
        overall_score = max(0, min(100, round(weighted_sum)))

        # 4. Determine Letter Grade
        if overall_score >= 95:
            grade = "A+"
        elif overall_score >= 90:
            grade = "A"
        elif overall_score >= 85:
            grade = "B+"
        elif overall_score >= 80:
            grade = "B"
        elif overall_score >= 70:
            grade = "C"
        elif overall_score >= 60:
            grade = "D"
        else:
            grade = "F"

        # 5. Top Prioritized Recommendations
        recommendations: List[str] = []
        # Security first
        if sec_rep.critical_count > 0 or sec_rep.high_count > 0:
            recommendations.append(f"[SECURITY] Address {sec_rep.critical_count + sec_rep.high_count} high/critical vulnerabilities (e.g. {sec_rep.items[0].description}).")
        # Missing dependencies
        if dep_rep.missing_count > 0:
            recommendations.append(f"[DEPENDENCY] Install {dep_rep.missing_count} missing packages in venv: {dep_rep.issues[0].package_name}.")
        # Complexity
        if comp_rep.high_complexity_count > 0:
            top_comp = comp_rep.items[0]
            recommendations.append(f"[COMPLEXITY] Refactor high-complexity function '{top_comp.function_name}' (CC: {top_comp.cyclomatic_complexity}) in {os.path.basename(top_comp.file_path)}.")
        # Circular imports
        if circ_rep.cycles_found > 0:
            recommendations.append(f"[CIRCULAR] Break circular import cycle: {circ_rep.cycles[0].display}.")
        # Dead code
        if dead_rep.very_likely_dead_count > 0:
            recommendations.append(f"[DEAD CODE] Review {dead_rep.very_likely_dead_count} unused symbols for safe retirement.")
        # Wildcard imports
        if imp_rep.wildcard_count > 0:
            recommendations.append(f"[IMPORTS] Replace {imp_rep.wildcard_count} wildcard 'import *' with explicit imports.")

        if not recommendations:
            recommendations.append("Project architecture and code hygiene are in excellent condition. No critical actions needed.")

        # 6. Format Chatbox Output
        lines = [
            "================================================================",
            "PROJECT HEALTH AUDIT REPORT",
            "================================================================",
            f"Overall Health Score: {overall_score} / 100  [GRADE: {grade}]",
            f"Analyzed Files: {cov_rep.total_source_modules} | Total Symbols: {dead_rep.total_symbols_analyzed:,}",
            "",
            "Pillar Breakdown:",
        ]
        for idx, p in enumerate(pillars, 1):
            lines.append(f"  [{idx}] {p.pillar_name:<23}: {p.score:>3}/100  ({p.details})")

        lines.extend(["", "Top Critical Recommendations:"])
        for idx, rec in enumerate(recommendations[:3], 1):
            lines.append(f"  {idx}. {rec}")

        lines.extend([
            "",
            "Safety Note:",
            "Code Assistant mode is 'READ_ONLY'.",
            "No files will be modified or deleted automatically.",
            "================================================================",
        ])

        chatbox_report = "\n".join(lines)

        return ProjectHealthReport(
            overall_score=overall_score,
            letter_grade=grade,
            total_files_analyzed=cov_rep.total_source_modules,
            total_symbols_analyzed=dead_rep.total_symbols_analyzed,
            pillar_scores=pillars,
            top_recommendations=recommendations,
            dead_code_report=dead_rep,
            dependency_report=dep_rep,
            import_report=imp_rep,
            duplication_report=dup_rep,
            complexity_report=comp_rep,
            architecture_report=arch_rep,
            circular_report=circ_rep,
            security_report=sec_rep,
            performance_report=perf_rep,
            coverage_report=cov_rep,
            summary_message=chatbox_report,
            formatted_chatbox_report=chatbox_report,
        )
