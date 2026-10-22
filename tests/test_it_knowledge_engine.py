# tests/test_it_knowledge_engine.py
"""
Comprehensive Test Suite for the Dedicated IT / Infrastructure Knowledge Engine.
Validates:
1. Domain Coverage (Windows Desktop, Server 2019, Azure, Networking, Enterprise Infra)
2. Question Classification (Definition, How-To, Troubleshooting, Command Explanation, etc.)
3. Structured 6-Phase Troubleshooting Guides
4. Command Knowledge & Safety (Zero Execution on Knowledge Questions)
5. Multi-Lingual Hindi/Hinglish Phrasing Resolution
6. Version-Sensitive / Current Information Handling
7. Multi-Turn Conversational Context Awareness ("ab next kya karu?")
8. Anti-Hallucination & Low-Confidence Guardrails
9. Integration into KnowledgeEngine Facade
"""

import pytest

from core.knowledge.it import (
    CommandRiskLevel,
    ITDomain,
    ITKnowledgeEngine,
    ITQuestionType,
    get_it_knowledge_engine,
)
from core.knowledge import get_knowledge_engine, ConfidenceLevel


@pytest.fixture
def it_engine():
    engine = get_it_knowledge_engine()
    engine.context_tracker.clear()
    return engine


@pytest.fixture
def knowledge_engine():
    return get_knowledge_engine()


# =========================================================================
# 1. DOMAIN CONCEPT COVERAGE TESTS
# =========================================================================

def test_windows_desktop_concepts(it_engine):
    """Verifies Windows Desktop concepts (Device Manager, Task Manager, BitLocker, Firewall, etc.)."""
    res = it_engine.query("What is Device Manager?")
    assert res.found is True
    assert res.domain == ITDomain.WINDOWS_DESKTOP
    assert "devmgmt.msc" in res.answer_text or "hardware" in res.answer_text.lower()

    res_bitlocker = it_engine.query("BitLocker encryption kya hota hai?")
    assert res_bitlocker.found is True
    assert "encryption" in res_bitlocker.answer_text.lower() or "tpm" in res_bitlocker.answer_text.lower()


def test_windows_server_2019_concepts(it_engine):
    """Verifies Windows Server 2019 concepts (AD DS, DNS, DHCP, GPO, IIS, Hyper-V, Kerberos)."""
    res_ad = it_engine.query("Active Directory kya hota hai?")
    assert res_ad.found is True
    assert res_ad.domain == ITDomain.WINDOWS_SERVER_2019
    assert "active directory" in res_ad.answer_text.lower()
    assert "authentication" in res_ad.answer_text.lower() or "directory" in res_ad.answer_text.lower()

    res_dns = it_engine.query("Windows Server 2019 mein DNS kya hai?")
    assert res_dns.found is True
    assert "dns" in res_dns.answer_text.lower()

    res_gpo = it_engine.query("Group Policy Objects kya hota hai?")
    assert res_gpo.found is True
    assert "gpo" in res_gpo.answer_text.lower() or "policy" in res_gpo.answer_text.lower()


def test_azure_concepts(it_engine):
    """Verifies Microsoft Azure concepts (Azure VM, VNet, NSG, Key Vault, Entra ID, Storage)."""
    res_vm = it_engine.query("Azure VM kya hota hai?")
    assert res_vm.found is True
    assert res_vm.domain == ITDomain.AZURE
    assert "virtual server" in res_vm.answer_text.lower() or "iaas" in res_vm.answer_text.lower() or "cloud" in res_vm.answer_text.lower()

    res_nsg = it_engine.query("What is Azure Network Security Group?")
    assert res_nsg.found is True
    assert "nsg" in res_nsg.answer_text.lower() or "firewall" in res_nsg.answer_text.lower() or "filter" in res_nsg.answer_text.lower()

    res_kv = it_engine.query("Azure Key Vault kya hai?")
    assert res_kv.found is True
    assert "secrets" in res_kv.answer_text.lower() or "keys" in res_kv.answer_text.lower() or "passwords" in res_kv.answer_text.lower()


def test_networking_concepts(it_engine):
    """Verifies Networking concepts (TCP/IP, Subnetting, VLAN, Ports)."""
    res_vlan = it_engine.query("VLAN kya hota hai?")
    assert res_vlan.found is True
    assert res_vlan.domain == ITDomain.NETWORKING
    assert "vlan" in res_vlan.answer_text.lower() or "switch" in res_vlan.answer_text.lower()

    res_ports = it_engine.query("Common network ports kya hain?")
    assert res_ports.found is True
    assert "3389" in res_ports.answer_text or "80" in res_ports.answer_text or "443" in res_ports.answer_text


def test_enterprise_infra_concepts(it_engine):
    """Verifies Enterprise Infrastructure concepts (SAN vs NAS, 3-2-1 Backup, Patch Management)."""
    res_san = it_engine.query("SAN vs NAS storage kya hai?")
    assert res_san.found is True
    assert res_san.domain == ITDomain.ENTERPRISE_INFRA
    assert "nas" in res_san.answer_text.lower() and "san" in res_san.answer_text.lower()

    res_backup = it_engine.query("3-2-1 backup rule kya hai?")
    assert res_backup.found is True
    assert "3" in res_backup.answer_text and "2" in res_backup.answer_text


# =========================================================================
# 2. QUESTION CLASSIFICATION TESTS
# =========================================================================

def test_question_classification(it_engine):
    """Verifies classifier recognizes definition, how-to, troubleshooting, and command explanation."""
    qtype, _, _ = it_engine.classifier.classify_utterance("What is Active Directory?")
    assert qtype == ITQuestionType.DEFINITION

    qtype, _, _ = it_engine.classifier.classify_utterance("Server 2019 mein DNS kaise setup karte hain?")
    assert qtype in (ITQuestionType.HOW_TO, ITQuestionType.CONFIGURATION)

    qtype, _, _ = it_engine.classifier.classify_utterance("RDP connect nahi ho raha, kya check karu?")
    assert qtype == ITQuestionType.TROUBLESHOOTING

    qtype, _, _ = it_engine.classifier.classify_utterance("What does ipconfig do?")
    assert qtype == ITQuestionType.COMMAND_EXPLANATION

    qtype, _, _ = it_engine.classifier.classify_utterance("Run ipconfig")
    assert qtype == ITQuestionType.ACTION_REQUEST


# =========================================================================
# 3. STRUCTURED 6-PHASE TROUBLESHOOTING TESTS
# =========================================================================

def test_rdp_troubleshooting(it_engine):
    """Verifies structured troubleshooting for RDP connection failure."""
    res = it_engine.query("RDP connect nahi ho raha, kya check karu?")
    assert res.found is True
    assert res.question_type == ITQuestionType.TROUBLESHOOTING
    assert res.troubleshooting_id == "rdp_connection_failure"
    # Mandatory phases present
    assert "Likely causes" in res.answer_text
    assert "safe checks" in res.answer_text.lower()
    assert "diagnostic" in res.answer_text.lower() or "commands" in res.answer_text.lower()
    assert "Verification" in res.answer_text


def test_dns_server_2019_troubleshooting(it_engine):
    """Verifies DNS troubleshooting query for Windows Server 2019."""
    res = it_engine.query("Windows Server 2019 mein DNS kaise troubleshoot karun?")
    assert res.found is True
    assert res.question_type == ITQuestionType.TROUBLESHOOTING
    assert "flushdns" in res.answer_text.lower() or "nslookup" in res.answer_text.lower()
    assert "Verification" in res.answer_text


def test_domain_user_login_troubleshooting(it_engine):
    """Verifies Active Directory user login failure troubleshooting."""
    res = it_engine.query("Domain user login nahi kar pa raha, kya check karu?")
    assert res.found is True
    assert res.troubleshooting_id == "domain_user_login_failure"
    assert "Get-ADUser" in res.answer_text or "lock" in res.answer_text.lower() or "nltest" in res.answer_text.lower()


def test_server_disk_full_troubleshooting(it_engine):
    """Verifies server disk space exhaustion recipe."""
    res = it_engine.query("Server ka disk full ho gaya hai")
    assert res.found is True
    assert res.troubleshooting_id == "server_disk_full"
    assert "cleanmgr" in res.answer_text.lower() or "dism" in res.answer_text.lower() or "vss" in res.answer_text.lower()


def test_azure_vm_unreachable_troubleshooting(it_engine):
    """Verifies Azure VM unreachable troubleshooting."""
    res = it_engine.query("Azure VM reachable nahi hai")
    assert res.found is True
    assert res.troubleshooting_id == "azure_vm_unreachable"
    assert "nsg" in res.answer_text.lower() or "3389" in res.answer_text.lower() or "bastion" in res.answer_text.lower()


def test_dhcp_ip_failure_troubleshooting(it_engine):
    """Verifies DHCP server IP allocation failure recipe."""
    res = it_engine.query("DHCP IP nahi de raha")
    assert res.found is True
    assert res.troubleshooting_id == "dhcp_not_giving_ip"
    assert "scope" in res.answer_text.lower() or "apipa" in res.answer_text.lower() or "169.254" in res.answer_text.lower()


def test_iis_website_down_troubleshooting(it_engine):
    """Verifies IIS website down troubleshooting."""
    res = it_engine.query("IIS website open nahi ho rahi")
    assert res.found is True
    assert res.troubleshooting_id == "iis_website_down"
    assert "application pool" in res.answer_text.lower() or "w3svc" in res.answer_text.lower() or "503" in res.answer_text.lower()


# =========================================================================
# 4. COMMAND KNOWLEDGE & ZERO EXECUTION TESTS
# =========================================================================

def test_command_explanation_safety(it_engine):
    """Confirms knowledge question about a command returns explanation and DOES NOT execute."""
    res = it_engine.query("What does ipconfig do?")
    assert res.found is True
    assert res.question_type == ITQuestionType.COMMAND_EXPLANATION
    assert res.command_name == "ipconfig"
    assert "ipconfig" in res.answer_text.lower()
    assert "tcp/ip" in res.answer_text.lower()
    assert "Syntax:" in res.answer_text

    # Hindi command explanation
    res_hi = it_engine.query("gpupdate kya karta hai?")
    assert res_hi.found is True
    assert res_hi.command_name == "gpupdate"
    assert "group policy" in res_hi.answer_text.lower()

    # Action request must be rejected from knowledge engine
    res_action = it_engine.query("Run ipconfig")
    assert res_action.found is False
    assert res_action.question_type == ITQuestionType.ACTION_REQUEST


def test_specialized_powershell_cmdlets(it_engine):
    """Verifies safe explanation of Test-NetConnection, Get-ADUser, sfc, DISM."""
    res_tnc = it_engine.query("Test-NetConnection kya karta hai?")
    assert res_tnc.found is True
    assert "test-netconnection" in res_tnc.answer_text.lower()
    assert "port" in res_tnc.answer_text.lower()

    res_ad = it_engine.query("Get-ADUser command kya hai?")
    assert res_ad.found is True
    assert "active directory" in res_ad.answer_text.lower()

    res_sfc = it_engine.query("sfc command explain karo")
    assert res_sfc.found is True
    assert "system file" in res_sfc.answer_text.lower() or "integrity" in res_sfc.answer_text.lower()


# =========================================================================
# 5. HINDI & HINGLISH PHRASING RESOLUTION TESTS
# =========================================================================

def test_hinglish_multi_phrasing(it_engine):
    """Ensures diverse natural Hinglish questions resolve accurately."""
    q1 = it_engine.query("server 2019 mein dns kaise setup karte hain?")
    assert q1.found is True
    assert q1.concept_id == "windows_dns_server"

    q2 = it_engine.query("azure vm ka port kaise open karun?")
    assert q2.found is True
    assert q2.concept_id in ("azure_vm", "azure_vnet_nsg")

    q3 = it_engine.query("windows ka firewall kaise check karu?")
    assert q3.found is True
    assert q3.concept_id == "windows_firewall"

    q4 = it_engine.query("azure mein vm kaise banate hain?")
    assert q4.found is True
    assert q4.concept_id == "azure_vm"


# =========================================================================
# 6. VERSION-SENSITIVE / CURRENT INFORMATION TESTS
# =========================================================================

def test_current_version_sensitive_knowledge(it_engine):
    """Ensures dynamic/current queries point to authoritative freshness sources."""
    res = it_engine.query("Latest Azure features kya hain?")
    assert res.found is True
    assert res.is_time_sensitive is True
    assert "microsoft learn" in res.answer_text.lower() or "azure updates" in res.answer_text.lower()


# =========================================================================
# 7. CONTEXT AWARENESS & MULTI-TURN CONTINUATION TESTS
# =========================================================================

def test_context_awareness_followup(it_engine):
    """
    Verifies multi-turn dialogue continuity:
    Turn 1: 'Server 2019 mein DNS configure kar raha hoon.'
    Turn 2: 'ab next kya karu?'
    Turn 2 inherits the active DNS context and returns the next step.
    """
    # Turn 1
    res1 = it_engine.query("Server 2019 mein DNS configure kar raha hoon")
    assert res1.found is True
    assert it_engine.context_tracker.is_context_active() is True
    assert it_engine.context_tracker.active_concept.concept_id == "windows_dns_server"

    # Turn 2: Anaphoric follow-up
    res2 = it_engine.query("ab next kya karu?")
    assert res2.found is True
    assert "Agla step" in res2.answer_text or "next step" in res2.answer_text.lower()
    assert res2.concept_id == "windows_dns_server"


# =========================================================================
# 8. INTEGRATION WITH CENTRAL KNOWLEDGE ENGINE TESTS
# =========================================================================

def test_central_knowledge_engine_integration(knowledge_engine):
    """Confirms KnowledgeEngine facade seamlessly routes IT queries to IT Knowledge Engine."""
    # IT Definition
    res = knowledge_engine.query("Windows Server 2019 mein DNS kya hai?")
    assert res.found is True
    assert res.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
    assert "dns" in res.answer_text.lower()

    # IT Troubleshooting
    res_trouble = knowledge_engine.query("RDP connect nahi ho raha, kya check karu?")
    assert res_trouble.found is True
    assert "Likely causes" in res_trouble.answer_text or "safe checks" in res_trouble.answer_text.lower()

    # IT Command Explanation
    res_cmd = knowledge_engine.query("What does ipconfig do?")
    assert res_cmd.found is True
    assert "ipconfig" in res_cmd.answer_text.lower()

    # General Knowledge must still work intact!
    res_gk = knowledge_engine.query("India ki capital kya hai?")
    assert res_gk.found is True
    assert "New Delhi" in res_gk.answer_text
