# core/knowledge/it/classifier.py
"""
IT Question Classifier & Hinglish NLP Resolver.
Analyzes user utterances to identify:
1. Question Type (Definition, How-to, Troubleshooting, Command Explanation, Configuration, etc.)
2. Primary IT Domain (Desktop, Server 2019, Azure, Networking, Enterprise)
3. Target Technical Entity or Command
4. Safety / Execution Gating (Distinguishes knowledge inquiries from execution commands).
"""

from typing import Dict, List, Optional, Tuple
import re

from .models import ITDomain, ITQuestionType


class ITQuestionClassifier:
    """Classifies user technical utterances into structured question intents and domains."""

    ACTION_VERBS = [
        "chalao", "run", "execute", "kholo", "open", "launch", "start", "band karo",
        "close", "terminate", "kill", "delete", "hatao", "format", "restart", "shutdown"
    ]

    TROUBLESHOOTING_TRIGGERS = [
        "troubleshoot", "nahi chal raha", "nahi ho raha", "fail", "failure", "error",
        "connect nahi ho raha", "login nahi kar pa raha", "login nahi ho raha", "disk full",
        "resolve nahi kar raha", "ip nahi de raha", "open nahi ho rahi", "down hai", "crash",
        "kaam nahi kar raha", "issue", "problem", "why is", "kyun nahi", "kyu nahi"
    ]

    HOW_TO_TRIGGERS = [
        "kaise", "how to", "how do i", "how can i", "karna hai", "karein", "karen",
        "tarika", "steps to", "create", "banate hain", "banayein"
    ]

    COMMAND_EXPLANATION_TRIGGERS = [
        "kya karta hai", "kya karti hai", "what does", "what is command", "command kya hai",
        "use of", "syntax of", "explain command", "command explain"
    ]

    DEFINITION_TRIGGERS = [
        "kya hai", "kya hota hai", "kya hoti hai", "what is", "what are", "meaning of",
        "define", "definition", "full form"
    ]

    CONFIGURATION_TRIGGERS = [
        "configure", "configuration", "setup", "install", "set up", "kaise configure", "kaise setup"
    ]

    COMPARISON_TRIGGERS = [
        "vs", "versus", "difference between", "kya antar hai", "me antar", "compare", "comparison"
    ]

    BEST_PRACTICE_TRIGGERS = [
        "best practice", "best practices", "recommendation", "guidelines", "sahi tarika"
    ]

    CURRENT_INFO_TRIGGERS = [
        "latest", "current", "taza", "naya", "aaj ka", "recent", "new feature"
    ]

    DOMAIN_KEYWORDS = {
        ITDomain.WINDOWS_DESKTOP: [
            "windows 10", "windows 11", "desktop", "laptop", "task manager", "device manager",
            "event viewer", "registry", "regedit", "bitlocker", "windows firewall", "local user",
            "mapped drive", "rdp", "mstsc"
        ],
        ITDomain.WINDOWS_SERVER_2019: [
            "server 2019", "windows server", "active directory", "ad ds", "domain controller",
            "gpo", "group policy", "ou", "dns server", "dhcp server", "iis", "hyper-v",
            "failover cluster", "kerberos", "ntlm", "smb", "file server"
        ],
        ITDomain.AZURE: [
            "azure", "azure vm", "vnet", "nsg", "resource group", "subscription", "blob",
            "storage account", "entra id", "azure ad", "rbac", "key vault", "log analytics",
            "azure monitor", "app service"
        ],
        ITDomain.NETWORKING: [
            "tcp/ip", "ipv4", "ipv6", "subnet", "subnetting", "cidr", "routing", "switching",
            "vlan", "vpn", "gateway", "port 80", "port 443", "port 3389", "ping", "tracert"
        ],
        ITDomain.ENTERPRISE_INFRA: [
            "san", "nas", "storage", "backup", "3-2-1", "disaster recovery", "rto", "rpo",
            "patch management", "wsus", "sccm", "intune", "endpoint"
        ]
    }

    def classify_utterance(self, query: str) -> Tuple[ITQuestionType, ITDomain, float]:
        """
        Classifies an utterance into (QuestionType, Domain, Confidence).
        Returns confidence score from 0.0 to 1.0.
        """
        lowered = query.strip().lower()

        # 1. Check for Action Execution Request
        # If user says "Run ipconfig" or "ipconfig chalao" or "system lock karo"
        if any(lowered.startswith(f"{v} ") for v in ["run", "execute", "start", "open", "launch"]) and not any(q in lowered for q in ["what", "how", "why", "kya"]):
            return ITQuestionType.ACTION_REQUEST, ITDomain.GENERAL_IT, 0.95

        if any(lowered.endswith(f" {v}") for v in ["chalao", "karo", "khol do", "run karo"]):
            if not any(q in lowered for q in ["kaise", "kyun", "kya", "explain"]):
                return ITQuestionType.ACTION_REQUEST, ITDomain.GENERAL_IT, 0.95

        # 2. Check for Troubleshooting Queries
        if any(t in lowered for t in self.TROUBLESHOOTING_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.TROUBLESHOOTING, domain, 0.90

        # 3. Check for Command Explanation ("What does ipconfig do?", "ipconfig kya karta hai?")
        if any(t in lowered for t in self.COMMAND_EXPLANATION_TRIGGERS) or (
            any(w in lowered for w in ["ipconfig", "ping", "tracert", "nslookup", "netstat", "sfc", "dism", "gpupdate", "whoami"])
            and any(w in lowered for w in ["kya", "what", "explain", "use", "syntax"])
        ):
            domain = self._detect_domain(lowered)
            return ITQuestionType.COMMAND_EXPLANATION, domain, 0.92

        # 4. Check for Current / Live Information
        if any(t in lowered for t in self.CURRENT_INFO_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.CURRENT_INFO, domain, 0.85

        # 5. Check for Comparison ("NTFS vs Share permissions")
        if any(t in lowered for t in self.COMPARISON_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.COMPARISON, domain, 0.88

        # 6. Check for Best Practices
        if any(t in lowered for t in self.BEST_PRACTICE_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.BEST_PRACTICE, domain, 0.88

        # 7. Check for Configuration / Setup ("Server 2019 mein DNS kaise configure karein?")
        if any(t in lowered for t in self.CONFIGURATION_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.CONFIGURATION, domain, 0.90

        # 8. Check for How-To / Procedural ("How do I create a user?")
        if any(t in lowered for t in self.HOW_TO_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.HOW_TO, domain, 0.85

        # 9. Check for Architecture / Deep Dive
        if any(w in lowered for w in ["architecture", "working", "internal", "structure", "kaise kaam karta"]):
            domain = self._detect_domain(lowered)
            return ITQuestionType.ARCHITECTURE, domain, 0.85

        # 10. Check for Definition / Explanations ("What is Active Directory?", "DNS kya hai?")
        if any(t in lowered for t in self.DEFINITION_TRIGGERS):
            domain = self._detect_domain(lowered)
            return ITQuestionType.DEFINITION, domain, 0.90

        # Default fallback
        domain = self._detect_domain(lowered)
        return ITQuestionType.DEFINITION, domain, 0.60

    def _detect_domain(self, lowered: str) -> ITDomain:
        """Determines the most probable IT Domain based on domain-specific keyword weights."""
        domain_scores: Dict[ITDomain, int] = {d: 0 for d in self.DOMAIN_KEYWORDS}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
                    domain_scores[domain] += 2

        # Strong Server 2019 cues
        if "2019" in lowered or "server" in lowered or "domain controller" in lowered or "ad ds" in lowered:
            domain_scores[ITDomain.WINDOWS_SERVER_2019] += 3

        # Strong Azure cues
        if "azure" in lowered or "cloud" in lowered or "vnet" in lowered or "entra" in lowered:
            domain_scores[ITDomain.AZURE] += 3

        # Strong Desktop cues
        if "desktop" in lowered or "windows 10" in lowered or "windows 11" in lowered:
            domain_scores[ITDomain.WINDOWS_DESKTOP] += 3

        best_domain = max(domain_scores, key=lambda k: domain_scores[k])
        if domain_scores[best_domain] > 0:
            return best_domain

        return ITDomain.GENERAL_IT
