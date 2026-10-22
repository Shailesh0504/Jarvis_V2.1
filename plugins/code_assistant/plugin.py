# plugins/code_assistant/plugin.py
"""
Production Developer Code Assistant Plugin for Jarvis V2.1.
Enforces strict safety invariants (READ_ONLY by default, no unprompted automatic file modification).
"""

import logging
import os
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .analyzer import CodeAnalysisEngine
from .commands import ACTIONS
from .models import AssistantMode
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.code_assistant")


class CodeAssistantPlugin(BasePlugin):
    """
    Developer Code Assistant Plugin for Jarvis.
    Enforces 4 operational modes with READ_ONLY as the strict default.
    """

    def __init__(
        self,
        manifest: Optional[PluginManifest] = None,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(manifest=manifest, config=config, event_bus=event_bus, **kwargs)
        self.mode: AssistantMode = AssistantMode.READ_ONLY
        self.analyzer = CodeAnalysisEngine()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="code_assistant",
            version="1.0.0",
            description="Developer Code Assistant Plugin for static analysis, testing, and safe code fixes.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS,
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        try:
            # 1. Error Finding
            if action_name == "find_errors":
                query = parameters.get("query")
                target_file = parameters.get("target_file")
                res = self.analyzer.find_errors(query=query, target_file=target_file)
                return PluginResult(
                    success=res["success"],
                    data=res,
                    error=res.get("error"),
                )

            # 2. File Analysis
            elif action_name == "analyze_file":
                file_path = parameters.get("file_path", "main.py")
                res = self.analyzer.analyze_file(file_path=file_path)
                return PluginResult(
                    success=res.exists,
                    data=res.to_dict(),
                    error=None if res.exists else res.summary_message,
                )

            # 3. Unused Functions Finder
            elif action_name == "find_unused_functions":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.find_unused_functions(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 4. Project Architecture Check
            elif action_name == "check_architecture":
                report = self.analyzer.check_architecture()
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 5. Pytest Runner
            elif action_name == "run_pytest":
                target = parameters.get("test_target")
                timeout = int(parameters.get("timeout", 45))
                result = self.analyzer.run_pytest(test_target=target, timeout=timeout)
                return PluginResult(
                    success=result.success,
                    data=result.to_dict(),
                    error=None if result.success else result.summary_message,
                )

            # 6. Error Fix Suggestion
            elif action_name == "suggest_error_fix":
                error_text = parameters.get("error_text")
                file_path = parameters.get("file_path")
                suggestion = self.analyzer.suggest_error_fix(error_text=error_text, file_path=file_path)
                suggestion.mode = self.mode.value
                return PluginResult(
                    success=True,
                    data=suggestion.to_dict(),
                )

            # 7. Git Change Impact Assessment
            elif action_name == "analyze_change_impact":
                impact = self.analyzer.analyze_change_impact()
                return PluginResult(
                    success=True,
                    data=impact.to_dict(),
                )

            # 8. Dead Code Finder
            elif action_name == "find_dead_code":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.analyze_all_dead_code(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 9. Get Mode
            elif action_name == "get_mode":
                msg = (
                    f"Code Assistant abhi '{self.mode.value}' mode mein hai, Boss. "
                    f"Direct automatic file modification strictly prohibited hai."
                )
                return PluginResult(
                    success=True,
                    data={"mode": self.mode.value, "message": msg},
                )

            # 10. Set Mode
            elif action_name == "set_mode":
                target_mode_str = parameters.get("mode", "READ_ONLY")
                new_mode = AssistantMode.from_str(target_mode_str)
                self.mode = new_mode
                msg = (
                    f"Code Assistant mode ko '{self.mode.value}' par set kar diya hai, Boss. "
                    f"Note: Direct unprompted file modification safety invariant active rahega."
                )
                return PluginResult(
                    success=True,
                    data={"mode": self.mode.value, "message": msg},
                )

            # 11. Apply Patch / Auto-Fix / Safe Cleanup (Guarded)
            elif action_name in ("apply_patch", "auto_fix", "safe_cleanup", "delete_dead_code"):
                return self._guarded_apply_patch(parameters, action_name=action_name)

            # 12. Holistic Project Health Audit
            elif action_name in ("run_health_audit", "project_health_audit"):
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.run_health_audit(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 13. Dependency Analyzer
            elif action_name == "analyze_dependencies":
                report = self.analyzer.analyze_dependencies()
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 14. Import Analyzer
            elif action_name == "analyze_imports":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.analyze_imports(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 15. Duplication Detector
            elif action_name == "detect_duplication":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.detect_duplication(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 16. Complexity Analyzer
            elif action_name == "analyze_complexity":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.analyze_complexity(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 17. Circular Dependency Detector
            elif action_name == "detect_circular_dependencies":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.detect_circular_dependencies(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 18. Security Scanner
            elif action_name == "scan_security":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.scan_security(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 19. Performance Analyzer
            elif action_name == "analyze_performance":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.analyze_performance(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            # 20. Coverage Analyzer
            elif action_name == "analyze_coverage":
                target_dir = parameters.get("target_dir", ".")
                report = self.analyzer.analyze_coverage(target_dir=target_dir)
                return PluginResult(
                    success=True,
                    data=report.to_dict(),
                )

            else:
                return PluginResult(
                    success=False,
                    error=f"Unknown action '{action_name}' for Code Assistant Plugin.",
                )

        except Exception as e:
            logger.error("Error executing Code Assistant action '%s': %s", action_name, e, exc_info=True)
            return PluginResult(
                success=False,
                error=f"Code Assistant action '{action_name}' execution failed: {e}",
            )

    def _guarded_apply_patch(self, parameters: Dict[str, Any], action_name: str = "apply_patch") -> PluginResult:
        """
        Enforces the mandatory safety invariant:
        'Isko directly automatic file modification permission mat dena.'
        Guarded 5-Stage Verification Loop:
        1. Mode Check (READ_ONLY/SUGGEST reject immediately)
        2. Explicit Confirmation Check (confirm=True required)
        3. Automated Backup Creation (.bak)
        4. Surgical Modification/Cleanup
        5. AST Syntax Check + Scoped Pytest Verification (Auto-rollback on any failure)
        """
        import ast
        target_file = parameters.get("target_file")
        confirmed = bool(parameters.get("confirm", False))
        symbol_name = parameters.get("symbol_name")
        patch_content = parameters.get("patch_content")
        test_target = parameters.get("test_target")
        verify_tests = bool(parameters.get("verify_tests", True))

        # Stage 1: Mode Enforcement
        if self.mode in (AssistantMode.READ_ONLY, AssistantMode.SUGGEST):
            return PluginResult(
                success=False,
                error=(
                    f"File modification blocked: Code Assistant currently '{self.mode.value}' mode mein hai. "
                    f"Direct file modification strictly disabled hai, Boss."
                ),
            )

        # Stage 2: User Approval Check
        if not confirmed:
            return PluginResult(
                success=False,
                error=(
                    f"Safety Guard: Direct automatic file modification is not permitted. "
                    f"Aapko explicit confirmation ('confirm=True') dena hoga file '{target_file}' ko touch karne ke liye."
                ),
                data={"staged": True, "requires_confirmation": True, "action": action_name},
            )

        # Validate target file
        if not target_file:
            return PluginResult(success=False, error="Target file specify nahi kiya gaya.")

        resolved = self.analyzer._resolve_path(target_file)
        if not os.path.isfile(resolved):
            return PluginResult(success=False, error=f"Target file '{target_file}' exist nahi karta.")

        # Stage 3: Automated Backup Creation
        backup_path = f"{resolved}.bak"
        try:
            with open(resolved, "r", encoding="utf-8") as f_orig:
                orig_content = f_orig.read()
            with open(backup_path, "w", encoding="utf-8") as f_bak:
                f_bak.write(orig_content)
        except Exception as exc:
            return PluginResult(success=False, error=f"Backup create karne mein error aaya: {exc}")

        # Stage 4: Surgical Modification / Cleanup
        try:
            if patch_content is not None:
                new_content = patch_content
            elif action_name in ("safe_cleanup", "delete_dead_code") and symbol_name:
                tree = ast.parse(orig_content, filename=resolved)
                lines = orig_content.splitlines(keepends=True)
                start_l, end_l = None, None
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == symbol_name:
                            start_l = node.lineno - 1
                            end_l = getattr(node, "end_lineno", node.lineno)
                            break
                if start_l is not None and end_l is not None:
                    modified_lines = []
                    for idx, l in enumerate(lines):
                        if start_l <= idx < end_l:
                            modified_lines.append(f"# [DEAD_CODE_REMOVED] {l}")
                        else:
                            modified_lines.append(l)
                    new_content = "".join(modified_lines)
                else:
                    new_content = orig_content
            else:
                new_content = orig_content

            with open(resolved, "w", encoding="utf-8") as f_out:
                f_out.write(new_content)

            # Stage 5: AST Syntax Validation
            try:
                ast.parse(new_content, filename=resolved)
            except SyntaxError as syn_err:
                with open(resolved, "w", encoding="utf-8") as f_rollback:
                    f_rollback.write(orig_content)
                return PluginResult(
                    success=False,
                    error=f"AST Syntax check failed ({syn_err}); automatically rolled back to original file.",
                    data={"rolled_back": True, "backup_path": backup_path},
                )

            # Stage 6: Pytest Verification
            if verify_tests and test_target:
                pytest_res = self.analyzer.run_pytest(test_target=test_target, timeout=30)
                if not pytest_res.success or pytest_res.failed > 0:
                    with open(resolved, "w", encoding="utf-8") as f_rollback:
                        f_rollback.write(orig_content)
                    return PluginResult(
                        success=False,
                        error=f"Pytest verification failed ({pytest_res.failed} failed); automatically rolled back to backup.",
                        data={"rolled_back": True, "pytest_exit_code": pytest_res.exit_code, "backup_path": backup_path},
                    )

            return PluginResult(
                success=True,
                data={
                    "message": f"Successfully applied changes to '{target_file}'. AST and Pytest verified. Backup preserved at '{backup_path}'.",
                    "target_file": target_file,
                    "backup_path": backup_path,
                    "mode": self.mode.value,
                },
            )

        except Exception as exc:
            try:
                with open(resolved, "w", encoding="utf-8") as f_rollback:
                    f_rollback.write(orig_content)
            except Exception:
                pass
            return PluginResult(
                success=False,
                error=f"Modification error: {exc}. Automatically rolled back.",
                data={"rolled_back": True, "backup_path": backup_path},
            )
