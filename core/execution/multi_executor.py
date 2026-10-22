# core/execution/multi_executor.py
"""
Multi-Action Execution and Universal Verification Coordinator for Jarvis V2.1.
Executes each ActionItem in a MultiActionPlan sequentially with verification:
UNDERSTAND -> EXECUTE -> VERIFY -> RECOVER -> REPORT.
Synthesizes honest, natural Hinglish feedback across all executed targets.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
from core.execution.strategies import ExecutionStrategyEngine
from core.execution.verifier import ExecutionVerificationLayer
from core.semantic.multi_entity import ActionItem, MultiActionPlan
from core.target_engine import TargetRequest, UniversalTargetDiscoveryEngine

logger = logging.getLogger("jarvis.execution.multi")


class MultiActionExecutor:
    """
    Coordinates verified sequential execution for multi-entity action plans.
    Guarantees every action is verified on OS state before claiming success.
    """

    def __init__(
        self,
        strategy_engine: Optional[ExecutionStrategyEngine] = None,
        target_engine: Optional[UniversalTargetDiscoveryEngine] = None,
        verifier: Optional[ExecutionVerificationLayer] = None,
        plugin_manager: Optional[Any] = None,
    ) -> None:
        self.strategy_engine = strategy_engine or ExecutionStrategyEngine()
        self.target_engine = target_engine or UniversalTargetDiscoveryEngine()
        self.verifier = verifier or getattr(self.strategy_engine, "verifier", None) or ExecutionVerificationLayer()
        self.plugin_manager = plugin_manager

    def execute_plan(
        self, plan: MultiActionPlan, active_context: Optional[Any] = None
    ) -> Tuple[bool, str, List[ExecutionResult]]:
        """
        Executes each ActionItem in the plan sequentially.
        Returns:
            (all_succeeded, synthesized_response_message, list_of_execution_results)
        """
        if not plan.actions:
            return False, "Koi action plan nahi mila, Boss.", []

        logger.info(
            "MULTI_ACTION_EXECUTION_START total_steps=%d global_action=%s",
            len(plan.actions),
            plan.global_action,
        )

        results: List[Tuple[ActionItem, ExecutionResult]] = []

        for idx, item in enumerate(plan.actions, start=1):
            logger.info(
                "EXECUTING_STEP %d/%d: action=%s target=%s entity_type=%s container=%s",
                idx,
                len(plan.actions),
                item.action,
                item.target,
                item.entity_type,
                item.container,
            )

            res = self._execute_single_item(item)
            results.append((item, res))

            # Update active context if successful
            if res.success and active_context:
                try:
                    if item.entity_type in ("website", "browser"):
                        active_context.set_website(item.target, action="open_website")
                    elif item.entity_type in ("application", "system_tool"):
                        active_context.set_application(item.target, action="launch_app")
                except Exception:
                    pass

            # Small delay between multiple launches to allow OS dispatch
            if idx < len(plan.actions):
                time.sleep(0.15)

        # Segregate verified successes and failures
        succeeded_items: List[str] = []
        failed_items: List[str] = []

        for item, res in results:
            is_verified = (
                res.success
                and res.verification_result is not None
                and res.verification_result.verified
            )
            item_label = f"{item.display_name} ({item.container.capitalize()})" if item.container else item.display_name
            if is_verified:
                succeeded_items.append(item_label)
            else:
                failed_items.append(item_label)

        all_success = len(failed_items) == 0 and len(succeeded_items) > 0
        response_msg = self._synthesize_response(
            plan.global_action, succeeded_items, failed_items
        )

        logger.info(
            "MULTI_ACTION_EXECUTION_FINISH all_success=%s succeeded=%s failed=%s",
            all_success,
            succeeded_items,
            failed_items,
        )

        return all_success, response_msg, [r for _, r in results]

    def _execute_single_item(self, item: ActionItem) -> ExecutionResult:
        """Executes a single ActionItem using the appropriate verified strategy."""
        action = item.action.lower().strip()
        target = item.target.lower().strip()
        entity_type = item.entity_type.lower().strip()

        try:
            # 1. Open Actions
            if action in ("open", "launch", "start", "run"):
                if entity_type == "website":
                    return self.strategy_engine.open_website_verified(
                        site=target,
                        browser=item.container or "",
                        plugin_manager=self.plugin_manager,
                    )
                elif entity_type == "folder":
                    return self.strategy_engine.open_folder_verified(target=target)
                else:
                    # Application, browser executable, or system tool
                    return self.strategy_engine.launch_application_verified(
                        app_name=target,
                        is_new=item.is_new,
                    )

            # 2. Close Actions
            elif action in ("close", "band"):
                if entity_type in ("website", "browser_tab") or item.container:
                    outcome = self.target_engine.execute(
                        TargetRequest(target=target, action="close", container=item.container or "")
                    )
                    state = ExecutionState.SUCCESS if outcome.success and outcome.verified else ExecutionState.FAILED
                    return ExecutionResult(
                        success=outcome.success and outcome.verified,
                        status=state,
                        requested_action="close",
                        executed_action="close_tab",
                        verification_result=VerificationResult(
                            verified=outcome.verified,
                            state=state,
                            check_type="tab_close",
                            expected=target,
                            actual=target if outcome.verified else None,
                            message=outcome.message,
                        ),
                        target=target,
                        action_type="tab",
                        error=None if (outcome.success and outcome.verified) else outcome.message,
                    )
                return self.strategy_engine.close_target_verified(
                    target=target,
                    action="close",
                    plugin_manager=self.plugin_manager,
                )

            # 3. Window Management Actions (maximize, minimize, restore, focus)
            elif action in ("maximize", "minimize", "restore", "focus"):
                outcome = self.target_engine.execute(
                    TargetRequest(target=target, action=action)
                )
                state = ExecutionState.SUCCESS if outcome.success and outcome.verified else ExecutionState.FAILED
                return ExecutionResult(
                    success=outcome.success and outcome.verified,
                    status=state,
                    requested_action=action,
                    executed_action=f"window_{action}",
                    verification_result=VerificationResult(
                        verified=outcome.verified,
                        state=state,
                        check_type=f"window_{action}",
                        expected=target,
                        actual=target if outcome.verified else None,
                        message=outcome.message,
                    ),
                    target=target,
                    action_type="window",
                    error=None if (outcome.success and outcome.verified) else outcome.message,
                )

            # 4. Fallback: Generic Target Engine dispatch
            else:
                outcome = self.target_engine.execute(
                    TargetRequest(target=target, action=action)
                )
                state = ExecutionState.SUCCESS if outcome.success and outcome.verified else ExecutionState.FAILED
                return ExecutionResult(
                    success=outcome.success and outcome.verified,
                    status=state,
                    requested_action=action,
                    executed_action=action,
                    verification_result=VerificationResult(
                        verified=outcome.verified,
                        state=state,
                        check_type=action,
                        expected=target,
                        actual=target if outcome.verified else None,
                        message=outcome.message,
                    ),
                    target=target,
                    action_type="general",
                )

        except Exception as exc:
            logger.error("Error executing ActionItem %s: %s", item.target, exc, exc_info=True)
            return ExecutionResult(
                success=False,
                status=ExecutionState.FAILED,
                requested_action=action,
                executed_action=action,
                verification_result=VerificationResult(
                    verified=False,
                    state=ExecutionState.FAILED,
                    check_type=action,
                    error=str(exc),
                    message=f"Execution error: {exc}",
                ),
                target=target,
                error=str(exc),
                reason="exception",
            )

    def _synthesize_response(
        self,
        global_action: str,
        succeeded: List[str],
        failed: List[str],
    ) -> str:
        """
        Produces accurate, natural Hinglish feedback covering all requested targets.
        """
        verb = global_action.lower().strip()

        # Helper to join list with Hindi conjunction 'aur'
        def _join_entities(names: List[str]) -> str:
            if not names:
                return ""
            if len(names) == 1:
                return names[0]
            if len(names) == 2:
                return f"{names[0]} aur {names[1]}"
            return f"{', '.join(names[:-1])} aur {names[-1]}"

        # OPEN ACTION
        if verb in ("open", "launch", "start", "run"):
            if succeeded and not failed:
                is_all_browsers = bool(
                    len(succeeded) == 2 and all(any(b in s.lower() for b in ("chrome", "brave", "edge", "firefox", "opera")) for s in succeeded)
                )
                if is_all_browsers:
                    return "Ji, dono browsers open kar diye."
                if len(succeeded) >= 3:
                    return f"{_join_entities(succeeded)} sab open ho gaye, Boss."
                return f"{_join_entities(succeeded)} open ho gaye, Boss."
            elif succeeded and failed:
                return f"{_join_entities(succeeded)} open ho gaye, lekin {_join_entities(failed)} open nahi ho paaya, Boss."
            else:
                return "Koi bhi app open nahi ho paya, Boss."

        # CLOSE ACTION
        elif verb in ("close", "band"):
            if succeeded and not failed:
                is_all_browsers = bool(
                    len(succeeded) == 2 and all(any(b in s.lower() for b in ("chrome", "brave", "edge", "firefox", "opera")) for s in succeeded)
                )
                if is_all_browsers:
                    return "Ji, dono browsers band kar diye."
                if len(succeeded) >= 3:
                    return f"{_join_entities(succeeded)} sab band ho gaye, Boss."
                return f"{_join_entities(succeeded)} band ho gaye, Boss."
            elif succeeded and failed:
                return f"{_join_entities(succeeded)} band ho gaye, lekin {_join_entities(failed)} band nahi ho paaya, Boss."
            else:
                return "Target apps band nahi ho paaye, Boss."

        # MINIMIZE ACTION
        elif verb == "minimize":
            if succeeded and not failed:
                return f"{_join_entities(succeeded)} minimize ho gaye, Boss."
            elif succeeded and failed:
                return f"{_join_entities(succeeded)} minimize ho gaye, lekin {_join_entities(failed)} minimize nahi ho paaye, Boss."
            else:
                return "Windows minimize nahi ho paayi, Boss."

        # MAXIMIZE ACTION
        elif verb == "maximize":
            if succeeded and not failed:
                return f"{_join_entities(succeeded)} maximize ho gaye, Boss."
            elif succeeded and failed:
                return f"{_join_entities(succeeded)} maximize ho gaye, lekin {_join_entities(failed)} maximize nahi ho paaye, Boss."
            else:
                return "Windows maximize nahi ho paayi, Boss."

        # GENERIC / OTHER ACTION
        else:
            if succeeded and not failed:
                return f"{_join_entities(succeeded)} {verb} ho gaye, Boss."
            elif succeeded and failed:
                return f"{_join_entities(succeeded)} {verb} ho gaye, lekin {_join_entities(failed)} {verb} nahi ho paaye, Boss."
            else:
                return f"Action {verb} complete nahi ho paya, Boss."
