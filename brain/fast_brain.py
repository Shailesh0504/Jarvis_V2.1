# brain/fast_brain.py
"""Fast Brain (System 1): Instant Reflexive Execution Engine (<5ms Latency)."""

from dataclasses import dataclass
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.brain.fast")


@dataclass
class FastMatchResult:
    matched: bool
    plugin_name: str = ""
    action_name: str = ""
    parameters: Dict[str, Any] = None
    confidence: float = 1.0


class FastBrain:
    """System 1: Evaluates and executes obvious, unambiguous single-action commands instantly."""

    def __init__(self, plugin_manager: Optional[Any] = None):
        self.plugin_manager = plugin_manager
        self._init_grammars()

    def _init_grammars(self) -> None:
        """Precompiled high-speed regex matchers."""
        self.patterns = [
            # 1. App Launching: "Chrome kholo", "open brave browser please", "open notepad", "calc launch karo", "vlc kholo"
            (
                re.compile(r"^(?:open|launch|start|run|kholo|chalao)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+(?:browser|app|editor))?(?:\s+(?:please|karo|na|dost|jarvis))?$", re.IGNORECASE),
                "windows",
                "launch_app",
                lambda m: {"app_name": m.group(1).strip()}
            ),
            (
                re.compile(r"^([a-zA-Z0-9_\-\s]+?)(?:\s+(?:browser|app|editor))?\s+(?:kholo|chalao|open\s+karo|launch\s+karo)(?:\s+(?:please|na|dost|jarvis))?$", re.IGNORECASE),
                "windows",
                "launch_app",
                lambda m: {"app_name": m.group(1).strip()}
            ),
            # 2. App Closing: "close excel", "excel band karo", "close chrome", "terminate notepad"
            (
                re.compile(r"^(?:close|kill|terminate|stop|exit)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+(?:app|browser|application|editor))?(?:\s+(?:please|karo|na|dost|jarvis))?$", re.IGNORECASE),
                "windows",
                "close_app",
                lambda m: {"app_name": m.group(1).strip()}
            ),
            (
                re.compile(r"^([a-zA-Z0-9_\-\s]+?)(?:\s+(?:app|browser|application|editor))?\s+(?:band\s+karo|close\s+karo|kill\s+karo|band\s+kar\s+do)(?:\s+(?:please|karo|na|dost|jarvis))?$", re.IGNORECASE),
                "windows",
                "close_app",
                lambda m: {"app_name": m.group(1).strip()}
            ),
            # 2. Volume control: "Volume 50 karo", "set volume 80", "volume 30"
            (
                re.compile(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})(?:\s*karo|\s*%|\s*percent)?$", re.IGNORECASE),
                "audio",
                "set_volume",
                lambda m: {"level": int(m.group(1))}
            ),
            # 3. Screenshot: "Screenshot lo", "take screenshot", "capture screen"
            (
                re.compile(r"^(?:take\s+)?screenshot(?:\s+lo|\s+karo)?$", re.IGNORECASE),
                "system",
                "take_screenshot",
                lambda m: {}
            ),
            # 4. VLC Play: "VLC play karo", "play vlc"
            (
                re.compile(r"^(?:vlc\s+play(?:\s+karo)?|play\s+vlc)$", re.IGNORECASE),
                "vlc",
                "play_file",
                lambda m: {"path": ""}
            ),
            # 5. System Lock: "system lock", "lock pc", "lock screen", "pc lock karo", "screen lock"
            (
                re.compile(r"^(?:system\s+lock|lock\s+pc|lock\s+screen|lock\s+system|pc\s+lock(?:\s+karo)?|screen\s+lock(?:\s+karo)?|lock\s+computer)$", re.IGNORECASE),
                "system",
                "lock_pc",
                lambda m: {}
            ),
            # 6. System Restart: "system restart", "system restart karo", "restart pc", "restart computer", "pc restart karo", "reboot"
            (
                re.compile(r"^(?:(?:system|computer|pc)\s+restart(?:\s+karo|\s+kar\s+do)?|restart\s+(?:the\s+)?(?:pc|computer|system)|reboot)$", re.IGNORECASE),
                "system",
                "shutdown_pc",
                lambda m: {"restart": True, "query": m.group(0).strip()}
            ),
            # 7. Shutdown PC: "Computer shutdown karo", "system shutdown karo", "shutdown pc", "shut down the computer", "pc band karo"
            (
                re.compile(r"^(?:(?:computer|pc|system)?\s*(?:shut\s*down|band\s+karo|turn\s+off|power\s+off)(?:\s+the)?(?:\s+pc|\s+computer|\s+system|\s+karo|\s+kar\s+do)?|(?:shut\s*down|turn\s+off|power\s+off)\s+(?:the\s+)?(?:pc|computer|system))$", re.IGNORECASE),
                "system",
                "shutdown_pc",
                lambda m: {"restart": False, "query": m.group(0).strip()}
            ),
            # 6. Time & Clock: "What time is it", "time batao", "current time", "time kya ho raha hai", "clock"
            (
                re.compile(r"^(?:what\s+time\s+(?:is\s+it)?|time|current\s+time|time\s+batao|time\s+bataiye|time\s+kya\s+(?:hai|hua|ho\s+raha\s+hai)|kya\s+time\s+(?:hai|hua|ho\s+raha\s+hai)|kitne\s+baje\s+(?:hain)?|samay\s+kya\s+hai|clock|date)$", re.IGNORECASE),
                "system",
                "get_time",
                lambda m: {"query": m.group(0).strip()}
            ),
            # 7. System status: "system stats", "hardware status", "health check"
            (
                re.compile(r"^(?:system\s+stats|hardware\s+status|check\s+status|pc\s+status|cpu\s+usage)$", re.IGNORECASE),
                "system",
                "get_system_info",
                lambda m: {}
            ),
            # 8. Math Calculations: "2+2=?", "2+2", "100/4", "calculate 25+35", "50*5", "what is 2+2"
            (
                re.compile(r"^(?:calculate|compute|solve|eval|evaluate|what\s+is|what\'s|batao|hisaab\s+karo)?\s*\(?\s*(\d+(?:\.\d+)?\s*(?:[\+\-\*\/\^%x]|times|plus|minus|into|divided\s+by|divide\s+by|multiplied\s+by)\s*\(?\s*\d+(?:\.\d+)?.*)\s*$", re.IGNORECASE),
                "math",
                "calculate",
                lambda m: {"expression": m.group(0).strip()}
            )
        ]

    def match_fast_command(self, query: str) -> FastMatchResult:
        cleaned = query.strip()
        lower = cleaned.lower()

        # Ignore complex compound requests containing 'aur', 'and', 'organize', 'report', 'duplicate'
        if any(w in lower for w in [" aur ", " and ", "organize", "duplicate", "report", "then", "clean"]):
            return FastMatchResult(matched=False)

        # Check explicit patterns
        for pattern, plugin, action, param_fn in self.patterns:
            m = pattern.match(cleaned)
            if m:
                if plugin == "windows" and action in ("launch_app", "close_app"):
                    app_candidate = m.group(1).lower().strip()
                    known_apps = {
                        "chrome", "edge", "brave", "firefox", "browser", "notepad",
                        "calc", "calculator", "vlc", "cmd", "powershell", "terminal",
                        "code", "vscode", "vs code", "explorer", "file explorer",
                        "word", "excel", "powerpoint", "store", "microsoft store",
                        "windows store", "ms store", "msstore", "spotify", "discord",
                        "telegram", "settings", "setting", "windows settings",
                        "control panel", "task manager", "taskmgr", "camera", "paint",
                        "whatsapp", "photos", "snipping tool", "clock", "weather"
                    }
                    if app_candidate not in known_apps:
                        continue

                params = param_fn(m)
                return FastMatchResult(
                    matched=True,
                    plugin_name=plugin,
                    action_name=action,
                    parameters=params,
                    confidence=0.99
                )

        return FastMatchResult(matched=False)

    def execute_fast(self, query: str) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        Attempts fast reflexive execution.
        Returns (executed_fast, response_message, result_data).
        """
        start_time = time.perf_counter()
        match = self.match_fast_command(query)
        if not match.matched or not self.plugin_manager:
            return False, None, None

        res = self.plugin_manager.execute_action(match.plugin_name, match.action_name, match.parameters)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(f"FastBrain executed in {elapsed_ms:.2f}ms: {match.plugin_name}.{match.action_name}")

        if res.success:
            if isinstance(res.data, dict):
                msg = res.data.get("formatted_answer") or res.data.get("message") or str(res.data)
            else:
                msg = str(res.data)
            return True, msg or f"Executed {match.action_name}.", res.data

        err_msg = (res.data.get("message") if isinstance(res.data, dict) and res.data.get("message") else None) or res.error or f"Fast execution failed: {match.plugin_name}.{match.action_name}"
        return True, err_msg, None
