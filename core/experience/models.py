# core/experience/models.py
"""
Data Models for the Persistent Experience Learning System.
Defines episodic, semantic, procedural, failure, and preference memory records,
confidence scoring, versioning, and planning context bundles.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from typing import Any, Dict, List, Optional
import uuid


class MemoryType(str, Enum):
    """Core taxonomy of cognitive experience memories."""
    EPISODIC = "episodic"        # Specific past task execution runs, traces, and tool calls
    SEMANTIC = "semantic"        # Declarative facts, concepts, and domain knowledge
    PROCEDURAL = "procedural"    # Reusable multi-step recipes, workflows, and solutions
    FAILURE = "failure"          # Pitfalls, dead-end paths, invalid parameters, and constraints
    PREFERENCE = "preference"    # User-specific defaults, preferred apps, formats, and styles


@dataclass
class ExperienceItem:
    """An individual unit of persistent experience memory."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_type: MemoryType = MemoryType.PROCEDURAL
    category: str = "general"               # Domain tag: excel, browser, files, system, etc.
    query_pattern: str = ""                 # Normalized trigger phrase or task intent
    content: Dict[str, Any] = field(default_factory=dict)  # Structured payload
    confidence: float = 1.0                 # Confidence score [0.0 - 1.0]
    success_count: int = 1                  # Successful uses
    failure_count: int = 0                  # Failed attempts
    version: int = 1                        # Knowledge version
    is_active: bool = True                  # Soft active flag (False if superseded/deprecated)
    superseded_by: Optional[str] = None     # Pointer to newer version if updated
    source: str = "execution"               # execution, user_correction, user_preference, inferred
    task_metadata: Dict[str, Any] = field(default_factory=dict) # Environment, task_id, session_id
    embedding: Optional[List[float]] = None # Semantic vector embedding
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes ExperienceItem to JSON-compatible dictionary."""
        return {
            "id": self.id,
            "memory_type": self.memory_type.value if isinstance(self.memory_type, MemoryType) else str(self.memory_type),
            "category": self.category,
            "query_pattern": self.query_pattern,
            "content": dict(self.content),
            "confidence": round(self.confidence, 4),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "version": self.version,
            "is_active": self.is_active,
            "superseded_by": self.superseded_by,
            "source": self.source,
            "task_metadata": dict(self.task_metadata),
            "embedding": list(self.embedding) if self.embedding is not None else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperienceItem":
        """Reconstructs ExperienceItem from dictionary."""
        raw_type = data.get("memory_type", MemoryType.PROCEDURAL.value)
        try:
            m_type = MemoryType(raw_type)
        except ValueError:
            m_type = MemoryType.PROCEDURAL

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            memory_type=m_type,
            category=data.get("category", "general"),
            query_pattern=data.get("query_pattern", ""),
            content=dict(data.get("content", {})),
            confidence=float(data.get("confidence", 1.0)),
            success_count=int(data.get("success_count", 1)),
            failure_count=int(data.get("failure_count", 0)),
            version=int(data.get("version", 1)),
            is_active=bool(data.get("is_active", True)),
            superseded_by=data.get("superseded_by"),
            source=data.get("source", "execution"),
            task_metadata=dict(data.get("task_metadata", {})),
            embedding=data.get("embedding"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class ExperienceContext:
    """Consolidated context retrieved from previous experience to guide reasoning and planning."""
    query: str = ""
    procedures: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    episodes: List[Dict[str, Any]] = field(default_factory=list)

    def has_relevant_experience(self) -> bool:
        """Returns True if any actionable procedural, failure, or preference insight is present."""
        return bool(self.procedures or self.failures or self.preferences)

    def format_for_planner(self) -> str:
        """Formats the experience context into a concise prompt for the agent reasoner."""
        lines = []
        if self.preferences:
            pref_strs = [f"- {k}: {v}" for k, v in self.preferences.items()]
            lines.append("User Preferences:\n" + "\n".join(pref_strs))

        if self.procedures:
            lines.append("Proven Historical Procedures:")
            for p in self.procedures[:3]:
                goal = p.get("goal") or p.get("query_pattern", "")
                steps = p.get("steps", [])
                steps_desc = ", ".join([s.get("description", f"{s.get('plugin')}.{s.get('action')}") for s in steps])
                lines.append(f"- For '{goal}': [{steps_desc}] (Confidence: {p.get('confidence', 1.0)})")

        if self.failures:
            lines.append("Known Pitfalls & Anti-Patterns to Avoid:")
            for f in self.failures[:3]:
                action = f.get("failed_action", "Action")
                reason = f.get("root_cause") or f.get("error", "Error")
                avoid = f.get("avoidance_strategy")
                avoid_str = f" -> Instead: {avoid}" if avoid else ""
                lines.append(f"- Avoid failing pattern on '{action}': {reason}{avoid_str}")

        return "\n\n".join(lines)
