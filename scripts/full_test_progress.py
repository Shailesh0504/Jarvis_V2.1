#!/usr/bin/env python
"""Whole-project test runner with a single-line live progress percentage.
==========================================================================
Runs the ENTIRE pytest suite and shows you only the progress percentage.
Every line of verbose pytest output goes to a timestamped log file instead, and
a machine-readable summary is written to JSON so the result survives the run.

Usage
-----
    # Run the whole suite (live % on the terminal)
    python scripts/full_test_progress.py

    # Start it detached and walk away, then check progress any time
    python scripts/full_test_progress.py --background
    python scripts/full_test_progress.py --status

    # Any extra arguments are forwarded straight to pytest
    python scripts/full_test_progress.py tests/test_agent.py -k open
    python scripts/full_test_progress.py -k "not slow"

Outputs (under logs/)
---------------------
    test_progress.txt   Single-line live progress ("042.7% ...") - easy to watch
    test_progress.json  Machine-readable progress/summary snapshot
    full_test_<ts>.log  Complete pytest output, unbuffered
    full_test_summary.json  Final pass/fail/error/skip + slowest tests

Exit code: number of failed tests (0 = everything passed), or 2 on setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
PROGRESS_TXT = LOG_DIR / "test_progress.txt"
PROGRESS_JSON = LOG_DIR / "test_progress.json"
SUMMARY_JSON = LOG_DIR / "full_test_summary.json"

BAR_WIDTH = 0


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _write_atomic(path: Path, text: str) -> None:
    """Best-effort atomic write so a watcher never reads a half-written file."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        pass


class ProgressPlugin:
    """Pytest plugin that reports only a percentage, plus counts, live.

    Note: this deliberately does NOT print pytest's own dots/progress. The
    runner redirects pytest's stdout into the log file, and this plugin writes
    to the real terminal handle it was handed.
    """

    def __init__(self, terminal, log_path: Path, verbose_line: bool = True) -> None:
        self.terminal = terminal
        self.log_path = log_path
        self.verbose_line = verbose_line
        self.total = 0
        self.completed = 0
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.xfailed = 0
        self.start = time.time()
        self.last_render = 0.0
        self.failures: List[str] = []
        self.collection_errors: List[str] = []
        self._rendered_any = False

    # -- pytest hooks ---------------------------------------------------------
    def pytest_collection_finish(self, session) -> None:
        self.total = len(session.items)
        self._render(force=True)

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.collection_errors.append(str(getattr(report, "longrepr", report.nodeid)))

    def pytest_runtest_logreport(self, report) -> None:
        # Count one unit per test (the "call" phase); setup/teardown errors count too.
        if report.when == "call":
            self.completed += 1
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
                if len(self.failures) < 200:
                    self.failures.append(report.nodeid)
            elif report.skipped:
                self.skipped += 1
            if getattr(report, "wasxfail", False):
                self.xfailed += 1
            self._render()
        elif report.when in ("setup", "teardown") and report.failed:
            self.errors += 1
            if len(self.failures) < 200:
                self.failures.append(f"{report.nodeid} [{report.when}]")
            self._render(force=True)

    def pytest_internalerror(self, excrepr) -> None:
        self.errors += 1
        self._render(force=True)

    # -- rendering ------------------------------------------------------------
    def _percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, 100.0 * self.completed / self.total)

    def _line(self) -> str:
        elapsed = time.time() - self.start
        pct = self._percent()
        parts = [f"{pct:6.1f}%  {self.completed}/{self.total} tests"]
        if self.completed:
            parts.append(f"pass {self.passed}")
            if self.failed:
                parts.append(f"FAIL {self.failed}")
            if self.errors:
                parts.append(f"error {self.errors}")
            if self.skipped:
                parts.append(f"skip {self.skipped}")
            remaining = elapsed * (self.total - self.completed) / self.completed
            parts.append(f"eta {_fmt_duration(remaining)}")
        parts.append(f"{_fmt_duration(elapsed)} elapsed")
        return " | ".join(parts)

    def _render(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self.last_render) < 0.25:
            return
        self.last_render = now
        line = self._line()
        try:
            width = max(len(line), 24)
            self.terminal.write("\r" + line.ljust(width))
            self.terminal.flush()
            self._rendered_any = True
        except Exception:
            pass
        _write_atomic(PROGRESS_TXT, line + "\n")
        _write_atomic(PROGRESS_JSON, json.dumps(self.snapshot(), indent=2))

    def snapshot(self, finished: bool = False) -> Dict[str, Any]:
        elapsed = time.time() - self.start
        return {
            "state": "DONE" if finished else ("RUNNING" if self.completed or self.total else "COLLECTING"),
            "percent": round(self._percent(), 2),
            "completed": self.completed,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "xfailed": self.xfailed,
            "elapsed_seconds": round(elapsed, 1),
            "elapsed": _fmt_duration(elapsed),
            "percent_passed": round(100.0 * self.passed / max(1, self.completed), 2) if self.completed else 0.0,
            "failures": self.failures[:200],
            "collection_errors": self.collection_errors[:20],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def finish_line(self) -> str:
        snap = self.snapshot(finished=True)
        return (
            f"DONE {snap['percent']:6.1f}%  ({snap['completed']}/{snap['total']} tests) | "
            f"pass {snap['passed']} | fail {snap['failed']} | error {snap['errors']} | "
            f"skip {snap['skipped']} | {snap['elapsed']}"
        )


def _run(argv: List[str]) -> int:
    import pytest

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"full_test_{stamp}.log"

    terminal = sys.stdout
    plugin = ProgressPlugin(terminal, log_path)
    pytest_args = ["-q", "--tb=short", "--durations=25", "-p", "no:cacheprovider", *argv]

    terminal.write(f"Running full test suite -> {log_path.name}\n")
    terminal.flush()
    _write_atomic(PROGRESS_JSON, json.dumps(plugin.snapshot(), indent=2))

    exit_code = 2
    log_handle = open(log_path, "w", encoding="utf-8", errors="replace")
    try:
        # Everything pytest prints goes to the log; the plugin owns the terminal.
        with log_handle:
            orig_stdout, orig_stderr = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = log_handle, log_handle
            try:
                log_handle.write(f"# pytest {' '.join(pytest_args)}\n# started {datetime.now().isoformat()}\n\n")
                log_handle.flush()
                exit_code = pytest.main(pytest_args, plugins=[plugin])
            except SystemExit as exc:  # pytest may raise SystemExit
                exit_code = int(exc.code or 0)
            except Exception as exc:  # never lose the log
                log_handle.write(f"\n# RUNNER ERROR: {exc!r}\n")
                exit_code = 2
            finally:
                sys.stdout, sys.stderr = orig_stdout, orig_stderr
    finally:
        pass

    snap = plugin.snapshot(finished=True)
    snap["exit_code"] = int(exit_code)
    snap["log_file"] = str(log_path)
    # pytest exit codes: 0 ok, 1 failures, 2 interrupted, 3 internal error, 4 usage, 5 no tests
    snap["status"] = {
        0: "PASS", 1: "FAIL", 2: "INTERRUPTED", 3: "INTERNAL_ERROR", 4: "USAGE_ERROR", 5: "NO_TESTS"
    }.get(int(exit_code), f"EXIT_{exit_code}")

    _write_atomic(SUMMARY_JSON, json.dumps(snap, indent=2))
    _write_atomic(PROGRESS_JSON, json.dumps(snap, indent=2))
    _write_atomic(PROGRESS_TXT, plugin.finish_line() + "\n")

    terminal.write("\r" + plugin.finish_line() + "\n")
    terminal.write(f"Full log: {log_path}\nSummary : {SUMMARY_JSON}\n")
    terminal.flush()

    # Exit with the failure count (clamped) so CI/shells can act on it.
    failures = int(snap["failed"]) + int(snap["errors"]) + (1 if int(exit_code) not in (0, 1, 5) else 0)
    return min(failures, 125)


def _status() -> int:
    if PROGRESS_JSON.exists():
        try:
            data = json.loads(PROGRESS_JSON.read_text(encoding="utf-8"))
            print(
                f"{data.get('state', '?')} {float(data.get('percent', 0)):6.1f}%  "
                f"({data.get('completed', 0)}/{data.get('total', 0)} tests) | "
                f"pass {data.get('passed', 0)} | fail {data.get('failed', 0)} | "
                f"error {data.get('errors', 0)} | skip {data.get('skipped', 0)} | "
                f"{data.get('elapsed', '0s')} | updated {data.get('updated_at', '?')}"
            )
            return 0
        except Exception as exc:
            print(f"Could not read progress: {exc}")
            return 2
    print("No test run in progress (no logs/test_progress.json yet).")
    return 1


def _background(argv: List[str]) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    console_log = LOG_DIR / f"full_test_console_{stamp}.log"
    cmd = [sys.executable, str(Path(__file__).resolve()), *argv]
    kwargs: Dict[str, Any] = {"cwd": str(PROJECT_ROOT)}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with open(console_log, "w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, **kwargs)
    print(f"Started full test run in background (pid {proc.pid}).")
    print(f"Watch progress : python scripts/full_test_progress.py --status")
    print(f"Live console   : {console_log}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the whole project test suite showing only a progress percentage.",
        add_help=True,
    )
    parser.add_argument("--status", action="store_true", help="Print the current progress and exit.")
    parser.add_argument("--background", action="store_true", help="Start the run detached and exit.")
    parser.add_argument("pytest_args", nargs="*", help="Extra arguments forwarded to pytest.")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    if args.status:
        return _status()
    if args.background:
        return _background(args.pytest_args)
    return _run(args.pytest_args)


if __name__ == "__main__":
    sys.exit(main())
