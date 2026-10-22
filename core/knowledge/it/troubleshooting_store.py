# core/knowledge/it/troubleshooting_store.py
"""
Structured IT Troubleshooting Knowledge Store.
Implements the mandatory 6-phase diagnostic workflow:
1. Problem Identification
2. Likely Causes
3. Safe Checks
4. Diagnostic Commands / Tools
5. Possible Fixes
6. Verification Steps
"""

from typing import Dict, List, Optional
import re

from .models import ITDomain, ITTroubleshootingGuide


class TroubleshootingKnowledgeStore:
    """Repository of structured troubleshooting guides across enterprise IT systems."""

    def __init__(self):
        self._guides: Dict[str, ITTroubleshootingGuide] = {}
        self._initialize_guides()

    def register_guide(self, guide: ITTroubleshootingGuide) -> None:
        self._guides[guide.issue_id.lower()] = guide

    def get_guide(self, issue_id: str) -> Optional[ITTroubleshootingGuide]:
        return self._guides.get(issue_id.lower())

    def match_guide(self, query: str) -> Optional[ITTroubleshootingGuide]:
        """Matches a user troubleshooting query using keyword triggers and synonyms."""
        cleaned = query.lower()
        best_match = None
        best_score = 0

        for guide in self._guides.values():
            score = 0
            for kw in guide.keywords:
                if kw in cleaned:
                    score += 2
            if guide.issue_id.replace("_", " ") in cleaned:
                score += 3
            if score > best_score:
                best_score = score
                best_match = guide

        # Minimum matching threshold
        if best_score >= 2:
            return best_match
        return None

    def _initialize_guides(self) -> None:
        # 1. RDP Connection Failure
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="rdp_connection_failure",
                title_en="Remote Desktop (RDP) Connection Troubleshooting",
                title_hi="RDP (Remote Desktop) Connect Nahi Ho Raha Hai",
                domain=ITDomain.WINDOWS_DESKTOP,
                keywords=[
                    "rdp", "remote desktop", "3389", "mstsc", "rdp connect", "rdp nahi chal raha",
                    "rdp error", "remote desktop connect nahi ho raha", "remote desktop error",
                    "rdp connect nahi ho raha", "remote desktop kaam nahi kar raha"
                ],
                symptoms=[
                    "Remote Desktop cannot connect to the remote computer.",
                    "Error code 0x204, 0x104, or internal error.",
                    "Connection times out or displays credentials prompt and immediately disconnects."
                ],
                likely_causes=[
                    "Target machine is powered off, sleeping, or not on the same network/VPN.",
                    "Remote Desktop service ('TermService') stopped or disabled on target machine.",
                    "Windows Defender Firewall blocking TCP/UDP port 3389.",
                    "Network Level Authentication (NLA) mismatch or user not in 'Remote Desktop Users' group.",
                    "Maximum concurrent session limit reached."
                ],
                safe_checks=[
                    "Verify target PC/Server is powered on and can be pinged.",
                    "Check if target machine has Remote Desktop enabled in System Properties (sysdm.cpl).",
                    "Confirm the connecting user account belongs to 'Remote Desktop Users' or 'Administrators'."
                ],
                commands_tools=[
                    "Test-NetConnection -ComputerName <TargetIP> -Port 3389",
                    "ping <TargetIP>",
                    "Get-Service -Name TermService",
                    "netstat -ano | findstr 3389"
                ],
                possible_fixes=[
                    "Enable Remote Desktop via sysdm.cpl > Remote tab > 'Allow remote connections to this computer'.",
                    "Start Remote Desktop Service: 'Start-Service -Name TermService'.",
                    "Open Windows Firewall rule: 'Enable-NetFirewallRule -DisplayGroup \"Remote Desktop\"'.",
                    "Temporarily disable NLA if connecting from an older or non-domain client."
                ],
                verification_steps=[
                    "Run 'Test-NetConnection -ComputerName <TargetIP> -Port 3389' and verify TcpTestSucceeded: True.",
                    "Launch mstsc.exe and initiate test connection."
                ],
                docs_source="Microsoft Learn - Troubleshoot Remote Desktop disconnected errors"
            )
        )

        # 2. DNS Resolution Failure / Server 2019 DNS Troubleshooting
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="dns_troubleshooting",
                title_en="Windows Server 2019 / Client DNS Resolution Troubleshooting",
                title_hi="DNS Resolve Nahi Kar Raha / Server 2019 DNS Troubleshooting",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "dns", "dns resolve", "name resolution", "nslookup", "dns server",
                    "dns troubleshoot", "dns kaam nahi kar raha", "dns resolve nahi kar raha",
                    "dns error", "server 2019 mein dns kaise troubleshoot karun", "dns kaise troubleshoot karun"
                ],
                symptoms=[
                    "Cannot resolve hostnames or internal domain names (e.g. dc01.corp.local).",
                    "Websites or internal shares accessible by IP but not by FQDN.",
                    "Active Directory replication errors due to SRV record resolution failure."
                ],
                likely_causes=[
                    "Client network adapter configured with wrong DNS server IP (e.g. 127.0.0.1 or public 8.8.8.8 instead of Domain Controller).",
                    "Stale or corrupted DNS client cache.",
                    "Windows DNS Server service ('DNS') stopped on the Domain Controller.",
                    "Missing forward lookup zone or SRV records in AD-integrated DNS.",
                    "Upstream DNS forwarders not responding."
                ],
                safe_checks=[
                    "Check client's active DNS server configuration using 'ipconfig /all'.",
                    "Verify if the DNS server itself is reachable on port 53 via ping and Test-NetConnection.",
                    "Check DNS Server service status on Windows Server 2019."
                ],
                commands_tools=[
                    "ipconfig /flushdns",
                    "nslookup <hostname> <dnsserver_ip>",
                    "Resolve-DnsName -Name <domain.local> -Server <dnsserver_ip>",
                    "Test-NetConnection -ComputerName <dnsserver_ip> -Port 53",
                    "Get-Service -Name DNS",
                    "Get-DnsServerZone"
                ],
                possible_fixes=[
                    "Flush client resolver cache: 'ipconfig /flushdns'.",
                    "Set primary DNS adapter to point to the Domain Controller IP.",
                    "On DNS Server: Restart DNS service ('Restart-Service -Name DNS').",
                    "Verify Forwarders in DNS Manager console (dnsmgmt.msc) and test root hints.",
                    "Run 'ipconfig /registerdns' on client and server."
                ],
                verification_steps=[
                    "Run 'nslookup domain.local' and confirm authoritative answer from local DC.",
                    "Verify ping by hostname succeeds without IP."
                ],
                docs_source="Microsoft Learn - Troubleshooting DNS servers and clients"
            )
        )

        # 3. Domain User Login Failure
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="domain_user_login_failure",
                title_en="Active Directory Domain User Login Failure Troubleshooting",
                title_hi="Domain User Login Nahi Kar Pa Raha / Active Directory Login Issue",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "domain user login", "domain login", "active directory login", "login nahi ho raha",
                    "user login fail", "domain user login nahi kar pa raha", "domain join login",
                    "trust relationship", "account locked", "cannot contact domain controller"
                ],
                symptoms=[
                    "'The trust relationship between this workstation and the primary domain failed.'",
                    "'The referenced account is currently locked out and may not be logged on to.'",
                    "'There are currently no logon servers available to service the logon request.'",
                    "Password incorrect error despite valid credentials."
                ],
                likely_causes=[
                    "Account is locked out due to multiple invalid password attempts.",
                    "Client computer DNS is not pointing to the Domain Controller.",
                    "Secure channel / computer account password out of sync with Active Directory.",
                    "Time desynchronization (Kerberos fails if client and DC clock skew > 5 minutes).",
                    "User account is disabled or expired."
                ],
                safe_checks=[
                    "Verify if user account is locked or disabled in AD Users and Computers (dsa.msc).",
                    "Check system time on both client machine and Domain Controller (must match within 5 mins).",
                    "Check network connectivity and DNS resolution to the Domain Controller FQDN."
                ],
                commands_tools=[
                    "Get-ADUser -Identity <username> -Properties LockedOut, Enabled, PasswordExpired",
                    "Unlock-ADAccount -Identity <username>",
                    "nltest /sc_query:<domain>",
                    "Test-ComputerSecureChannel -Verbose",
                    "w32tm /query /status",
                    "w32tm /resync"
                ],
                possible_fixes=[
                    "If locked out: Run 'Unlock-ADAccount -Identity <username>' on the Domain Controller.",
                    "If clock skew: Synchronize time using 'w32tm /resync /force'.",
                    "If secure channel broken: Run 'Test-ComputerSecureChannel -Repair -Credential (Get-Credential)' or re-join computer to domain.",
                    "Ensure client network card primary DNS points strictly to the Domain Controller IP."
                ],
                verification_steps=[
                    "Confirm 'nltest /sc_query:domain' returns 'NERR_Success'.",
                    "Have the domain user log in interactively on the workstation."
                ],
                docs_source="Microsoft Learn - Troubleshoot Active Directory logon issues"
            )
        )

        # 4. Server Disk Full
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="server_disk_full",
                title_en="Windows Server Disk Space Exhaustion Troubleshooting",
                title_hi="Server Ka Disk Full Ho Gaya Hai / Low Disk Space",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "disk full", "server disk full", "disk space", "low disk space", "c drive full",
                    "hard disk full", "server ka disk full ho gaya hai", "disk space khatam",
                    "storage full", "drive full"
                ],
                symptoms=[
                    "Low disk space warning on C: drive (< 5% or 0 MB free).",
                    "Windows services (Exchange, SQL, IIS, Windows Update) crashing or refusing to start.",
                    "Event ID 2013: 'The disk is at or near capacity'."
                ],
                likely_causes=[
                    "Accumulation of Windows Update files and Component Store (C:\\Windows\\WinSxS).",
                    "IIS log files piling up in C:\\inetpub\\logs\\LogFiles.",
                    "Large temp files in C:\\Windows\\Temp and user AppData\\Local\\Temp.",
                    "VSS / Volume Shadow Copies consuming excessive storage.",
                    "Database transaction log files (.ldf) or memory dumps (MEMORY.DMP)."
                ],
                safe_checks=[
                    "Identify largest folders using PowerShell or TreeSize Free / WinDirStat.",
                    "Check shadow copy allocation using 'vssadmin list shadowstorage'.",
                    "Check IIS and Windows Update log directory sizes."
                ],
                commands_tools=[
                    "Get-Volume",
                    "vssadmin list shadowstorage",
                    "DISM /Online /Cleanup-Image /AnalyzeComponentStore",
                    "DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase",
                    "cleanmgr /sageset:1 & cleanmgr /sagerun:1"
                ],
                possible_fixes=[
                    "Run Disk Cleanup: 'cleanmgr /lowdisk'.",
                    "Clean Component Store: 'DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase'.",
                    "Compress or purge older IIS logs from C:\\inetpub\\logs\\LogFiles (archive logs > 30 days).",
                    "Delete memory dump files: C:\\Windows\\MEMORY.DMP and minidumps.",
                    "Adjust VSS storage limit: 'vssadmin resize shadowstorage /for=C: /on=C: /maxsize=10%'."
                ],
                verification_steps=[
                    "Run 'Get-Volume -DriveLetter C' and verify FreeSpace is healthy (> 15% recommended).",
                    "Confirm all stopped services restart successfully."
                ],
                docs_source="Microsoft Learn - Free up drive space in Windows Server"
            )
        )

        # 5. Azure VM Unreachable
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="azure_vm_unreachable",
                title_en="Azure Virtual Machine Unreachable / RDP / SSH Troubleshooting",
                title_hi="Azure VM Reachable Nahi Hai / Azure VM Connect Issue",
                domain=ITDomain.AZURE,
                keywords=[
                    "azure vm", "azure vm reachable nahi", "azure vm unreachable",
                    "azure vm connect", "azure vm down", "azure rdp",
                    "azure vm reachable nahi hai", "azure vm ping nahi ho raha", "azure vm timeout"
                ],
                symptoms=[
                    "Cannot RDP (port 3389) or SSH (port 22) into Azure Virtual Machine.",
                    "Public IP connection times out.",
                    "Azure Portal shows VM status as 'Running' but machine does not respond."
                ],
                likely_causes=[
                    "Network Security Group (NSG) inbound security rule missing or blocked for port 3389/22.",
                    "Guest OS Windows Firewall or Linux iptables blocking the port internally.",
                    "VM guest OS is hung, crashed with blue screen, or stuck in Windows Update boot loop.",
                    "Public IP address changed (dynamic IP unassigned after deallocation).",
                    "Subnet route table (UDR) routing traffic to a non-existent virtual appliance."
                ],
                safe_checks=[
                    "Check Azure Portal: Verify VM power state is 'Running'.",
                    "Inspect Boot Diagnostics screenshot in the Azure Portal to see if Windows is booted or BSOD.",
                    "Check effective NSG rules for the VM's network interface (NIC)."
                ],
                commands_tools=[
                    "az vm show -g <ResourceGroup> -n <VMName> -d --query [powerState,publicIps] -o tsv",
                    "az network watcher test-ip-flow",
                    "az vm open-port -g <ResourceGroup> -n <VMName> --port 3389",
                    "Test-NetConnection -ComputerName <PublicIP> -Port 3389"
                ],
                possible_fixes=[
                    "Add Inbound NSG Rule allowing TCP port 3389 (RDP) or 22 (SSH) from your client IP.",
                    "Use Azure Bastion to connect securely over HTTPS via private IP.",
                    "Use Azure Serial Console or Run Command ('EnableRemotePS', 'ResetRDPSettings') to repair guest OS settings.",
                    "Redeploy the VM to a new Azure host using Azure Portal > Redeploy blade."
                ],
                verification_steps=[
                    "Use 'IP Flow Verify' in Azure Network Watcher to confirm packet allow status.",
                    "Test RDP connection via mstsc.exe or Azure Portal 'Connect' blade."
                ],
                docs_source="Microsoft Learn - Troubleshoot Remote Desktop connections to an Azure VM"
            )
        )

        # 6. DHCP IP Allocation Failure
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="dhcp_not_giving_ip",
                title_en="DHCP Server Not Assigning IP Addresses Troubleshooting",
                title_hi="DHCP IP Nahi De Raha / DHCP Client APIPA 169.254.x.x Issue",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "dhcp", "dhcp ip nahi de raha", "dhcp error", "dhcp not working",
                    "apipa", "169.254", "dhcp scope", "dhcp assign nahi kar raha", "dhcp down"
                ],
                symptoms=[
                    "Clients get APIPA automatic private IP address (169.254.x.x).",
                    "No internet or LAN connectivity on client computers.",
                    "Event Viewer displays Event ID 1001: 'Your computer was not assigned an address from the network'."
                ],
                likely_causes=[
                    "DHCP scope is 100% exhausted (no free IP addresses in pool).",
                    "DHCP Server service stopped or crashed on the server.",
                    "DHCP server is not authorized in Active Directory.",
                    "Network switch VLAN configuration missing IP Helper address (DHCP Relay).",
                    "Rogue DHCP server on the local subnet."
                ],
                safe_checks=[
                    "Check DHCP Server service status ('DHCPServer') on Windows Server.",
                    "Check DHCP MMC console (dhcpmgmt.msc) to verify scope active status and % free addresses.",
                    "Verify if server is authorized in AD (green arrow in DHCP console)."
                ],
                commands_tools=[
                    "Get-Service -Name DHCPServer",
                    "Get-DhcpServerv4Scope",
                    "Get-DhcpServerv4Lease -ScopeId <SubnetID>",
                    "ipconfig /release & ipconfig /renew"
                ],
                possible_fixes=[
                    "If service stopped: Start DHCP service ('Start-Service DHCPServer').",
                    "If scope exhausted: Expand scope range, reduce DHCP lease duration, or deactivate obsolete reservations.",
                    "If unauthorized: Right-click DHCP Server in console > Authorize.",
                    "If routed across VLANs: Configure IP helper-address on the core switch / router pointing to DHCP server IP."
                ],
                verification_steps=[
                    "On client: Run 'ipconfig /renew' and verify a valid subnet IP is obtained.",
                    "Check DHCP console Address Leases to confirm newly assigned lease."
                ],
                docs_source="Microsoft Learn - Troubleshoot issues on the DHCP server"
            )
        )

        # 7. IIS Website Down / 500 Error
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="iis_website_down",
                title_en="IIS Web Server Website Down / HTTP 500 Error Troubleshooting",
                title_hi="IIS Website Open Nahi Ho Rahi / IIS Web Server Issue",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "iis", "iis website", "iis website open nahi ho rahi", "500 internal server error",
                    "503 service unavailable", "iis site down", "w3wp", "app pool stopped",
                    "iis web server", "iis kaam nahi kar raha"
                ],
                symptoms=[
                    "Browser shows 'HTTP Error 503. The service is unavailable.'",
                    "HTTP Error 500.19 / 500.0 Internal Server Error.",
                    "Cannot reach website via HTTP (port 80) or HTTPS (port 443)."
                ],
                likely_causes=[
                    "Application Pool is stopped (often due to rapid fail protection or invalid identity credentials).",
                    "Port conflict on 80/443 with another process (e.g. Skype, Apache, or another site binding).",
                    "Invalid XML or missing modules in the website's web.config file.",
                    "World Wide Web Publishing Service ('W3SVC') is stopped.",
                    "NTFS file permission missing for 'IIS_IUSRS' on the website folder."
                ],
                safe_checks=[
                    "Check IIS Manager (inetmgr): Check if site and its Application Pool are in 'Started' state.",
                    "Check Windows Event Viewer > Application log for event source 'WAS' or 'IIS-W3SVC-WP'.",
                    "Check if port 80/443 is listening using 'netstat -ano'."
                ],
                commands_tools=[
                    "Get-Service -Name W3SVC",
                    "Get-IISAppPool",
                    "netstat -ano | findstr :80",
                    "iisreset /status",
                    "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='WAS'} -MaxEvents 5"
                ],
                possible_fixes=[
                    "If Application Pool stopped: Start the Application Pool in IIS Manager or 'Start-WebAppPool'.",
                    "If 503 error due to AppPool identity: Update the domain service account password in AppPool Advanced Settings.",
                    "If web.config error: Correct XML syntax or install missing IIS role features (e.g. URL Rewrite, ASP.NET Core Module).",
                    "Grant 'IIS_IUSRS' Read & Execute permissions on website directory.",
                    "Restart IIS cleanly: 'iisreset'."
                ],
                verification_steps=[
                    "Open local browser and navigate to 'http://localhost' or site URL.",
                    "Confirm HTTP 200 OK status in IIS log file (C:\\inetpub\\logs\\LogFiles)."
                ],
                docs_source="Microsoft Learn - Troubleshoot IIS web server issues"
            )
        )

        # 8. Group Policy Not Applying
        self.register_guide(
            ITTroubleshootingGuide(
                issue_id="gpo_not_applying",
                title_en="Group Policy (GPO) Not Applying Troubleshooting",
                title_hi="Group Policy Apply Nahi Ho Rahi / GPO Troubleshooting",
                domain=ITDomain.WINDOWS_SERVER_2019,
                keywords=[
                    "group policy", "gpo", "gpo apply nahi ho rahi", "group policy apply",
                    "gpupdate fail", "gpo not applying", "group policy issue", "gpresult"
                ],
                symptoms=[
                    "Configured GPO settings do not take effect on client or server.",
                    "gpupdate /force fails with 'The processing of Group Policy failed'.",
                    "gpresult /r does not list the expected GPO under Applied Group Policy Objects."
                ],
                likely_causes=[
                    "Computer or User object is in the wrong Organizational Unit (OU) where GPO is not linked.",
                    "Security Filtering or WMI Filtering blocking the computer or user.",
                    "GPO link is disabled or Block Inheritance is enabled on the OU.",
                    "Active Directory replication delay or SYSVOL replication failure (DFS-R issue).",
                    "Fast Startup in Windows 10/11 bypassing synchronous GPO processing."
                ],
                safe_checks=[
                    "Verify OU placement of the target computer and user in AD Users & Computers.",
                    "Generate HTML GPResult report using 'gpresult /h report.html' to see 'Denied GPOs' reason.",
                    "Check client DNS settings to ensure it resolves domain SYSVOL share."
                ],
                commands_tools=[
                    "gpupdate /force",
                    "gpresult /r",
                    "gpresult /h C:\\gpreport.html",
                    "nltest /dsgetdc:<domain>",
                    "Test-Path \\\\<domain>\\SYSVOL"
                ],
                possible_fixes=[
                    "Verify GPO is linked to the correct OU in Group Policy Management Console (gpmc.msc).",
                    "Check Security Filtering: ensure 'Authenticated Users' or specific target group has 'Read' and 'Apply group policy' permissions.",
                    "Force replication between Domain Controllers: 'repadmin /syncall /AdeP'.",
                    "Run 'gpupdate /force /boot' to apply policies requiring reboot."
                ],
                verification_steps=[
                    "Run 'gpresult /r' and confirm the GPO appears under 'Applied Group Policy Objects'.",
                    "Verify registry keys or settings modified by the policy."
                ],
                docs_source="Microsoft Learn - Troubleshooting Group Policy processing"
            )
        )
