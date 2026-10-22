# plugins/manifest.py
"""Plugin Manifest and Data Transfer Objects for Jarvis V2."""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
from core.permissions import PermissionLevel, PluginCapability


class PluginStatus(str, Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"
    REMOVED = "REMOVED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class PluginParameter:
    name: str
    type: str
    description: str
    required: bool = False
    default: Any = None


@dataclass
class PluginAction:
    name: str
    description: str
    keywords: List[str]
    parameters: List[PluginParameter] = field(default_factory=list)
    required_permission: PermissionLevel = PermissionLevel.READ
    required_capability: Optional[str] = None  # e.g. "filesystem", "office", "network", etc.


@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    author: str = "Jarvis"
    enabled: bool = True
    permissions: List[Any] = field(default_factory=list)  # List of capability strings or permissions
    actions: List[PluginAction] = field(default_factory=list)
    supported_intents: List[str] = field(default_factory=list)

    @property
    def normalized_permissions(self) -> List[str]:
        """Convert any declared permissions (strings, enums, or dict keys) into standardized capability strings."""
        raw = self.permissions
        if isinstance(raw, dict):
            raw = list(raw.keys())
        result: List[str] = []
        for p in raw:
            val = p.value if hasattr(p, "value") else str(p)
            result.append(str(val).strip().lower())
        return result

    def get_action(self, action_name: str) -> Optional[PluginAction]:
        for a in self.actions:
            if a.name.lower() == action_name.lower():
                return a
        return None

    @classmethod
    def from_json_file(cls, filepath: str) -> "PluginManifest":
        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        actions = []
        for raw_action in data.get("actions", []):
            parameters = [PluginParameter(
                name=p["name"], type=p.get("type", "string"),
                description=p.get("description", ""), required=p.get("required", False),
                default=p.get("default")
            ) for p in raw_action.get("parameters", [])]
            try:
                permission = PermissionLevel(raw_action.get("required_permission", PermissionLevel.READ.value))
            except (TypeError, ValueError):
                permission = PermissionLevel.READ
            actions.append(PluginAction(
                name=raw_action["name"], description=raw_action.get("description", ""),
                keywords=raw_action.get("keywords", []), parameters=parameters,
                required_permission=permission,
                required_capability=raw_action.get("required_capability")
            ))
        return cls(
            name=data.get("name", "unknown"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "Jarvis"),
            enabled=data.get("enabled", True),
            permissions=data.get("permissions", []),
            actions=actions,
            supported_intents=data.get("supported_intents", [])
        )


@dataclass
class PluginResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    status: Optional[str] = None
    verification_result: Optional[Any] = None
    strategy_used: str = "primary"
    retry_count: int = 0
    timestamp: float = field(default_factory=time.time)
