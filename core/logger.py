# core/logger.py
"""
Production-Grade Structured Action Logger and Central Logging System for Jarvis V2.
Features:
- Safe log rotation with bounded disk usage (10 MB x 5 backups, Windows-safe).
- Zero duplicate handlers and zero duplicate log entries.
- Automated secret and credential sanitization (API keys, tokens, passwords, cookies).
- High-frequency low-noise protection for voice and real-time execution.
- Standardized structured event logging (TASK_STARTED, COMMAND_EXECUTED, APP_OPENED, etc.).
- Startup diagnostics and unhandled crash resilience via excepthooks.
- Backward-compatible public API.
"""

from collections import deque
from dataclasses import dataclass, field
import datetime
from enum import Enum
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

# Defaults
DEFAULT_LOG_DIR = os.getenv("JARVIS_LOG_DIR", "logs")
DEFAULT_LOG_LEVEL = os.getenv("JARVIS_LOG_LEVEL", "INFO")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

# Backward-compatible global aliases
LOGS_DIR = DEFAULT_LOG_DIR
MAIN_LOG_FILE = os.path.join(LOGS_DIR, "jarvis.log")
MISTAKES_LOG_FILE = os.path.join(LOGS_DIR, "jarvis_mistakes.jsonl")


# =========================================================================
# 1. Credential & Sensitive Data Sanitization
# =========================================================================

class SensitiveDataFilter(logging.Filter):
    """
    Scrubs passwords, API keys, bearer tokens, cookies, and secrets
    from log records before they are written to disk or console.
    """

    SENSITIVE_PATTERNS = [
        # API Keys (OpenAI, Anthropic, Google, Groq, etc.)
        (re.compile(r'\b(sk-[a-zA-Z0-9_\-]{20,})\b', re.IGNORECASE), r'[REDACTED_API_KEY]'),
        (re.compile(r'\b(gsk_[a-zA-Z0-9_\-]{20,})\b', re.IGNORECASE), r'[REDACTED_API_KEY]'),
        (re.compile(r'\b(AIza[0-9A-Za-z_\-]{30,45})\b'), r'[REDACTED_API_KEY]'),
        (re.compile(r'\b(Bearer\s+)[a-zA-Z0-9\-_.~+/]+=*\b', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),

        # Key-Value Secrets (password="...", api_key="...", admin_passcode="...")
        (
            re.compile(
                r'((?:password|passwd|passcode|admin_passcode|master_pin|pin|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*[\'"]?)([^\'"\s,;]{3,})([\'"]?)',
                re.IGNORECASE
            ),
            r'\1[REDACTED]\3'
        ),

        # Authorization headers and cookies
        (
            re.compile(
                r'((?:authorization|cookie|session_id)\s*[:=]\s*[\'"]?)([^\'"\s,;]{5,})([\'"]?)',
                re.IGNORECASE
            ),
            r'\1[REDACTED]\3'
        ),

        # Private Keys
        (
            re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[^-]+-----END [A-Z ]*PRIVATE KEY-----', re.DOTALL),
            r'[REDACTED_PRIVATE_KEY]'
        ),
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Sanitizes text by masking matched credential patterns."""
        if not text or not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    def filter(self, record: logging.LogRecord) -> bool:
        """Mutates record in-place to scrub secrets from message and arguments."""
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.sanitize(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self.sanitize(a) if isinstance(a, str) else a for a in record.args)
        return True


class SanitizingFormatter(logging.Formatter):
    """Formats log records and ensures output (including tracebacks) is thoroughly sanitized."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return SensitiveDataFilter.sanitize(formatted)


# =========================================================================
# 2. Windows-Safe Rotating File Handler
# =========================================================================

class SafeRotatingFileHandler(RotatingFileHandler):
    """
    Windows-resilient RotatingFileHandler.
    Prevents PermissionError or transient file locks during rollover from crashing Jarvis.
    Never deletes the active log file during rotation.
    """

    def doRollover(self) -> None:
        """Safely performs file rollover with retry logic for Windows file locking."""
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # On Windows, if indexer or virus scanner briefly holds the file, retry once
            try:
                time.sleep(0.05)
                super().doRollover()
            except Exception as retry_err:
                # Logging failure must never crash Jarvis: write warning to stderr and continue
                sys.stderr.write(f"[JarvisLogging Warning] Log rotation deferred: {retry_err}\n")

    def handleError(self, record: logging.LogRecord) -> None:
        """Swallows logging handler exceptions to guarantee zero application crashes."""
        try:
            super().handleError(record)
        except Exception:
            pass


# =========================================================================
# 3. Structured Events
# =========================================================================

class JarvisEvent(str, Enum):
    """Standardized production event types for multi-step tasks, memory, and actions."""
    TASK_STARTED = "TASK_STARTED"
    TASK_STEP_STARTED = "TASK_STEP_STARTED"
    TASK_STEP_COMPLETED = "TASK_STEP_COMPLETED"
    TASK_STEP_FAILED = "TASK_STEP_FAILED"
    TASK_RETRY = "TASK_RETRY"
    TASK_RESUMED = "TASK_RESUMED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_COMPLETED = "TASK_COMPLETED"
    MEMORY_STORED = "MEMORY_STORED"
    MEMORY_RETRIEVED = "MEMORY_RETRIEVED"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    PLUGIN_EXECUTED = "PLUGIN_EXECUTED"
    APP_OPENED = "APP_OPENED"
    APP_CLOSED = "APP_CLOSED"


# =========================================================================
# 4. In-Memory Activity Buffer & Data Models
# =========================================================================

@dataclass
class LogEntry:
    timestamp: str
    level: str  # DEBUG, INFO, WARNING, ERROR, SUCCESS, INTENT, PLUGIN, ACTION, MEMORY, INPUT, EVENT
    category: str
    message: str
    raw_time: float = 0.0


class LogBuffer:
    """Thread-safe in-memory ring buffer holding recent log entries for GUI and live telemetry."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[LogEntry], None]] = []

    def append(self, entry: LogEntry) -> None:
        with self._lock:
            self._buffer.append(entry)
        for cb in self._callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    def get_entries(self, level_filter: Optional[str] = None, search: Optional[str] = None) -> List[LogEntry]:
        with self._lock:
            entries = list(self._buffer)

        if level_filter and level_filter != "ALL":
            entries = [e for e in entries if e.level == level_filter]

        if search:
            s_lower = search.lower()
            entries = [e for e in entries if s_lower in e.message.lower() or s_lower in e.category.lower()]

        return entries

    def register_callback(self, cb: Callable[[LogEntry], None]) -> None:
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


# Global Log Buffer Singleton
GLOBAL_LOG_BUFFER = LogBuffer()


# =========================================================================
# 5. Structured Action & Event Logger
# =========================================================================

class StructuredActionLogger:
    """Formats and records pipeline actions and high-level structured events."""

    def __init__(self, buffer: Optional[LogBuffer] = None, logger_instance: Optional[logging.Logger] = None):
        self.buffer = buffer or GLOBAL_LOG_BUFFER
        self.logger = logger_instance or logging.getLogger("jarvis.action")

    def _now(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _log(self, level: str, category: str, message: str) -> LogEntry:
        ts = self._now()
        entry = LogEntry(timestamp=ts, level=level, category=category, message=message, raw_time=time.time())
        self.buffer.append(entry)
        formatted = f"{ts} {category.upper()}: {message}"
        self.logger.info(formatted)
        return entry

    def log_input(self, text: str) -> LogEntry:
        return self._log("INPUT", "INPUT", text)

    def log_intent(self, intent_name: str, confidence: float = 1.0) -> LogEntry:
        return self._log("INTENT", "INTENT", f"{intent_name} (conf: {confidence:.2f})")

    def log_plugin(self, plugin_name: str) -> LogEntry:
        return self._log("PLUGIN", "PLUGIN", plugin_name)

    def log_action(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> LogEntry:
        params_str = f" ({parameters})" if parameters else ""
        return self._log("ACTION", "ACTION", f"{action_name}{params_str}")

    def log_success(self, message: str, execution_time_ms: float = 0.0) -> LogEntry:
        time_suffix = f" ({execution_time_ms:.2f}ms)" if execution_time_ms > 0 else ""
        return self._log("SUCCESS", "SUCCESS", f"{message}{time_suffix}")

    def log_error(self, error_message: str) -> LogEntry:
        return self._log("ERROR", "ERROR", error_message)

    def log_memory(self, detail: str) -> LogEntry:
        return self._log("MEMORY", "MEMORY", detail)

    def log_debug(self, detail: str) -> LogEntry:
        return self._log("DEBUG", "DEBUG", detail)

    def log_event(
        self,
        event: Union[JarvisEvent, str],
        details: Optional[Dict[str, Any]] = None,
        message: str = ""
    ) -> LogEntry:
        """Records a standardized structured event in both disk log and in-memory buffer."""
        evt_name = event.value if isinstance(event, JarvisEvent) else str(event)
        parts = []
        if message:
            parts.append(message)
        if details:
            clean_details = " ".join(f"{k}={v!r}" for k, v in details.items())
            parts.append(clean_details)
        content = f"[EVENT:{evt_name}] " + (" ".join(parts) if parts else "")
        return self._log("EVENT", evt_name, content.strip())


def log_event(
    event: Union[JarvisEvent, str],
    details: Optional[Dict[str, Any]] = None,
    message: str = "",
    level: int = logging.INFO
) -> None:
    """Convenience module function to log a standardized structured event to jarvis.event."""
    evt_name = event.value if isinstance(event, JarvisEvent) else str(event)
    logger = logging.getLogger("jarvis.event")
    parts = []
    if message:
        parts.append(message)
    if details:
        clean_details = " ".join(f"{k}={v!r}" for k, v in details.items())
        parts.append(clean_details)
    payload = f"[EVENT:{evt_name}] " + (" ".join(parts) if parts else "")
    logger.log(level, payload.strip())


# =========================================================================
# 5b. Machine-Readable Structured Mistake & Learning Logger
# =========================================================================

class MistakeCategory(str, Enum):
    """Failure and mistake taxonomy for machine learning and root cause analysis."""
    INTENT_ERROR = "intent_error"
    TARGET_RESOLUTION_ERROR = "target_resolution_error"
    TOOL_FAILURE = "tool_failure"
    VERIFICATION_FAILURE = "verification_failure"
    SYNTAX_EXCEPTION = "syntax_exception"
    SYSTEM_PERMISSION_ERROR = "system_permission_error"
    USER_CORRECTION = "user_correction"
    EXECUTION_ERROR = "execution_error"
    GENERAL_FAILURE = "general_failure"


@dataclass
class MistakeRecord:
    """
    Standardized, machine-readable structured mistake record for self-learning.
    Designed so an AI agent can parse, inspect, cluster, and learn from past failures.
    """
    log_id: str
    timestamp: str
    category: str
    user_query: str
    normalized_query: str = ""
    turn_id: str = ""
    intent: str = ""
    confidence: float = 0.0
    attempted_action: str = ""
    action_parameters: Dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""
    failing_module: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    diagnosis: str = ""
    anti_pattern: str = ""
    recommended_fix: str = ""
    learned_status: str = "PENDING"  # PENDING, DIGESTED, DISCARDED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "turn_id": self.turn_id,
            "user_query": self.user_query,
            "normalized_query": self.normalized_query,
            "intent": self.intent,
            "confidence": self.confidence,
            "attempted_action": self.attempted_action,
            "action_parameters": self.action_parameters,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "failing_module": self.failing_module,
            "context": self.context,
            "diagnosis": self.diagnosis,
            "anti_pattern": self.anti_pattern,
            "recommended_fix": self.recommended_fix,
            "learned_status": self.learned_status
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MistakeRecord":
        return cls(
            log_id=data.get("log_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.datetime.now().isoformat()),
            category=data.get("category", MistakeCategory.GENERAL_FAILURE.value),
            turn_id=data.get("turn_id", ""),
            user_query=data.get("user_query", ""),
            normalized_query=data.get("normalized_query", ""),
            intent=data.get("intent", ""),
            confidence=float(data.get("confidence", 0.0)),
            attempted_action=data.get("attempted_action", ""),
            action_parameters=data.get("action_parameters", {}) or {},
            error_type=data.get("error_type", ""),
            error_message=data.get("error_message", ""),
            failing_module=data.get("failing_module", ""),
            context=data.get("context", {}) or {},
            diagnosis=data.get("diagnosis", ""),
            anti_pattern=data.get("anti_pattern", ""),
            recommended_fix=data.get("recommended_fix", ""),
            learned_status=data.get("learned_status", "PENDING")
        )


class MistakeLogWriter:
    """
    Thread-safe writer and reader for the structured JSONL learning log.
    Ensures zero secret leakage, safe Windows file operations, and idempotent digestion.
    """

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir or LOGS_DIR
        self._lock = threading.RLock()

    @property
    def log_file(self) -> str:
        return os.path.join(self.log_dir, "jarvis_mistakes.jsonl")

    def write_mistake(self, record: Union[MistakeRecord, Dict[str, Any]]) -> str:
        with self._lock:
            try:
                os.makedirs(self.log_dir, exist_ok=True)
                data = record.to_dict() if isinstance(record, MistakeRecord) else dict(record)
                if "log_id" not in data or not data["log_id"]:
                    data["log_id"] = str(uuid.uuid4())
                if "timestamp" not in data or not data["timestamp"]:
                    data["timestamp"] = datetime.datetime.now().isoformat()
                if "learned_status" not in data:
                    data["learned_status"] = "PENDING"

                # Sanitize all string values for credential security
                sanitized_data = self._sanitize_dict(data)

                line = json.dumps(sanitized_data, ensure_ascii=False)
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                return sanitized_data["log_id"]
            except Exception as exc:
                sys.stderr.write(f"[MistakeLogWriter Warning] Failed to write mistake record: {exc}\n")
                return ""

    def get_unlearned_mistakes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            if not os.path.exists(self.log_file):
                return []
            unlearned = []
            try:
                with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            item = json.loads(line_str)
                            if item.get("learned_status") == "PENDING":
                                unlearned.append(item)
                                if len(unlearned) >= limit:
                                    break
                        except Exception:
                            continue
            except Exception as e:
                logging.getLogger("jarvis.logger").debug("Error reading unlearned mistakes: %s", e)
            return unlearned

    def mark_as_digested(self, log_ids: List[str]) -> None:
        if not log_ids:
            return
        id_set = set(log_ids)
        with self._lock:
            if not os.path.exists(self.log_file):
                return
            lines = []
            updated = False
            try:
                with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            item = json.loads(line_str)
                            if item.get("log_id") in id_set and item.get("learned_status") != "DIGESTED":
                                item["learned_status"] = "DIGESTED"
                                item["digested_at"] = datetime.datetime.now().isoformat()
                                lines.append(json.dumps(item, ensure_ascii=False))
                                updated = True
                            else:
                                lines.append(line_str)
                        except Exception:
                            lines.append(line_str)

                if updated:
                    temp_file = self.log_file + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        for l in lines:
                            f.write(l + "\n")
                    if os.path.exists(temp_file):
                        try:
                            os.replace(temp_file, self.log_file)
                        except Exception:
                            import shutil
                            shutil.copyfile(temp_file, self.log_file)
                            os.remove(temp_file)
            except Exception as e:
                logging.getLogger("jarvis.logger").debug("Error marking mistakes as digested: %s", e)

    def get_all_mistakes(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            if not os.path.exists(self.log_file):
                return []
            items = []
            try:
                with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line_str = line.strip()
                        if line_str:
                            try:
                                items.append(json.loads(line_str))
                            except Exception:
                                pass
            except Exception:
                pass
            return items[-limit:]

    def _sanitize_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        sensitive_keys = {"password", "passwd", "passcode", "secret", "token", "api_key", "apikey", "pin", "auth"}
        res = {}
        for k, v in d.items():
            k_lower = str(k).lower().strip()
            if any(s in k_lower for s in sensitive_keys) and isinstance(v, str):
                res[k] = "[REDACTED]"
            elif isinstance(v, str):
                res[k] = SensitiveDataFilter.sanitize(v)
            elif isinstance(v, dict):
                res[k] = self._sanitize_dict(v)
            elif isinstance(v, list):
                res[k] = [
                    SensitiveDataFilter.sanitize(x)
                    if isinstance(x, str)
                    else (self._sanitize_dict(x) if isinstance(x, dict) else x)
                    for x in v
                ]
            else:
                res[k] = v
        return res


_GLOBAL_MISTAKE_WRITER: Optional[MistakeLogWriter] = None


def get_mistake_logger() -> MistakeLogWriter:
    """Returns the central MistakeLogWriter singleton."""
    global _GLOBAL_MISTAKE_WRITER
    if _GLOBAL_MISTAKE_WRITER is None:
        _GLOBAL_MISTAKE_WRITER = MistakeLogWriter(log_dir=LOGS_DIR)
    return _GLOBAL_MISTAKE_WRITER


def log_mistake(
    category: Union[MistakeCategory, str],
    user_query: str,
    error_message: str,
    normalized_query: str = "",
    turn_id: str = "",
    intent: str = "",
    confidence: float = 0.0,
    attempted_action: str = "",
    action_parameters: Optional[Dict[str, Any]] = None,
    error_type: str = "",
    failing_module: str = "",
    context: Optional[Dict[str, Any]] = None,
    diagnosis: str = "",
    anti_pattern: str = "",
    recommended_fix: str = ""
) -> str:
    """
    Convenience function to log a structured mistake record to logs/jarvis_mistakes.jsonl.
    Returns the generated log_id.
    """
    cat_val = category.value if isinstance(category, MistakeCategory) else str(category)
    record = MistakeRecord(
        log_id=str(uuid.uuid4()),
        timestamp=datetime.datetime.now().isoformat(),
        category=cat_val,
        turn_id=turn_id,
        user_query=user_query,
        normalized_query=normalized_query or user_query,
        intent=intent,
        confidence=confidence,
        attempted_action=attempted_action,
        action_parameters=action_parameters or {},
        error_type=error_type,
        error_message=error_message,
        failing_module=failing_module,
        context=context or {},
        diagnosis=diagnosis,
        anti_pattern=anti_pattern,
        recommended_fix=recommended_fix
    )
    return get_mistake_logger().write_mistake(record)


# =========================================================================
# 6. Startup Diagnostics & Crash Handler
# =========================================================================

def install_crash_handler(logger_instance: Optional[logging.Logger] = None) -> None:
    """Installs sys.excepthook and threading.excepthook to log unhandled fatal crashes with tracebacks."""
    target_logger = logger_instance or logging.getLogger("jarvis.crash")

    def handle_sys_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        target_logger.critical("UNHANDLED_EXCEPTION: An unhandled crash occurred", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
        except Exception:
            pass

    sys.excepthook = handle_sys_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            target_logger.critical(
                f"UNHANDLED_THREAD_EXCEPTION: Thread '{args.thread.name}' crashed",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
            )
        threading.excepthook = handle_thread_exception


def log_startup_diagnostics(
    version: str = "2.0.0",
    log_dir: Optional[str] = None,
    task_recovery_status: Optional[str] = None
) -> None:
    """Logs startup diagnostics without exposing sensitive credentials or env vars."""
    logger = logging.getLogger("jarvis.startup")
    effective_level = logging.getLevelName(logging.getLogger().getEffectiveLevel())
    py_ver = sys.version.split()[0]
    os_info = f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
    target_dir = os.path.abspath(log_dir or DEFAULT_LOG_DIR)
    recovery_info = task_recovery_status or "Normal startup (no active tasks pending)"

    logger.info("================== JARVIS STARTUP DIAGNOSTICS ==================")
    logger.info("Jarvis Version:           v%s", version)
    logger.info("Python Version:           %s", py_ver)
    logger.info("Operating System:         %s", os_info)
    logger.info("Logging Level:            %s", effective_level)
    logger.info("Log Directory:            %s", target_dir)
    logger.info("Active Task Recovery:     %s", recovery_info)
    logger.info("================================================================")


# =========================================================================
# 7. Central Idempotent Logging Configuration
# =========================================================================

def setup_logging(
    level_name: Optional[str] = None,
    log_to_file: bool = True,
    log_dir: Optional[str] = None,
    console_output: bool = True,
    install_crash_hooks: bool = True,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """
    Configures production logging for Jarvis V2 with:
    - Bounded log rotation (10 MB x 5 backups by default).
    - Secret and credential sanitization on all handlers.
    - Idempotent handler setup to completely eliminate duplicate logging.
    - Configurable log levels via JARVIS_LOG_LEVEL environment variable or argument.
    """
    # 1. Resolve log level
    env_level = os.getenv("JARVIS_LOG_LEVEL")
    selected_level_str = env_level or level_name or DEFAULT_LOG_LEVEL
    numeric_level = getattr(logging, selected_level_str.upper(), logging.INFO)

    # 2. Resolve log directory & path
    env_dir = os.getenv("JARVIS_LOG_DIR")
    effective_log_dir = env_dir or log_dir or DEFAULT_LOG_DIR
    os.makedirs(effective_log_dir, exist_ok=True)
    active_log_file = os.path.join(effective_log_dir, "jarvis.log")

    # Update global module constants
    global LOGS_DIR, MAIN_LOG_FILE, MISTAKES_LOG_FILE, _GLOBAL_MISTAKE_WRITER
    LOGS_DIR = effective_log_dir
    MAIN_LOG_FILE = active_log_file
    MISTAKES_LOG_FILE = os.path.join(effective_log_dir, "jarvis_mistakes.jsonl")
    if _GLOBAL_MISTAKE_WRITER is not None:
        _GLOBAL_MISTAKE_WRITER.log_dir = effective_log_dir

    # 3. Clean existing handlers on root and jarvis loggers to prevent duplication
    root = logging.getLogger()
    root.setLevel(numeric_level)
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    jarvis_logger = logging.getLogger("jarvis")
    jarvis_logger.setLevel(numeric_level)
    jarvis_logger.propagate = True
    for h in list(jarvis_logger.handlers):
        jarvis_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    # 4. Formatter & Sanitizer
    formatter = SanitizingFormatter(
        fmt="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    secret_filter = SensitiveDataFilter()

    # 5. Console Handler
    if console_output:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(numeric_level)
        console.setFormatter(formatter)
        console.addFilter(secret_filter)
        root.addHandler(console)

    # 6. Rotating File Handler
    if log_to_file:
        rfh = SafeRotatingFileHandler(
            active_log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        rfh.setLevel(numeric_level)
        rfh.setFormatter(formatter)
        rfh.addFilter(secret_filter)
        root.addHandler(rfh)

    # 7. Install crash hooks
    if install_crash_hooks:
        install_crash_handler(logging.getLogger("jarvis.crash"))

    return jarvis_logger
