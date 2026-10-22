# core/knowledge/it/command_store.py
"""
Safe Technical Command Knowledge Store.
Indexes administrative tools, PowerShell cmdlets, CMD utilities, and Azure CLI commands.
Provides safe explanations, syntax, options, and security classification WITHOUT executing them.
"""

from typing import Dict, List, Optional
import re

from .models import CommandRiskLevel, ITCommand


class CommandKnowledgeStore:
    """Repository of technical commands and cmdlets across Windows, Server, Azure, and Network."""

    def __init__(self):
        self._commands: Dict[str, ITCommand] = {}
        self._alias_map: Dict[str, str] = {}
        self._initialize_commands()

    def register_command(self, cmd: ITCommand, aliases: Optional[List[str]] = None) -> None:
        key = cmd.command.lower()
        self._commands[key] = cmd
        self._alias_map[key] = key
        if aliases:
            for alias in aliases:
                self._alias_map[alias.lower()] = key

    def get_command(self, query: str) -> Optional[ITCommand]:
        cleaned = query.strip().lower()
        if cleaned in self._alias_map:
            return self._commands[self._alias_map[cleaned]]
        for key in self._commands:
            if re.search(r"\b" + re.escape(key) + r"\b", cleaned):
                return self._commands[key]
        return None

    def search_commands_by_concept(self, concept_name: str) -> List[ITCommand]:
        c_low = concept_name.lower()
        results = []
        for cmd in self._commands.values():
            if any(c_low in rel.lower() for rel in cmd.related_concepts):
                results.append(cmd)
        return results

    def _initialize_commands(self) -> None:
        # 1. ipconfig
        self.register_command(
            ITCommand(
                command="ipconfig",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays all current TCP/IP network configuration values and refreshes DHCP and DNS settings.",
                purpose_hi="Current TCP/IP network configuration (IP address, subnet mask, default gateway) display karta hai aur DNS/DHCP refresh karta hai.",
                syntax="ipconfig [/all | /flushdns | /renew | /release]",
                common_options={
                    "/all": "Displays full configuration details including MAC address, DHCP server, and DNS servers.",
                    "/flushdns": "Purges and resets the contents of the DNS client resolver cache.",
                    "/renew": "Renews DHCP configuration for all or specified network adapters.",
                    "/release": "Sends a DHCPRELEASE message to the DHCP server to release the current IP address."
                },
                safe_examples=["ipconfig /all", "ipconfig /flushdns", "ipconfig /renew"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["dns", "dhcp", "tcp/ip", "network troubleshooting"]
            ),
            aliases=["ip config", "ipconfig.exe"]
        )

        # 2. ping
        self.register_command(
            ITCommand(
                command="ping",
                tool="CMD / PowerShell",
                platform="Cross-platform / Windows / Network",
                purpose_en="Verifies IP-level connectivity to another computer or domain by sending ICMP Echo Request messages.",
                purpose_hi="ICMP packets bhejkar kisi IP address ya host ke saath network connectivity aur latency verify karta hai.",
                syntax="ping <target_host_or_ip> [-t] [-n count] [-l size]",
                common_options={
                    "-t": "Pings the specified host continuously until stopped by pressing Ctrl+C.",
                    "-n <count>": "Specifies the number of Echo Request messages to send (default 4).",
                    "-l <size>": "Specifies the buffer length in bytes for the send packet."
                },
                safe_examples=["ping 8.8.8.8", "ping google.com", "ping 192.168.1.1 -n 4"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["tcp/ip", "icmp", "network troubleshooting"]
            )
        )

        # 3. tracert / traceroute
        self.register_command(
            ITCommand(
                command="tracert",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Traces the network path to a destination by sending ICMP packets with incrementing TTL (Time to Live) values.",
                purpose_hi="Destination tak pahunchne wale packet ke saare network hops aur routers ka path trace karta hai.",
                syntax="tracert [-d] [-h max_hops] <target_host>",
                common_options={
                    "-d": "Prevents tracert from attempting to resolve intermediate router IP addresses to names, speeding up trace.",
                    "-h <max_hops>": "Specifies the maximum number of hops to search for the target."
                },
                safe_examples=["tracert -d 8.8.8.8", "tracert google.com"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["routing", "network troubleshooting", "hops"]
            ),
            aliases=["traceroute"]
        )

        # 4. nslookup
        self.register_command(
            ITCommand(
                command="nslookup",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Queries DNS servers to find IP addresses associated with domain names or to test DNS resolution records.",
                purpose_hi="Domain names aur IP addresses ke beech DNS resolution verify karne aur DNS records query karne ke liye use hota hai.",
                syntax="nslookup <domain_name> [dns_server_ip]",
                common_options={
                    "-type=A": "Queries IPv4 host address records.",
                    "-type=MX": "Queries Mail Exchange mail server records.",
                    "-type=PTR": "Queries reverse DNS lookup pointer records.",
                    "-type=SOA": "Queries Start of Authority records for a DNS zone."
                },
                safe_examples=["nslookup google.com", "nslookup dc01.corp.local 10.0.0.1", "nslookup -type=mx domain.com"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["dns", "domain controller", "active directory"]
            )
        )

        # 5. netstat
        self.register_command(
            ITCommand(
                command="netstat",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays active TCP connections, listening ports, Ethernet statistics, IP routing table, and protocol statistics.",
                purpose_hi="System ke active network connections, listening ports aur unse associated Process IDs (PID) display karta hai.",
                syntax="netstat [-a] [-n] [-o] [-p protocol] [-r]",
                common_options={
                    "-a": "Displays all active connections and listening TCP/UDP ports.",
                    "-n": "Displays addresses and port numbers in numerical form without name lookup.",
                    "-o": "Displays the owning process ID (PID) associated with each connection.",
                    "-r": "Displays the IP routing table."
                },
                safe_examples=["netstat -ano", "netstat -ano | findstr 3389", "netstat -ano | findstr 80"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["ports", "tcp/ip", "rdp", "iis", "troubleshooting"]
            )
        )

        # 6. tasklist
        self.register_command(
            ITCommand(
                command="tasklist",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays a list of currently running processes on local or remote computers with Memory usage and PID.",
                purpose_hi="Local ya remote system par chal rahe saare active processes, unke PID aur memory usage ki list dikhata hai.",
                syntax="tasklist [/s system [/u username [/p password]]] [/fi filterformat]",
                common_options={
                    "/m [modulename]": "Lists all processes with loaded modules/DLLs.",
                    "/svc": "Displays services hosted in each process.",
                    "/fi <filter>": "Filters output (e.g. /fi \"MEMUSAGE gt 50000\")."
                },
                safe_examples=["tasklist", "tasklist /svc", "tasklist /fi \"IMAGENAME eq chrome.exe\""],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["processes", "task manager", "services", "memory"]
            )
        )

        # 7. taskkill
        self.register_command(
            ITCommand(
                command="taskkill",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Terminates tasks and processes by process ID (PID) or image name.",
                purpose_hi="Kisi running process ko uske PID ya process name ke dwara force ya gracefully terminate karta hai.",
                syntax="taskkill [/s system] {[/pid processid | /im imagename]} [/f] [/t]",
                common_options={
                    "/f": "Forcefully terminates the process.",
                    "/t": "Terminates the specified process and any child processes started by it.",
                    "/im <name>": "Specifies the image name of the process to terminate."
                },
                safe_examples=["taskkill /im notepad.exe", "taskkill /f /pid 1234"],
                risk_level=CommandRiskLevel.HIGH_DESTRUCTIVE,
                related_concepts=["processes", "task manager", "troubleshooting"]
            )
        )

        # 8. sfc (System File Checker)
        self.register_command(
            ITCommand(
                command="sfc",
                tool="CMD / PowerShell (Admin)",
                platform="Windows Desktop / Server",
                purpose_en="Scans and verifies the integrity of all protected Windows system files and replaces corrupted files from cache.",
                purpose_hi="Protected Windows system files ki integrity scan karta hai aur corrupted ya missing files ko clean cached copy se restore karta hai.",
                syntax="sfc [/scannow] [/verifyonly] [/scanfile=file]",
                common_options={
                    "/scannow": "Scans integrity of all protected system files and repairs files with problems.",
                    "/verifyonly": "Scans integrity of all protected system files with no repair operations performed."
                },
                safe_examples=["sfc /scannow", "sfc /verifyonly"],
                risk_level=CommandRiskLevel.MEDIUM_STATE_CHANGE,
                related_concepts=["system integrity", "windows repair", "corruption", "dism"]
            )
        )

        # 9. DISM
        self.register_command(
            ITCommand(
                command="dism",
                tool="CMD / PowerShell (Admin)",
                platform="Windows Desktop / Server",
                purpose_en="Deployment Image Servicing and Management tool used for servicing Windows images and repairing Windows Component Store (WinSxS).",
                purpose_hi="Windows image servicing aur corrupt Component Store (WinSxS) ko repair karne ke liye authoritative tool hai.",
                syntax="DISM /Online /Cleanup-Image {/CheckHealth | /ScanHealth | /RestoreHealth}",
                common_options={
                    "/CheckHealth": "Checks whether corruption has been flagged by a previous process.",
                    "/ScanHealth": "Scans the component store for corruption without fixing.",
                    "/RestoreHealth": "Scans the image for component store corruption and performs repair operations automatically from Windows Update."
                },
                safe_examples=["DISM /Online /Cleanup-Image /ScanHealth", "DISM /Online /Cleanup-Image /RestoreHealth"],
                risk_level=CommandRiskLevel.MEDIUM_STATE_CHANGE,
                related_concepts=["winsxs", "system repair", "sfc", "windows update"]
            )
        )

        # 10. gpupdate
        self.register_command(
            ITCommand(
                command="gpupdate",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server (Domain Joined)",
                purpose_en="Refreshes local and Active Directory-based Group Policy settings on the computer.",
                purpose_hi="Computer aur user context ke Group Policy (GPO) settings ko manually aur immediately refresh karta hai.",
                syntax="gpupdate [/target:{computer | user}] [/force] [/wait:value] [/logoff] [/boot]",
                common_options={
                    "/force": "Reapplies all policy settings even if no policy changes have occurred.",
                    "/target:computer": "Refreshes only computer-level policy settings.",
                    "/target:user": "Refreshes only user-level policy settings."
                },
                safe_examples=["gpupdate /force", "gpupdate /target:computer"],
                risk_level=CommandRiskLevel.MEDIUM_STATE_CHANGE,
                related_concepts=["group policy", "active directory", "gpo", "domain controller"]
            )
        )

        # 11. gpresult
        self.register_command(
            ITCommand(
                command="gpresult",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays the Resultant Set of Policy (RSoP) information for a remote user and computer.",
                purpose_hi="System aur user par kaun-kaun se Group Policies apply huye hain unka complete RSoP report display karta hai.",
                syntax="gpresult [/s system] [/user targetusername] [/r | /h reportname.html]",
                common_options={
                    "/r": "Displays summary RSoP data directly in the console.",
                    "/h <filename.html>": "Generates a comprehensive HTML visual report of all applied GPOs.",
                    "/scope {user | computer}": "Displays results for user or computer only."
                },
                safe_examples=["gpresult /r", "gpresult /h C:\\gp_report.html"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["group policy", "gpo", "active directory", "rsop"]
            )
        )

        # 12. whoami
        self.register_command(
            ITCommand(
                command="whoami",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays current user, domain, group membership, and privilege security identifier (SID) information.",
                purpose_hi="Current logged-in user identity, domain name, security groups aur assigned privileges dikhata hai.",
                syntax="whoami [/user] [/groups] [/priv] [/all]",
                common_options={
                    "/all": "Displays current user name, security ID (SID), security groups, and privileges.",
                    "/groups": "Displays current user group memberships.",
                    "/priv": "Displays current security privileges held by the user token."
                },
                safe_examples=["whoami", "whoami /all", "whoami /groups"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["security", "authentication", "permissions", "active directory"]
            )
        )

        # 13. hostname
        self.register_command(
            ITCommand(
                command="hostname",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Prints the current computer name (NetBIOS name).",
                purpose_hi="Current computer ka system name display karta hai.",
                syntax="hostname",
                common_options={},
                safe_examples=["hostname"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["system info", "computer name", "netbios"]
            )
        )

        # 14. systeminfo
        self.register_command(
            ITCommand(
                command="systeminfo",
                tool="CMD / PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays detailed configuration information about a computer and its operating system, hardware, hotfixes, and domain.",
                purpose_hi="OS version, system uptime, processor, memory, BIOS version, domain aur installed hotfixes ki comprehensive list dikhata hai.",
                syntax="systeminfo [/s system [/u username [/p password]]] [/fo format]",
                common_options={
                    "/fo {TABLE | LIST | CSV}": "Specifies output format."
                },
                safe_examples=["systeminfo", "systeminfo | findstr /B /C:\"OS Name\" /C:\"OS Version\""],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["system configuration", "os version", "hotfixes", "uptime"]
            )
        )

        # 15. Get-ComputerInfo
        self.register_command(
            ITCommand(
                command="get-computerinfo",
                tool="PowerShell",
                platform="Windows 10/11 / Server 2016+",
                purpose_en="PowerShell cmdlet that retrieves a consolidated object of system and operating system properties.",
                purpose_hi="Operating system aur hardware properties ka structured object return karta hai (PowerShell replacement for systeminfo).",
                syntax="Get-ComputerInfo [[-Property] <string[]>]",
                common_options={
                    "-Property": "Filters specific properties like OsName, WindowsVersion, BiosBIOSVersion."
                },
                safe_examples=["Get-ComputerInfo", "Get-ComputerInfo -Property OsName, WindowsVersion, OsUptime"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["powershell", "system info", "hardware"]
            )
        )

        # 16. Get-Service
        self.register_command(
            ITCommand(
                command="get-service",
                tool="PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Gets objects that represent the services on a computer, including status (Running/Stopped).",
                purpose_hi="System ke Windows services aur unke current status (Running/Stopped) ko query karta hai.",
                syntax="Get-Service [[-Name] <string[]>] [-ComputerName <string[]>]",
                common_options={
                    "-Name <string>": "Specifies service name (e.g. wuauserv, spooler, TermService, DNS).",
                    "-DisplayName": "Specifies service display name."
                },
                safe_examples=["Get-Service -Name TermService", "Get-Service | Where-Object {$_.Status -eq 'Running'}"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["services", "rdp", "dns", "spooler", "troubleshooting"]
            )
        )

        # 17. Get-Process
        self.register_command(
            ITCommand(
                command="get-process",
                tool="PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Gets the processes that are running on the local computer or a remote computer.",
                purpose_hi="Running processes ki list unke CPU, memory usage aur process ID ke saath return karta hai.",
                syntax="Get-Process [[-Name] <string[]>] [-Id <Int32[]>]",
                common_options={
                    "-Name": "Process name filter.",
                    "-Id": "Process ID filter."
                },
                safe_examples=["Get-Process -Name explorer", "Get-Process | Sort-Object CPU -Descending | Select-Object -First 10"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["task manager", "processes", "performance monitor"]
            )
        )

        # 18. Get-WinEvent / Get-EventLog
        self.register_command(
            ITCommand(
                command="get-winevent",
                tool="PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Gets events from event logs and event tracing log files on local and remote computers.",
                purpose_hi="Event Viewer logs (Application, System, Security) ko filter aur query karta hai.",
                syntax="Get-WinEvent [-LogName <string[]>] [-MaxEvents <int64>] [-FilterHashtable <hashtable>]",
                common_options={
                    "-LogName": "Log name (System, Application, Security).",
                    "-MaxEvents": "Limits number of events returned.",
                    "-FilterHashtable": "High-performance hashtable filter for EventID, ProviderName, Level."
                },
                safe_examples=["Get-WinEvent -LogName System -MaxEvents 20", "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 10"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["event viewer", "logs", "troubleshooting", "diagnostics"]
            ),
            aliases=["get-eventlog"]
        )

        # 19. Test-NetConnection
        self.register_command(
            ITCommand(
                command="test-netconnection",
                tool="PowerShell",
                platform="Windows Desktop / Server",
                purpose_en="Displays diagnostic information for a connection, testing ICMP ping, DNS resolution, and specific TCP port reachability.",
                purpose_hi="Network connection diagnostic tool jo ICMP ping, DNS lookup aur specific TCP port reachability test karta hai.",
                syntax="Test-NetConnection [-ComputerName <string>] [-Port <int>] [-InformationLevel <string>]",
                common_options={
                    "-Port <int>": "Specifies TCP port to test (e.g. 3389 for RDP, 80 for HTTP, 443 for HTTPS).",
                    "-CommonTCPPort": "Tests common ports like HTTP, RDP, SMB, WINRM.",
                    "-TraceRoute": "Performs route tracing."
                },
                safe_examples=["Test-NetConnection -ComputerName 192.168.1.10 -Port 3389", "Test-NetConnection -ComputerName dc01 -Port 53"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["network troubleshooting", "ports", "rdp", "dns", "firewall"]
            ),
            aliases=["tnc"]
        )

        # 20. Get-ADUser
        self.register_command(
            ITCommand(
                command="get-aduser",
                tool="PowerShell (ActiveDirectory Module)",
                platform="Windows Server 2019 / RSAT",
                purpose_en="Gets one or more Active Directory user objects with identity and account attributes (Enabled, LockedOut, PasswordExpired).",
                purpose_hi="Active Directory user objects aur unke account status (LockedOut, Enabled, PasswordLastSet) ko query karta hai.",
                syntax="Get-ADUser [-Identity] <string> [-Properties <string[]>] [-Filter <string>]",
                common_options={
                    "-Identity": "Specifies user account SAMAccountName, UPN, or DistinguishedName.",
                    "-Properties *": "Returns all extended user attributes.",
                    "-Filter": "Queries AD users matching criteria (e.g. {LockedOut -eq $true})."
                },
                safe_examples=["Get-ADUser -Identity john.doe -Properties LockedOut, Enabled, PasswordLastSet", "Get-ADUser -Filter {LockedOut -eq $true}"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["active directory", "domain controller", "domain user login", "troubleshooting"]
            )
        )

        # 21. Get-ADComputer
        self.register_command(
            ITCommand(
                command="get-adcomputer",
                tool="PowerShell (ActiveDirectory Module)",
                platform="Windows Server 2019 / RSAT",
                purpose_en="Gets one or more Active Directory computer accounts.",
                purpose_hi="Active Directory domain mein joined computer accounts aur unke OS details retrieve karta hai.",
                syntax="Get-ADComputer [-Identity] <string> [-Properties <string[]>] [-Filter <string>]",
                common_options={
                    "-Filter *": "Retrieves all domain computers.",
                    "-Properties OperatingSystem": "Returns OS version information."
                },
                safe_examples=["Get-ADComputer -Identity WS01 -Properties OperatingSystem", "Get-ADComputer -Filter *"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["active directory", "domain controller", "computers"]
            )
        )

        # 22. Get-DnsServerZone
        self.register_command(
            ITCommand(
                command="get-dnsserverzone",
                tool="PowerShell (DnsServer Module)",
                platform="Windows Server 2019",
                purpose_en="Retrieves a list of DNS zones hosted on a DNS server or details of a specified zone.",
                purpose_hi="Windows DNS Server par configured forward aur reverse lookup zones ki information return karta hai.",
                syntax="Get-DnsServerZone [[-Name] <string>] [-ComputerName <string>]",
                common_options={
                    "-Name <string>": "Specifies zone name (e.g. corp.local).",
                    "-ZoneType": "Filters by Primary, Secondary, Forwarder, Stub."
                },
                safe_examples=["Get-DnsServerZone", "Get-DnsServerZone -Name corp.local"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["dns", "windows server 2019", "domain controller"]
            )
        )

        # 23. Get-DhcpServerv4Scope
        self.register_command(
            ITCommand(
                command="get-dhcpserverv4scope",
                tool="PowerShell (DhcpServer Module)",
                platform="Windows Server 2019",
                purpose_en="Returns the IPv4 scope configuration of the specified DHCP scopes on a DHCP Server.",
                purpose_hi="Windows Server DHCP service par configured IPv4 scopes, address ranges aur status return karta hai.",
                syntax="Get-DhcpServerv4Scope [-ScopeId <IPAddress[]>] [-ComputerName <string>]",
                common_options={
                    "-ScopeId": "Specifies subnet ID for the scope.",
                    "-ComputerName": "DHCP Server host."
                },
                safe_examples=["Get-DhcpServerv4Scope", "Get-DhcpServerv4Scope -ScopeId 192.168.1.0"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["dhcp", "ip address", "windows server 2019", "networking"]
            )
        )

        # 24. az vm
        self.register_command(
            ITCommand(
                command="az vm",
                tool="Azure CLI",
                platform="Microsoft Azure",
                purpose_en="Manages Linux or Windows virtual machines in Microsoft Azure.",
                purpose_hi="Microsoft Azure virtual machines ko manage karne (list, start, stop, show) ka command line interface hai.",
                syntax="az vm {list | show | start | restart | deallocate | stop | open-port}",
                common_options={
                    "list -o table": "Lists all Azure VMs in the active subscription.",
                    "show -g <rg> -n <vm> -d": "Shows details and public/private IP of a specific VM.",
                    "open-port -g <rg> -n <vm> --port <port>": "Adds an inbound NSG rule to open a specific port."
                },
                safe_examples=["az vm list -o table", "az vm show -g MyResourceGroup -n MyVM -d", "az vm open-port -g MyRG -n MyVM --port 3389"],
                risk_level=CommandRiskLevel.MEDIUM_STATE_CHANGE,
                related_concepts=["azure vm", "azure", "nsg", "virtual machines"]
            )
        )

        # 25. az account
        self.register_command(
            ITCommand(
                command="az account",
                tool="Azure CLI",
                platform="Microsoft Azure",
                purpose_en="Manages Azure subscription information and active tenant context.",
                purpose_hi="Azure CLI mein active subscription aur logged-in tenant account view aur switch karne ke liye use hota hai.",
                syntax="az account {show | list | set}",
                common_options={
                    "show": "Shows active subscription details.",
                    "list -o table": "Lists all subscriptions available to user.",
                    "set --subscription <name/id>": "Sets the active subscription."
                },
                safe_examples=["az account show", "az account list -o table"],
                risk_level=CommandRiskLevel.SAFE_READ_ONLY,
                related_concepts=["azure", "subscriptions", "cloud"]
            )
        )
