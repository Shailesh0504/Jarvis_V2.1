# core/knowledge/it/concept_store.py
"""
Canonical IT Concept & Entity Knowledge Store.
Indexes core enterprise IT concepts across Windows Desktop, Windows Server 2019,
Microsoft Azure, Networking, and Enterprise Infrastructure.
Stores underlying principles, definitions, architecture, how-tos, commands, and best practices.
"""

from typing import Dict, List, Optional
import re

from .models import ITConcept, ITDomain


class ITConceptStore:
    """Repository of structured IT concepts and reusable domain knowledge."""

    def __init__(self):
        self._concepts: Dict[str, ITConcept] = {}
        self._alias_map: Dict[str, str] = {}
        self._domain_index: Dict[ITDomain, List[str]] = {d: [] for d in ITDomain}
        self._initialize_concepts()

    def register_concept(self, concept: ITConcept) -> None:
        key = concept.concept_id.lower()
        self._concepts[key] = concept
        self._alias_map[key] = key
        self._alias_map[concept.canonical_name.lower()] = key

        for alias in concept.aliases:
            self._alias_map[alias.lower()] = key

        if concept.domain in self._domain_index:
            self._domain_index[concept.domain].append(key)

    def get_concept(self, concept_id: str) -> Optional[ITConcept]:
        return self._concepts.get(concept_id.lower())

    def resolve_concept(self, query: str) -> Optional[ITConcept]:
        """Resolves user query to a canonical ITConcept using aliases and keywords."""
        cleaned = query.strip().lower()

        # 1. Exact alias match
        if cleaned in self._alias_map:
            return self._concepts[self._alias_map[cleaned]]

        # Compound technical intent combinations (e.g. azure + vm, azure + nsg)
        if "azure" in cleaned and any(w in cleaned for w in ["vm", "vms", "virtual machine"]):
            return self._concepts.get("azure_vm")
        if "azure" in cleaned and any(w in cleaned for w in ["nsg", "port", "vnet", "security group"]):
            return self._concepts.get("azure_vnet_nsg")

        # 2. Word boundary match across aliases (longest first for maximum specificity)
        sorted_aliases = sorted(self._alias_map.items(), key=lambda x: len(x[0]), reverse=True)
        for alias, cid in sorted_aliases:
            if re.search(r"\b" + re.escape(alias) + r"\b", cleaned):
                # If alias is very generic like 'azure', ensure more specific child concepts are checked
                if alias == "azure" and any(k in cleaned for k in ["vm", "vnet", "nsg", "storage", "key vault", "entra"]):
                    continue
                return self._concepts[cid]

        # 3. Keyword scoring match (using strict word boundaries)
        best_match = None
        best_score = 0
        for concept in self._concepts.values():
            score = 0
            for kw in concept.keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", cleaned):
                    score += 2
            if score > best_score:
                best_score = score
                best_match = concept

        if best_score >= 2:
            return best_match

        return None

    def get_concepts_by_domain(self, domain: ITDomain) -> List[ITConcept]:
        ids = self._domain_index.get(domain, [])
        return [self._concepts[cid] for cid in ids if cid in self._concepts]

    def _initialize_concepts(self) -> None:
        # =========================================================================
        # DOMAIN 1: WINDOWS DESKTOP
        # =========================================================================

        # 1. Windows 10/11 Overview & Settings
        self.register_concept(
            ITConcept(
                concept_id="windows_desktop_os",
                canonical_name="Windows 10 / Windows 11",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Operating System",
                aliases=["windows 10", "windows 11", "windows desktop", "win 10", "win 11"],
                keywords=["windows 10", "windows 11", "client os", "modern standby", "windows settings"],
                definition_en="Windows 10 and 11 are Microsoft's client operating systems designed for personal and enterprise desktop computing, featuring centralized Settings, Windows Defender security, and enterprise domain management.",
                definition_hi="Windows 10 aur 11 Microsoft ke client desktop operating systems hain jo modern UI, robust security features aur enterprise domain joining support karte hain.",
                how_to_steps=[
                    "Open Windows Settings via shortcut Win + I or running 'ms-settings:'.",
                    "Manage user accounts, display, network, and updates from the modern Settings app.",
                    "Access legacy configuration via Control Panel (control.exe)."
                ],
                best_practices=[
                    "Keep Windows Update enabled for timely cumulative security patches.",
                    "Use standard user accounts for daily tasks and restrict administrative privileges via UAC."
                ],
                related_commands=["winver", "ms-settings:", "control"],
                docs_source="Microsoft Learn - Windows client documentation"
            )
        )

        # 2. Device Manager
        self.register_concept(
            ITConcept(
                concept_id="device_manager",
                canonical_name="Device Manager",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Administrative Tool",
                aliases=["device manager", "devmgmt.msc", "hardware manager"],
                keywords=["device manager", "drivers", "hardware", "device", "devmgmt"],
                definition_en="Device Manager is a Windows Management Console snap-in (devmgmt.msc) that displays installed hardware devices and allows administrators to update drivers, view hardware conflicts, and enable or disable devices.",
                definition_hi="Device Manager ek administrative tool hai jisse system mein installed hardware devices, unke drivers, status aur conflicts inspect aur update kiye jate hain.",
                how_to_steps=[
                    "Press Win + X and select 'Device Manager', or press Win + R and type 'devmgmt.msc'.",
                    "Expand the hardware category (e.g. Network adapters, Display adapters).",
                    "Right-click the target device and select 'Update driver', 'Disable device', or 'Properties'."
                ],
                best_practices=[
                    "Check for yellow exclamation marks indicating missing or corrupt drivers.",
                    "Download driver packages directly from the OEM manufacturer website rather than third-party driver software."
                ],
                related_commands=["devmgmt.msc", "pnputil"],
                docs_source="Microsoft Learn - Device Manager"
            )
        )

        # 3. Task Manager
        self.register_concept(
            ITConcept(
                concept_id="task_manager",
                canonical_name="Task Manager",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Monitoring Tool",
                aliases=["task manager", "taskmgr", "taskmgr.exe"],
                keywords=["task manager", "taskmgr", "cpu usage", "memory usage", "kill process", "end task"],
                definition_en="Task Manager provides detailed real-time information about running processes, system performance (CPU, Memory, Disk, GPU), startup applications, user sessions, and Windows services.",
                definition_hi="Task Manager system ke active processes, performance metrics (CPU, RAM, Disk), startup apps aur background services ko monitor aur manage karne ka tool hai.",
                how_to_steps=[
                    "Press Ctrl + Shift + Esc directly to open Task Manager instantly.",
                    "In the Processes tab, sort by CPU or Memory to find resource-heavy applications.",
                    "To terminate an unresponsive application, right-click it and choose 'End task'."
                ],
                best_practices=[
                    "Disable unnecessary startup applications in the Startup tab to improve boot times.",
                    "Check the Details tab for exact Process IDs (PIDs) and handles."
                ],
                related_commands=["taskmgr.exe", "tasklist", "taskkill"],
                docs_source="Microsoft Learn - Task Manager documentation"
            )
        )

        # 4. Event Viewer
        self.register_concept(
            ITConcept(
                concept_id="event_viewer",
                canonical_name="Event Viewer",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Diagnostic Tool",
                aliases=["event viewer", "eventvwr", "eventvwr.msc", "event log"],
                keywords=["event viewer", "eventvwr", "logs", "system log", "application log", "event id"],
                definition_en="Event Viewer (eventvwr.msc) is a management console tool that logs administrative, application, system, and security events generated by Windows and installed programs.",
                definition_hi="Event Viewer Windows ka diagnostic tool hai jismein system, application aur security ke crash, warning aur error logs (Event IDs) store hote hain.",
                how_to_steps=[
                    "Press Win + R, type 'eventvwr.msc', and press Enter.",
                    "Expand 'Windows Logs' on the left pane: Application, Security, Setup, or System.",
                    "Use 'Filter Current Log' to filter by Event level (Critical, Error, Warning) or specific Event ID."
                ],
                best_practices=[
                    "Always look for Red Error and Critical events matching the timestamp of an incident.",
                    "Use PowerShell's Get-WinEvent for rapid remote log queries."
                ],
                related_commands=["eventvwr.msc", "Get-WinEvent", "wevtutil"],
                docs_source="Microsoft Learn - Event Viewer"
            )
        )

        # 5. Windows Registry
        self.register_concept(
            ITConcept(
                concept_id="windows_registry",
                canonical_name="Windows Registry",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="System Configuration",
                aliases=["registry", "regedit", "regedit.exe", "registry editor"],
                keywords=["registry", "regedit", "hklm", "hkcu", "registry key", "reg"],
                definition_en="The Windows Registry is a hierarchical database that stores low-level configuration settings for the operating system, hardware devices, services, and software applications.",
                definition_hi="Windows Registry ek central hierarchical database hai jismein operating system, software aur hardware ki low-level configurations aur keys store hoti hain.",
                how_to_steps=[
                    "Press Win + R, type 'regedit', and press Enter with administrative privileges.",
                    "Navigate through the 5 root hives: HKEY_CLASSES_ROOT, HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE (HKLM), HKEY_USERS, and HKEY_CURRENT_CONFIG.",
                    "Export and back up keys before making any modifications."
                ],
                best_practices=[
                    "Always export the target registry key (.reg file) or create a System Restore point before editing.",
                    "Avoid using third-party registry cleaners as they can cause OS instability."
                ],
                related_commands=["regedit.exe", "reg query", "reg add", "Get-ItemProperty"],
                docs_source="Microsoft Learn - Windows Registry reference"
            )
        )

        # 6. Windows Firewall
        self.register_concept(
            ITConcept(
                concept_id="windows_firewall",
                canonical_name="Windows Defender Firewall",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Security",
                aliases=["firewall", "windows firewall", "wf.msc", "defender firewall"],
                keywords=["firewall", "windows firewall", "wf.msc", "inbound rule", "outbound rule", "open port", "block port"],
                definition_en="Windows Defender Firewall with Advanced Security filters incoming and outgoing network traffic based on configured security rules and network profiles (Domain, Private, Public).",
                definition_hi="Windows Defender Firewall network traffic ko filter karta hai aur rules ke basis par incoming/outgoing ports aur programs ko allow ya block karta hai.",
                how_to_steps=[
                    "Press Win + R, type 'wf.msc' to open Windows Defender Firewall with Advanced Security.",
                    "Click 'Inbound Rules' > 'New Rule' > choose 'Port' > select TCP/UDP and enter port number.",
                    "Choose 'Allow the connection' and select appropriate profiles (Domain, Private, Public)."
                ],
                best_practices=[
                    "Restrict inbound management ports (like RDP 3389) to specific trusted IP subnets.",
                    "Keep Public network profile locked down by default."
                ],
                related_commands=["wf.msc", "netsh advfirewall", "Get-NetFirewallRule", "New-NetFirewallRule"],
                docs_source="Microsoft Learn - Windows Defender Firewall with Advanced Security"
            )
        )

        # 7. BitLocker Drive Encryption
        self.register_concept(
            ITConcept(
                concept_id="bitlocker",
                canonical_name="BitLocker Drive Encryption",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Security & Encryption",
                aliases=["bitlocker", "bitlocker encryption", "manage-bde"],
                keywords=["bitlocker", "tpm", "drive encryption", "recovery key", "manage-bde"],
                definition_en="BitLocker is Windows volume-level encryption feature designed to protect data by providing full disk encryption using AES encryption integrated with TPM (Trusted Platform Module).",
                definition_hi="BitLocker Windows ka full-disk encryption feature hai jo TPM chip aur AES encryption use karke hard drive ke data ko unauthorized physical access se protect karta hai.",
                how_to_steps=[
                    "Open Control Panel > BitLocker Drive Encryption or Settings > Device encryption.",
                    "Click 'Turn on BitLocker' on the target OS or data drive.",
                    "Save the 48-digit recovery key securely to Microsoft Account, Active Directory, or Azure Entra ID."
                ],
                best_practices=[
                    "Store BitLocker recovery keys in Active Directory or Microsoft Entra ID centrally.",
                    "Ensure TPM 2.0 is enabled in system UEFI/BIOS."
                ],
                related_commands=["manage-bde -status", "manage-bde -on", "Get-BitLockerVolume"],
                docs_source="Microsoft Learn - BitLocker overview"
            )
        )

        # 8. NTFS vs Share Permissions
        self.register_concept(
            ITConcept(
                concept_id="permissions_ntfs_share",
                canonical_name="NTFS and Share Permissions",
                domain=ITDomain.WINDOWS_DESKTOP,
                category="Storage & Security",
                aliases=["ntfs permissions", "share permissions", "file sharing", "mapped drives"],
                keywords=["ntfs", "share permissions", "permissions", "smb share", "mapped drive", "icacls", "net use"],
                definition_en="Share permissions control network access to shared folders over SMB, while NTFS permissions control local and network access directly at the filesystem level. The effective permission is always the MOST RESTRICTIVE combination.",
                definition_hi="Share permissions network SMB access control karte hain jabki NTFS permissions filesystem level par security control karte hain. Effective permission dono mein se sabse restrictive wali hoti hai.",
                how_to_steps=[
                    "Standard practice: Set Share Permissions to 'Everyone: Modify' or 'Authenticated Users: Full Control'.",
                    "Enforce granular access control strictly using NTFS Permissions in folder Properties > Security tab.",
                    "Map network drive via CMD: 'net use Z: \\\\server\\share /persistent:yes'."
                ],
                best_practices=[
                    "Never assign NTFS permissions to individual users; assign permissions to Security Groups (AGDLP principle).",
                    "Do not disable NTFS inheritance without a well-documented reason."
                ],
                related_commands=["icacls", "net share", "net use", "Get-Acl"],
                docs_source="Microsoft Learn - Share and NTFS Permissions"
            )
        )

        # =========================================================================
        # DOMAIN 2: WINDOWS SERVER 2019
        # =========================================================================

        # 9. Active Directory Domain Services (AD DS)
        self.register_concept(
            ITConcept(
                concept_id="active_directory",
                canonical_name="Active Directory Domain Services (AD DS)",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Directory & Identity",
                aliases=["active directory", "ad ds", "ad", "domain controller", "dc", "activedirectory"],
                keywords=["active directory", "ad ds", "domain controller", "domain", "forest", "tree", "dsa.msc"],
                definition_en="Active Directory Domain Services (AD DS) is Microsoft's directory service that stores information about network objects (users, computers, groups, printers) and provides centralized authentication, authorization, and policy enforcement across a domain.",
                definition_hi="Active Directory Domain Services (AD DS) Windows Server ka central directory service hai jo users, computers, groups aur security policies ko centralized manage aur authenticate karta hai.",
                architecture_overview="Organized hierarchically into Forests, Domains, Trees, and Organizational Units (OUs), utilizing Kerberos v5 for authentication and LDAP for querying.",
                components=["Domain Controller (DC)", "Kerberos Authentication", "LDAP (Port 389/636)", "DNS Server", "SYSVOL Share", "Global Catalog"],
                how_to_steps=[
                    "Install AD DS role via Server Manager > Add Roles and Features > Active Directory Domain Services.",
                    "Promote the server to a Domain Controller using the post-deployment configuration wizard.",
                    "Manage directory objects using Active Directory Users and Computers (dsa.msc) or Active Directory Administrative Center (dsac.exe)."
                ],
                best_practices=[
                    "Always deploy at least two Domain Controllers per domain for redundancy and high availability.",
                    "Ensure Domain Controllers run dedicated AD-integrated DNS.",
                    "Regularly test and back up System State."
                ],
                related_commands=["dsa.msc", "Get-ADUser", "Get-ADComputer", "dcdiag", "repadmin /syncall"],
                docs_source="Microsoft Learn - Active Directory Domain Services overview"
            )
        )

        # 10. Group Policy (GPO)
        self.register_concept(
            ITConcept(
                concept_id="group_policy",
                canonical_name="Group Policy Objects (GPO)",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Policy & Configuration",
                aliases=["group policy", "gpo", "gpmc", "gpmc.msc"],
                keywords=["group policy", "gpo", "gpmc", "gpupdate", "gpresult", "ou", "security filtering"],
                definition_en="Group Policy provides centralized management and configuration of operating systems, applications, and users' settings in an Active Directory environment through Group Policy Objects (GPOs).",
                definition_hi="Group Policy Active Directory environment mein computers aur users ki settings, security configurations aur software deployment ko centrally enforce karne ka mechanism hai.",
                architecture_overview="Processing order follows LSDOU: Local, Site, Domain, and Organizational Unit. Innermost OU takes highest precedence unless Enforced is configured.",
                how_to_steps=[
                    "Open Group Policy Management Console (gpmc.msc).",
                    "Right-click the target OU and choose 'Create a GPO in this domain, and Link it here...'.",
                    "Right-click the GPO > Edit to configure Computer Configuration or User Configuration policies.",
                    "Apply immediately on clients using 'gpupdate /force'."
                ],
                best_practices=[
                    "Do not modify the 'Default Domain Policy' or 'Default Domain Controllers Policy' directly except for domain account passwords and Kerberos policies.",
                    "Use granular, modular GPOs named descriptively (e.g. 'SEC_Disable_USB_Storage')."
                ],
                related_commands=["gpmc.msc", "gpupdate /force", "gpresult /r", "gpresult /h"],
                docs_source="Microsoft Learn - Group Policy overview"
            )
        )

        # 11. DNS Server (Windows Server 2019)
        self.register_concept(
            ITConcept(
                concept_id="windows_dns_server",
                canonical_name="Windows DNS Server",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Network Services",
                aliases=["dns server", "windows server dns", "dnsmgmt.msc", "ad integrated dns"],
                keywords=["dns", "dns server", "forward lookup zone", "reverse lookup zone", "srv record", "forwarders"],
                definition_en="Windows DNS Server resolves hostnames to IP addresses and is the backbone of Active Directory, responsible for publishing SRV locator records that allow domain computers to locate Domain Controllers, Kerberos, and LDAP services.",
                definition_hi="Windows Server DNS network names ko IP addresses mein resolve karta hai aur Active Directory ke liye crucial hai kyunki ye SRV records ke zariye Domain Controllers locate karwata hai.",
                how_to_steps=[
                    "Open DNS Manager (dnsmgmt.msc).",
                    "Review Forward Lookup Zones (e.g. corp.local) for host A records and _msdcs SRV records.",
                    "Configure DNS Forwarders (e.g. 1.1.1.1 or 8.8.8.8) for external internet name resolution."
                ],
                best_practices=[
                    "Always store domain DNS zones as Active Directory-Integrated zones for multimaster replication and secure dynamic updates.",
                    "Configure reliable public DNS forwarders rather than relying solely on root hints."
                ],
                related_commands=["dnsmgmt.msc", "Get-DnsServerZone", "dnscmd", "Resolve-DnsName", "ipconfig /flushdns"],
                docs_source="Microsoft Learn - DNS Server overview"
            )
        )

        # 12. DHCP Server (Windows Server 2019)
        self.register_concept(
            ITConcept(
                concept_id="windows_dhcp_server",
                canonical_name="Windows DHCP Server",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Network Services",
                aliases=["dhcp server", "windows server dhcp", "dhcpmgmt.msc", "dhcp scope"],
                keywords=["dhcp", "dhcp server", "dhcp scope", "lease", "reservation", "apipa"],
                definition_en="Dynamic Host Configuration Protocol (DHCP) Server automatically assigns IP addresses, subnet masks, default gateways, and DNS server settings to client devices on the network.",
                definition_hi="DHCP Server network par connected devices ko automatically IP address, subnet mask, default gateway aur DNS configurations assign karta hai.",
                how_to_steps=[
                    "Install DHCP role and authorize the server in Active Directory.",
                    "Open DHCP Management console (dhcpmgmt.msc).",
                    "Right-click IPv4 > New Scope > specify IP range, subnet mask, exclusions, and lease duration.",
                    "Configure Scope Options: 003 Router (Default Gateway) and 006 DNS Servers."
                ],
                best_practices=[
                    "Configure DHCP Failover (Load Balance or Hot Standby) across two servers for high availability.",
                    "Use DHCP Reservations for printers and fixed appliances."
                ],
                related_commands=["dhcpmgmt.msc", "Get-DhcpServerv4Scope", "Get-DhcpServerv4Lease"],
                docs_source="Microsoft Learn - Dynamic Host Configuration Protocol (DHCP)"
            )
        )

        # 13. IIS (Internet Information Services)
        self.register_concept(
            ITConcept(
                concept_id="iis_web_server",
                canonical_name="Internet Information Services (IIS)",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Application & Web Hosting",
                aliases=["iis", "iis server", "inetmgr", "w3wp", "web server"],
                keywords=["iis", "inetmgr", "application pool", "w3wp", "http 500", "503 service unavailable", "web.config"],
                definition_en="Internet Information Services (IIS) is Microsoft's flexible, secure web server for Windows Server, hosting ASP.NET, PHP, HTML websites, and enterprise web APIs.",
                definition_hi="IIS (Internet Information Services) Microsoft ka web server hai jo ASP.NET, web applications aur sites ko port 80/443 par host karta hai.",
                how_to_steps=[
                    "Open IIS Manager by running 'inetmgr'.",
                    "Manage Application Pools to isolate worker processes (w3wp.exe) for security and fault tolerance.",
                    "Bind domain SSL/TLS certificates under Site Bindings for HTTPS (port 443)."
                ],
                best_practices=[
                    "Run each enterprise application in its own dedicated Application Pool.",
                    "Redirect all HTTP traffic to HTTPS and disable obsolete TLS protocols (TLS 1.0/1.1)."
                ],
                related_commands=["inetmgr", "iisreset", "Get-IISAppPool", "appcmd.exe"],
                docs_source="Microsoft Learn - IIS overview"
            )
        )

        # 14. Hyper-V
        self.register_concept(
            ITConcept(
                concept_id="hyper_v",
                canonical_name="Hyper-V Virtualization",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Virtualization",
                aliases=["hyper-v", "hyperv", "virtmgmt.msc"],
                keywords=["hyper-v", "hyperv", "type-1 hypervisor", "virtual switch", "vhdx", "vm", "generation 2"],
                definition_en="Hyper-V is Microsoft's Type-1 hardware hypervisor enabling administrators to virtualize operating systems, compute, memory, and virtual switches on Windows Server 2019.",
                definition_hi="Hyper-V Microsoft ka Type-1 hypervisor hai jo Windows Server par multiple virtual machines (VMs) ko independently host aur manage karta hai.",
                how_to_steps=[
                    "Install Hyper-V role via Server Manager and restart server.",
                    "Open Hyper-V Manager (virtmgmt.msc) and create an External Virtual Switch bound to physical NIC.",
                    "Create New Virtual Machine: select Generation 2 (UEFI), assign vCPU/RAM, and attach VHDX disk."
                ],
                best_practices=[
                    "Always choose Generation 2 VMs for modern 64-bit OS with Secure Boot and TPM support.",
                    "Place VHDX disks on dedicated high-speed NVMe/SSD storage or SAN/CSV volumes."
                ],
                related_commands=["virtmgmt.msc", "Get-VM", "Start-VM", "Stop-VM"],
                docs_source="Microsoft Learn - Hyper-V on Windows Server"
            )
        )

        # 15. Storage, Volumes, and RAID
        self.register_concept(
            ITConcept(
                concept_id="storage_raid",
                canonical_name="Storage Pools, Volumes, and RAID Concepts",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Storage",
                aliases=["raid", "storage pools", "storage spaces", "disks", "volumes"],
                keywords=["raid", "raid 0", "raid 1", "raid 5", "raid 10", "storage spaces", "resilient file system", "refs", "ntfs"],
                definition_en="Storage management in Windows Server combines physical disks into Storage Pools or hardware RAID arrays (RAID 0 striping, RAID 1 mirroring, RAID 5 parity, RAID 10 striped mirrors) formatted with NTFS or ReFS.",
                definition_hi="Storage management mein multiple disks ko RAID (RAID 0, 1, 5, 10) ya Storage Spaces pools mein combine kiya jata hai taaki redundancy, fault tolerance aur performance mile.",
                architecture_overview="RAID 0 provides performance without redundancy. RAID 1 mirrors data (50% capacity). RAID 5 offers single-drive fault tolerance with parity. RAID 10 combines mirror and stripe for high performance and redundancy.",
                best_practices=[
                    "Use RAID 10 for high I/O workloads like SQL Server and Hyper-V host disks.",
                    "Use ReFS (Resilient File System) for Hyper-V VHDX storage due to fast block cloning."
                ],
                related_commands=["diskmgmt.msc", "diskpart", "Get-Disk", "Get-Volume", "Get-StoragePool"],
                docs_source="Microsoft Learn - Storage Spaces and RAID"
            )
        )

        # 16. Authentication: Kerberos vs NTLM
        self.register_concept(
            ITConcept(
                concept_id="kerberos_ntlm",
                canonical_name="Kerberos and NTLM Authentication",
                domain=ITDomain.WINDOWS_SERVER_2019,
                category="Security & Identity",
                aliases=["kerberos", "ntlm", "authentication", "ticket granting ticket", "tgt"],
                keywords=["kerberos", "ntlm", "authentication", "kdc", "tgt", "ticket", "clock skew"],
                definition_en="Kerberos is the default, ticket-based cryptographic authentication protocol in Active Directory (port 88), whereas NTLM is an older challenge/response protocol kept for backward compatibility. Kerberos requires strict time synchronization (< 5 minutes).",
                definition_hi="Kerberos Active Directory ka default fast aur secure ticket-based authentication protocol hai. NTLM purana challenge/response protocol hai. Kerberos client aur DC ke beech time sync (clock skew < 5 mins) par depend karta hai.",
                best_practices=[
                    "Audit and disable NTLMv1 across the enterprise to prevent pass-the-hash attacks.",
                    "Ensure reliable NTP time synchronization from the PDC Emulator Domain Controller."
                ],
                related_commands=["klist", "w32tm /query /status", "w32tm /resync"],
                docs_source="Microsoft Learn - Kerberos Authentication overview"
            )
        )

        # =========================================================================
        # DOMAIN 3: MICROSOFT AZURE
        # =========================================================================

        # 17. Azure Fundamentals & Resource Hierarchy
        self.register_concept(
            ITConcept(
                concept_id="azure_fundamentals",
                canonical_name="Azure Fundamentals & Resource Hierarchy",
                domain=ITDomain.AZURE,
                category="Cloud Architecture",
                aliases=["azure", "azure fundamentals", "resource group", "subscription", "management group"],
                keywords=["azure", "subscription", "resource group", "region", "availability zone", "arm"],
                definition_en="Microsoft Azure is a global public cloud computing platform organized in a 4-level hierarchy: Management Groups > Subscriptions > Resource Groups > Resources, deployed across global Regions and Availability Zones.",
                definition_hi="Microsoft Azure Microsoft ka cloud computing platform hai jismein resources ko 4 levels par organize kiya jata hai: Management Groups, Subscriptions, Resource Groups, aur individual Resources.",
                architecture_overview="Regions are geographic locations with datacenters. Availability Zones are physically separate datacenters within an Azure region offering 99.99% VM uptime SLA.",
                best_practices=[
                    "Group resources sharing the same lifecycle, permissions, and deployment cycle into the same Resource Group.",
                    "Use Azure Policy and Tags for cost tracking and governance."
                ],
                related_commands=["az account show", "az group list", "az group create"],
                docs_source="Microsoft Learn - Azure fundamentals documentation"
            )
        )

        # 18. Azure Virtual Machines (Azure VM)
        self.register_concept(
            ITConcept(
                concept_id="azure_vm",
                canonical_name="Azure Virtual Machines",
                domain=ITDomain.AZURE,
                category="Compute",
                aliases=["azure vm", "azure virtual machine", "azure compute"],
                keywords=["azure vm", "virtual machine", "azure vms", "vm size", "burstable", "managed disk"],
                definition_en="Azure Virtual Machines provides on-demand Infrastructure as a Service (IaaS) computing instances supporting Windows Server and Linux workloads with scalable CPU, RAM, and attached Managed Disks.",
                definition_hi="Azure VM Microsoft Azure mein ek scalable virtual server (IaaS) hai jise aap Windows Server ya Linux enterprise workloads run karne ke liye deploy kar sakte hain.",
                how_to_steps=[
                    "In Azure Portal, search 'Virtual Machines' > click 'Create' > 'Azure virtual machine'.",
                    "Select Subscription, Resource Group, Region, and Image (e.g. Windows Server 2019 Datacenter).",
                    "Select VM size (e.g. Standard_D4s_v5), configure administrator credentials, and attach VNet/Subnet.",
                    "Review and deploy."
                ],
                best_practices=[
                    "Use Azure Bastion for management instead of exposing port 3389 or 22 directly to the public internet.",
                    "Enable auto-shutdown on development/testing VMs to prevent unnecessary cost accumulation."
                ],
                related_commands=["az vm list", "az vm start", "az vm stop", "az vm open-port", "Get-AzVM"],
                docs_source="Microsoft Learn - Virtual machines in Azure"
            )
        )

        # 19. Azure Virtual Network (VNet) & NSG
        self.register_concept(
            ITConcept(
                concept_id="azure_vnet_nsg",
                canonical_name="Azure Virtual Network (VNet) and NSG",
                domain=ITDomain.AZURE,
                category="Networking",
                aliases=["vnet", "azure vnet", "nsg", "network security group", "subnet"],
                keywords=["vnet", "nsg", "virtual network", "subnet", "security rule", "inbound rule", "peering"],
                definition_en="Azure Virtual Network (VNet) is the fundamental building block for private cloud networks in Azure. Network Security Groups (NSGs) act as virtual firewalls containing stateful access control rules that filter network traffic to subnets and NICs.",
                definition_hi="Azure VNet cloud mein aapka private network isolation provide karta hai. Network Security Groups (NSG) virtual firewall ki tarah subnets aur VMs ke inbound/outbound ports ko filter karte hain.",
                how_to_steps=[
                    "Create a VNet with a private IPv4 address space (e.g. 10.1.0.0/16).",
                    "Divide into Subnets (e.g. WebSubnet 10.1.1.0/24, DBSubnet 10.1.2.0/24).",
                    "Create an NSG, configure Inbound Security Rules with Priority (100-4096), Port, Protocol, and Action (Allow/Deny), then associate to the subnet."
                ],
                best_practices=[
                    "Associate NSGs at the subnet level rather than individual NICs for cleaner management.",
                    "Use VNet Peering to connect virtual networks privately with ultra-low latency."
                ],
                related_commands=["az network vnet list", "az network nsg list", "az network nsg rule create"],
                docs_source="Microsoft Learn - Azure Virtual Network and NSG overview"
            )
        )

        # 20. Azure Storage Accounts & Blob Storage
        self.register_concept(
            ITConcept(
                concept_id="azure_storage",
                canonical_name="Azure Storage Accounts (Blob, Files, Disks)",
                domain=ITDomain.AZURE,
                category="Storage",
                aliases=["azure storage", "blob storage", "azure files", "storage account"],
                keywords=["azure storage", "blob", "azure files", "smb in azure", "storage account", "access tier", "hot cool archive"],
                definition_en="Azure Storage is Microsoft's cloud storage service offering Blob storage for unstructured data, Azure Files for managed SMB/NFS cloud file shares, Managed Disks for VMs, and Queue/Table storage.",
                definition_hi="Azure Storage Microsoft ka durable cloud storage service hai jo Blob (unstructured data), Azure Files (managed SMB file shares) aur VM Managed Disks provide karta hai.",
                architecture_overview="Offers access tiers: Hot (frequently accessed), Cool (infrequently accessed, lower storage cost), and Archive (long-term offline backup).",
                best_practices=[
                    "Enforce 'Secure transfer required' (HTTPS) and disable anonymous public blob access.",
                    "Configure Lifecycle Management policies to automatically transition older data to Cool or Archive tier."
                ],
                related_commands=["az storage account list", "az storage blob list", "az storage share list"],
                docs_source="Microsoft Learn - Introduction to Azure Storage"
            )
        )

        # 21. Microsoft Entra ID (formerly Azure AD) & RBAC
        self.register_concept(
            ITConcept(
                concept_id="entra_id_rbac",
                canonical_name="Microsoft Entra ID and Azure RBAC",
                domain=ITDomain.AZURE,
                category="Identity & Access",
                aliases=["entra id", "azure ad", "rbac", "role based access control", "entra"],
                keywords=["entra id", "azure ad", "rbac", "conditional access", "mfa", "role assignment"],
                definition_en="Microsoft Entra ID (formerly Azure AD) is a cloud-based identity and access management service. Azure Role-Based Access Control (RBAC) manages who has access to Azure resources, what they can do with those resources, and what areas they have access to.",
                definition_hi="Microsoft Entra ID (pehle Azure AD) cloud identity service hai. Azure RBAC se aap users ko specific roles (Owner, Contributor, Reader) assign karke unke permissions control karte hain.",
                best_practices=[
                    "Follow Principle of Least Privilege: assign 'Reader' or custom roles rather than global 'Contributor' or 'Owner'.",
                    "Enforce Multi-Factor Authentication (MFA) via Conditional Access Policies."
                ],
                related_commands=["az role assignment list", "az ad user list", "Get-AzRoleAssignment"],
                docs_source="Microsoft Learn - What is Microsoft Entra ID"
            )
        )

        # 22. Azure Key Vault
        self.register_concept(
            ITConcept(
                concept_id="azure_key_vault",
                canonical_name="Azure Key Vault",
                domain=ITDomain.AZURE,
                category="Security",
                aliases=["key vault", "azure key vault", "akv"],
                keywords=["key vault", "secrets", "keys", "certificates", "hsm", "encryption keys"],
                definition_en="Azure Key Vault is a cloud service for securely storing and accessing secrets (API keys, passwords), cryptographic keys, and SSL/TLS certificates backed by hardware security modules (HSMs).",
                definition_hi="Azure Key Vault ek secure cloud storage service hai jo application passwords, API keys, certificates aur encryption keys ko safely store karta hai.",
                best_practices=[
                    "Never hardcode credentials or connection strings in application code; fetch them dynamically from Key Vault using Managed Identities.",
                    "Enable soft-delete and purge protection to prevent accidental secret loss."
                ],
                related_commands=["az keyvault secret show", "az keyvault secret set", "Get-AzKeyVault"],
                docs_source="Microsoft Learn - Azure Key Vault overview"
            )
        )

        # 23. Azure Monitor & Log Analytics
        self.register_concept(
            ITConcept(
                concept_id="azure_monitor",
                canonical_name="Azure Monitor and Log Analytics",
                domain=ITDomain.AZURE,
                category="Monitoring & Management",
                aliases=["azure monitor", "log analytics", "kql", "azure alerts"],
                keywords=["azure monitor", "log analytics", "kql", "kusto query", "metrics", "diagnostic settings"],
                definition_en="Azure Monitor collects and analyzes telemetry from cloud and on-premises environments, offering real-time metrics, automated alert rules, and deep log querying using Kusto Query Language (KQL).",
                definition_hi="Azure Monitor cloud resources ki performance aur health telemetry collect karta hai aur Log Analytics workspace mein KQL queries dwara centralized monitoring provide karta hai.",
                best_practices=[
                    "Configure Action Groups to send automated SMS/Email/Webhook notifications on critical metric breaches (e.g. High CPU > 90%).",
                    "Set appropriate data retention periods in Log Analytics to optimize costs."
                ],
                related_commands=["az monitor metrics list", "az monitor alert list"],
                docs_source="Microsoft Learn - Azure Monitor overview"
            )
        )

        # =========================================================================
        # DOMAIN 4: NETWORKING
        # =========================================================================

        # 24. TCP/IP & OSI Model
        self.register_concept(
            ITConcept(
                concept_id="tcp_ip_osi",
                canonical_name="TCP/IP and OSI Networking Models",
                domain=ITDomain.NETWORKING,
                category="Fundamentals",
                aliases=["tcp/ip", "osi", "osi model", "tcp ip", "networking basics"],
                keywords=["tcp/ip", "osi model", "layers", "transport layer", "packet", "frame", "handshake"],
                definition_en="The OSI Model is a 7-layer theoretical framework (Physical, Data Link, Network, Transport, Session, Presentation, Application), while TCP/IP is the practical 4-layer suite powering the modern internet and enterprise networking.",
                definition_hi="OSI model 7 layers ka theoretical framework hai jabki TCP/IP 4 layers ka practical model hai jo network communication, packet routing aur reliable data delivery regulate karta hai.",
                components=["Physical (Layer 1)", "Data Link / MAC (Layer 2)", "Network / IP (Layer 3)", "Transport / TCP/UDP (Layer 4)", "Application (Layer 7)"],
                best_practices=[
                    "Use Layer 1-7 bottom-up approach when diagnosing network outages (Cable -> Link/Switch -> IP/Ping -> Port/Firewall -> Application)."
                ],
                related_commands=["ping", "tracert", "netstat", "ipconfig"],
                docs_source="RFC 793 / Microsoft Learn Networking concepts"
            )
        )

        # 25. IPv4, IPv6, and Subnetting
        self.register_concept(
            ITConcept(
                concept_id="ipv4_subnetting",
                canonical_name="IPv4, IPv6, and Subnetting (CIDR)",
                domain=ITDomain.NETWORKING,
                category="Addressing",
                aliases=["ipv4", "ipv6", "subnetting", "cidr", "subnet mask"],
                keywords=["ipv4", "ipv6", "subnetting", "cidr", "subnet mask", "default gateway", "private ip"],
                definition_en="IPv4 uses 32-bit numerical addresses divided into network and host bits via subnet masks or CIDR notation (e.g. /24 = 255.255.255.0). IPv6 uses 128-bit hexadecimal addresses to overcome IPv4 address exhaustion.",
                definition_hi="IPv4 32-bit address format use karta hai jise subnet mask ya CIDR notation (jaise /24) se network aur host parts mein divide kiya jata hai. IPv6 128-bit address space provide karta hai.",
                architecture_overview="Private IP ranges (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, and 192.168.0.0/16. These addresses are not routable on the public internet without NAT.",
                best_practices=[
                    "Design scalable subnet hierarchies with room for 30-50% growth per subnet.",
                    "Never overlap private subnets across on-premises and cloud VNets if planning VPN or ExpressRoute connection."
                ],
                related_commands=["ipconfig /all", "Get-NetIPAddress"],
                docs_source="RFC 1918 / Microsoft Learn IP addressing"
            )
        )

        # 26. VLANs, Routing, and Switching
        self.register_concept(
            ITConcept(
                concept_id="vlan_routing_switching",
                canonical_name="VLANs, Routing, and Switching",
                domain=ITDomain.NETWORKING,
                category="Infrastructure",
                aliases=["vlan", "routing", "switching", "default gateway", "router", "switch"],
                keywords=["vlan", "routing", "switching", "trunk", "access port", "layer 3 switch", "default gateway"],
                definition_en="Switches forward frames at Layer 2 using MAC addresses. VLANs (Virtual Local Area Networks) partition a physical switch into isolated broadcast domains. Routers or Layer 3 switches route packets across different VLANs and subnets.",
                definition_hi="Switch Layer 2 par MAC addresses ke zariye local traffic forward karta hai. VLANs ek physical switch ko multiple isolated logical networks mein divide karte hain, aur Router alag-alag VLANs ke beech traffic route karta hai.",
                best_practices=[
                    "Separate Management traffic, VoIP phones, Guest Wi-Fi, and Production servers into dedicated VLANs.",
                    "Disable unused switch ports and place them into a dummy unrouted VLAN."
                ],
                related_commands=["arp -a", "route print", "tracert"],
                docs_source="Network Infrastructure Design Best Practices"
            )
        )

        # 27. VPN & Common Network Ports
        self.register_concept(
            ITConcept(
                concept_id="vpn_ports",
                canonical_name="VPN and Common Network Ports",
                domain=ITDomain.NETWORKING,
                category="Protocols & Ports",
                aliases=["vpn", "network ports", "common ports", "ports"],
                keywords=["vpn", "port 80", "port 443", "port 3389", "port 53", "port 22", "port 445", "ipsec"],
                definition_en="A Virtual Private Network (VPN) creates an encrypted tunnel across the public internet. Common networking ports: HTTP (80), HTTPS (443), DNS (53), DHCP (67/68), Kerberos (88), SSH (22), Telnet (23), RDP (3389), SMB (445), LDAP (389).",
                definition_hi="VPN internet ke through encrypted aur secure private tunnel create karta hai. Important ports: RDP (3389), DNS (53), HTTPS (443), SMB (445), LDAP (389), SSH (22).",
                best_practices=[
                    "Block unencrypted protocols like Telnet (23) and plain HTTP (80) across enterprise perimeter.",
                    "Enforce Multi-Factor Authentication (MFA) on all client VPN endpoints."
                ],
                related_commands=["Test-NetConnection", "netstat -ano"],
                docs_source="IANA Port Numbers / Microsoft Learn"
            )
        )

        # =========================================================================
        # DOMAIN 5: ENTERPRISE INFRASTRUCTURE
        # =========================================================================

        # 28. SAN vs NAS Storage
        self.register_concept(
            ITConcept(
                concept_id="san_nas_storage",
                canonical_name="SAN vs NAS Enterprise Storage",
                domain=ITDomain.ENTERPRISE_INFRA,
                category="Storage",
                aliases=["san", "nas", "san vs nas", "storage area network", "network attached storage"],
                keywords=["san", "nas", "iscsi", "fibre channel", "block level", "file level", "storage"],
                definition_en="NAS (Network Attached Storage) provides file-level storage accessed over network protocols (SMB/NFS). SAN (Storage Area Network) provides high-speed block-level storage over dedicated Fibre Channel or iSCSI networks presented as raw disks.",
                definition_hi="NAS file-level storage hota hai jo SMB/NFS ke through shared folders provide karta hai. SAN dedicated network par block-level storage deta hai jo servers ko raw local disks ki tarah dikhai deta hai.",
                best_practices=[
                    "Use SAN (iSCSI/FC) for high-performance virtual machine clustering and database storage.",
                    "Use NAS for centralized office file sharing and secondary backup targets."
                ],
                related_commands=["iscsicpl.exe", "Get-IscsiTarget"],
                docs_source="Enterprise Storage Architecture Guidelines"
            )
        )

        # 29. Backup Strategy: 3-2-1 Rule & Disaster Recovery
        self.register_concept(
            ITConcept(
                concept_id="backup_dr_strategy",
                canonical_name="Backup Strategy (3-2-1 Rule) & Disaster Recovery",
                domain=ITDomain.ENTERPRISE_INFRA,
                category="Business Continuity",
                aliases=["backup", "disaster recovery", "3-2-1 rule", "disaster recovery dr", "dr strategy", "rto", "rpo"],
                keywords=["backup", "3-2-1", "disaster recovery", "rto", "rpo", "retention", "immutable backup"],
                definition_en="The 3-2-1 Backup Rule requires: 3 total copies of data, stored on 2 different media types, with 1 copy kept offsite (or in the cloud). RTO (Recovery Time Objective) defines acceptable downtime; RPO (Recovery Point Objective) defines acceptable data loss.",
                definition_hi="3-2-1 Backup Rule: Data ki 3 copies honi chahiye, 2 alag-alag media types par, aur kam se kam 1 copy off-site ya cloud mein. RTO se downtime limit tay hoti hai aur RPO se data loss limit.",
                best_practices=[
                    "Implement immutable or air-gapped backups to prevent ransomware from wiping backup repositories.",
                    "Conduct automated monthly backup restoration tests rather than assuming backups work."
                ],
                related_commands=["wbadmin", "Start-WBBackup"],
                docs_source="CISA / NIST Guidelines for Data Backup and Recovery"
            )
        )

        # 30. Patch Management & Endpoint Management
        self.register_concept(
            ITConcept(
                concept_id="patch_endpoint_management",
                canonical_name="Patch Management and Endpoint Management",
                domain=ITDomain.ENTERPRISE_INFRA,
                category="Systems Management",
                aliases=["patch management", "wsus", "sccm", "intune", "endpoint management"],
                keywords=["patch management", "wsus", "intune", "sccm", "patching", "updates", "endpoint"],
                definition_en="Enterprise patch management centrally deploys, tests, and verifies software and OS security updates across desktops and servers using tools like WSUS, Microsoft Intune, and Microsoft Endpoint Configuration Manager (MECM/SCCM).",
                definition_hi="Patch Management enterprise ke saare computers aur servers par security updates ko systematically test aur deploy karne ka process hai (WSUS, Intune, SCCM ke zariye).",
                best_practices=[
                    "Establish staged deployment rings (Pilot ring -> IT Test ring -> General Production rings).",
                    "Never deploy updates to production Domain Controllers without prior staging validation."
                ],
                related_commands=["Get-HotFix", "wmic qfe list"],
                docs_source="Microsoft Learn - Windows Update for Business and WSUS"
            )
        )
