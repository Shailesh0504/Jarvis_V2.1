# plugins/math/models.py
"""
Mathematical Data Models and Operation Types for Jarvis V2 Math Plugin.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class MathOperationType(str, Enum):
    ARITHMETIC = "arithmetic"
    PERCENTAGE = "percentage"
    EQUATION = "equation"
    POWER_ROOT = "power_root"
    STATISTICS = "statistics"
    FINANCE = "finance"
    GEOMETRY = "geometry"
    TRIGONOMETRY = "trigonometry"
    CALCULUS = "calculus"


@dataclass
class MathResult:
    """Structured deterministic result of a mathematical computation."""
    success: bool
    operation: MathOperationType
    expression: str
    result_value: Any
    formatted_answer: str
    steps: List[str] = field(default_factory=list)
    units: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation.value,
            "expression": self.expression,
            "result_value": self.result_value,
            "formatted_answer": self.formatted_answer,
            "steps": self.steps,
            "units": self.units,
            "error": self.error
        }
