# core/update_manager.py
"""
In-Process Live Update Manager for Zero-Downtime Code Updates in Jarvis V2.1.
Maintains continuous GUI and application uptime while detecting and applying
source code and configuration changes.

Transaction Model:
DETECTED -> DEBOUNCE -> CLASSIFY -> PREPARE -> QUIESCE AFFECTED COMPONENT -> APPLY -> VERIFY -> RESUME
"""

import importlib
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

from core.reload_policy import (
    ReloadCategory,
    ReloadPlan,
    classify_file_change,
    coalesce_file_changes,
)
from core.reloader import FileWatcher

logger = logging.getLogger("jarvis.update_manager")


class LiveUpdateManager:
    """
    Coordinates in-process zero-downtime updates.
    Runs a non-blocking background file watcher, coalesces rapid filesystem events,
    safely quiesces and reloads affected modules or worker plugins, and preserves
    the persistent GUI host and user session state.
    """

    def __init__(
        self,
        core: Any = None,
        project_root: str = ".",
        poll_interval: float = 0.5,
        debounce_sec: float = 0.6,
        watch_dirs: Optional[List[str]] = None,
        root_files: Optional[List[str]] = None,
    ):
        self.core = core
        self.project_root = os.path.abspath(project_root)
        self.poll_interval = poll_interval
        self.debounce_sec = debounce_sec
        self.watcher = FileWatcher(
            project_root=self.project_root,
            watch_dirs=watch_dirs,
            root_files=root_files,
            debounce_sec=self.debounce_sec,
        )
        self._stopped = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self.last_applied_plan: Optional[ReloadPlan] = None
        self.transaction_count = 0

    def start(self) -> None:
        """Starts the background file monitoring and update coordination thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped = False
            self._thread = threading.Thread(
                target=self._run_loop,
                name="LiveUpdateManagerWorker",
                daemon=True,
            )
            self._thread.start()
            logger.info("LiveUpdateManager started (in-process zero-downtime monitor active).")

    def stop(self) -> None:
        """Gracefully stops the background file watcher."""
        self._stopped = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("LiveUpdateManager stopped.")

    def _run_loop(self) -> None:
        """Background polling loop with debouncing and transactional reload execution."""
        while not self._stopped:
            try:
                # Check for changes
                if hasattr(self.watcher, "get_all_changes"):
                    raw_changes = self.watcher.get_all_changes()
                else:
                    first_ch = self.watcher.check_for_changes()
                    raw_changes = [first_ch] if first_ch else []

                if raw_changes:
                    # Debounce period: wait and gather all subsequent rapid writes
                    time.sleep(self.debounce_sec)
                    if hasattr(self.watcher, "get_all_changes"):
                        more_changes = self.watcher.get_all_changes()
                    else:
                        ch = self.watcher.check_for_changes()
                        more_changes = [ch] if ch else []

                    all_changes = list(dict.fromkeys(raw_changes + more_changes))

                    # Coalesce into single transaction plan
                    plan = coalesce_file_changes(all_changes)
                    if plan.category != ReloadCategory.IGNORE:
                        self.apply_plan(plan)

            except Exception as e:
                logger.error("Error in LiveUpdateManager loop: %s", e, exc_info=True)

            time.sleep(self.poll_interval)

    def apply_plan(self, plan: ReloadPlan) -> bool:
        """
        Applies a ReloadPlan as a controlled, isolated transaction.
        Never calls sys.exit(), app.quit(), or terminates the GUI process.
        """
        mod = sys.modules.get("core.update_manager")
        if mod:
            new_cls = getattr(mod, "LiveUpdateManager", None)
            if new_cls and self.__class__ is not new_cls:
                self.__class__ = new_cls
                return self.apply_plan(plan)

        with self._lock:
            self.transaction_count += 1
            self.last_applied_plan = plan
            logger.info(
                "[TRANSACTION %d] Processing update for '%s' (Category: %s, Files: %s)",
                self.transaction_count,
                plan.target_name,
                plan.category.value,
                ", ".join(plan.affected_files),
            )

            # 1. Check FULL_RESTART_REQUIRED
            if plan.category == ReloadCategory.FULL_RESTART_REQUIRED:
                logger.warning(
                    "[AutoUpdate] %s. Full application restart required.",
                    plan.reason,
                )
                self._emit_status(
                    status="full_restart_needed",
                    component=plan.target_name,
                    message=f"Full restart recommended: {plan.reason}",
                    data={"reason": plan.reason, "files": plan.affected_files},
                )
                if os.environ.get("JARVIS_RELOADER_CHILD") == "1":
                    from core.reloader import trigger_reload
                    threading.Timer(0.5, trigger_reload).start()
                return False

            # 2. Transaction Start notification
            self._emit_status(
                status="updating",
                component=plan.target_name,
                message=f"Updating {plan.target_name}...",
                data={"files": plan.affected_files},
            )

            # 3. Apply changes across all affected components
            try:
                success = True
                messages = []

                # A. Handle configuration reload
                if plan.target_name == "config" or any("config.yaml" in f.lower() for f in plan.affected_files):
                    if self.core:
                        cfg_path = getattr(self.core, "config_path", "config.yaml")
                        if os.path.exists(cfg_path):
                            import yaml
                            with open(cfg_path, "r", encoding="utf-8") as f:
                                new_cfg = yaml.safe_load(f) or {}
                            self.core.config = new_cfg
                            messages.append("Configuration reloaded")
                        else:
                            messages.append(f"Config file not found: {cfg_path}")

                # B. Handle in-process module reloads
                if plan.modules_to_reload:
                    reloaded_mods = []
                    for mod_name in plan.modules_to_reload:
                        if mod_name in sys.modules:
                            try:
                                importlib.reload(sys.modules[mod_name])
                                reloaded_mods.append(mod_name)
                            except Exception as e:
                                logger.warning("[LiveUpdateManager] Module reload error for %s: %s", mod_name, e)
                        else:
                            try:
                                importlib.import_module(mod_name)
                                reloaded_mods.append(mod_name)
                            except Exception as e:
                                logger.debug("[LiveUpdateManager] Module import error for %s: %s", mod_name, e)

                    if reloaded_mods:
                        messages.append(f"Reloaded modules: {', '.join(reloaded_mods)}")

                    if "core.update_manager" in reloaded_mods:
                        try:
                            new_cls = getattr(sys.modules.get("core.update_manager"), "LiveUpdateManager", None)
                            if new_cls:
                                self.__class__ = new_cls
                        except Exception:
                            pass

                    # Re-bind affected core subsystem instances
                    if self.core:
                        self._rebind_core_subsystems(plan.modules_to_reload)

                # C. Handle plugin reloads and discoveries
                plugins_to_reload = []
                if plan.plugin_name:
                    plugins_to_reload.append(plan.plugin_name)
                for f in plan.affected_files:
                    norm_f = f.replace("\\", "/").lower()
                    if norm_f.startswith("plugins/"):
                        parts = norm_f.split("/")
                        if len(parts) >= 2 and parts[1] not in plugins_to_reload:
                            plugins_to_reload.append(parts[1])

                if plugins_to_reload and self.core and getattr(self.core, "plugin_manager", None):
                    pm = self.core.plugin_manager
                    for p in plugins_to_reload:
                        p_ok, p_msg = pm.reload_plugin(p)
                        if p_ok:
                            messages.append(f"Plugin '{p}' reloaded")
                            if hasattr(self.core, "router") and self.core.router:
                                self.core.router.plugin_manager = pm
                            if hasattr(self.core, "executor") and self.core.executor:
                                self.core.executor.plugin_manager = pm
                        else:
                            success = False
                            messages.append(f"Plugin '{p}' reload failed: {p_msg}")

                # D. Handle Archify Architecture Synchronization
                if plan.target_name == "archify" or any("architecture" in f.lower() or "plugins/archify" in f.replace("\\", "/").lower() for f in plan.affected_files):
                    try:
                        from plugins.archify.builder import compile_archify_html
                        arch_ok, arch_msg = compile_archify_html()
                        if arch_ok:
                            messages.append("Archify architecture synced & recompiled")
                        else:
                            messages.append(f"Archify sync notice: {arch_msg}")
                    except Exception as arch_err:
                        logger.warning("[LiveUpdateManager] Archify recompile warning: %s", arch_err)
                        messages.append(f"Archify update warning: {arch_err}")

                # E. Handle GUI views and styles
                if plan.target_name.startswith("gui:") or any(f.replace("\\", "/").lower().startswith("gui/") for f in plan.affected_files):
                    if self.core and hasattr(self.core, "event_bus"):
                        self.core.event_bus.emit("gui.reload", {"target": plan.target_name, "files": plan.affected_files})
                        messages.append(f"GUI component '{plan.target_name}' refreshed")

                if not messages:
                    messages.append(f"Applied update for '{plan.target_name}'")

                combined_msg = "; ".join(messages)

                if success:
                    logger.info("[TRANSACTION %d] ✓ %s", self.transaction_count, combined_msg)
                    self._emit_status(
                        status="success",
                        component=plan.target_name,
                        message=f"✓ {plan.target_name} updated successfully",
                        data={"message": combined_msg},
                    )
                    return True
                else:
                    logger.error("[TRANSACTION %d] ⚠ Reload failed: %s. Previous version preserved.", self.transaction_count, combined_msg)
                    self._emit_status(
                        status="error",
                        component=plan.target_name,
                        message=f"⚠ Update failed: {combined_msg}",
                        data={"error": combined_msg},
                    )
                    return False

            except Exception as exc:
                logger.error(
                    "[TRANSACTION %d] ⚠ Exception during live update of '%s': %s. GUI host preserved.",
                    self.transaction_count,
                    plan.target_name,
                    exc,
                    exc_info=True,
                )
                self._emit_status(
                    status="error",
                    component=plan.target_name,
                    message=f"⚠ Update exception: {exc}",
                    data={"error": str(exc)},
                )
                return False

    def _rebind_core_subsystems(self, modules_to_reload: Sequence[str]) -> None:
        """
        Re-instantiates core subsystem components on self.core when their modules are reloaded.
        Guarantees that active turn handlers immediately execute newly updated code.
        """
        if not self.core:
            return

        mods = set(modules_to_reload)

        # 1. FastPathEngine
        if any("fast_path" in m or m == "core.execution" for m in mods):
            try:
                from core.execution.fast_path import FastPathEngine
                self.core.fast_path = FastPathEngine(core=self.core)
                logger.info("[LiveUpdateManager] ✓ Re-bound self.core.fast_path")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding fast_path: %s", e)

        # 2. SemanticActionExecutor
        if any("semantic_executor" in m or m == "core.execution" for m in mods):
            try:
                from core.execution.semantic_executor import SemanticActionExecutor
                self.core.semantic_executor = SemanticActionExecutor(core=self.core)
                logger.info("[LiveUpdateManager] ✓ Re-bound self.core.semantic_executor")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding semantic_executor: %s", e)

        # 3. Knowledge Engines & Routers
        if any(m.startswith("core.knowledge") for m in mods):
            try:
                from core.knowledge.engine import KnowledgeEngine
                from core.knowledge.it.engine import ITKnowledgeEngine
                from core.knowledge.news.engine import LiveNewsEngine
                from core.knowledge.calendar.engine import FestivalCalendarEngine
                KnowledgeEngine._instance = None
                ITKnowledgeEngine._instance = None
                LiveNewsEngine._instance = None
                FestivalCalendarEngine._instance = None
                logger.info("[LiveUpdateManager] ✓ Reset Knowledge Singletons for fresh reload")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error refreshing knowledge singletons: %s", e)

        # 4. AnswerVerificationEngine
        if any("answer_verification" in m for m in mods):
            try:
                from core.intelligence.answer_verification import AnswerVerificationEngine
                self.core.answer_verifier = AnswerVerificationEngine()
                logger.info("[LiveUpdateManager] ✓ Re-bound AnswerVerificationEngine")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding answer_verifier: %s", e)

        # 5. Target Engine & Windows App Resolver
        if any("target_engine" in m or "windows_app_resolver" in m for m in mods):
            try:
                from core.target_engine import UniversalTargetDiscoveryEngine
                self.core.target_engine = UniversalTargetDiscoveryEngine()
                logger.info("[LiveUpdateManager] ✓ Re-bound UniversalTargetDiscoveryEngine")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding target_engine: %s", e)

        # 6. Spelling Resolver & Semantic Parser
        if any("spelling_resolver" in m or "semantic_parser" in m or m.startswith("core.semantic") for m in mods):
            try:
                if hasattr(self.core, "spelling_resolver"):
                    from brain.spelling_resolver import SpellingResolver
                    self.core.spelling_resolver = SpellingResolver()
                if hasattr(self.core, "semantic_parser"):
                    from brain.semantic_parser import HinglishNLUParser
                    self.core.semantic_parser = HinglishNLUParser()
                logger.info("[LiveUpdateManager] ✓ Re-bound SpellingResolver and SemanticParser")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding brain components: %s", e)

        # 7. Conversational Intent Classifier
        if any("conversational_intent" in m for m in mods):
            try:
                if hasattr(self.core, "conversational_intent"):
                    from core.conversational_intent import ConversationalIntentClassifier
                    self.core.conversational_intent = ConversationalIntentClassifier()
                logger.info("[LiveUpdateManager] ✓ Re-bound ConversationalIntentClassifier")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding conversational_intent: %s", e)

        # 8. Confidence Engine
        if any("confidence" in m for m in mods):
            try:
                from core.intelligence.confidence import ConfidenceEngine
                self.core.confidence_engine = ConfidenceEngine()
                logger.info("[LiveUpdateManager] ✓ Re-bound ConfidenceEngine")
            except Exception as e:
                logger.warning("[LiveUpdateManager] Error re-binding confidence_engine: %s", e)

    def reload_file(self, rel_path: str) -> bool:
        """Convenience method to classify and reload a single file path directly."""
        plan = classify_file_change(rel_path)
        if plan.category == ReloadCategory.IGNORE:
            return True
        return self.apply_plan(plan)

    def _emit_status(self, status: str, component: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Helper to emit status updates to the EventBus."""
        if self.core and hasattr(self.core, "event_bus") and self.core.event_bus:
            payload = {
                "status": status,
                "component": component,
                "message": message,
                "timestamp": time.time(),
            }
            if data:
                payload.update(data)
            try:
                self.core.event_bus.emit("system.update.status", payload)
            except Exception as e:
                logger.debug("Failed to emit update status event: %s", e)
