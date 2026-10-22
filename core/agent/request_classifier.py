# core/agent/request_classifier.py
"""
Agent Request Classifier determining Fast Path vs Agent Path execution routing.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, Optional


class RequestType(str, Enum):
    """Classification of the incoming user request."""
    DIRECT_COMMAND = "DIRECT_COMMAND"            # Fast Path: Single deterministic action
    INFORMATION_REQUEST = "INFORMATION_REQUEST"  # Fast Path: Static/dynamic query without action
    CONVERSATIONAL = "CONVERSATIONAL"            # Fast Path: Small talk, greetings, chit-chat
    MULTI_STEP_TASK = "MULTI_STEP_TASK"          # Agent Path: Explicit compound/sequential actions
    GOAL_ORIENTED_TASK = "GOAL_ORIENTED_TASK"    # Agent Path: High-level outcome requiring planning
    AMBIGUOUS_TASK = "AMBIGUOUS_TASK"            # Agent Path: Underspecified goal requiring context/clarification


@dataclass
class ClassificationResult:
    """Outcome of request classification."""
    request_type: RequestType
    is_agent_path: bool
    confidence: float
    reason: str
    detected_entities: Dict[str, Any]


# Backward-compatible alias
RequestClassification = ClassificationResult


class RequestClassifier:
    """
    Evaluates user requests to route deterministic commands directly through the
    low-latency Fast Path, while dispatching multi-step or goal-oriented requests
    to the Agent Orchestrator.
    """

    # Multi-step conjunction connectors
    RE_SEQUENTIAL_CONNECTORS = re.compile(
        r"\b(?:then|and\s+then|after\s+that|aur\s+phir|aur\s+fir|fir|phir|pehle\s+.*?fir|baad\s+me)\b|"
        r"\b(?:aur|and)\s+(?:usme|isme|wahan|there|then)\b|"
        r",\s*(?:then|and\s+then|aur|phir|fir)\s+",
        re.IGNORECASE
    )

    # Goal-oriented verbs & high-level outcomes
    RE_GOAL_ORIENTED = re.compile(
        r"\b(?:organize|organise|summarize|summarise|analyze|analyse|audit|research|collect|gather)\b|"
        r"\b(?:list\s+banao|summary\s+bana(?:o|do)|report\s+banao|data\s+collect\s+karke)\b|"
        r"\b(?:project\s+ko\s+organize|files?\s+ko\s+organize|clean\s+up\s+project)\b|"
        r"\b(?:presentation\s+ke\s+liye|meeting\s+ke\s+liye)\b|"
        r"\b(?:find\s+all|extract\s+all|calculate\s+total\s+of|average\s+of)\b",
        re.IGNORECASE
    )

    # Ambiguous commands needing resolution
    RE_AMBIGUOUS_DEMONSTRATIVE = re.compile(
        r"^(?:isko|ise|yeh|yah|is|usko|use|this|it)\s+(?:thik\s+karo|dekhna|check\s+karo|kuch\s+karo|handle\s+karo|fix\s+karo|sahi\s+karo)$|"
        r"^(?:thik\s+karo|fix\s+it|fix\s+this(?:\s+issue)?|do\s+something|kuch\s+karo)$",
        re.IGNORECASE
    )

    # Direct information inquiries
    RE_INFORMATION_INQUIRY = re.compile(
        r"\b(?:kitni|kitna|kaun\s+sa|konsa|what\s+is|what\s+are|how\s+much|tell\s+me\s+about|version|ram|cpu|battery|specs|kya\s+hai)\b",
        re.IGNORECASE
    )

    # Conversational smalltalk
    RE_CONVERSATIONAL = re.compile(
        r"^(?:hi|hello|hey|namaste|kaise\s+ho|kya\s+haal|good\s+(?:morning|afternoon|evening)|bhai|jarvis)\b|"
        r"^(?:who\s+are\s+you|tum\s+kaun\s+ho|tumhara\s+naam\s+kya\s+hai)$",
        re.IGNORECASE
    )

    # Explicit single action indicators (Fast Path direct command candidates)
    RE_DIRECT_ACTIONS = re.compile(
        r"\b(?:kholo|open|launch|start|chalao|band\s+karo|close|exit|quit|"
        r"minimise|minimize|maximise|maximize|restore|focus|"
        r"volume|mute|unmute|play|pause|stop|type|write|likho)\b",
        re.IGNORECASE
    )

    @classmethod
    def classify(cls, text: str, context: Optional[Any] = None) -> ClassificationResult:
        """Classifies the request and decides if Agent Path is warranted."""
        raw = text.strip()
        lowered = re.sub(r"[.!?,]+$", "", raw.lower()).strip()

        # 1. Check Ambiguous Task (Agent Path for context resolution or clarification)
        if cls.RE_AMBIGUOUS_DEMONSTRATIVE.match(lowered):
            return ClassificationResult(
                request_type=RequestType.AMBIGUOUS_TASK,
                is_agent_path=True,
                confidence=0.92,
                reason="Underspecified deictic instruction requires context resolution",
                detected_entities={"query": raw}
            )

        # 2. Check Goal-Oriented Task (Agent Path)
        if cls.RE_GOAL_ORIENTED.search(lowered):
            return ClassificationResult(
                request_type=RequestType.GOAL_ORIENTED_TASK,
                is_agent_path=True,
                confidence=0.95,
                reason="High-level autonomous objective requiring task decomposition",
                detected_entities={"query": raw}
            )

        # 3. Check Multi-Step Sequential Task (Agent Path)
        # Note: Must distinguish compound multi-action from simple single conjunction
        has_sequential = bool(cls.RE_SEQUENTIAL_CONNECTORS.search(lowered))
        has_multiple_verbs = len(cls.RE_DIRECT_ACTIONS.findall(lowered)) >= 2
        has_aur_conjunction = (" aur " in lowered or " and " in lowered) and has_multiple_verbs

        if has_sequential or has_multiple_verbs or has_aur_conjunction:
            return ClassificationResult(
                request_type=RequestType.MULTI_STEP_TASK,
                is_agent_path=True,
                confidence=0.94,
                reason="Compound multi-step instruction requiring sequential plan execution",
                detected_entities={"query": raw}
            )

        # 4. Check Conversational (Fast Path)
        if cls.RE_CONVERSATIONAL.match(lowered) and not cls.RE_DIRECT_ACTIONS.search(lowered):
            return ClassificationResult(
                request_type=RequestType.CONVERSATIONAL,
                is_agent_path=False,
                confidence=0.90,
                reason="Conversational dialogue routed to fast conversational policy",
                detected_entities={"query": raw}
            )

        # 5. Check Information Inquiries (Fast Path)
        if cls.RE_INFORMATION_INQUIRY.search(lowered) and not cls.RE_DIRECT_ACTIONS.search(lowered):
            return ClassificationResult(
                request_type=RequestType.INFORMATION_REQUEST,
                is_agent_path=False,
                confidence=0.88,
                reason="Information query routed to knowledge/system inspection",
                detected_entities={"query": raw}
            )

        # 6. Default to Direct Command (Fast Path for maximum responsiveness)
        return ClassificationResult(
            request_type=RequestType.DIRECT_COMMAND,
            is_agent_path=False,
            confidence=0.90,
            reason="Deterministic single command routed directly to Fast Path",
            detected_entities={"query": raw}
        )
