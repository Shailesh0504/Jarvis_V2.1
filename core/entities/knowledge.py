# core/entities/knowledge.py
"""
Central Entity Knowledge Base for Jarvis V2.1.
Maintains canonical knowledge of applications, browsers, websites, system tools,
folders, and media utilities, with alias mapping and multi-word span extraction.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class EntityDefinition:
    """Canonical representation of a known system entity."""
    entity_id: str
    canonical_name: str
    display_name: str
    entity_type: str  # "application", "browser", "website", "folder", "media", "system_tool"
    aliases: List[str] = field(default_factory=list)
    executables: List[str] = field(default_factory=list)
    url: Optional[str] = None
    preferred_browser: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Default entity knowledge registry
_DEFAULT_ENTITIES: List[EntityDefinition] = [
    # 1. Applications & Office Suite
    EntityDefinition(
        entity_id="excel",
        canonical_name="Microsoft Excel",
        display_name="Excel",
        entity_type="application",
        aliases=["excel", "ms excel", "microsoft excel", "msexcel", "excel sheet", "workbook"],
        executables=["excel.exe"],
    ),
    EntityDefinition(
        entity_id="word",
        canonical_name="Microsoft Word",
        display_name="Word",
        entity_type="application",
        aliases=["word", "ms word", "microsoft word", "msword", "winword"],
        executables=["winword.exe"],
    ),
    EntityDefinition(
        entity_id="powerpoint",
        canonical_name="Microsoft PowerPoint",
        display_name="PowerPoint",
        entity_type="application",
        aliases=["powerpoint", "power point", "ppt", "ms ppt", "microsoft powerpoint", "ms powerpoint", "powerpnt"],
        executables=["powerpnt.exe"],
    ),
    EntityDefinition(
        entity_id="access",
        canonical_name="Microsoft Access",
        display_name="Access",
        entity_type="application",
        aliases=["access", "ms access", "microsoft access", "msaccess"],
        executables=["msaccess.exe"],
    ),
    EntityDefinition(
        entity_id="publisher",
        canonical_name="Microsoft Publisher",
        display_name="Publisher",
        entity_type="application",
        aliases=["publisher", "ms publisher", "microsoft publisher", "mspub"],
        executables=["mspub.exe"],
    ),
    EntityDefinition(
        entity_id="outlook",
        canonical_name="Microsoft Outlook",
        display_name="Outlook",
        entity_type="application",
        aliases=["outlook", "ms outlook", "microsoft outlook"],
        executables=["outlook.exe"],
    ),
    EntityDefinition(
        entity_id="onenote",
        canonical_name="Microsoft OneNote",
        display_name="OneNote",
        entity_type="application",
        aliases=["onenote", "ms onenote", "microsoft onenote"],
        executables=["onenote.exe"],
    ),

    # 2. Web Browsers (both an application and a browser container)
    EntityDefinition(
        entity_id="chrome",
        canonical_name="Google Chrome",
        display_name="Chrome",
        entity_type="browser",
        aliases=["chrome", "google chrome", "chrome browser", "chrom", "crome", "chorme"],
        executables=["chrome.exe"],
    ),
    EntityDefinition(
        entity_id="brave",
        canonical_name="Brave Browser",
        display_name="Brave",
        entity_type="browser",
        aliases=["brave", "brave browser"],
        executables=["brave.exe"],
    ),
    EntityDefinition(
        entity_id="edge",
        canonical_name="Microsoft Edge",
        display_name="Edge",
        entity_type="browser",
        aliases=["edge", "ms edge", "microsoft edge", "msedge"],
        executables=["msedge.exe"],
    ),
    EntityDefinition(
        entity_id="firefox",
        canonical_name="Mozilla Firefox",
        display_name="Firefox",
        entity_type="browser",
        aliases=["firefox", "mozilla firefox", "firefox browser"],
        executables=["firefox.exe"],
    ),
    EntityDefinition(
        entity_id="opera",
        canonical_name="Opera Browser",
        display_name="Opera",
        entity_type="browser",
        aliases=["opera", "opera browser"],
        executables=["opera.exe"],
    ),

    # 3. Developer Tools
    EntityDefinition(
        entity_id="code",
        canonical_name="Visual Studio Code",
        display_name="VS Code",
        entity_type="application",
        aliases=["vs code", "vscode", "code", "visual studio code"],
        executables=["code.exe"],
    ),
    EntityDefinition(
        entity_id="antigravity",
        canonical_name="Antigravity IDE",
        display_name="Antigravity",
        entity_type="application",
        aliases=["antigravity", "anti gravity", "antigravity ide", "antigravity app", "agy"],
        executables=["antigravity.exe"],
    ),
    EntityDefinition(
        entity_id="terminal",
        canonical_name="Windows Terminal",
        display_name="Terminal",
        entity_type="system_tool",
        aliases=["terminal", "windows terminal", "wt"],
        executables=["wt.exe"],
    ),
    EntityDefinition(
        entity_id="cmd",
        canonical_name="Command Prompt",
        display_name="Command Prompt",
        entity_type="system_tool",
        aliases=["cmd", "command prompt"],
        executables=["cmd.exe"],
    ),
    EntityDefinition(
        entity_id="powershell",
        canonical_name="PowerShell",
        display_name="PowerShell",
        entity_type="system_tool",
        aliases=["powershell", "power shell", "pwsh"],
        executables=["powershell.exe"],
    ),

    # 4. System Tools & Utilities
    EntityDefinition(
        entity_id="camera",
        canonical_name="Windows Camera",
        display_name="Camera",
        entity_type="system_tool",
        aliases=["camera", "kamera", "webcam", "web cam", "cam", "windows camera", "camera app"],
        executables=["WindowsCamera.exe"],
    ),
    EntityDefinition(
        entity_id="calc",
        canonical_name="Windows Calculator",
        display_name="Calculator",
        entity_type="system_tool",
        aliases=["calculator", "calc", "calci", "hisab kitab", "calculator app"],
        executables=["calc.exe", "CalculatorApp.exe"],
    ),
    EntityDefinition(
        entity_id="notepad",
        canonical_name="Notepad",
        display_name="Notepad",
        entity_type="application",
        aliases=["notepad", "note pad", "text editor", "notepad app"],
        executables=["notepad.exe"],
    ),
    EntityDefinition(
        entity_id="paint",
        canonical_name="Paint",
        display_name="Paint",
        entity_type="application",
        aliases=["paint", "mspaint", "ms paint", "paint 3d", "paint app"],
        executables=["mspaint.exe"],
    ),
    EntityDefinition(
        entity_id="taskmgr",
        canonical_name="Task Manager",
        display_name="Task Manager",
        entity_type="system_tool",
        aliases=["task manager", "taskmgr", "task manager app", "task monitor", "processes"],
        executables=["taskmgr.exe"],
    ),
    EntityDefinition(
        entity_id="control_panel",
        canonical_name="Control Panel",
        display_name="Control Panel",
        entity_type="system_tool",
        aliases=["control panel", "control panel app"],
        executables=["control.exe"],
    ),
    EntityDefinition(
        entity_id="settings",
        canonical_name="Windows Settings",
        display_name="Settings",
        entity_type="system_tool",
        aliases=["settings", "setting", "windows settings", "system settings", "pc settings"],
        executables=["SystemSettings.exe"],
    ),
    EntityDefinition(
        entity_id="snipping_tool",
        canonical_name="Snipping Tool",
        display_name="Snipping Tool",
        entity_type="system_tool",
        aliases=["snipping tool", "snippingtool", "snip", "snip and sketch", "screen clip"],
        executables=["SnippingTool.exe"],
    ),
    EntityDefinition(
        entity_id="explorer",
        canonical_name="File Explorer",
        display_name="File Explorer",
        entity_type="system_tool",
        aliases=["file explorer", "windows explorer", "my computer", "this pc", "file manager"],
        executables=["explorer.exe"],
    ),
    EntityDefinition(
        entity_id="temp_files",
        canonical_name="Temporary Files",
        display_name="Temp Files",
        entity_type="system_tool",
        aliases=["temp files", "temporary files", "temp", "temp data", "temp folder", "temporary junk", "temporary data"],
    ),
    EntityDefinition(
        entity_id="recycle_bin",
        canonical_name="Recycle Bin",
        display_name="Recycle Bin",
        entity_type="system_tool",
        aliases=["recycle bin", "recyclebin", "trash can", "trash", "dustbin"],
    ),

    # 5. Media Applications
    EntityDefinition(
        entity_id="vlc",
        canonical_name="VLC Media Player",
        display_name="VLC",
        entity_type="media",
        aliases=["vlc", "vlc player", "vlc media player"],
        executables=["vlc.exe"],
    ),
    EntityDefinition(
        entity_id="spotify",
        canonical_name="Spotify",
        display_name="Spotify",
        entity_type="media",
        aliases=["spotify", "spotify music"],
        executables=["spotify.exe"],
        url="https://open.spotify.com",
    ),

    # 6. Popular Websites & Web Services
    EntityDefinition(
        entity_id="youtube",
        canonical_name="YouTube",
        display_name="YouTube",
        entity_type="website",
        aliases=["youtube", "youtub", "utube", "yt"],
        url="https://www.youtube.com",
    ),
    EntityDefinition(
        entity_id="gmail",
        canonical_name="Gmail",
        display_name="Gmail",
        entity_type="website",
        aliases=["gmail", "google mail"],
        url="https://mail.google.com",
    ),
    EntityDefinition(
        entity_id="google",
        canonical_name="Google",
        display_name="Google",
        entity_type="website",
        aliases=["google", "google search"],
        url="https://www.google.com",
    ),
    EntityDefinition(
        entity_id="github",
        canonical_name="GitHub",
        display_name="GitHub",
        entity_type="website",
        aliases=["github", "git hub"],
        url="https://github.com",
    ),
    EntityDefinition(
        entity_id="chatgpt",
        canonical_name="ChatGPT",
        display_name="ChatGPT",
        entity_type="website",
        aliases=["chatgpt", "chat gpt", "openai"],
        url="https://chatgpt.com",
    ),
    EntityDefinition(
        entity_id="flipkart",
        canonical_name="Flipkart",
        display_name="Flipkart",
        entity_type="website",
        aliases=["flipkart"],
        url="https://www.flipkart.com",
    ),
    EntityDefinition(
        entity_id="amazon",
        canonical_name="Amazon",
        display_name="Amazon",
        entity_type="website",
        aliases=["amazon"],
        url="https://www.amazon.in",
    ),
    EntityDefinition(
        entity_id="reddit",
        canonical_name="Reddit",
        display_name="Reddit",
        entity_type="website",
        aliases=["reddit"],
        url="https://www.reddit.com",
    ),
    EntityDefinition(
        entity_id="linkedin",
        canonical_name="LinkedIn",
        display_name="LinkedIn",
        entity_type="website",
        aliases=["linkedin", "linked in"],
        url="https://www.linkedin.com",
    ),
    EntityDefinition(
        entity_id="twitter",
        canonical_name="Twitter",
        display_name="Twitter",
        entity_type="website",
        aliases=["twitter", "x.com"],
        url="https://twitter.com",
    ),
    EntityDefinition(
        entity_id="netflix",
        canonical_name="Netflix",
        display_name="Netflix",
        entity_type="website",
        aliases=["netflix"],
        url="https://www.netflix.com",
    ),
    EntityDefinition(
        entity_id="whatsapp",
        canonical_name="WhatsApp",
        display_name="WhatsApp",
        entity_type="application",
        aliases=["whatsapp", "whats app"],
        executables=["WhatsApp.exe"],
        url="https://web.whatsapp.com",
    ),
]


class EntityKnowledgeBase:
    """
    Central repository of known applications, browsers, websites, and system tools.
    Provides indexed alias resolution and greedily extracts non-overlapping entity spans.
    """

    _instance: Optional["EntityKnowledgeBase"] = None

    def __init__(self) -> None:
        self._entities: Dict[str, EntityDefinition] = {}
        self._alias_to_entity: Dict[str, EntityDefinition] = {}
        self._compiled_regexes: List[Tuple[re.Pattern, str, EntityDefinition]] = []
        self._load_defaults()
        self._load_from_app_registry()

    @classmethod
    def get_instance(cls) -> "EntityKnowledgeBase":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_entity(self, entity: EntityDefinition) -> None:
        """Registers an entity and indexes its aliases."""
        self._entities[entity.entity_id.lower()] = entity
        for alias in entity.aliases:
            clean_alias = self._normalize_alias(alias)
            if clean_alias:
                self._alias_to_entity[clean_alias] = entity
        self._rebuild_compiled_regexes()

    def get_entity(self, entity_id: str) -> Optional[EntityDefinition]:
        """Retrieves entity by canonical ID."""
        return self._entities.get(entity_id.lower().strip())

    def find_by_alias(self, query: str) -> Optional[EntityDefinition]:
        """Resolves an alias string to an EntityDefinition."""
        clean = self._normalize_alias(query)
        if clean in self._alias_to_entity:
            return self._alias_to_entity[clean]
        return None

    def extract_entities_from_text(self, text: str) -> List[Tuple[EntityDefinition, int, int]]:
        """
        Extracts all non-overlapping entity mentions from text.
        Returns a list of tuples: (EntityDefinition, start_index, end_index)
        sorted by their appearance in the text.
        """
        clean_text = text.lower()
        found_matches: List[Tuple[int, int, EntityDefinition]] = []

        # Find all occurrences of each compiled alias regex
        for pattern, alias_text, entity in self._compiled_regexes:
            for match in pattern.finditer(clean_text):
                start, end = match.span()
                found_matches.append((start, end, entity))

        if not found_matches:
            return []

        # Sort matches by start position ascending, and longer spans first for ties
        found_matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))

        # Resolve overlaps greedily (keep earlier/longer match)
        non_overlapping: List[Tuple[EntityDefinition, int, int]] = []
        occupied_indices: Set[int] = set()

        for start, end, entity in found_matches:
            span_indices = set(range(start, end))
            if not (span_indices & occupied_indices):
                non_overlapping.append((entity, start, end))
                occupied_indices.update(span_indices)

        # Sort strictly by appearance index
        non_overlapping.sort(key=lambda item: item[1])
        return non_overlapping

    @staticmethod
    def _normalize_alias(text: str) -> str:
        """Standardizes alias strings for indexing."""
        if not text:
            return ""
        s = text.lower().strip()
        s = re.sub(r'[^\w\s.-]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _load_defaults(self) -> None:
        """Loads default entities."""
        for ent in _DEFAULT_ENTITIES:
            self._entities[ent.entity_id.lower()] = ent
            for alias in ent.aliases:
                clean_alias = self._normalize_alias(alias)
                if clean_alias:
                    self._alias_to_entity[clean_alias] = ent

    def _load_from_app_registry(self) -> None:
        """Syncs additional aliases from existing APPLICATION_ALIASES and WEBSITE_ALIASES."""
        try:
            from core.apps.aliases import APPLICATION_ALIASES, WEBSITE_ALIASES
            for alias, app_id in APPLICATION_ALIASES.items():
                clean_alias = self._normalize_alias(alias)
                if clean_alias and clean_alias not in self._alias_to_entity:
                    entity = self._entities.get(app_id.lower())
                    if entity:
                        self._alias_to_entity[clean_alias] = entity

            for alias, url in WEBSITE_ALIASES.items():
                clean_alias = self._normalize_alias(alias)
                if clean_alias and clean_alias not in self._alias_to_entity:
                    # Check if already a website entity
                    if alias.lower() in self._entities:
                        self._alias_to_entity[clean_alias] = self._entities[alias.lower()]
                    else:
                        ent = EntityDefinition(
                            entity_id=clean_alias,
                            canonical_name=clean_alias.capitalize(),
                            display_name=clean_alias.capitalize(),
                            entity_type="website",
                            aliases=[clean_alias],
                            url=url
                        )
                        self.register_entity(ent)

            from core.windows_app_resolver import get_windows_app_resolver
            win_resolver = get_windows_app_resolver()
            for app_id, win_spec in win_resolver._apps.items():
                if app_id not in self._entities:
                    ent = EntityDefinition(
                        entity_id=win_spec.canonical_id,
                        canonical_name=win_spec.display_name,
                        display_name=win_spec.display_name,
                        entity_type="system_tool" if win_spec.is_system_app else "application",
                        aliases=win_spec.aliases,
                        executables=win_spec.executables,
                    )
                    self._entities[app_id] = ent
                else:
                    existing = self._entities[app_id]
                    for al in win_spec.aliases:
                        if al not in existing.aliases:
                            existing.aliases.append(al)

                for al in win_spec.aliases:
                    clean_al = self._normalize_alias(al)
                    if clean_al and clean_al not in self._alias_to_entity:
                        self._alias_to_entity[clean_al] = self._entities[app_id]
        except Exception:
            pass

        self._rebuild_compiled_regexes()

    def _rebuild_compiled_regexes(self) -> None:
        """Precompiles word-boundary regex patterns sorted by alias length descending."""
        sorted_aliases = sorted(self._alias_to_entity.keys(), key=lambda a: len(a), reverse=True)
        compiled: List[Tuple[re.Pattern, str, EntityDefinition]] = []
        for alias in sorted_aliases:
            if not alias.strip():
                continue
            entity = self._alias_to_entity[alias]
            escaped = re.escape(alias)
            # Use boundary matching so 'word' matches 'word' but not 'sword'
            pattern = re.compile(rf'(?:\b|_){escaped}(?:\b|_)', re.IGNORECASE)
            compiled.append((pattern, alias, entity))
        self._compiled_regexes = compiled


def get_entity_knowledge_base() -> EntityKnowledgeBase:
    """Helper to access global EntityKnowledgeBase instance."""
    return EntityKnowledgeBase.get_instance()
