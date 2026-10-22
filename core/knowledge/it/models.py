# core/knowledge/it/models.py
"""
Data Models and Enums for the IT / Infrastructure Knowledge Engine.
Defines domains, question classifications, structured concept entities,
command specifications, troubleshooting recipes, and query results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ITDomain(str, Enum):
    WINDOWS_DESKTOP = "WINDOWS_DESKTOP"
    WINDOWS_SERVER_2019 = "WINDOWS_SERVER_2019"
    AZURE = "AZURE"
    NETWORKING = "NETWORKING"
    ENTERPRISE_INFRA = "ENTERPRISE_INFRA"
    GENERAL_IT = "GENERAL_IT"


class ITQuestionType(str, Enum):
    DEFINITION = "DEFINITION"                  # "What is Active Directory?"
    HOW_TO = "HOW_TO"                          # "How do I create a user in Server 2019?"
    TROUBLESHOOTING = "TROUBLESHOOTING"        # "RDP connect nahi ho raha, kya check karu?"
    COMMAND_EXPLANATION = "COMMAND_EXPLANATION"# "What does ipconfig do?"
    CONFIGURATION = "CONFIGURATION"            # "DNS kaise configure karte hain?"
    ARCHITECTURE = "ARCHITECTURE"              # "Azure VNet architecture kya hai?"
    COMPARISON = "COMPARISON"                  # "NTFS vs Share permissions"
    BEST_PRACTICE = "BEST_PRACTICE"            # "Backup best practices"
    CURRENT_INFO = "CURRENT_INFO"              # "Latest Azure features / latest patch"
    ACTION_REQUEST = "ACTION_REQUEST"          # "Run ipconfig" (strictly routed to execution, not knowledge)


class CommandRiskLevel(str, Enum):
    SAFE_READ_ONLY = "SAFE_READ_ONLY"          # ipconfig, ping, Get-Service, hostname
    MEDIUM_STATE_CHANGE = "MEDIUM_STATE_CHANGE"# gpupdate, restart-service
    HIGH_DESTRUCTIVE = "HIGH_DESTRUCTIVE"      # format, diskpart, taskkill /f, Stop-Computer, Remove-ADUser


@dataclass
class ITCommand:
    """Safe command knowledge specification."""
    command: str
    tool: str                                  # "PowerShell", "CMD", "Azure CLI", "Bash"
    platform: str                              # "Windows Desktop", "Windows Server 2019", "Azure", "Network"
    purpose_en: str
    purpose_hi: str
    syntax: str
    common_options: Dict[str, str] = field(default_factory=dict)
    safe_examples: List[str] = field(default_factory=list)
    risk_level: CommandRiskLevel = CommandRiskLevel.SAFE_READ_ONLY
    related_concepts: List[str] = field(default_factory=list)


@dataclass
class ITTroubleshootingGuide:
    """
    Structured 6-phase IT Troubleshooting Recipe:
    1. Problem Identification
    2. Likely Causes
    3. Safe Checks
    4. Diagnostic Commands / Tools
    5. Possible Fixes
    6. Verification Steps
    """
    issue_id: str
    title_en: str
    title_hi: str
    domain: ITDomain
    keywords: List[str] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)
    likely_causes: List[str] = field(default_factory=list)
    safe_checks: List[str] = field(default_factory=list)
    commands_tools: List[str] = field(default_factory=list)
    possible_fixes: List[str] = field(default_factory=list)
    verification_steps: List[str] = field(default_factory=list)
    docs_source: str = "Microsoft Learn / Windows Server Documentation"


@dataclass
class ITConcept:
    """Reusable technical concept and entity model."""
    concept_id: str
    canonical_name: str
    domain: ITDomain
    category: str
    aliases: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    definition_en: str = ""
    definition_hi: str = ""
    architecture_overview: str = ""
    components: List[str] = field(default_factory=list)
    how_to_steps: List[str] = field(default_factory=list)
    best_practices: List[str] = field(default_factory=list)
    related_commands: List[str] = field(default_factory=list)
    related_concepts: List[str] = field(default_factory=list)
    troubleshooting_relevance: str = ""
    docs_source: str = "Microsoft Learn"
    last_verified: str = "2026"
    is_version_sensitive: bool = False


@dataclass
class ITQueryResult:
    """Structured response payload from the IT Knowledge Engine."""
    found: bool
    confidence: float                          # 0.0 to 1.0
    question_type: ITQuestionType
    domain: ITDomain
    concept_id: Optional[str] = None
    command_name: Optional[str] = None
    troubleshooting_id: Optional[str] = None
    answer_text: str = ""
    detailed_steps: List[str] = field(default_factory=list)
    diagnostic_commands: List[str] = field(default_factory=list)
    source: str = "Microsoft Technical Documentation"
    is_time_sensitive: bool = False
    clarification_needed: bool = False
