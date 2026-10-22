# plugins/code_assistant/commands.py
"""PluginAction definitions for the Code Assistant Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="find_errors",
        description="Finds syntax errors, tracebacks, or log exceptions in Jarvis codebase",
        keywords=[
            "jarvis code mein ye error find karo",
            "jarvis code mein error find karo",
            "code mein ye error find karo",
            "code mein error find karo",
            "find errors in code",
            "find code errors",
            "error find karo",
            "find error",
        ],
        parameters=[
            PluginParameter(name="query", type="string", description="Error message or query to search for", required=False, default=None),
            PluginParameter(name="target_file", type="string", description="Optional file to check syntax on", required=False, default=None),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_file",
        description="Performs AST, complexity, and structural analysis of a python file",
        keywords=[
            "main.py analyze karo",
            "analyze main.py",
            "file analyze karo",
            "code analyze karo",
            "analyze file",
            "analyze python file",
        ],
        parameters=[
            PluginParameter(name="file_path", type="string", description="File to analyze", required=False, default="main.py"),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="find_unused_functions",
        description="Finds unreferenced/unused function definitions across the codebase",
        keywords=[
            "unused functions find karo",
            "find unused functions",
            "unused function dhundo",
            "uncalled functions find karo",
            "unused functions check karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to scan", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="check_architecture",
        description="Checks architectural integrity, SSOT guidelines, and feature registry sync",
        keywords=[
            "project architecture check karo",
            "architecture check karo",
            "check project architecture",
            "system architecture check karo",
            "architecture verify karo",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="run_pytest",
        description="Executes pytest test suite safely and parses pass/fail statistics",
        keywords=[
            "pytest run karo",
            "run pytest",
            "tests run karo",
            "run tests",
            "pytest chalao",
            "unit tests chalao",
        ],
        parameters=[
            PluginParameter(name="test_target", type="string", description="Specific test file or directory", required=False, default=None),
            PluginParameter(name="timeout", type="int", description="Max timeout in seconds", required=False, default=45),
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value,
    ),
    PluginAction(
        name="suggest_error_fix",
        description="Diagnoses an error and suggests a surgical fix and unified diff",
        keywords=[
            "error fix suggest karo",
            "suggest error fix",
            "error ka fix batao",
            "fix suggest karo",
            "how to fix error",
            "suggest fix",
        ],
        parameters=[
            PluginParameter(name="error_text", type="string", description="Error text or traceback", required=False, default=None),
            PluginParameter(name="file_path", type="string", description="Target file path", required=False, default=None),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_change_impact",
        description="Analyzes git status/diff, affected components, and assigns Risk Tier",
        keywords=[
            "last change ka impact batao",
            "change impact batao",
            "last change ka impact kya hai",
            "change impact analyze karo",
            "git diff impact batao",
            "analyze change impact",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value,
    ),
    PluginAction(
        name="find_dead_code",
        description="Finds unreachable code blocks and dead code paths in the codebase",
        keywords=[
            "dead code find karo",
            "find dead code",
            "dead code dhundo",
            "unreachable code find karo",
            "dead code check karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to scan", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="get_mode",
        description="Returns the active operational safety mode of the Code Assistant",
        keywords=[
            "code assistant mode check karo",
            "code assistant mode kya hai",
            "assistant mode check karo",
            "get assistant mode",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="set_mode",
        description="Switches the operational mode (READ_ONLY, SUGGEST, PATCH, AUTO_FIX)",
        keywords=[
            "code assistant mode set karo",
            "code assistant mode badlo",
            "set assistant mode",
        ],
        parameters=[
            PluginParameter(name="mode", type="string", description="Target mode (READ_ONLY, SUGGEST, PATCH, AUTO_FIX)", required=True),
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="safe_cleanup",
        description="Safely removes dead code or unreferenced symbols with guarded backup and pytest auto-rollback",
        keywords=[
            "safe cleanup karo",
            "dead code cleanup karo",
            "clean dead code",
            "safe delete dead code",
        ],
        parameters=[
            PluginParameter(name="target_file", type="string", description="Target python file", required=True),
            PluginParameter(name="symbol_name", type="string", description="Target symbol to remove", required=False, default=None),
            PluginParameter(name="confirm", type="bool", description="Explicit user confirmation required", required=False, default=False),
            PluginParameter(name="test_target", type="string", description="Scoped test to verify against", required=False, default=None),
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="run_health_audit",
        description="Executes a 10-pillar holistic health audit across the entire codebase",
        keywords=[
            "jarvis, mere pure project ka health audit karo",
            "mere pure project ka health audit karo",
            "project ka health audit karo",
            "project health audit karo",
            "project health check karo",
            "code health audit",
            "full project audit karo",
            "project health score batao",
            "audit project health",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to audit", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_dependencies",
        description="Audits requirements.txt against active environment packages",
        keywords=[
            "dependency analyze karo",
            "dependencies check karo",
            "analyze dependencies",
            "check requirements",
            "missing dependencies check karo",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_imports",
        description="Checks import hygiene, wildcard imports, and module ordering",
        keywords=[
            "imports analyze karo",
            "wildcard imports check karo",
            "check imports",
            "import hygiene check karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to check", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="detect_duplication",
        description="Detects duplicate logic blocks and repeated function bodies across files",
        keywords=[
            "duplicate code find karo",
            "code duplication check karo",
            "find duplicate code",
            "duplicate blocks find karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to scan", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_complexity",
        description="Calculates cyclomatic and cognitive complexity metrics",
        keywords=[
            "code complexity check karo",
            "complex functions find karo",
            "analyze code complexity",
            "cyclomatic complexity check karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to analyze", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="detect_circular_dependencies",
        description="Detects circular import dependency cycles across modules",
        keywords=[
            "circular dependencies check karo",
            "circular imports find karo",
            "detect circular dependencies",
            "check import cycles",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to scan", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="scan_security",
        description="Scans for vulnerabilities, eval/exec, shell=True, and hardcoded secrets",
        keywords=[
            "security scan karo",
            "security check karo",
            "vulnerabilities find karo",
            "scan code security",
            "hardcoded secrets find karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to scan", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_performance",
        description="Detects blocking async calls and uncompiled regex in tight loops",
        keywords=[
            "performance analyze karo",
            "performance issues find karo",
            "check code performance",
            "blocking calls find karo",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to check", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
    PluginAction(
        name="analyze_coverage",
        description="Evaluates test suite completeness and untested source modules",
        keywords=[
            "test coverage check karo",
            "coverage report batao",
            "untested modules find karo",
            "check test coverage",
        ],
        parameters=[
            PluginParameter(name="target_dir", type="string", description="Directory to check", required=False, default="."),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value,
    ),
]


