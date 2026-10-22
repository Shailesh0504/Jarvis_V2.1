# core/capabilities.py
"""
Authoritative Single Source of Truth (SSOT) Capability Registry for Jarvis V2.1.
Enforces Rule 1.1 Invariant: catalogs what Jarvis can actually do, maps goals to capabilities,
and prevents hallucinating unsupported capabilities.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.capabilities")


@dataclass
class CapabilityDescriptor:
    """Descriptor defining an authoritative capability in Jarvis."""
    capability_id: str
    name: str
    intents: List[str]
    goals: List[str]
    entities: List[str]
    actions: List[str]
    risk: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    service: str = "system"
    action_name: str = ""
    description: str = ""
    is_available: bool = True
    parameters_schema: Dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    """
    Central Capability Registry indexing all system, application, browser,
    media, and maintenance capabilities across Jarvis.
    """

    _REGISTRY: Dict[str, CapabilityDescriptor] = {}
    _GOAL_INDEX: Dict[str, List[str]] = {}
    _INTENT_INDEX: Dict[str, List[str]] = {}

    # Known unsupported/dangerous operations that must NEVER be hallucinated or executed
    UNSUPPORTED_PATTERNS = [
        re.compile(r"\b(?:registry\s+(?:optimize|clean|fix|repair|edit)|optimize\s+(?:the\s+)?registry)\b", re.IGNORECASE),
        re.compile(r"\b(?:windows\s+)?(?:ka\s+)?(?:pura\s+)?registry\s+(?:optimize|clean|repair)\b", re.IGNORECASE),
        re.compile(r"\b(?:hack|crack)\s+(?:wifi|password|account|system|fbi|neighbor)\b", re.IGNORECASE),
        re.compile(r"\b(?:overclock|underclock)\b(?:\s+(?:the|my|system|pc|computer))?\s*(?:cpu|gpu|ram|processor)\b", re.IGNORECASE),
        re.compile(r"\b(?:compile|build)\s+(?:linux|kernel|operating\s+system)\b", re.IGNORECASE),
        re.compile(r"\b(?:format|erase)\s+(?:c\s*:|c\s+drive|hard\s*drive|disk)\b", re.IGNORECASE),
        re.compile(r"\b(?:flash|update)\s+(?:bios|uefi)\b", re.IGNORECASE),
    ]

    UNSUPPORTED_RESPONSE = "Ye exact operation abhi meri available capabilities mein nahi hai."

    @classmethod
    def register(cls, cap: CapabilityDescriptor) -> None:
        """Registers a capability descriptor into the central registry."""
        cls._REGISTRY[cap.capability_id] = cap
        for g in cap.goals:
            cls._GOAL_INDEX.setdefault(g.upper(), []).append(cap.capability_id)
        for i in cap.intents:
            cls._INTENT_INDEX.setdefault(i.upper(), []).append(cap.capability_id)

    @classmethod
    def get_capability(cls, capability_id: str) -> Optional[CapabilityDescriptor]:
        """Retrieves a capability by its unique ID."""
        cls._ensure_initialized()
        return cls._REGISTRY.get(capability_id)

    @classmethod
    def find_capabilities_by_goal(cls, goal: str) -> List[CapabilityDescriptor]:
        """Finds all capabilities satisfying a canonical goal."""
        cls._ensure_initialized()
        cap_ids = cls._GOAL_INDEX.get(goal.upper(), [])
        return [cls._REGISTRY[cid] for cid in cap_ids if cid in cls._REGISTRY]

    @classmethod
    def find_capabilities_by_intent(cls, intent: str) -> List[CapabilityDescriptor]:
        """Finds all capabilities satisfying a canonical intent."""
        cls._ensure_initialized()
        cap_ids = cls._INTENT_INDEX.get(intent.upper(), [])
        return [cls._REGISTRY[cid] for cid in cap_ids if cid in cls._REGISTRY]

    @classmethod
    def is_available(cls, capability_id: str) -> bool:
        """Checks if a capability exists and is currently available."""
        cls._ensure_initialized()
        cap = cls._REGISTRY.get(capability_id)
        return bool(cap and cap.is_available)

    @classmethod
    def is_unsupported_operation(cls, raw_text: str, goal: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Detects if an utterance requests an unsupported/dangerous capability.
        Returns: (is_unsupported, refusal_prompt)
        """
        raw = raw_text.strip()
        for pat in cls.UNSUPPORTED_PATTERNS:
            if pat.search(raw):
                return True, cls.UNSUPPORTED_RESPONSE

        if goal and goal.upper() in {"REGISTRY_OPTIMIZATION", "HACK_WIFI", "OVERCLOCK_SYSTEM", "FORMAT_SYSTEM"}:
            return True, cls.UNSUPPORTED_RESPONSE

        return False, None

    @classmethod
    def list_all(cls) -> List[CapabilityDescriptor]:
        """Returns all registered capabilities."""
        cls._ensure_initialized()
        return list(cls._REGISTRY.values())

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Lazy initialization of core capabilities index."""
        if cls._REGISTRY:
            return

        # 1. System Maintenance
        cls.register(CapabilityDescriptor(
            capability_id="system.maintenance.temp_cleanup",
            name="Temporary Files Cleanup",
            intents=["TEMP_FILE_CLEANUP", "SYSTEM_MAINTENANCE"],
            goals=["TEMP_FILE_CLEANUP", "SYSTEM_CLEANUP"],
            entities=["temp_files", "temporary_files", "temp", "temp_data", "temp_folder", "junk"],
            actions=["clean", "clear", "delete", "remove", "saaf", "hatao"],
            risk="LOW",
            service="system",
            action_name="clear_temp_files",
            description="Cleans Windows temporary files from %TEMP% and system Temp directories.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="system.maintenance.recycle_bin",
            name="Recycle Bin Cleanup",
            intents=["RECYCLE_BIN_CLEANUP", "SYSTEM_MAINTENANCE"],
            goals=["RECYCLE_BIN_CLEANUP", "SYSTEM_CLEANUP"],
            entities=["recycle_bin", "trash", "dustbin", "kachra"],
            actions=["empty", "clear", "clean", "khali", "saaf"],
            risk="LOW",
            service="system",
            action_name="empty_recycle_bin",
            description="Empties the Windows Recycle Bin.",
        ))

        # 2. System Power & Session
        cls.register(CapabilityDescriptor(
            capability_id="system.power.lock",
            name="Lock System",
            intents=["LOCK_SYSTEM"],
            goals=["LOCK_SYSTEM"],
            entities=["system", "pc", "computer", "screen"],
            actions=["lock"],
            risk="LOW",
            service="system",
            action_name="lock_pc",
            description="Locks the Windows workstation.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="system.power.restart",
            name="Restart System",
            intents=["SYSTEM_RESTART"],
            goals=["SYSTEM_RESTART"],
            entities=["system", "pc", "computer"],
            actions=["restart", "reboot"],
            risk="HIGH",
            service="system",
            action_name="restart_pc",
            description="Restarts the computer.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="system.power.shutdown",
            name="Shutdown System",
            intents=["SYSTEM_SHUTDOWN"],
            goals=["SYSTEM_SHUTDOWN"],
            entities=["system", "pc", "computer"],
            actions=["shutdown", "turn_off", "band"],
            risk="HIGH",
            service="system",
            action_name="shutdown_pc",
            description="Powers down the computer.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="system.power.sleep",
            name="Sleep System",
            intents=["SLEEP_SYSTEM"],
            goals=["SLEEP_SYSTEM"],
            entities=["system", "pc", "computer"],
            actions=["sleep"],
            risk="LOW",
            service="system",
            action_name="sleep_pc",
            description="Puts the system to sleep.",
        ))

        # 3. Audio Volume Control
        cls.register(CapabilityDescriptor(
            capability_id="audio.volume.set",
            name="Set Volume",
            intents=["SET_VOLUME"],
            goals=["SET_VOLUME"],
            entities=["volume", "sound", "awaaz", "audio"],
            actions=["set", "adjust"],
            risk="LOW",
            service="audio",
            action_name="set_volume",
            description="Sets audio volume to a specific percentage.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="audio.volume.up",
            name="Increase Volume",
            intents=["VOLUME_UP"],
            goals=["VOLUME_UP", "ADJUST_VOLUME"],
            entities=["volume", "sound", "awaaz", "audio"],
            actions=["up", "increase", "badhao", "tez"],
            risk="LOW",
            service="audio",
            action_name="volume_up",
            description="Increases audio volume.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="audio.volume.down",
            name="Decrease Volume",
            intents=["VOLUME_DOWN"],
            goals=["VOLUME_DOWN", "ADJUST_VOLUME"],
            entities=["volume", "sound", "awaaz", "audio"],
            actions=["down", "decrease", "kam", "dheere"],
            risk="LOW",
            service="audio",
            action_name="volume_down",
            description="Decreases audio volume.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="audio.volume.mute",
            name="Mute Audio",
            intents=["MUTE"],
            goals=["MUTE"],
            entities=["volume", "sound", "audio"],
            actions=["mute"],
            risk="LOW",
            service="audio",
            action_name="mute",
            description="Mutes system audio.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="audio.volume.unmute",
            name="Unmute Audio",
            intents=["UNMUTE"],
            goals=["UNMUTE"],
            entities=["volume", "sound", "audio"],
            actions=["unmute"],
            risk="LOW",
            service="audio",
            action_name="unmute",
            description="Unmutes system audio.",
        ))

        # 4. Windows Applications & Window Management
        cls.register(CapabilityDescriptor(
            capability_id="windows.application.launch",
            name="Launch Application",
            intents=["OPEN_APPLICATION", "OPEN_APP"],
            goals=["OPEN_APPLICATION"],
            entities=["application", "app", "software", "program"],
            actions=["open", "launch", "start", "kholo", "chalao"],
            risk="LOW",
            service="windows",
            action_name="launch_app",
            description="Launches a desktop application or service.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="windows.application.close",
            name="Close Application",
            intents=["CLOSE_APPLICATION"],
            goals=["CLOSE_APPLICATION"],
            entities=["application", "app", "window"],
            actions=["close", "band", "exit", "terminate", "kill"],
            risk="MEDIUM",
            service="windows",
            action_name="close_app",
            description="Closes an application or active window.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="windows.window.minimize",
            name="Minimize Window",
            intents=["MINIMIZE_WINDOW"],
            goals=["MINIMIZE_WINDOW"],
            entities=["window", "app"],
            actions=["minimize", "chhota"],
            risk="LOW",
            service="windows",
            action_name="minimize_window",
            description="Minimizes a window.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="windows.window.maximize",
            name="Maximize Window",
            intents=["MAXIMIZE_WINDOW"],
            goals=["MAXIMIZE_WINDOW"],
            entities=["window", "app"],
            actions=["maximize", "bada"],
            risk="LOW",
            service="windows",
            action_name="maximize_window",
            description="Maximizes a window.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="windows.folder.open",
            name="Open Folder",
            intents=["FOLDER_OPEN"],
            goals=["FOLDER_OPEN"],
            entities=["folder", "directory"],
            actions=["open", "kholo"],
            risk="LOW",
            service="windows",
            action_name="open_folder",
            description="Opens a folder in File Explorer.",
        ))

        # 5. Browser & Web Search
        cls.register(CapabilityDescriptor(
            capability_id="browser.website.open",
            name="Open Website",
            intents=["OPEN_WEBSITE"],
            goals=["OPEN_WEBSITE"],
            entities=["website", "site", "url", "webpage"],
            actions=["open", "browse", "kholo", "visit"],
            risk="LOW",
            service="browser",
            action_name="open_website",
            description="Opens a website in the default or active browser.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="browser.web_search",
            name="Search Web",
            intents=["SEARCH_WEB"],
            goals=["SEARCH_WEB"],
            entities=["query", "search_term", "web"],
            actions=["search", "dhoondo", "find", "look_up"],
            risk="LOW",
            service="browser",
            action_name="search_web",
            description="Performs a web search via default search engine.",
        ))

        # 6. Media Playback
        cls.register(CapabilityDescriptor(
            capability_id="media.youtube.play",
            name="Play Media on YouTube",
            intents=["PLAY_MEDIA"],
            goals=["PLAY_MEDIA"],
            entities=["youtube", "song", "video", "gaana", "music", "track"],
            actions=["play", "chalao", "bajao", "laga", "sunao"],
            risk="LOW",
            service="youtube",
            action_name="search_and_play",
            description="Plays a song or video on YouTube.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="media.playback.control",
            name="Media Playback Controls",
            intents=["MEDIA_PLAYBACK", "YOUTUBE_CONTROL"],
            goals=["MEDIA_CONTROL"],
            entities=["media", "video", "player"],
            actions=["pause", "resume", "play", "stop", "seek", "forward", "rewind"],
            risk="LOW",
            service="youtube",
            action_name="control_playback",
            description="Controls media playback (play, pause, seek).",
        ))

        # 7. Screen Operations
        cls.register(CapabilityDescriptor(
            capability_id="screen.screenshot",
            name="Take Screenshot",
            intents=["TAKE_SCREENSHOT"],
            goals=["TAKE_SCREENSHOT"],
            entities=["screen", "screenshot", "screen_capture"],
            actions=["take", "capture", "lo", "kheecho"],
            risk="LOW",
            service="screen",
            action_name="take_screenshot",
            description="Captures a full-screen screenshot.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="screen.record",
            name="Screen Recording",
            intents=["SCREEN_RECORD"],
            goals=["SCREEN_RECORD"],
            entities=["screen", "recording"],
            actions=["record", "start", "stop"],
            risk="LOW",
            service="screen",
            action_name="record_screen",
            description="Starts or stops screen video recording.",
        ))

        # 8. Security & Face Auth
        cls.register(CapabilityDescriptor(
            capability_id="security.password.generate",
            name="Generate Password",
            intents=["GENERATE_PASSWORD"],
            goals=["GENERATE_PASSWORD"],
            entities=["password", "passcode"],
            actions=["generate", "create", "banao"],
            risk="LOW",
            service="security",
            action_name="generate_password",
            description="Generates a cryptographically secure random password.",
        ))

        # 9. System Information & Time
        cls.register(CapabilityDescriptor(
            capability_id="system.time.query",
            name="Query Time and Date",
            intents=["TIME_QUERY"],
            goals=["TIME_QUERY"],
            entities=["time", "date", "clock", "tarikh", "samay", "din"],
            actions=["query", "tell", "batao", "bata"],
            risk="LOW",
            service="system",
            action_name="get_time",
            description="Queries current local time, date, and weekday.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="system.status.query",
            name="Query System Status",
            intents=["STATUS_QUERY"],
            goals=["QUERY_STATUS", "STATUS_QUERY"],
            entities=["system", "pc", "computer", "status"],
            actions=["query", "check", "batao"],
            risk="LOW",
            service="system",
            action_name="get_status",
            description="Queries current system, application, and background task status.",
        ))

        # 10. Weather & Forecast
        cls.register(CapabilityDescriptor(
            capability_id="weather.forecast.query",
            name="Query Weather and Forecast",
            intents=["WEATHER_QUERY", "FORECAST_QUERY"],
            goals=["WEATHER_CHECK", "WEATHER_QUERY"],
            entities=["weather", "mausam", "temperature", "forecast", "rain", "barish"],
            actions=["query", "check", "batao"],
            risk="LOW",
            service="weather",
            action_name="get_weather",
            description="Queries real-time and hourly weather forecasts for any city.",
        ))

        # 11. IT & Infrastructure Knowledge & Troubleshooting
        cls.register(CapabilityDescriptor(
            capability_id="it.infrastructure.troubleshoot",
            name="IT Troubleshooting and Diagnostic Guidance",
            intents=["IT_TROUBLESHOOTING", "TECH_SUPPORT"],
            goals=["IT_TROUBLESHOOTING", "NETWORK_DIAGNOSTICS"],
            entities=["rdp", "dns", "active_directory", "firewall", "port", "azure", "vm"],
            actions=["troubleshoot", "diagnose", "check", "fix"],
            risk="LOW",
            service="it_knowledge",
            action_name="troubleshoot_topic",
            description="Provides 6-phase structured IT systems administrator diagnostic checklists.",
        ))

        # 12. Office & Excel Automation
        cls.register(CapabilityDescriptor(
            capability_id="office.excel.operations",
            name="Excel Formulas and Spreadsheet Operations",
            intents=["EXCEL_OPERATIONS", "EXCEL_FORMULA"],
            goals=["EXCEL_DUPLICATE_REMOVAL", "EXCEL_FORMULA_GUIDE"],
            entities=["excel", "spreadsheet", "workbook", "duplicate", "formula", "vlookup"],
            actions=["open", "remove_duplicates", "calculate", "format"],
            risk="LOW",
            service="excel",
            action_name="excel_operation",
            description="Assists with Excel formulas, duplicate removal, and spreadsheet automation.",
        ))

        # 13. Network & System Configuration
        cls.register(CapabilityDescriptor(
            capability_id="system.network.configuration",
            name="Network and DNS Configuration",
            intents=["NETWORK_CONFIG", "DNS_SETUP"],
            goals=["DNS_EXPLANATION_OR_SETUP", "NETWORK_CONFIG"],
            entities=["dns", "ip", "network", "adapter", "ping"],
            actions=["setup", "configure", "flush", "check"],
            risk="LOW",
            service="system",
            action_name="network_setup",
            description="Provides practical configuration guides and safe diagnostic commands for DNS and networking.",
        ))

        # 14. System Backup Management
        cls.register(CapabilityDescriptor(
            capability_id="system.backup.management",
            name="Backup Planning and Management",
            intents=["BACKUP_MANAGEMENT", "FILE_BACKUP"],
            goals=["BACKUP_PLANNING", "FILE_BACKUP"],
            entities=["backup", "files", "data", "restore"],
            actions=["plan", "setup", "configure"],
            risk="LOW",
            service="system",
            action_name="backup_planning",
            description="Guides automated file history and cloud backup configuration.",
        ))

        # 15. Software & System Updates
        cls.register(CapabilityDescriptor(
            capability_id="software.update.winget",
            name="WinGet Application Updates",
            intents=["SOFTWARE_UPDATE_ALL", "UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES"],
            goals=["UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES", "EXECUTE_UPDATE_PLAN"],
            entities=["software", "apps", "applications", "programs"],
            actions=["update", "upgrade", "check", "install"],
            risk="MEDIUM",
            service="software_update",
            action_name="install_updates",
            description="Manages third-party application upgrades via Windows Package Manager (winget).",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="software.update.windows",
            name="Windows OS Updates",
            intents=["WINDOWS_UPDATE", "UPDATE_WINDOWS", "CHECK_FOR_UPDATES"],
            goals=["UPDATE_WINDOWS", "CHECK_FOR_UPDATES", "EXECUTE_UPDATE_PLAN"],
            entities=["windows", "os", "system", "patches"],
            actions=["update", "upgrade", "check", "install"],
            risk="HIGH",
            service="software_update",
            action_name="windows_update",
            description="Manages Windows operating system patches, service checks, and reboot pending states.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="software.update.microsoft_store",
            name="Microsoft Store Application Updates",
            intents=["STORE_UPDATE", "UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES"],
            goals=["UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES"],
            entities=["store", "microsoft_store", "uwp"],
            actions=["update", "check"],
            risk="MEDIUM",
            service="software_update",
            action_name="check_updates",
            description="Inspects and manages Microsoft Store UWP applications.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="software.update.unknown",
            name="Unmanaged / Unknown Software Detection",
            intents=["UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES"],
            goals=["UPDATE_INSTALLED_SOFTWARE", "CHECK_FOR_UPDATES"],
            entities=["unknown", "unmanaged", "pinned"],
            actions=["inspect", "skip"],
            risk="LOW",
            service="software_update",
            action_name="check_updates",
            description="Identifies applications not resolvable via managed package repositories.",
        ))
        cls.register(CapabilityDescriptor(
            capability_id="software.update.report",
            name="Software Update Reporting",
            intents=["SOFTWARE_UPDATE_REPORT", "STATUS_QUERY"],
            goals=["QUERY_STATUS", "STATUS_QUERY"],
            entities=["report", "status", "history"],
            actions=["query", "report", "show"],
            risk="LOW",
            service="software_update",
            action_name="get_status",
            description="Generates truthful source-separated software and OS update reports.",
        ))

        # 24. Indian Equity Research & Decision Support (1-Month Horizon)
        cls.register(CapabilityDescriptor(
            capability_id="finance.equity_research",
            name="Indian Equity 1-Month Research & Decision Support",
            intents=["EQUITY_RESEARCH", "STOCK_ANALYSIS", "MARKET_REGIME", "MONITOR_STOCK"],
            goals=["SHORT_TERM_INVESTMENT_RESEARCH", "SINGLE_STOCK_ANALYSIS", "MARKET_REGIME_ANALYSIS", "MONITOR_THESIS"],
            entities=["stock", "share", "equity", "nifty", "indian_stock", "portfolio"],
            actions=["analyze", "research", "suggest", "scan", "evaluate", "monitor"],
            risk="LOW",
            service="equity_research",
            action_name="research_shortlist",
            description="Professional 1-month horizon Indian equity decision support, regime analysis, and multi-factor research.",
        ))


def get_capability_registry() -> type[CapabilityRegistry]:
    """Retrieves the authoritative CapabilityRegistry singleton class."""
    CapabilityRegistry._ensure_initialized()
    return CapabilityRegistry
