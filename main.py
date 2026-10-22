# main.py
import logging
import os
import sys
import time

# Ensure workspace root is in python path and stdout is UTF-8
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        # pyrefly: ignore [missing-attribute]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# COM SAFETY PATCH — Prevent comtypes __del__ access violations from crashing
# the process.  Windows CoreAudio COM pointers garbage-collected on the wrong
# thread (or after CoUninitialize) trigger STATUS_ACCESS_VIOLATION (0xC0000005)
# in Release().  This is a harmless cleanup failure, NOT a functional bug —
# but without this patch it kills the entire Jarvis process (exit code
# 3221225477).
#
# Defence layers:
#   Layer 1: Monkey-patch _compointer_base.__del__ to swallow Python OSError.
#   Layer 2: Monkey-patch _compointer_base.Release to catch ctypes-level SEH.
#   Layer 3: Windows SetUnhandledExceptionFilter as last resort crash guard.
# ---------------------------------------------------------------------------
if os.name == "nt":
    def _apply_com_safety_patches():
        """
        COM SAFETY PATCH — Prevent comtypes __del__ access violations from crashing
        the process. Windows CoreAudio COM pointers garbage-collected on the wrong
        thread (or after CoUninitialize) trigger STATUS_ACCESS_VIOLATION (0xC0000005)
        in native C Release().
        In Python's asynchronous GC, calling unmarshaled COM Release() across
        arbitrary worker threads is unsafe and causes exit code 3221225477.
        Suppressing Release() during GC is completely harmless and guarantees zero native crashes.
        """
        try:
            from comtypes._post_coinit.unknwn import _compointer_base  # type: ignore

            def _safe_del(self, _shutting_down_attr="_com_shutting_down"):
                # No-op during asynchronous Python garbage collection.
                # COM object refcounts are safely reclaimed by the OS / audio engine
                # without risking cross-apartment STATUS_ACCESS_VIOLATION crashes.
                return

            _compointer_base.__del__ = _safe_del
        except Exception:
            pass

    _apply_com_safety_patches()

    # Explicit Windows Taskbar Application ID so Windows Shell displays
    # the custom Jarvis logo instead of grouping under generic python.exe
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("jarvis.ai.desktop.assistant.v2")
    except Exception:
        pass


from brain.classifier import IntentClassifier
from brain.llm import get_llm_provider
from brain.response import ResponseGenerator
from core.app import JarvisCore
from learning.learner import LearningManager
from memory.memory_manager import MemoryManager
from plugins.manager import PluginManager

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _project_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def setup_logging(log_level_str: str = "INFO") -> None:
    from core.logger import setup_logging as core_setup_logging
    core_setup_logging(
        level_name=log_level_str,
        log_to_file=True,
        log_dir=_project_path("logs"),
        console_output=True,
        install_crash_hooks=True
    )


def create_jarvis(config_path: str = "config.yaml") -> JarvisCore:
    """Factory creating and wiring all Jarvis subsystems."""
    # 1. Initialize core
    config_path = _project_path(config_path)
    core = JarvisCore(config_path=config_path)
    cfg = core.config

    # Setup logging based on config
    setup_logging(cfg.get("system", {}).get("log_level", "INFO"))
    from core.logger import log_startup_diagnostics
    log_startup_diagnostics(
        version=cfg.get("system", {}).get("version", "2.0.0"),
        log_dir=_project_path("logs"),
        task_recovery_status="Core systems initializing"
    )

    logger = logging.getLogger("jarvis.main")
    logger.info("=" * 60)
    logger.info(f"Starting {cfg.get('system', {}).get('name', 'JARVIS')} v{cfg.get('system', {}).get('version', '2.0.0')}")
    logger.info("=" * 60)

    # 2. Memory Subsystem
    db_path = _project_path(cfg.get("memory", {}).get("db_path", "data/jarvis.db"))
    memory_manager = MemoryManager(db_path=db_path)

    # 3. Learning Subsystem
    learning_enabled = cfg.get("learning", {}).get("enabled", True)
    learning_manager = LearningManager(db=memory_manager.db, enabled=learning_enabled)

    # 4. Brain & LLM Provider
    llm_provider = get_llm_provider(cfg)
    response_generator = ResponseGenerator(llm_provider=llm_provider)

    # 5. Plugin Subsystem
    plugin_dir = _project_path(cfg.get("plugins", {}).get("plugin_dir", "plugins"))
    plugin_manager = PluginManager(plugin_dir=plugin_dir, config=cfg, event_bus=core.event_bus)
    if cfg.get("plugins", {}).get("auto_load", True):
        plugin_manager.discover_and_load()

    # 6. Intent & Command Classifier
    classifier = IntentClassifier(
        llm_provider=llm_provider,
        plugin_manager=plugin_manager,
        learning_manager=learning_manager
    )

    # 7. Wire into Core
    core.initialize_subsystems(
        memory_manager=memory_manager,
        learning_manager=learning_manager,
        brain=response_generator,
        classifier=classifier,
        plugin_manager=plugin_manager,
        response_generator=response_generator
    )

    return core


def run_interactive_cli(core: JarvisCore) -> None:
    """Interactive command-line interface for testing the full core pipeline."""
    print("\n" + "=" * 60)
    print("   JARVIS V2 - ONLINE & READY")
    print("   Type your command, query, or 'help' (type 'exit' to quit)")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            response = core.process_input(user_input, source="cli")
            print(f"\nJarvis: {response}\n")

            if hasattr(core, "take_sensitive_display"):
                sensitive_payload = core.take_sensitive_display()
                if isinstance(sensitive_payload, dict) and sensitive_payload.get("type") == "wifi_credentials":
                    lines = ["Saved Wi-Fi credentials:"]
                    for index, item in enumerate(sensitive_payload.get("items", []), start=1):
                        lines.append(f"  {index}. SSID: {item.get('ssid', '')}")
                        lines.append(f"     Password: {item.get('password', '')}")
                    print("\n".join(lines) + "\n")

            if core.state_machine.current_state.value == "SHUTDOWN":
                break

        except (KeyboardInterrupt, EOFError):
            print("\nShutting down Jarvis...")
            break


def authenticate_cli_session(core: JarvisCore, bypass_auth: bool = False) -> bool:
    """Authenticate command-line entry points unless the user explicitly bypasses it."""
    if bypass_auth:
        return True
    from security.face_authenticator import FaceAuthenticator
    auth = FaceAuthenticator(core.config)
    return not auth.enabled or auth.authenticate_cli().success


def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS v2.0.0 - Autonomous AI Assistant")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--query", type=str, default=None, help="Execute single query and exit")
    parser.add_argument("--gui", action="store_true", help="Launch modern PySide6 graphical user interface (default)")
    parser.add_argument("--cli", action="store_true", help="Launch interactive command-line interface instead of GUI")
    parser.add_argument("--no-auth", "--bypass-auth", action="store_true", dest="no_auth", help="Bypass biometric face authentication gate")
    parser.add_argument("--enroll-face", action="store_true", help="Capture and register user facial biometric profile")
    parser.add_argument("--reload", action="store_true", dest="reload", help="Enable live auto-update / hot-reloading on file updates")
    parser.add_argument("--no-reload", action="store_true", dest="no_reload", help="Disable live auto-update / hot-reloading")
    args = parser.parse_args()

    # All built-in data/plugin paths are project-relative, independent of the
    # directory used by shortcuts, schedulers, or shells to launch Jarvis.
    os.chdir(PROJECT_ROOT)

    from core.reloader import is_reloader_child, is_reload_session, ReloaderSupervisor

    # If this process was spawned as part of a hot-reload, preserve auth session
    if is_reload_session():
        args.no_auth = True

    # External supervisor process handles process lifecycle when auto-reload is active.
    # In-process LiveUpdateManager handles zero-downtime hot-reloads within the worker.
    is_oneshot = bool(args.query or args.enroll_face)
    if not is_oneshot and not is_reloader_child():
        auto_reload_enabled = args.reload
        if not args.no_reload and not args.reload:
            try:
                # pyrefly: ignore [untyped-import]
                import yaml
                cfg_file = args.config or "config.yaml"
                if os.path.exists(cfg_file):
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg_dict = yaml.safe_load(f) or {}
                    auto_reload_enabled = cfg_dict.get("system", {}).get("auto_reload", True)
            except Exception:
                auto_reload_enabled = True

        if auto_reload_enabled:
            supervisor = ReloaderSupervisor(project_root=PROJECT_ROOT)
            sys.exit(supervisor.run())

    jarvis_instance = create_jarvis(args.config)
    if args.no_reload and hasattr(jarvis_instance, "update_manager") and jarvis_instance.update_manager:
        jarvis_instance.update_manager.stop()
        jarvis_instance.update_manager = None
    logger = logging.getLogger("jarvis.main")

    # Handle enrollment flag
    if args.enroll_face:
        from security.face_authenticator import FaceAuthenticator
        auth = FaceAuthenticator(jarvis_instance.config)
        if auth.has_enrolled_profile() and not authenticate_cli_session(jarvis_instance, args.no_auth):
            print("\n[!] Authentication required before replacing the enrolled face.\n")
            return
        res = auth.enroll()
        if res.get("success"):
            print(f"\n[SUCCESS] {res.get('message')}\n")
        else:
            print(f"\n[ERROR] {res.get('error')}\n")
        return

    if args.query:
        if not authenticate_cli_session(jarvis_instance, args.no_auth):
            print("\n[!] Access Denied. Exiting Jarvis.\n")
            return
        resp = jarvis_instance.process_input(args.query, source="cli")
        print(f"\nJarvis: {resp}\n")
        if hasattr(jarvis_instance, "take_sensitive_display"):
            sensitive_payload = jarvis_instance.take_sensitive_display()
            if isinstance(sensitive_payload, dict) and sensitive_payload.get("type") == "wifi_credentials":
                lines = ["Saved Wi-Fi credentials:"]
                for index, item in enumerate(sensitive_payload.get("items", []), start=1):
                    lines.append(f"  {index}. SSID: {item.get('ssid', '')}")
                    lines.append(f"     Password: {item.get('password', '')}")
                print("\n".join(lines) + "\n")
        return

    if args.cli:
        if not authenticate_cli_session(jarvis_instance, args.no_auth):
            print("\n[!] Access Denied. Exiting Jarvis.\n")
            return
        run_interactive_cli(jarvis_instance)
        return

    # Default: Launch modern PySide6 GUI directly
    try:
        from gui import launch_gui
        print("\n[+] Launching JARVIS V2 PySide6 Graphical User Interface...")
        sys.exit(launch_gui(jarvis_instance, bypass_auth=args.no_auth))
    except Exception as e:
        logger.error(f"Failed to launch GUI: {e}")
        print(f"[!] Unable to launch GUI ({e}). Falling back to interactive CLI...\n")
        if not args.no_auth:
            from security.face_authenticator import FaceAuthenticator
            auth = FaceAuthenticator(jarvis_instance.config)
            if auth.enabled:
                auth_res = auth.authenticate_cli()
                if not auth_res.success:
                    print("\n[!] Access Denied. Exiting Jarvis.\n")
                    return
        run_interactive_cli(jarvis_instance)


if __name__ == "__main__":
    main()
