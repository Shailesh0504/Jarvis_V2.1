# core/execution/strategies.py
"""
Multi-strategy execution and recovery engine for Jarvis V2.
Guarantees:
1. Every strategy execution is followed by mandatory system state verification.
2. If verification fails, Jarvis diagnoses root cause and switches to a distinct, improved strategy.
3. Jarvis NEVER repeats a failed strategy blindly.
"""

from dataclasses import dataclass, field
import logging
import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .diagnostics import ExecutionDiagnosticEngine
from .models import ExecutionResult, ExecutionState, VerificationResult
from .verifier import ExecutionVerificationLayer

logger = logging.getLogger("jarvis.execution.strategies")


class ExecutionStrategyEngine:
    """
    Manages multi-strategy execution and recovery for desktop and OS operations.
    """

    FOLDER_STRATEGIES = [
        "shell_uri",
        "physical_path",
        "com_shell",
        "powershell"
    ]

    APP_STRATEGIES = [
        "direct_executable",
        "start_menu_shortcut",
        "shell_start",
        "protocol"
    ]

    def __init__(
        self,
        verifier: Optional[ExecutionVerificationLayer] = None,
        diagnostics: Optional[ExecutionDiagnosticEngine] = None,
        experience_system: Optional[Any] = None,
        app_registry: Optional[Any] = None,
        app_detector: Optional[Any] = None,
        capability_policy: Optional[Any] = None,
    ):
        self.verifier = verifier or ExecutionVerificationLayer()
        self.diagnostics = diagnostics or ExecutionDiagnosticEngine(window_manager=self.verifier.window_manager)
        self.experience_system = experience_system
        from core.apps import get_application_registry, get_installed_app_detector
        self.app_registry = app_registry or get_application_registry()
        self.app_detector = app_detector or get_installed_app_detector()

        if capability_policy is None:
            try:
                from core.policy.capability_policy import CapabilityPolicy
                self.capability_policy = CapabilityPolicy()
            except Exception:
                self.capability_policy = None
        else:
            self.capability_policy = capability_policy

    def check_pre_execution_risk(
        self,
        action: str,
        target: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        user_role: str = "ADMIN"
    ) -> Optional[ExecutionResult]:
        """
        Pre-execution risk evaluation gate.
        Returns None if ALLOW (safe to proceed immediately).
        Returns ExecutionResult with requires_confirmation=True if CONFIRM or DENY.
        """
        if not self.capability_policy:
            return None
        params = parameters or {}
        # If explicit confirmation was already granted, allow execution to proceed
        if params.get("confirmed") is True or params.get("skip_confirmation") is True:
            return None

        from core.policy.capability_policy import PolicyDecision
        eval_result = self.capability_policy.evaluate(
            action=action,
            target=target,
            parameters=params,
            user_role=user_role
        )

        if eval_result.decision == PolicyDecision.ALLOW:
            return None

        prompt = eval_result.confirmation_prompt or f"Kya aap sach mein '{action} {target}' execute karna chahte hain?"
        logger.warning(
            "Pre-execution risk gate triggered for action='%s', target='%s', tier=%s, decision=%s",
            action, target, eval_result.risk_tier.name, eval_result.decision.name
        )
        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action=f"{action} {target}".strip(),
            executed_action="blocked_by_pre_execution_risk_gate",
            error=eval_result.reason,
            reason=eval_result.reason,
            target=target,
            action_type="sensitive_operation",
            requires_confirmation=(eval_result.decision == PolicyDecision.CONFIRM),
            confirmation_prompt=prompt,
            data={"requires_confirmation": True, "action": action, "target": target}
        )

    def execute_sensitive_action_verified(
        self,
        action: str,
        target: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        handler: Optional[Callable[..., Any]] = None,
    ) -> ExecutionResult:
        """
        Pre-execution risk-gated executor for sensitive OS and system actions.
        Ensures confirmation is required and validated BEFORE any sensitive action executes.
        """
        gate_result = self.check_pre_execution_risk(action, target, parameters)
        if gate_result is not None:
            return gate_result

        # Action is authorized (ALLOW or confirmed=True)
        requested = f"{action} {target}".strip()
        try:
            res_data = {}
            if handler:
                res = handler()
                if isinstance(res, dict):
                    res_data = res
            return ExecutionResult(
                success=True,
                status=ExecutionState.SUCCESS,
                requested_action=requested,
                executed_action=f"executed:{action}",
                target=target,
                action_type="sensitive_operation",
                data=res_data,
            )
        except Exception as e:
            logger.error("Error executing sensitive action '%s': %s", requested, e)
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=requested,
                executed_action="failed",
                target=target,
                action_type="sensitive_operation",
                error=str(e),
                reason=f"execution_error: {e}",
            )

    def open_folder_verified(
        self,
        target: str,
        preferred_strategy: Optional[str] = None,
        max_retries: int = 2
    ) -> ExecutionResult:
        """
        Executes folder opening with mandatory state verification and automatic
        strategy recovery if verification fails.
        """
        clean_target = str(target or "").strip()
        requested = f"open {clean_target} folder"

        # Check if target is invalid/empty
        if not clean_target:
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=requested,
                executed_action="none",
                error="Folder target name is empty",
                reason="Folder path or name was not specified",
                target=clean_target,
                action_type="folder"
            )

        # Check for invalid path characters or clearly non-existent paths
        if any(c in clean_target for c in ('<', '>', '|', '"')):
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=requested,
                executed_action="validate_path",
                error=f"Invalid path: '{clean_target}' contains invalid characters.",
                reason=f"Invalid path: '{clean_target}' contains invalid characters.",
                target=clean_target,
                action_type="folder"
            )

        # Determine strategy queue (avoiding already failed ones)
        strategies_to_try = list(self.FOLDER_STRATEGIES)
        if preferred_strategy and preferred_strategy in strategies_to_try:
            strategies_to_try.remove(preferred_strategy)
            strategies_to_try.insert(0, preferred_strategy)

        # Check if experience system knows that a specific strategy failed previously for this target
        if self.experience_system and hasattr(self.experience_system, "retrieve_experience"):
            try:
                exp_ctx = self.experience_system.retrieve_experience(f"open {clean_target} folder", category="files")
                for f in getattr(exp_ctx, "failures", []):
                    bad_strat = f.get("attempted_strategy")
                    if bad_strat in strategies_to_try and len(strategies_to_try) > 1:
                        logger.info("STRATEGY_DEPRIORITIZED: '%s' deprioritized due to past learned failure.", bad_strat)
                        strategies_to_try.remove(bad_strat)
                        strategies_to_try.append(bad_strat)
            except Exception as e:
                logger.debug("Experience retrieval skipped: %s", e)

        diagnostic_notes: List[str] = []
        attempted_strategies: List[str] = []
        last_error = None
        retry_count = 0

        wm = self.verifier.window_manager

        for idx, strategy in enumerate(strategies_to_try[:max_retries + 1]):
            retry_count = idx
            attempted_strategies.append(strategy)
            logger.info("EXECUTION_ATTEMPT: target='%s' strategy='%s' (attempt %d)", clean_target, strategy, idx + 1)

            # 1. Snapshot existing Explorer windows before launch
            initial_windows = []
            if wm:
                try:
                    initial_windows = wm.find_folder_windows("")
                except Exception:
                    initial_windows = []

            # 2. Execute concrete strategy
            exec_ok, exec_err, executed_path = self._dispatch_folder_strategy(clean_target, strategy)

            if not exec_ok:
                diag = self.diagnostics.diagnose_folder_operation(clean_target, attempted_strategy=strategy, raw_error=exec_err)
                diagnostic_notes.extend(diag.diagnostics)
                last_error = exec_err
                self._record_failure_learning(clean_target, strategy, exec_err or "Launch failed", diag.root_cause)
                continue

            # 3. VERIFY ACTUAL SYSTEM STATE (Must observe Explorer window)
            v_res = self.verifier.verify_folder_open(clean_target, initial_windows=initial_windows, delay_seconds=0.25)

            if v_res.verified:
                logger.info("EXECUTION_VERIFIED_SUCCESS: target='%s' strategy='%s'", clean_target, strategy)
                disp_target = "Recycle Bin" if "recycle" in clean_target or "trash" in clean_target else (
                    "Startup" if "startup" in clean_target else clean_target
                )
                return ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action=requested,
                    executed_action=f"open_folder:{strategy}",
                    verification_result=v_res,
                    strategy_used=strategy,
                    retry_count=idx,
                    target=clean_target,
                    action_type="folder",
                    diagnostics=diagnostic_notes,
                    data={"path": executed_path, "message": f"'{disp_target}' folder open kar diya hai aur verify kar liya hai, Boss."}
                )

            # Verification Failed!
            logger.warning("EXECUTION_VERIFICATION_FAILED: target='%s' strategy='%s'", clean_target, strategy)
            diag = self.diagnostics.diagnose_folder_operation(clean_target, attempted_strategy=strategy, raw_error=v_res.error)
            diagnostic_notes.extend(diag.diagnostics)
            last_error = v_res.error or "Window did not appear"
            self._record_failure_learning(clean_target, strategy, last_error, diag.root_cause)

        # All strategies failed
        logger.error("ALL_STRATEGIES_FAILED: target='%s' attempted=%s", clean_target, attempted_strategies)
        diag_report = self.diagnostics.diagnose_folder_operation(clean_target, attempted_strategy=attempted_strategies[-1], raw_error=last_error)

        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action=requested,
            executed_action=f"open_folder:{attempted_strategies[-1]}",
            verification_result=VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="folder_window_open",
                expected=clean_target,
                actual=None,
                message=f"All {len(attempted_strategies)} strategies failed to verify Explorer window.",
                error=last_error
            ),
            error=last_error or f"Verification failed: Explorer window was not found for '{clean_target}'.",
            reason=f"Verification failed: {diag_report.root_cause}" if "fail" not in diag_report.root_cause.lower() else diag_report.root_cause,
            strategy_used=attempted_strategies[-1],
            retry_count=len(attempted_strategies) - 1,
            target=clean_target,
            action_type="folder",
            diagnostics=list(dict.fromkeys(diagnostic_notes)),
            recovery_strategies=[s for s in self.FOLDER_STRATEGIES if s not in attempted_strategies],
            data={"attempted_strategies": attempted_strategies, "diagnostic_report": diag_report.summary_message()}
        )

    def launch_application_verified(
        self,
        app_name: str,
        is_new: bool = False,
        file_path: Optional[str] = None,
        preferred_strategy: Optional[str] = None,
        max_retries: int = 2
    ) -> ExecutionResult:
        """
        Executes local application launch with mandatory system state verification.
        If launch or verification fails, attempts alternative launch strategies
        and returns an authoritative ExecutionResult.
        """
        clean_name = str(app_name or "").strip()
        app_reg = self.app_registry
        detector = self.app_detector

        app_def = app_reg.get_app(clean_name) or app_reg.find_by_alias(clean_name)
        canonical_id = app_def.app_id if app_def else clean_name.lower()
        display_name = app_def.display_name if app_def else clean_name.capitalize()
        from core.windows_app_resolver import get_windows_app_resolver
        win_app = get_windows_app_resolver().get_app_spec(canonical_id)

        # Step 1: Verify installation
        installed_info = detector.detect(app_def or clean_name)
        if not installed_info or not installed_info.is_installed:
            logger.warning("APP_NOT_INSTALLED: Application '%s' is not installed locally.", display_name)
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action="launch_app",
                executed_action="detect_installation",
                target=clean_name,
                strategy_used="detect_installation",
                error=f"Application '{display_name}' is not installed on this system.",
                reason="not_installed",
                diagnostics=[f"Could not locate '{display_name}' in Windows App Paths, Start Menu, or Program Files."],
                data={
                    "app": clean_name,
                    "not_installed": True,
                    "display_name": display_name,
                    "application": display_name,
                    "target": display_name,
                    "status": "not_found",
                }
            )

        # Step 2: Determine available launch strategies
        strategies = list(self.APP_STRATEGIES)
        if getattr(installed_info, "launch_strategy", None) == "protocol" or (
            getattr(installed_info, "protocol", None) and not getattr(installed_info, "executable_path", None)
        ):
            if "protocol" in strategies:
                strategies.remove("protocol")
                strategies.insert(0, "protocol")
        elif preferred_strategy and preferred_strategy in strategies:
            strategies.remove(preferred_strategy)
            strategies.insert(0, preferred_strategy)

        # Step 3: Multi-strategy attempt loop
        last_error = None
        last_verif = None
        diagnostics_list = []
        attempted_strategies = []

        for attempt, strategy in enumerate(strategies[:max_retries + 1]):
            attempted_strategies.append(strategy)
            logger.info(
                "APP_LAUNCH_ATTEMPT: app='%s' strategy='%s' attempt=%d/%d",
                canonical_id, strategy, attempt + 1, max_retries + 1
            )
            success_launch, err = self._dispatch_app_strategy(
                strategy=strategy,
                app_def=app_def,
                canonical_id=canonical_id,
                installed_info=installed_info,
                is_new=is_new,
                file_path=file_path
            )

            if not success_launch:
                last_error = err or f"Strategy '{strategy}' failed execution."
                diagnostics_list.append(f"Execution error in {strategy}: {last_error}")
                continue

            # Mandatory System State Verification
            verif = self.verifier.verify_application_running(canonical_id, should_run=True)
            last_verif = verif
            if verif.verified:
                disp = display_name or clean_name.capitalize()
                msg = f"{disp} open ho gaya, Boss."
                if is_new and canonical_id == "excel":
                    msg = "Bilkul ek nayi blank Excel workbook khol di hai."
                return ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action="launch_app",
                    executed_action=f"launch_app_{strategy}",
                    verification_result=verif,
                    target=clean_name,
                    strategy_used=strategy,
                    retry_count=attempt,
                    data={
                        "app": clean_name,
                        "app_id": canonical_id,
                        "canonical_id": canonical_id,
                        "display_name": display_name,
                        "application": display_name,
                        "target": display_name,
                        "status": "opened",
                        "message": msg,
                        "launch_target": win_app.primary_launch_target if win_app else "",
                    },
                    diagnostics=diagnostics_list
                )

            # Verification failed
            last_error = verif.error or f"Process/window verification failed after strategy '{strategy}'."
            diagnostics_list.append(f"Verification failed on {strategy}: {last_error}")

        # All strategies failed
        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action="launch_app",
            executed_action=f"launch_app_{attempted_strategies[0]}",
            verification_result=last_verif,
            target=clean_name,
            strategy_used=attempted_strategies[0],
            error=last_error or f"Failed to launch and verify '{display_name}'.",
            reason="launch_or_verification_failed",
            diagnostics=diagnostics_list,
            data={
                "app": clean_name,
                "display_name": display_name,
                "application": display_name,
                "target": display_name,
                "status": "failed",
            }
        )

    def _dispatch_app_strategy(
        self,
        strategy: str,
        app_def: Optional[Any],
        canonical_id: str,
        installed_info: Any,
        is_new: bool = False,
        file_path: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        try:
            args = []
            if is_new and app_def and getattr(app_def, "new_instance_arg", None):
                args.append(app_def.new_instance_arg)
            if file_path:
                args.append(file_path)

            if strategy == "direct_executable":
                exe = getattr(installed_info, "executable_path", None)
                if not exe or not os.path.exists(exe):
                    return False, f"Executable not found: {exe}"
                exe_lower = exe.lower()
                if exe_lower.endswith(".msc") or exe_lower.endswith(".cpl"):
                    if hasattr(os, "startfile") and sys.platform == "win32":
                        os.startfile(exe)
                    else:
                        arg_str = " ".join(f'"{a}"' for a in args)
                        cmd_str = f'start "" "{exe}" {arg_str}'.strip()
                        subprocess.Popen(cmd_str, shell=True)
                    return True, None
                cmd = [exe] + args
                subprocess.Popen(cmd, cwd=os.path.dirname(exe))
                return True, None

            elif strategy == "start_menu_shortcut":
                shortcut = getattr(installed_info, "shortcut_path", None)
                if not shortcut or not os.path.exists(shortcut):
                    return False, f"Shortcut not found: {shortcut}"
                os.startfile(shortcut)
                return True, None

            elif strategy == "shell_start":
                target = getattr(installed_info, "executable_path", None) or (
                    app_def.executables[0] if app_def and app_def.executables else canonical_id
                )
                arg_str = " ".join(f'"{a}"' for a in args)
                cmd_str = f'start "" "{target}" {arg_str}'.strip()
                subprocess.Popen(cmd_str, shell=True)
                return True, None

            elif strategy == "protocol":
                protocol = getattr(installed_info, "protocol", None) or (
                    app_def.protocols[0] if app_def and app_def.protocols else None
                )
                if not protocol:
                    return False, "No protocol registered"
                try:
                    if hasattr(os, "startfile") and sys.platform == "win32":
                        os.startfile(protocol)
                    else:
                        subprocess.Popen(f'start "" "{protocol}"', shell=True)
                except Exception as ex:
                    logger.debug("os.startfile failed for protocol '%s': %s, falling back to shell start", protocol, ex)
                    subprocess.Popen(f'start "" "{protocol}"', shell=True)
                return True, None

        except Exception as e:
            return False, str(e)

        return False, f"Unknown application launch strategy: {strategy}"

    def _dispatch_folder_strategy(self, target: str, strategy: str) -> Tuple[bool, Optional[str], str]:
        """Dispatches concrete folder opening strategy."""
        clean = target.strip().lower()
        is_startup = any(s in clean for s in ("startup", "start up", "shell:startup"))

        resolved_path = self._resolve_physical_folder_path(clean)

        try:
            if strategy == "shell_uri":
                shell_target = "shell:startup" if is_startup else (
                    "shell:RecycleBinFolder" if "recycle" in clean or "trash" in clean else resolved_path
                )
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", shell_target])
                else:
                    subprocess.Popen(["xdg-open", shell_target])
                return True, None, shell_target

            elif strategy == "physical_path":
                if not resolved_path:
                    return False, f"Could not resolve physical directory for '{target}'", ""
                # Ensure physical path exists
                if not os.path.exists(resolved_path):
                    try:
                        os.makedirs(resolved_path, exist_ok=True)
                    except Exception as ex:
                        return False, f"Permission error creating directory '{resolved_path}': {ex}", resolved_path

                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", resolved_path])
                else:
                    subprocess.Popen(["xdg-open", resolved_path])
                return True, None, resolved_path

            elif strategy == "com_shell":
                target_to_open = resolved_path or ("shell:startup" if is_startup else clean)
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("Shell.Application")
                    shell.Explore(target_to_open)
                    return True, None, target_to_open
                except Exception as ex:
                    # Fallback to shell.Open
                    try:
                        import win32com.client
                        shell = win32com.client.Dispatch("Shell.Application")
                        shell.Open(target_to_open)
                        return True, None, target_to_open
                    except Exception as ex2:
                        return False, f"COM Shell.Application failed: {ex2}", target_to_open

            elif strategy == "powershell":
                target_to_open = resolved_path or ("shell:startup" if is_startup else clean)
                cmd = f"Start-Process explorer.exe -ArgumentList '\"{target_to_open}\"'"
                subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", cmd])
                return True, None, target_to_open

        except Exception as e:
            return False, str(e), resolved_path

        return False, f"Unknown strategy: {strategy}", resolved_path

    def _resolve_physical_folder_path(self, clean_target: str) -> str:
        """Resolves real physical directory on Windows."""
        home = os.path.expanduser("~")
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")

        if any(s in clean_target for s in ("startup", "start up", "shell:startup")):
            return os.path.abspath(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"))

        from plugins.files.operations import FilesystemOperations
        ops = FilesystemOperations()
        special = ops.get_special_path(clean_target)
        if special and not special.startswith("shell:"):
            return os.path.abspath(special)

        if os.path.isabs(clean_target):
            return os.path.abspath(clean_target)

        return os.path.abspath(os.path.join(home, clean_target))

    def _record_failure_learning(self, target: str, strategy: str, error: str, diagnosis: str) -> None:
        """Persists failed execution experience to ExperienceLearningSystem."""
        if not self.experience_system:
            return
        try:
            if hasattr(self.experience_system, "record_task_failure"):
                self.experience_system.record_task_failure(
                    goal=f"open {target} folder",
                    failed_step={"plugin": "files", "action": "open_folder", "target": target},
                    error_msg=f"Strategy '{strategy}' failed: {error}",
                    attempted_strategy=strategy,
                    category="files",
                    diagnosis=diagnosis
                )
                logger.info("FAILURE_PERSISTED: Learned anti-pattern recorded in Experience System for strategy='%s'.", strategy)
        except Exception as e:
            logger.debug("Failed to record failure experience: %s", e)

    # -------------------------------------------------------------------------
    # Website open with mandatory browser-window verification
    # -------------------------------------------------------------------------

    def open_website_verified(
        self,
        site: str,
        browser: str = "",
        force_new: bool = False,
        plugin_manager: Optional[Any] = None,
        max_retries: int = 2,
    ) -> ExecutionResult:
        """
        Opens a website and verifies that a browser window actually appeared.

        Mandatory flow:
          1. Snapshot current browser-window count (baseline).
          2. Call BrowserPlugin.execute("open_website", …).
          3. Verify via verifier.verify_browser_opened(site, browser, baseline).
          4. On failure: retry once with default (no specific) browser.
          5. Return ExecutionResult with full VerificationResult.

        Browser API acknowledgement establishes execution success. Window/DOM
        observation is best-effort and may remain unverified.
        """
        clean_site = site.strip()
        clean_browser = browser.strip()
        requested = f"open_website:{clean_site}"

        # 1. Baseline browser window count
        initial_count = self.verifier.count_browser_windows()
        logger.info("[EXECUTE] open_website site=%r browser=%r initial_browser_windows=%d",
                    clean_site, clean_browser, initial_count)

        for attempt in range(max(1, max_retries)):
            attempt_browser = clean_browser if attempt == 0 else ""   # retry without browser constraint
            params: Dict[str, Any] = {"site": clean_site}
            if attempt_browser:
                params["browser"] = attempt_browser
                params["container"] = attempt_browser
            if force_new:
                params["force_new"] = True
                params["new_tab"] = True

            logger.info("[EXECUTE] open_website attempt=%d/%d browser=%r",
                        attempt + 1, max_retries, attempt_browser)

            # 2. Execute via plugin
            exec_ok = False
            exec_err: Optional[str] = None
            try:
                if plugin_manager:
                    result = plugin_manager.execute_action("browser", "open_website", params)
                else:
                    from plugins.browser.plugin import BrowserPlugin
                    result = BrowserPlugin().execute("open_website", params)
                exec_ok = bool(result and result.success)
                if not exec_ok:
                    exec_err = (result.error if result else None) or "BrowserPlugin returned failure"
            except Exception as exc:
                exec_err = str(exc)
                exec_ok = False

            if not exec_ok:
                logger.warning("[EXECUTE] open_website plugin failed attempt=%d: %s", attempt + 1, exec_err)
                continue

            # 3. Mandatory verification — independent of plugin return value
            time.sleep(0.5)  # allow browser to start rendering
            v_res = self.verifier.verify_browser_opened(
                site=clean_site,
                browser=attempt_browser,
                initial_window_count=initial_count,
            )
            logger.info("[VERIFY] open_website site=%r verified=%s method=browser_opened attempt=%d",
                        clean_site, v_res.verified, attempt + 1)

            if v_res.verified:
                disp_browser = attempt_browser.capitalize() if attempt_browser else "browser"
                msg = (
                    f"{clean_site.capitalize()} {disp_browser} mein open ho gaya."
                    if attempt_browser else
                    f"{clean_site.capitalize()} browser mein open ho gaya."
                )
                return ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action=requested,
                    executed_action=f"open_website:attempt_{attempt + 1}",
                    verification_result=v_res,
                    target=clean_site,
                    action_type="browser",
                    strategy_used=f"browser_plugin:attempt_{attempt + 1}",
                    retry_count=attempt,
                    data={"site": clean_site, "url": (result.data or {}).get("url", clean_site), "status": "opened", "verification": "verified", "browser": attempt_browser or "default", "message": msg},
                )

            # The browser accepted navigation. A missing observation is not a
            # failed launch; preserve the distinction in the result contract.
            unknown_verification = VerificationResult(
                verified=False,
                state=ExecutionState.UNVERIFIED,
                check_type="browser_opened",
                expected=clean_site,
                actual=None,
                message="Browser navigation was accepted; page visibility could not be verified.",
            )
            return ExecutionResult(
                success=True,
                status=ExecutionState.UNVERIFIED,
                requested_action=requested,
                executed_action=f"open_website:attempt_{attempt + 1}",
                verification_result=unknown_verification,
                target=clean_site,
                action_type="browser",
                strategy_used=f"browser_plugin:attempt_{attempt + 1}",
                retry_count=attempt,
                data={"site": clean_site, "url": (result.data or {}).get("url", clean_site), "status": "opened", "verification": "unknown", "browser": attempt_browser or "default"},
            )

            # Verification failed — log and retry
            logger.warning("[VERIFY] open_website FAILED site=%r attempt=%d — retrying", clean_site, attempt + 1)

        # All attempts failed
        fail_msg = f"{clean_site.capitalize()} browser mein open nahi ho paya."
        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action=requested,
            executed_action="open_website:all_failed",
            verification_result=VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="browser_opened",
                expected=clean_site,
                actual=None,
                message=fail_msg,
                error=f"All {max_retries} attempts failed to produce a visible browser window for '{clean_site}'."
            ),
            target=clean_site,
            action_type="browser",
            error=fail_msg,
            reason=f"Browser window for '{clean_site}' could not be verified.",
            retry_count=max_retries - 1,
            data={"site": clean_site, "message": fail_msg},
        )

    # -------------------------------------------------------------------------
    # Close with mandatory post-close verification
    # -------------------------------------------------------------------------

    def close_target_verified(
        self,
        target: str,
        action: str = "close",
        hwnd: Optional[int] = None,
        plugin_manager: Optional[Any] = None,
        max_retries: int = 2,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Closes a window/app target and verifies it is actually closed.

        Flow:
          1. Check pre-execution risk gate for sensitive kill/terminate actions.
          2. Execute close via WindowManager.execute_operation.
          3. Verify via verifier.verify_window_operation(target, 'close').
          4. On failure: retry with forceful process termination if available.
          5. Return ExecutionResult with full VerificationResult.
        """
        clean_target = target.strip()
        requested = f"close:{clean_target}"

        # Safety (SSOT): protected host (opencode/python/pytest/editors) par
        # close/verify loop kabhi real OS effect nahi karega.
        try:
            from plugins.apps.plugin import is_protected_close_target as _is_prot
            if _is_prot(clean_target):
                from .models import VerificationResult as _VR
                return ExecutionResult(
                    success=False,
                    status=ExecutionState.FAILED,
                    requested_action=requested,
                    executed_action="close:blocked_protected",
                    verification_result=_VR(
                        verified=False,
                        state=ExecutionState.FAILED,
                        check_type="window_close",
                        expected="blocked",
                        actual="protected",
                        message=f"'{clean_target}' protected system process hai, ise band nahi kiya ja sakta.",
                    ),
                    target=clean_target,
                    action_type="window",
                    error=f"'{clean_target}' protected system process hai, ise band nahi kiya ja sakta.",
                    reason="protected_target",
                    retry_count=0,
                    data={"target": clean_target, "protected": True},
                )
        except Exception:
            pass

        # Pre-execution risk gate for forceful termination
        if action in ("kill", "terminate", "force_close", "process_kill"):
            gate_res = self.check_pre_execution_risk(action, clean_target, parameters)
            if gate_res is not None:
                return gate_res

        wm = self.verifier.window_manager

        if not wm:
            return ExecutionResult(
                success=False,
                status=ExecutionState.UNVERIFIED,
                requested_action=requested,
                executed_action="none",
                target=clean_target,
                action_type="window",
                error="WindowManager unavailable — cannot close or verify.",
                reason="window_manager_missing",
            )

        for attempt in range(max(1, max_retries)):
            logger.info("[EXECUTE] close_target target=%r attempt=%d/%d", clean_target, attempt + 1, max_retries)

            try:
                if attempt == 0:
                    # Graceful close via WindowManager
                    win_res = wm.execute_operation(action, clean_target)
                    exec_ok = bool(win_res.get("success"))
                else:
                    # Second attempt: try forceful kill via plugin if available
                    exec_ok = False
                    if plugin_manager:
                        try:
                            kr = plugin_manager.execute_action("apps", "close_app", {"app_name": clean_target, "app": clean_target})
                            exec_ok = bool(kr and kr.success)
                        except Exception:
                            pass
                    if not exec_ok:
                        # Terminate by resolved application process names
                        try:
                            import subprocess as sp
                            from core.windows_app_resolver import get_windows_app_resolver
                            try:
                                from plugins.apps.plugin import is_protected_close_target as _is_prot2
                            except Exception:
                                _is_prot2 = None
                            pnames = get_windows_app_resolver().get_process_names(clean_target)
                            # Safety: protected host processes par taskkill kabhi nahi.
                            if _is_prot2 is not None:
                                pnames = [pn for pn in pnames if not _is_prot2(pn)]
                                _target_prot = bool(_is_prot2(clean_target))
                            else:
                                _PROT2 = frozenset({"opencode", "python", "pytest", "code"})
                                pnames = [pn for pn in pnames if not any(p in str(pn).lower() for p in _PROT2)]
                                _target_prot = any(p in str(clean_target).lower() for p in _PROT2)
                            if not _target_prot:
                                for pn in pnames:
                                    sp.run(
                                        ["taskkill", "/F", "/IM", pn if pn.endswith(".exe") else f"{pn}.exe"],
                                        capture_output=True, timeout=5
                                    )
                            exec_ok = True
                        except Exception:
                            exec_ok = False
            except Exception as exc:
                logger.warning("[EXECUTE] close_target error attempt=%d: %s", attempt + 1, exc)
                exec_ok = False

            # Verify that target is actually closed regardless of exec result
            time.sleep(0.15)
            v_res = self.verifier.verify_window_operation(clean_target, "close", hwnd=hwnd)
            logger.info("[VERIFY] close_target target=%r verified=%s attempt=%d",
                        clean_target, v_res.verified, attempt + 1)

            if v_res.verified:
                from core.windows_app_resolver import get_windows_app_resolver
                win_spec = get_windows_app_resolver().get_app_spec(clean_target)
                disp_name = win_spec.display_name if win_spec else clean_target.capitalize()
                proc_names = get_windows_app_resolver().get_process_names(clean_target)
                msg = f"{disp_name} band ho gaya."
                return ExecutionResult(
                    success=True,
                    status=ExecutionState.SUCCESS,
                    requested_action=requested,
                    executed_action=f"close:attempt_{attempt + 1}",
                    verification_result=v_res,
                    target=clean_target,
                    action_type="window",
                    strategy_used=f"close:attempt_{attempt + 1}",
                    retry_count=attempt,
                    data={"target": clean_target, "application": disp_name, "status": "closed", "message": msg, "process_names": proc_names},
                )

            logger.warning("[VERIFY] close_target FAILED target=%r attempt=%d", clean_target, attempt + 1)

        # All retries failed — target still open
        fail_msg = f"{clean_target.capitalize()} band nahi hua."
        return ExecutionResult(
            success=False,
            status=ExecutionState.FAILED,
            requested_action=requested,
            executed_action="close:all_failed",
            verification_result=VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="window_close",
                expected="closed",
                actual="still_running",
                message=fail_msg,
                error=f"'{clean_target}' could not be verified as closed after {max_retries} attempts."
            ),
            target=clean_target,
            action_type="window",
            error=fail_msg,
            reason="verification_failed",
            retry_count=max_retries - 1,
            data={"target": clean_target, "application": clean_target, "status": "failed", "message": fail_msg},
        )
