# tests/test_production_logging.py
"""
Unit and Integration Tests for Jarvis V2 Production-Grade Logging System.
Validates:
- Safe log rotation at byte threshold
- Retention of up to 5 backup files (.1 to .5) and pruning beyond 5
- Append behavior on restart without file deletion
- Secret/credential masking (API keys, tokens, passwords, cookies, private keys)
- Idempotent setup preventing duplicate log handlers and duplicate output
- Configurable log levels via argument and environment variable
- Structured event logging (JarvisEvent) to disk and buffer
- Exception traceback logging and crash handler hooks (sys.excepthook)
- Multithreaded concurrent logging safety
- Safe startup diagnostics
"""

import logging
import os
import sys
import threading
import time
from typing import Generator
import pytest

from core.logger import (
    SafeRotatingFileHandler,
    SensitiveDataFilter,
    SanitizingFormatter,
    JarvisEvent,
    StructuredActionLogger,
    LogBuffer,
    log_event,
    install_crash_handler,
    log_startup_diagnostics,
    setup_logging,
)


@pytest.fixture
def temp_log_dir(tmp_path) -> str:
    """Provides an isolated directory for log file tests."""
    log_dir = str(tmp_path / "test_logs")
    os.makedirs(log_dir, exist_ok=True)
    yield log_dir


class TestLogRotationAndRetention:
    """Tests for bounded rotation, backup file retention, and clean restart."""

    def test_safe_rotating_file_handler_rollover_and_retention(self, temp_log_dir: str):
        log_file = os.path.join(temp_log_dir, "jarvis.log")
        max_bytes = 400  # small threshold to trigger rotation quickly
        backup_count = 5

        handler = SafeRotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        test_logger = logging.getLogger("test.rotation")
        test_logger.setLevel(logging.INFO)
        test_logger.addHandler(handler)
        test_logger.propagate = False

        try:
            # Write enough data to trigger multiple rotations
            for i in range(100):
                test_logger.info(f"Log line number {i:03d}: Writing test message with some extra padding to consume bytes.")
                handler.flush()

            # Verify files created
            assert os.path.exists(log_file), "Active log file must exist"
            
            # Check rotated backups
            backups = [f for f in os.listdir(temp_log_dir) if f.startswith("jarvis.log.")]
            assert len(backups) > 0, "At least one backup file should be created"
            assert len(backups) <= backup_count, f"Backup count must never exceed {backup_count}"

            # Verify backup naming follows .1, .2, etc.
            for backup in backups:
                suffix = backup.replace("jarvis.log.", "")
                assert suffix.isdigit()
                idx = int(suffix)
                assert 1 <= idx <= backup_count, f"Rotated index {idx} out of range [1, {backup_count}]"

            # Check that jarvis.log.6 or higher was NEVER created
            excess_backups = [f for f in os.listdir(temp_log_dir) if f.startswith("jarvis.log.") and int(f.split(".")[-1]) > backup_count]
            assert len(excess_backups) == 0, f"Found excess backup files beyond {backup_count}: {excess_backups}"

        finally:
            handler.close()
            test_logger.removeHandler(handler)

    def test_restart_after_rotation_appends_cleanly(self, temp_log_dir: str):
        log_file = os.path.join(temp_log_dir, "jarvis.log")
        handler1 = SafeRotatingFileHandler(log_file, maxBytes=1000, backupCount=3, encoding="utf-8")
        test_logger = logging.getLogger("test.restart")
        test_logger.setLevel(logging.INFO)
        test_logger.addHandler(handler1)
        test_logger.propagate = False

        test_logger.info("Session 1: Initial message before shutdown")
        handler1.close()
        test_logger.removeHandler(handler1)

        # Reopen handler (simulating Jarvis restart)
        handler2 = SafeRotatingFileHandler(log_file, maxBytes=1000, backupCount=3, encoding="utf-8")
        test_logger.addHandler(handler2)
        test_logger.info("Session 2: Message after restart")
        handler2.close()
        test_logger.removeHandler(handler2)

        # Verify active log file preserved both sessions
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Session 1: Initial message before shutdown" in content
        assert "Session 2: Message after restart" in content


class TestCredentialAndSecretSanitization:
    """Tests for redacting secrets, API keys, bearer tokens, passwords, and cookies."""

    def test_sensitive_data_filter_and_formatter(self):
        formatter = SanitizingFormatter(fmt="%(levelname)s: %(message)s")

        samples = [
            # OpenAI / Groq / General API Key
            ("sk-1234567890abcdef1234567890abcdef", "[REDACTED_API_KEY]"),
            ("gsk_1234567890abcdef1234567890abcdef", "[REDACTED_API_KEY]"),
            ("AIzaSyD-abc123xyz123456789012345678901", "[REDACTED_API_KEY]"),
            # Bearer tokens
            ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz", "Bearer [REDACTED_TOKEN]"),
            # Key-value passwords and PINs
            ("password='my_secret_password_123'", "password='[REDACTED]'"),
            ('pin="987654"', 'pin="[REDACTED]"'),
            ("api_key: secret_token_xyz", "api_key: [REDACTED]"),
            # Cookies & Session IDs
            ('cookie: session_id="abc123xyz_cookie_val"', '[REDACTED]'),
            # Private keys
            (
                "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----",
                "[REDACTED_PRIVATE_KEY]"
            ),
        ]

        for secret_text, expected_mask in samples:
            sanitized = SensitiveDataFilter.sanitize(secret_text)
            assert expected_mask in sanitized, f"Failed to redact '{secret_text}'. Got: '{sanitized}'"
            assert secret_text not in sanitized, f"Original secret '{secret_text}' leaked in: '{sanitized}'"

    def test_logger_with_sanitizing_formatter(self, temp_log_dir: str):
        log_file = os.path.join(temp_log_dir, "sanitized.log")
        handler = SafeRotatingFileHandler(log_file, maxBytes=10000, backupCount=2, encoding="utf-8")
        handler.setFormatter(SanitizingFormatter(fmt="%(message)s"))
        handler.addFilter(SensitiveDataFilter())

        logger = logging.getLogger("test.sanitizer")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        try:
            logger.info("Connecting to service with sk-abcdef1234567890abcdef123456 and password='UltraSecurePassword!'")
            handler.flush()
        finally:
            handler.close()
            logger.removeHandler(handler)

        with open(log_file, "r", encoding="utf-8") as f:
            log_output = f.read()

        assert "sk-abcdef1234567890abcdef123456" not in log_output
        assert "UltraSecurePassword!" not in log_output
        assert "[REDACTED_API_KEY]" in log_output
        assert "password='[REDACTED]'" in log_output


class TestDuplicatePreventionAndConfig:
    """Tests for idempotent setup_logging and duplicate line prevention."""

    def test_duplicate_handler_prevention(self, temp_log_dir: str):
        # Call setup_logging 3 times consecutively
        for _ in range(3):
            setup_logging(
                level_name="INFO",
                log_to_file=True,
                log_dir=temp_log_dir,
                console_output=False,
                install_crash_hooks=False,
            )

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, SafeRotatingFileHandler)]
        assert len(file_handlers) == 1, f"Expected exactly 1 SafeRotatingFileHandler, found {len(file_handlers)}"

        # Verify a logged message is recorded exactly once in the file
        test_msg = "UNIQUE_VERIFICATION_MESSAGE_XYZ"
        logging.getLogger("jarvis").info(test_msg)

        log_file = os.path.join(temp_log_dir, "jarvis.log")
        for h in root.handlers:
            h.flush()

        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        occurrences = content.count(test_msg)
        assert occurrences == 1, f"Expected message to appear once, found {occurrences} times in log file"

    def test_configurable_log_level(self, temp_log_dir: str):
        # Setup logger at WARNING level
        setup_logging(
            level_name="WARNING",
            log_to_file=True,
            log_dir=temp_log_dir,
            console_output=False,
            install_crash_hooks=False,
        )

        logger = logging.getLogger("jarvis")
        logger.debug("DEBUG_SHOULD_BE_IGNORED")
        logger.info("INFO_SHOULD_BE_IGNORED")
        logger.warning("WARNING_SHOULD_BE_RECORDED")
        logger.error("ERROR_SHOULD_BE_RECORDED")

        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

        log_file = os.path.join(temp_log_dir, "jarvis.log")
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "DEBUG_SHOULD_BE_IGNORED" not in content
        assert "INFO_SHOULD_BE_IGNORED" not in content
        assert "WARNING_SHOULD_BE_RECORDED" in content
        assert "ERROR_SHOULD_BE_RECORDED" in content


class TestStructuredEventLogging:
    """Tests for standardized JarvisEvent logging and LogBuffer."""

    def test_structured_event_logging(self, temp_log_dir: str):
        setup_logging(
            level_name="INFO",
            log_to_file=True,
            log_dir=temp_log_dir,
            console_output=False,
            install_crash_hooks=False,
        )

        buffer = LogBuffer(max_size=50)
        action_logger = StructuredActionLogger(buffer=buffer)

        # Log high-level events
        action_logger.log_event(
            JarvisEvent.TASK_STARTED,
            details={"task_id": "task_101", "goal": "create report"},
            message="User requested report generation"
        )
        action_logger.log_event(
            JarvisEvent.COMMAND_EXECUTED,
            details={"command": "dir", "status": "success"},
            message="Directory listed"
        )

        # Also use module-level log_event
        log_event(JarvisEvent.APP_OPENED, details={"app": "notepad.exe"}, message="Notepad launched")

        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

        log_file = os.path.join(temp_log_dir, "jarvis.log")
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "[EVENT:TASK_STARTED]" in content
        assert "task_id='task_101'" in content
        assert "[EVENT:COMMAND_EXECUTED]" in content
        assert "[EVENT:APP_OPENED]" in content

        # Check buffer
        entries = buffer.get_entries()
        events = [e for e in entries if e.level == "EVENT"]
        assert len(events) >= 2
        assert any(e.category == "TASK_STARTED" for e in events)
        assert any(e.category == "COMMAND_EXECUTED" for e in events)


class TestDiagnosticsAndCrashHandling:
    """Tests for startup diagnostics and unhandled exception hooks."""

    def test_startup_diagnostics(self, temp_log_dir: str):
        setup_logging(
            level_name="INFO",
            log_to_file=True,
            log_dir=temp_log_dir,
            console_output=False,
            install_crash_hooks=False,
        )

        log_startup_diagnostics(
            version="2.1.0-test",
            log_dir=temp_log_dir,
            task_recovery_status="Recovered 0 pending tasks"
        )

        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

        log_file = os.path.join(temp_log_dir, "jarvis.log")
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "JARVIS STARTUP DIAGNOSTICS" in content
        assert "v2.1.0-test" in content
        assert "Operating System:" in content
        assert "Recovered 0 pending tasks" in content

    def test_exception_traceback_logging(self, temp_log_dir: str):
        setup_logging(
            level_name="INFO",
            log_to_file=True,
            log_dir=temp_log_dir,
            console_output=False,
            install_crash_hooks=False,
        )

        logger = logging.getLogger("jarvis.test_exception")
        try:
            raise ValueError("Test explicit failure for traceback")
        except ValueError:
            logger.exception("A handled error occurred during processing")

        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

        log_file = os.path.join(temp_log_dir, "jarvis.log")
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "A handled error occurred during processing" in content
        assert "ValueError: Test explicit failure for traceback" in content
        assert "Traceback (most recent call last):" in content

    def test_crash_handler_hook(self):
        captured_records = []

        class TestCrashHandler(logging.Handler):
            def emit(self, record):
                captured_records.append(record)

        crash_logger = logging.getLogger("jarvis.test_crash")
        handler = TestCrashHandler()
        crash_logger.addHandler(handler)

        original_sys_excepthook = sys.excepthook
        try:
            install_crash_handler(crash_logger)
            assert sys.excepthook != original_sys_excepthook

            # Simulate an unhandled exception through the hook
            try:
                raise RuntimeError("Simulated fatal uncaught crash")
            except RuntimeError as exc:
                sys.excepthook(type(exc), exc, exc.__traceback__)

            assert len(captured_records) == 1
            assert captured_records[0].levelno == logging.CRITICAL
            assert "UNHANDLED_EXCEPTION" in captured_records[0].getMessage()
            assert captured_records[0].exc_info is not None
        finally:
            sys.excepthook = original_sys_excepthook
            crash_logger.removeHandler(handler)


class TestMultithreadedLoggingSafety:
    """Tests for thread safety under concurrent logging."""

    def test_concurrent_logging(self, temp_log_dir: str):
        log_file = os.path.join(temp_log_dir, "concurrent.log")
        handler = SafeRotatingFileHandler(log_file, maxBytes=100000, backupCount=3, encoding="utf-8")
        logger = logging.getLogger("test.concurrent")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        thread_count = 8
        messages_per_thread = 50
        errors = []

        def worker(tid: int):
            try:
                for j in range(messages_per_thread):
                    logger.info(f"Thread {tid} message {j}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        handler.close()
        logger.removeHandler(handler)

        assert len(errors) == 0, f"Encountered errors during concurrent logging: {errors}"
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == thread_count * messages_per_thread
