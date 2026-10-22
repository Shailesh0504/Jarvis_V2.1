# core/agent/tool_registry.py
"""
Centralized Agent Tool Registry wrapping existing Jarvis skills and plugins without duplicate logic.
"""

from dataclasses import dataclass, field
import glob
import logging
import os
import platform
import psutil
from typing import Any, Callable, Dict, List, Optional

from core.agent.agent_state import AgentRiskLevel

logger = logging.getLogger("jarvis.agent.tool_registry")


@dataclass
class ToolResult:
    """Standardized output structure for any AgentTool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    observation: Optional[Dict[str, Any]] = None
    verified: bool = False

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: Optional[str] = None,
        observation: Optional[Dict[str, Any]] = None,
        verified: bool = False,
        output_data: Any = None,
    ):
        self.success = success
        self.data = data if data is not None else output_data
        self.error = error
        self.observation = observation
        self.verified = verified

    @property
    def output_data(self) -> Any:
        return self.data

    @output_data.setter
    def output_data(self, val: Any) -> None:
        self.data = val


@dataclass
class AgentTool:
    """Encapsulates a system capability into an autonomous agent tool."""
    name: str
    description: str
    risk_level: AgentRiskLevel
    handler: Callable[..., ToolResult]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    supports_verification: bool = True

    def execute(self, *args, **kwargs) -> ToolResult:
        try:
            if args:
                return self.handler(*args, **kwargs)
            return self.handler(**kwargs)
        except TypeError:
            try:
                return self.handler(kwargs)
            except Exception as e:
                return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.error("Error executing tool '%s': %s", self.name, e, exc_info=True)
            return ToolResult(success=False, error=str(e))


class ToolRegistry:
    """
    Authoritative registry mapping tool names to existing Jarvis capabilities.
    Enforces the NO-DUPLICATION rule by wrapping existing single-source-of-truth modules.
    """

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}
        self._register_default_tools()

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered agent tool: %s (%s)", tool.name, tool.risk_level)

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def get_tool(self, name: str) -> Optional[AgentTool]:
        return self.get(name)

    def execute(self, tool_name: str, parameters: Optional[Dict[str, Any]] = None, **kwargs) -> ToolResult:
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {tool_name}")
        params = dict(parameters or {})
        params.update(kwargs)
        return tool.execute(**params)

    def list_tools(self) -> List[AgentTool]:
        return list(self._tools.values())

    # --- Tool Implementations wrapping existing subsystems ---

    def _register_default_tools(self):
        # 1. Desktop: Open Application
        def _handle_open_app(target: str, **kwargs) -> ToolResult:
            from core.windows_app_resolver import get_windows_app_resolver
            resolver = get_windows_app_resolver()
            spec = resolver.resolve(target)
            if spec:
                from core.execution.strategies import get_execution_strategy_engine
                engine = get_execution_strategy_engine()
                outcome = engine.execute(spec)
                return ToolResult(
                    success=outcome.success,
                    data={"target": target, "app_id": spec.app_id, "mode": spec.launch_mode},
                    error=outcome.error,
                    verified=outcome.verified,
                    observation={"launched": outcome.success, "app": spec.canonical_name}
                )
            return ToolResult(success=False, error=f"Could not resolve application: {target}")

        self.register(AgentTool(
            name="desktop.open_application",
            description="Launches an installed Windows application or service by name",
            risk_level=AgentRiskLevel.LOW,
            handler=_handle_open_app,
            input_schema={"target": "str"},
        ))

        # 2. Desktop: Window Operations (minimize, maximize, restore, close, focus)
        def _handle_window_op(target: str, operation: str, **kwargs) -> ToolResult:
            from plugins.windows.window_manager import WindowManager
            wm = WindowManager()
            op = operation.lower()
            if op == "minimize":
                success = wm.minimize_target(target)
            elif op == "maximize":
                success = wm.maximize_target(target)
            elif op == "restore":
                success = wm.restore_target(target)
            elif op == "close":
                success = wm.close_target(target)
            elif op == "focus":
                success = wm.focus_target(target)
            else:
                return ToolResult(success=False, error=f"Unknown window operation: {operation}")

            return ToolResult(
                success=success,
                data={"target": target, "operation": operation},
                verified=success,
                observation={"operation": operation, "target": target, "success": success}
            )

        self.register(AgentTool(
            name="desktop.window_operation",
            description="Performs window state operations: minimize, maximize, restore, close, focus",
            risk_level=AgentRiskLevel.LOW,
            handler=_handle_window_op,
            input_schema={"target": "str", "operation": "str"},
        ))

        # 3. Browser: Open URL / Search
        def _handle_browser_open(url_or_query: str, browser: str = "chrome", **kwargs) -> ToolResult:
            from core.target_engine import UniversalTargetDiscoveryEngine
            engine = UniversalTargetDiscoveryEngine()
            outcome = engine.execute(f"open {url_or_query} in {browser}")
            return ToolResult(
                success=outcome.success,
                data=outcome.data,
                error=outcome.error,
                verified=outcome.verified,
                observation={"url_or_query": url_or_query, "browser": browser}
            )

        self.register(AgentTool(
            name="browser.open_url",
            description="Navigates to a website or executes a search in the specified browser",
            risk_level=AgentRiskLevel.LOW,
            handler=_handle_browser_open,
            input_schema={"url_or_query": "str", "browser": "str"},
        ))

        # 4. Filesystem: Inspect & Count Lines (supports Scenario 3)
        def _handle_fs_line_count(directory: str = ".", extension: str = ".py", min_lines: int = 1500, **kwargs) -> ToolResult:
            matches = []
            for dirpath, _, filenames in os.walk(directory):
                if any(p in dirpath for p in [".venv", "__pycache__", ".git", ".pytest_cache", "node_modules"]):
                    continue
                for f in filenames:
                    if f.endswith(extension):
                        full_path = os.path.join(dirpath, f)
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                                line_count = len(fp.readlines())
                            if line_count >= min_lines:
                                matches.append({"file": full_path, "lines": line_count})
                        except Exception:
                            pass
            matches.sort(key=lambda x: x["lines"], reverse=True)
            return ToolResult(
                success=True,
                data={"matches": matches, "count": len(matches)},
                verified=True,
                observation={"scanned_dir": directory, "found_count": len(matches)}
            )

        self.register(AgentTool(
            name="filesystem.find_large_files",
            description="Scans directory for source files exceeding specified line count threshold",
            risk_level=AgentRiskLevel.SAFE,
            handler=_handle_fs_line_count,
            input_schema={"directory": "str", "extension": "str", "min_lines": "int"},
        ))

        # 5. Filesystem: File Search & Read
        def _handle_read_file(file_path: str, max_lines: int = 200, **kwargs) -> ToolResult:
            if not os.path.exists(file_path):
                return ToolResult(success=False, error=f"File does not exist: {file_path}")
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                    content = "".join([fp.readline() for _ in range(max_lines)])
                return ToolResult(
                    success=True,
                    data={"file_path": file_path, "content": content},
                    verified=True,
                    observation={"file_size": os.path.getsize(file_path)}
                )
            except Exception as e:
                return ToolResult(success=False, error=str(e))

        self.register(AgentTool(
            name="filesystem.read_file",
            description="Reads text content from a specified file path",
            risk_level=AgentRiskLevel.SAFE,
            handler=_handle_read_file,
            input_schema={"file_path": "str", "max_lines": "int"},
        ))

        # 6. System: Get Hardware and System Telemetry
        def _handle_system_info(**kwargs) -> ToolResult:
            mem = psutil.virtual_memory()
            cpu_pct = psutil.cpu_percent(interval=0.1)
            info = {
                "os": platform.system(),
                "os_version": platform.version(),
                "total_ram_gb": round(mem.total / (1024 ** 3), 2),
                "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                "available_ram_gb": round(mem.available / (1024 ** 3), 2),
                "used_ram_percent": mem.percent,
                "ram_used_percent": mem.percent,
                "cpu_percent": cpu_pct,
            }
            return ToolResult(
                success=True,
                data=info,
                verified=True,
                observation=info
            )

        self.register(AgentTool(
            name="system.get_info",
            description="Retrieves OS, CPU, and RAM telemetry",
            risk_level=AgentRiskLevel.SAFE,
            handler=_handle_system_info,
        ))

        # 7. Media: Volume Control
        def _handle_volume(level: int, **kwargs) -> ToolResult:
            try:
                from plugins.audio.volume_controller import set_system_volume
                set_system_volume(level)
                return ToolResult(
                    success=True,
                    data={"volume": level},
                    verified=True,
                    observation={"volume_set": level}
                )
            except Exception as e:
                return ToolResult(success=False, error=str(e))

        self.register(AgentTool(
            name="system.set_volume",
            description="Sets system audio volume to specified percentage (0-100)",
            risk_level=AgentRiskLevel.LOW,
            handler=_handle_volume,
            input_schema={"level": "int"},
        ))


# Global singleton instance
_GLOBAL_REGISTRY: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ToolRegistry()
    return _GLOBAL_REGISTRY
