# core/reloader.py
"""Live auto-update and hot-reloader subsystem for Jarvis V2."""

import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional

logger = logging.getLogger("jarvis.core.reloader")

RELOAD_EXIT_CODE = 42
ENV_RELOADER_CHILD = "JARVIS_RELOADER_CHILD"
ENV_RELOAD_SESSION = "JARVIS_RELOAD_SESSION"

DEFAULT_WATCH_DIRS = [
    "core", "brain", "gui", "plugins", "memory", "learning", "security", "tools", "voice"
]
DEFAULT_ROOT_FILES = ["main.py", "config.yaml", "architecture.txt"]
WATCH_EXTS = {".py", ".yaml", ".yml", ".json"}
IGNORE_DIRS = {
    ".git", "__pycache__", "logs", "data", ".pytest_cache", ".venv",
    "artifacts", "scratch", ".system_generated", ".agents", "node_modules"
}
IGNORE_EXTS = {
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3", ".log",
    ".tmp", ".swp", ".bak", ".pid", ".lock"
}


def is_reloader_child() -> bool:
    """Check whether the current process is a worker child under ReloaderSupervisor."""
    return os.environ.get(ENV_RELOADER_CHILD) == "1"


def is_reload_session() -> bool:
    """Check whether this process was spawned as part of a live auto-reload."""
    return os.environ.get(ENV_RELOAD_SESSION) == "1"


def trigger_reload() -> None:
    """
    Triggers an immediate live reload of the Jarvis application.
    If running under the supervisor, exits with RELOAD_EXIT_CODE.
    Otherwise, restarts the current process in-place.
    """
    if is_reloader_child():
        logger.info("Triggering reloader supervisor restart (code %d)", RELOAD_EXIT_CODE)
        if "pytest" in sys.modules:
            sys.exit(RELOAD_EXIT_CODE)
        os._exit(RELOAD_EXIT_CODE)
    else:
        logger.info("Triggering standalone in-place process restart")
        py_exe = sys.executable
        venv_py = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            py_exe = venv_py
        main_script = os.path.join(os.getcwd(), "main.py")
        args = list(sys.argv)
        if not any(a.endswith("main.py") for a in args):
            cmd = [py_exe, main_script] + args[1:]
        else:
            cmd = [py_exe] + args
        if os.name == "nt":
            subprocess.Popen(cmd)
            if "pytest" in sys.modules:
                sys.exit(0)
            os._exit(0)
        else:
            os.execv(py_exe, cmd)


class FileWatcher:
    """Pure standard-library file change watcher with fast mtime polling and debouncing."""

    def __init__(
        self,
        project_root: str,
        watch_dirs: Optional[List[str]] = None,
        root_files: Optional[List[str]] = None,
        debounce_sec: float = 0.6
    ):
        self.project_root = os.path.abspath(project_root)
        self.watch_dirs = watch_dirs or list(DEFAULT_WATCH_DIRS)
        self.root_files = root_files or list(DEFAULT_ROOT_FILES)
        self.debounce_sec = debounce_sec
        self.snapshot = self.capture_snapshot()

    def capture_snapshot(self) -> Dict[str, float]:
        """Capture mtimes of all tracked source and configuration files."""
        mtimes: Dict[str, float] = {}
        for d in self.watch_dirs:
            full_d = os.path.join(self.project_root, d)
            if not os.path.isdir(full_d):
                continue
            for root, dirs, files in os.walk(full_d):
                dirs[:] = [
                    sub for sub in dirs
                    if sub not in IGNORE_DIRS and not sub.startswith(".")
                ]
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in WATCH_EXTS and ext not in IGNORE_EXTS:
                        p = os.path.join(root, f)
                        try:
                            mtimes[p] = os.path.getmtime(p)
                        except OSError:
                            pass

        for rf in self.root_files:
            p = os.path.join(self.project_root, rf)
            if os.path.isfile(p):
                try:
                    mtimes[p] = os.path.getmtime(p)
                except OSError:
                    pass

        return mtimes

    def check_for_changes(self) -> Optional[str]:
        """
        Compares current file mtimes against snapshot.
        Returns the relative path of the first changed/added/deleted file, or None.
        """
        changes = self.get_all_changes()
        return changes[0] if changes else None

    def get_all_changes(self) -> List[str]:
        """
        Compares current file mtimes against snapshot.
        Returns a list of relative paths for all changed/added/deleted files, or empty list.
        """
        current = self.capture_snapshot()
        changes = []

        # Check for modified or deleted files
        for path, old_mtime in self.snapshot.items():
            if path not in current:
                changes.append(os.path.relpath(path, self.project_root))
            elif current[path] > old_mtime:
                changes.append(os.path.relpath(path, self.project_root))

        # Check for newly added files
        for path in current:
            if path not in self.snapshot:
                changes.append(os.path.relpath(path, self.project_root))

        if changes:
            self.snapshot = current
        return changes


class ReloaderSupervisor:
    """Supervises the Jarvis process and handles live auto-updates on file modification."""

    def __init__(
        self,
        project_root: str,
        args: Optional[List[str]] = None,
        poll_interval: float = 0.5,
        debounce_sec: float = 0.6
    ):
        self.project_root = os.path.abspath(project_root)
        self.args = args if args is not None else sys.argv[1:]
        self.poll_interval = poll_interval
        self.watcher = FileWatcher(
            project_root=self.project_root,
            debounce_sec=debounce_sec
        )
        self.process: Optional[subprocess.Popen] = None
        self._stopped = False

    def _spawn_child(self, is_reload: bool = False) -> subprocess.Popen:
        env = os.environ.copy()
        env[ENV_RELOADER_CHILD] = "1"
        if is_reload:
            env[ENV_RELOAD_SESSION] = "1"
        py_exe = sys.executable
        venv_py = os.path.join(self.project_root, ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            py_exe = venv_py

        main_script = os.path.join(self.project_root, "main.py")
        args = list(self.args)
        if not any(a.endswith("main.py") for a in args):
            cmd = [py_exe, main_script] + args
        else:
            cmd = [py_exe] + args
        return subprocess.Popen(cmd, cwd=self.project_root, env=env)

    def _terminate_child(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=1.0)
                except Exception:
                    pass

    def stop(self) -> None:
        """Stops the supervisor and terminates the child process."""
        self._stopped = True
        self._terminate_child()

    def run(self) -> int:
        """
        Runs the supervisor loop.
        Monitors child process health and restarts child on crash or explicit reload exit code.
        Source-file updates are handled in-process by LiveUpdateManager with zero GUI downtime.
        """
        print("\n" + "=" * 62)
        print("   [JARVIS LIVE AUTO-UPDATE] Hot-Reload Supervisor Active")
        print("   Any code or config change will auto-update Jarvis live.")
        print("=" * 62 + "\n")

        is_reload = False
        try:
            while not self._stopped:
                self.process = self._spawn_child(is_reload=is_reload)
                is_reload = False

                while not self._stopped:
                    ret = self.process.poll()
                    if ret is not None:
                        if ret == RELOAD_EXIT_CODE:
                            print(f"\n[AutoReload] Reload requested (code {ret}). Restarting Jarvis live...")
                            is_reload = True
                            time.sleep(0.3)
                            break
                        elif ret == 0:
                            # Clean exit requested by user
                            return 0
                        else:
                            print(f"\n[AutoReload] Jarvis process exited with code {ret}.")
                            print("[AutoReload] Watching files for changes to auto-restart...")
                            while not self._stopped:
                                changed = self.watcher.check_for_changes()
                                if changed:
                                    print(f"[AutoReload] Detected update in '{changed}'. Live restarting Jarvis...")
                                    time.sleep(self.watcher.debounce_sec)
                                    is_reload = True
                                    break
                                time.sleep(self.poll_interval)
                            break

                    # Child is actively running.
                    # Check if a bootstrap file requiring full restart changed
                    changed = self.watcher.check_for_changes()
                    if changed:
                        from core.reload_policy import classify_file_change, ReloadCategory
                        plan = classify_file_change(changed)
                        if plan.category == ReloadCategory.FULL_RESTART_REQUIRED:
                            print(f"\n[AutoReload] Bootstrap update in '{changed}'. Live restarting Jarvis...")
                            self._terminate_child()
                            is_reload = True
                            time.sleep(0.3)
                            break

                    time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n[AutoReload] Stopping Jarvis supervisor...")
            self._terminate_child()
            return 0
        finally:
            self._terminate_child()

        return 0
