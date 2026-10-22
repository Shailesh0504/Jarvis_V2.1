# plugins/code_assistant/models.py
"""Data models and Enums for the Code Assistant Plugin."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AssistantMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    SUGGEST = "SUGGEST"
    PATCH = "PATCH"
    AUTO_FIX = "AUTO_FIX"

    @classmethod
    def from_str(cls, val: str) -> "AssistantMode":
        cleaned = str(val).strip().upper()
        for mode in cls:
            if mode.value == cleaned:
                return mode
        return cls.READ_ONLY


@dataclass
class FileAnalysisResult:
    file_path: str
    exists: bool
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    function_count: int = 0
    class_count: int = 0
    import_count: int = 0
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    syntax_valid: bool = True
    syntax_error: Optional[str] = None
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "exists": self.exists,
            "total_lines": self.total_lines,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "blank_lines": self.blank_lines,
            "function_count": self.function_count,
            "class_count": self.class_count,
            "import_count": self.import_count,
            "functions": self.functions,
            "classes": self.classes,
            "imports": self.imports,
            "syntax_valid": self.syntax_valid,
            "syntax_error": self.syntax_error,
            "summary_message": self.summary_message,
        }


@dataclass
class UnusedFunctionInfo:
    name: str
    file_path: str
    line_number: int
    is_method: bool = False
    class_name: Optional[str] = None
    category: str = "top_level"  # top_level, class_method, private_helper
    confidence: str = "HIGH"     # HIGH, MEDIUM, LOW
    full_signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "is_method": self.is_method,
            "class_name": self.class_name,
            "category": self.category,
            "confidence": self.confidence,
            "full_signature": self.full_signature or (f"{self.class_name}.{self.name}" if self.class_name else self.name),
        }


@dataclass
class UnusedFunctionsReport:
    total_count: int
    top_level_count: int
    class_methods_count: int
    private_helpers_count: int
    top_level_functions: List[UnusedFunctionInfo] = field(default_factory=list)
    class_methods: List[UnusedFunctionInfo] = field(default_factory=list)
    private_helpers: List[UnusedFunctionInfo] = field(default_factory=list)
    module_breakdown: Dict[str, int] = field(default_factory=dict)
    summary_message: str = ""
    total_functions_analyzed: int = 0
    high_confidence_count: int = 0
    possibly_dynamic_count: int = 0
    public_api_count: int = 0
    test_only_count: int = 0
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        all_funcs = self.top_level_functions + self.class_methods + self.private_helpers
        return {
            "count": self.total_count,
            "total_count": self.total_count,
            "top_level_count": self.top_level_count,
            "class_methods_count": self.class_methods_count,
            "private_helpers_count": self.private_helpers_count,
            "total_functions_analyzed": self.total_functions_analyzed,
            "high_confidence_count": self.high_confidence_count,
            "possibly_dynamic_count": self.possibly_dynamic_count,
            "public_api_count": self.public_api_count,
            "test_only_count": self.test_only_count,
            "top_level_functions": [f.to_dict() for f in self.top_level_functions],
            "class_methods": [f.to_dict() for f in self.class_methods],
            "private_helpers": [f.to_dict() for f in self.private_helpers],
            "unused_functions": [f.to_dict() for f in all_funcs],
            "module_breakdown": self.module_breakdown,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class ArchitectureReport:
    core_modules_present: Dict[str, bool]
    ssot_violations: List[str] = field(default_factory=list)
    duplicate_modules: List[str] = field(default_factory=list)
    registry_synchronized: bool = True
    warnings: List[str] = field(default_factory=list)
    total_files_checked: int = 0
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "core_modules_present": self.core_modules_present,
            "ssot_violations": self.ssot_violations,
            "duplicate_modules": self.duplicate_modules,
            "registry_synchronized": self.registry_synchronized,
            "warnings": self.warnings,
            "total_files_checked": self.total_files_checked,
            "summary_message": self.summary_message,
        }


@dataclass
class PytestResult:
    command: str
    exit_code: int
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    stdout_summary: str = ""
    success: bool = True
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_seconds": self.duration_seconds,
            "stdout_summary": self.stdout_summary,
            "success": self.success,
            "summary_message": self.summary_message,
        }


@dataclass
class ChangeImpactReport:
    modified_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    affected_components: List[str] = field(default_factory=list)
    risk_tier: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    risk_rationale: str = ""
    recommended_tests: List[str] = field(default_factory=list)
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modified_files": self.modified_files,
            "untracked_files": self.untracked_files,
            "affected_components": self.affected_components,
            "risk_tier": self.risk_tier,
            "risk_rationale": self.risk_rationale,
            "recommended_tests": self.recommended_tests,
            "summary_message": self.summary_message,
        }


@dataclass
class DeadCodeItem:
    file_path: str
    line_number: int
    item_type: str  # unreachable_code, unused_import, empty_pass
    description: str


@dataclass
class ErrorFixSuggestion:
    error_type: str
    error_message: str
    target_file: Optional[str] = None
    target_line: Optional[int] = None
    root_cause: str = ""
    suggested_fix: str = ""
    diff: str = ""
    patch_applied: bool = False
    mode: str = AssistantMode.READ_ONLY.value
    summary_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "target_file": self.target_file,
            "target_line": self.target_line,
            "root_cause": self.root_cause,
            "suggested_fix": self.suggested_fix,
            "diff": self.diff,
            "patch_applied": self.patch_applied,
            "mode": self.mode,
            "summary_message": self.summary_message,
        }


class SymbolType(str, Enum):
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    METHOD = "METHOD"
    IMPORT = "IMPORT"
    VARIABLE = "VARIABLE"
    MODULE = "MODULE"
    PLUGIN = "PLUGIN"
    ROUTE = "ROUTE"
    CLI_COMMAND = "CLI_COMMAND"
    EVENT_HANDLER = "EVENT_HANDLER"
    DECORATOR = "DECORATOR"


class ConfidenceTier(str, Enum):
    VERY_LIKELY_DEAD = "VERY_LIKELY_DEAD"  # 95-100%
    PROBABLY_UNUSED = "PROBABLY_UNUSED"    # 80-94%
    NEEDS_REVIEW = "NEEDS_REVIEW"          # 50-79%
    POSSIBLY_DYNAMIC = "POSSIBLY_DYNAMIC"  # <50%

    @classmethod
    def from_percentage(cls, pct: int) -> "ConfidenceTier":
        if pct >= 95:
            return cls.VERY_LIKELY_DEAD
        elif pct >= 80:
            return cls.PROBABLY_UNUSED
        elif pct >= 50:
            return cls.NEEDS_REVIEW
        else:
            return cls.POSSIBLY_DYNAMIC


@dataclass
class DeadSymbolItem:
    name: str
    file_path: str
    line_number: int
    symbol_type: SymbolType
    confidence_pct: int
    confidence_tier: ConfidenceTier
    rationale: str = ""
    code_snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "symbol_type": self.symbol_type.value if hasattr(self.symbol_type, "value") else str(self.symbol_type),
            "confidence_pct": self.confidence_pct,
            "confidence_tier": self.confidence_tier.value if hasattr(self.confidence_tier, "value") else str(self.confidence_tier),
            "rationale": self.rationale,
            "code_snippet": self.code_snippet,
        }


@dataclass
class ComprehensiveDeadCodeReport:
    total_symbols_analyzed: int
    potentially_unused_count: int
    very_likely_dead_count: int      # 95-100%
    probably_unused_count: int       # 80-94%
    needs_review_count: int          # 50-79%
    possibly_dynamic_count: int      # <50%
    by_symbol_type: Dict[str, int] = field(default_factory=dict)
    symbols: List[DeadSymbolItem] = field(default_factory=list)
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_symbols_analyzed": self.total_symbols_analyzed,
            "potentially_unused_count": self.potentially_unused_count,
            "very_likely_dead_count": self.very_likely_dead_count,
            "probably_unused_count": self.probably_unused_count,
            "needs_review_count": self.needs_review_count,
            "possibly_dynamic_count": self.possibly_dynamic_count,
            "by_symbol_type": self.by_symbol_type,
            "symbols": [s.to_dict() for s in self.symbols],
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


# =============================================================================
# Code Intelligence & Project Health Models (10 Analyzers)
# =============================================================================

@dataclass
class DependencyIssue:
    package_name: str
    issue_type: str  # missing, unpinned, outdated
    installed_version: Optional[str] = None
    required_version: Optional[str] = None
    file_path: str = "requirements.txt"
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "issue_type": self.issue_type,
            "installed_version": self.installed_version,
            "required_version": self.required_version,
            "file_path": self.file_path,
            "recommendation": self.recommendation,
        }


@dataclass
class DependencyReport:
    total_dependencies: int
    missing_count: int
    unpinned_count: int
    issues: List[DependencyIssue] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_dependencies": self.total_dependencies,
            "missing_count": self.missing_count,
            "unpinned_count": self.unpinned_count,
            "issues": [i.to_dict() for i in self.issues],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class ImportIssue:
    file_path: str
    line_number: int
    module_name: str
    issue_type: str  # unused, wildcard, out_of_order, deprecated
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "module_name": self.module_name,
            "issue_type": self.issue_type,
            "recommendation": self.recommendation,
        }


@dataclass
class ImportAnalysisReport:
    total_imports_checked: int
    wildcard_count: int
    unused_count: int
    out_of_order_count: int
    issues: List[ImportIssue] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_imports_checked": self.total_imports_checked,
            "wildcard_count": self.wildcard_count,
            "unused_count": self.unused_count,
            "out_of_order_count": self.out_of_order_count,
            "issues": [i.to_dict() for i in self.issues],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class DuplicateBlock:
    file_path: str
    start_line: int
    end_line: int
    lines_count: int
    duplicate_of_file: str
    duplicate_of_line: int
    similarity_pct: int
    snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "lines_count": self.lines_count,
            "duplicate_of_file": self.duplicate_of_file,
            "duplicate_of_line": self.duplicate_of_line,
            "similarity_pct": self.similarity_pct,
            "snippet": self.snippet,
        }


@dataclass
class DuplicationReport:
    total_files_analyzed: int
    duplicate_blocks_count: int
    duplicate_lines_count: int
    duplicates: List[DuplicateBlock] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files_analyzed": self.total_files_analyzed,
            "duplicate_blocks_count": self.duplicate_blocks_count,
            "duplicate_lines_count": self.duplicate_lines_count,
            "duplicates": [d.to_dict() for d in self.duplicates],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class ComplexityItem:
    file_path: str
    function_name: str
    line_number: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    line_count: int
    risk_level: str  # LOW, MEDIUM, HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "function_name": self.function_name,
            "line_number": self.line_number,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "cognitive_complexity": self.cognitive_complexity,
            "line_count": self.line_count,
            "risk_level": self.risk_level,
        }


@dataclass
class ComplexityReport:
    total_functions_analyzed: int
    avg_cyclomatic_complexity: float
    high_complexity_count: int
    items: List[ComplexityItem] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_functions_analyzed": self.total_functions_analyzed,
            "avg_cyclomatic_complexity": self.avg_cyclomatic_complexity,
            "high_complexity_count": self.high_complexity_count,
            "items": [i.to_dict() for i in self.items],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class CircularDependencyCycle:
    cycle_path: List[str]
    cycle_length: int

    @property
    def display(self) -> str:
        return " -> ".join(self.cycle_path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_path": self.cycle_path,
            "cycle_length": self.cycle_length,
            "display": self.display,
        }


@dataclass
class CircularDependencyReport:
    total_modules_analyzed: int
    cycles_found: int
    cycles: List[CircularDependencyCycle] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_modules_analyzed": self.total_modules_analyzed,
            "cycles_found": self.cycles_found,
            "cycles": [c.to_dict() for c in self.cycles],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class SecurityVulnerability:
    file_path: str
    line_number: int
    rule_id: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    code_snippet: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "description": self.description,
            "code_snippet": self.code_snippet,
            "recommendation": self.recommendation,
        }


@dataclass
class SecurityReport:
    total_files_scanned: int
    vulnerabilities_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    items: List[SecurityVulnerability] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files_scanned": self.total_files_scanned,
            "vulnerabilities_count": self.vulnerabilities_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "items": [i.to_dict() for i in self.items],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class PerformanceAntipattern:
    file_path: str
    line_number: int
    pattern_type: str  # blocking_in_async, uncompiled_regex_loop, heavy_io_loop
    description: str
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "suggestion": self.suggestion,
        }


@dataclass
class PerformanceReport:
    total_checks_performed: int
    issues_found: int
    items: List[PerformanceAntipattern] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checks_performed": self.total_checks_performed,
            "issues_found": self.issues_found,
            "items": [i.to_dict() for i in self.items],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class ModuleCoverageItem:
    module_path: str
    has_test_file: bool
    test_file_path: Optional[str] = None
    estimated_coverage_pct: int = 0
    test_functions_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_path": self.module_path,
            "has_test_file": self.has_test_file,
            "test_file_path": self.test_file_path,
            "estimated_coverage_pct": self.estimated_coverage_pct,
            "test_functions_count": self.test_functions_count,
        }


@dataclass
class CoverageReport:
    total_source_modules: int
    tested_modules: int
    untested_modules: int
    overall_coverage_pct: int
    items: List[ModuleCoverageItem] = field(default_factory=list)
    health_score: int = 100
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_source_modules": self.total_source_modules,
            "tested_modules": self.tested_modules,
            "untested_modules": self.untested_modules,
            "overall_coverage_pct": self.overall_coverage_pct,
            "items": [i.to_dict() for i in self.items],
            "health_score": self.health_score,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


@dataclass
class PillarScore:
    pillar_name: str
    score: int
    weight: float
    details: str
    critical_issues_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pillar_name": self.pillar_name,
            "score": self.score,
            "weight": self.weight,
            "details": self.details,
            "critical_issues_count": self.critical_issues_count,
        }


@dataclass
class ProjectHealthReport:
    overall_score: int
    letter_grade: str  # A+, A, B+, B, C, D, F
    total_files_analyzed: int
    total_symbols_analyzed: int
    pillar_scores: List[PillarScore] = field(default_factory=list)
    top_recommendations: List[str] = field(default_factory=list)
    dead_code_report: Optional[ComprehensiveDeadCodeReport] = None
    dependency_report: Optional[DependencyReport] = None
    import_report: Optional[ImportAnalysisReport] = None
    duplication_report: Optional[DuplicationReport] = None
    complexity_report: Optional[ComplexityReport] = None
    architecture_report: Optional[ArchitectureReport] = None
    circular_report: Optional[CircularDependencyReport] = None
    security_report: Optional[SecurityReport] = None
    performance_report: Optional[PerformanceReport] = None
    coverage_report: Optional[CoverageReport] = None
    summary_message: str = ""
    formatted_chatbox_report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "letter_grade": self.letter_grade,
            "total_files_analyzed": self.total_files_analyzed,
            "total_symbols_analyzed": self.total_symbols_analyzed,
            "pillar_scores": [p.to_dict() for p in self.pillar_scores],
            "top_recommendations": self.top_recommendations,
            "summary_message": self.summary_message,
            "formatted_chatbox_report": self.formatted_chatbox_report,
        }


