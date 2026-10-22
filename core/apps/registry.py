# core/apps/registry.py
"""Normalized application alias registry and query normalization for Jarvis V2."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.apps.aliases import APPLICATION_ALIASES


@dataclass
class AppDefinition:
    """Represents a canonical local application and its launch metadata."""
    app_id: str
    display_name: str
    executables: List[str] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    is_office: bool = False
    new_instance_arg: Optional[str] = None
    window_titles: List[str] = field(default_factory=list)


# Precompiled regex patterns for query cleaning
PUNCTUATION_RE = re.compile(r'[^\w\s.-]', re.IGNORECASE)
WHITESPACE_RE = re.compile(r'\s+')
HINDI_OPEN_VERBS_RE = re.compile(
    r'\b(?:can\s+you\s+(?:please\s+)?open|can\s+you\s+(?:please\s+)?launch|can\s+you\s+(?:please\s+)?start|'
    r'could\s+you\s+(?:please\s+)?open|could\s+you\s+(?:please\s+)?launch|would\s+you\s+(?:please\s+)?open|'
    r'kya\s+tum\s+(?:kripya\s+)?(?:open|khol|chala|start)\s+kar\s+sakte\s+ho|'
    r'kya\s+aap\s+(?:kripya\s+)?(?:open|khol|chala|start)\s+kar\s+sakte\s+hain|'
    r'kholo|khol\s+do|khol\s+de|khol\s+kar|kholiye|'
    r'open\s+karo|open\s+kar\s+do|open\s+kar|open\s+kijiye|'
    r'chalao|chala\s+do|chala\s+de|chala\s+kar|chalu\s+karo|'
    r'start\s+karo|start\s+kar\s+do|start\s+kar|'
    r'launch\s+karo|launch\s+kar\s+do|launch\s+kar|launch\s+kijiye|'
    r'run\s+karo|run\s+kar|'
    r'open|launch|start|run|play)\b',
    re.IGNORECASE
)
HINDI_PARTICLES_RE = re.compile(
    r'\b(?:please|kripya|kindly|zara|thoda|thodi|na|ko|ka|ki|ke|par|pe|me|mein|boss|yaar|bhai|bhi|dost|ji|can\s+you|could\s+you|would\s+you)\b',
    re.IGNORECASE
)
NEW_INSTANCE_RE = re.compile(
    r'\b(?:new|blank|nayi|naya|khali|fresh|empty)\b',
    re.IGNORECASE
)
WEBSITE_KEYWORD_RE = re.compile(
    r'\b(?:website|site|portal|webpage|web\s+page|online|web|url)\b',
    re.IGNORECASE
)
APPLICATION_KEYWORD_RE = re.compile(
    r'\b(?:application|app|software|program)\b',
    re.IGNORECASE
)
FILE_KEYWORD_RE = re.compile(
    r'\b(?:file|document|sheet|spreadsheet|workbook|presentation|doc)\b',
    re.IGNORECASE
)
FILE_EXT_RE = re.compile(
    r'\.(?:xlsx|xls|csv|xlsm|docx|doc|pptx|ppt|pdf|txt|py|json|xml|html|zip|rar)\b',
    re.IGNORECASE
)
FOLDER_KEYWORD_RE = re.compile(
    r'\b(?:folder|directory|dir)\b',
    re.IGNORECASE
)


class ApplicationRegistry:
    """
    Centralized maintainable registry of canonical desktop applications and aliases.
    Normalizes speech variants, punctuation, English and Hindi/Hinglish phrasing.
    """

    def __init__(self) -> None:
        self._apps: Dict[str, AppDefinition] = {}
        self._alias_to_app: Dict[str, AppDefinition] = {}
        self._register_default_apps()

    def register(self, app: AppDefinition) -> None:
        """Register an application and index all its aliases."""
        self._apps[app.app_id.lower()] = app
        for alias in app.aliases:
            normalized_alias = self._normalize_alias_string(alias)
            if normalized_alias:
                self._alias_to_app[normalized_alias] = app

    def get_app(self, app_id: str) -> Optional[AppDefinition]:
        """Retrieve application by canonical ID."""
        return self._apps.get(app_id.lower().strip())

    def find_by_alias(self, query: str) -> Optional[AppDefinition]:
        """Find an application by normalized alias string."""
        normalized = self._normalize_alias_string(query)
        if not normalized:
            return None

        # 1. Exact alias match
        if normalized in self._alias_to_app:
            return self._alias_to_app[normalized]

        # 2. Try stripping "ms" or "microsoft" prefix if present
        if normalized.startswith("microsoft "):
            sub = normalized[len("microsoft "):].strip()
            if sub in self._alias_to_app:
                return self._alias_to_app[sub]
        elif normalized.startswith("ms "):
            sub = normalized[len("ms "):].strip()
            if sub in self._alias_to_app:
                return self._alias_to_app[sub]
        elif normalized.startswith("ms"):
            sub = normalized[2:].strip()
            if sub in self._alias_to_app:
                return self._alias_to_app[sub]

        # 3. Try checking if query starts with or equals alias
        for alias, app in self._alias_to_app.items():
            if normalized == alias or normalized.startswith(f"{alias} ") or normalized.endswith(f" {alias}"):
                return app

        # 4. Try fuzzy alias matching for minor typing/STT variations
        from difflib import SequenceMatcher
        best_match = None
        best_score = 0.0
        for alias, app in self._alias_to_app.items():
            if len(alias) >= 4 and abs(len(normalized) - len(alias)) <= 2:
                if normalized[0] == alias[0]:
                    score = SequenceMatcher(None, normalized, alias).ratio()
                    if score >= 0.85 and score > best_score:
                        best_score = score
                        best_match = app
        if best_match:
            return best_match

        # 5. Check WindowsAppResolver for fuzzy/phonetic alias match
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_match = get_windows_app_resolver().resolve_application(normalized, allow_fuzzy=True)
            if win_match and win_match.canonical_id in self._apps:
                return self._apps[win_match.canonical_id]
        except Exception:
            pass

        return None

    def list_apps(self) -> List[AppDefinition]:
        """Return all registered application definitions."""
        return list(self._apps.values())

    def get_all_aliases(self) -> List[str]:
        """Return a deduplicated list of all registered alias strings."""
        return list(self._alias_to_app.keys())

    @staticmethod
    def _normalize_alias_string(text: str) -> str:
        """Standardize casing, punctuation, and whitespace for alias indexing."""
        if not text:
            return ""
        s = text.lower().strip()
        s = PUNCTUATION_RE.sub(" ", s)
        s = WHITESPACE_RE.sub(" ", s).strip()
        return s

    def parse_query(self, query: str) -> Tuple[Optional[AppDefinition], Dict[str, Any]]:
        """
        Extract application intent, modifiers, and classification flags from user query.
        Returns (matched_app, metadata_dict).
        """
        raw = query.strip()
        lowered = raw.lower()

        is_application = bool(APPLICATION_KEYWORD_RE.search(lowered)) or any(
            re.search(rf'\b{re.escape(w)}\b', lowered) for w in ("ide", "editor", "compiler")
        )
        is_website = bool(WEBSITE_KEYWORD_RE.search(lowered)) or any(
            lowered.endswith(tld) or f"{tld}/" in lowered or f"{tld} " in lowered
            for tld in (".com", ".org", ".net", ".in", ".co", ".io", ".ai", ".gov", ".edu")
        )
        is_file_ext = bool(FILE_EXT_RE.search(lowered))
        is_file_kw = bool(FILE_KEYWORD_RE.search(lowered))
        is_folder = bool(FOLDER_KEYWORD_RE.search(lowered))
        is_new = bool(NEW_INSTANCE_RE.search(lowered))

        # Clean verbs and particles to isolate the application target
        cleaned = HINDI_OPEN_VERBS_RE.sub(" ", lowered)
        cleaned = re.sub(
            r'\b(?:close\s+karo|close\s+kar\s+do|band\s+karo|band\s+kar\s+do|band\s+kar|band|close|kill|terminate|exit)\b',
            ' ',
            cleaned,
            flags=re.IGNORECASE
        )
        cleaned = HINDI_PARTICLES_RE.sub(" ", cleaned)
        if is_new:
            cleaned = NEW_INSTANCE_RE.sub(" ", cleaned)
        if is_website:
            cleaned = WEBSITE_KEYWORD_RE.sub(" ", cleaned)
        if is_application:
            cleaned = APPLICATION_KEYWORD_RE.sub(" ", cleaned)
        if is_folder:
            cleaned = FOLDER_KEYWORD_RE.sub(" ", cleaned)

        # Run particle cleaning again to strip connectors like 'ki', 'ke', 'ko' remaining after keyword removal
        cleaned = HINDI_PARTICLES_RE.sub(" ", cleaned)
        cleaned = PUNCTUATION_RE.sub(" ", cleaned)
        cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()

        matched_app = self.find_by_alias(cleaned)

        # If not matched directly, try matching within the raw cleaned words
        if not matched_app:
            tokens = cleaned.split()
            for i in range(len(tokens), 0, -1):
                candidate = " ".join(tokens[:i])
                found = self.find_by_alias(candidate)
                if found:
                    matched_app = found
                    break

        # If still not matched, check WindowsAppResolver
        if not matched_app:
            try:
                from core.windows_app_resolver import get_windows_app_resolver
                win_match = get_windows_app_resolver().resolve_application(cleaned, allow_fuzzy=True)
                if win_match and win_match.canonical_id in self._apps:
                    matched_app = self._apps[win_match.canonical_id]
            except Exception:
                pass

        if is_website:
            target_type = "website"
        elif is_application:
            target_type = "application"
        elif is_folder:
            target_type = "folder"
        elif is_file_ext or (is_file_kw and not matched_app):
            target_type = "file"
        else:
            target_type = "auto"

        extracted_entity = matched_app.app_id if matched_app else cleaned

        meta = {
            "original_query": raw,
            "cleaned_target": cleaned,
            "extracted_entity": extracted_entity,
            "is_new": is_new,
            "is_application": is_application,
            "is_website": is_website,
            "is_file": is_file_ext or (is_file_kw and not matched_app),
            "is_folder": is_folder,
            "has_file_extension": is_file_ext,
            "target_type": target_type,
        }
        return matched_app, meta

    def _register_default_apps(self) -> None:
        """Register the core Windows and Microsoft Office application suite."""
        # 1. Microsoft Word
        self.register(AppDefinition(
            app_id="word",
            display_name="Microsoft Word",
            executables=["winword.exe", "winword"],
            protocols=["ms-word:"],
            aliases=[
                "word", "microsoft word", "ms word", "winword", "msword",
                "ms-word", "win word", "microsoft winword"
            ],
            is_office=True,
            new_instance_arg="/n",
            window_titles=["Word", "Microsoft Word"]
        ))

        # 2. Microsoft Excel
        self.register(AppDefinition(
            app_id="excel",
            display_name="Microsoft Excel",
            executables=["excel.exe", "excel"],
            protocols=["ms-excel:"],
            aliases=[
                "excel", "microsoft excel", "ms excel", "msexcel",
                "ms-excel", "excel sheet", "excel app"
            ],
            is_office=True,
            new_instance_arg="/x",
            window_titles=["Excel", "Microsoft Excel"]
        ))

        # 3. Microsoft PowerPoint
        self.register(AppDefinition(
            app_id="powerpoint",
            display_name="Microsoft PowerPoint",
            executables=["powerpnt.exe", "powerpnt", "powerpoint.exe"],
            protocols=["ms-powerpoint:"],
            aliases=[
                "ppt", "powerpoint", "power point", "microsoft powerpoint",
                "microsoft power point", "ms powerpoint", "ms power point",
                "mspowerpoint", "powerpnt", "ms ppt", "microsoft ppt"
            ],
            is_office=True,
            new_instance_arg="/n",
            window_titles=["PowerPoint", "Microsoft PowerPoint"]
        ))

        # 4. Microsoft Access
        self.register(AppDefinition(
            app_id="access",
            display_name="Microsoft Access",
            executables=["msaccess.exe", "msaccess", "access.exe"],
            protocols=["ms-access:"],
            aliases=[
                "access", "microsoft access", "ms access", "msaccess",
                "ms-access", "microsoft msaccess"
            ],
            is_office=True,
            window_titles=["Access", "Microsoft Access"]
        ))

        # 5. Microsoft Publisher
        self.register(AppDefinition(
            app_id="publisher",
            display_name="Microsoft Publisher",
            executables=["mspub.exe", "mspub", "publisher.exe"],
            protocols=["ms-publisher:"],
            aliases=[
                "publisher", "microsoft publisher", "ms publisher", "mspub",
                "ms-publisher", "microsoft mspub"
            ],
            is_office=True,
            window_titles=["Publisher", "Microsoft Publisher"]
        ))

        # 6. Microsoft Outlook
        self.register(AppDefinition(
            app_id="outlook",
            display_name="Microsoft Outlook",
            executables=["outlook.exe", "outlook"],
            protocols=["outlookmail:"],
            aliases=[
                "outlook", "microsoft outlook", "ms outlook", "msoutlook"
            ],
            is_office=True,
            window_titles=["Outlook", "Microsoft Outlook"]
        ))

        # 7. Microsoft OneNote
        self.register(AppDefinition(
            app_id="onenote",
            display_name="Microsoft OneNote",
            executables=["onenote.exe", "onenote"],
            protocols=["onenote:"],
            aliases=[
                "onenote", "microsoft onenote", "ms onenote", "msonenote", "one note"
            ],
            is_office=True,
            window_titles=["OneNote", "Microsoft OneNote"]
        ))

        # 8. Web Browsers
        self.register(AppDefinition(
            app_id="chrome",
            display_name="Google Chrome",
            executables=["chrome.exe", "chrome"],
            protocols=["googlechrome:"],
            aliases=["chrome", "google chrome", "chrome browser"],
            window_titles=["Google Chrome", "Chrome"]
        ))
        self.register(AppDefinition(
            app_id="brave",
            display_name="Brave Browser",
            executables=["brave.exe", "brave"],
            aliases=["brave", "brave browser"],
            window_titles=["Brave"]
        ))
        self.register(AppDefinition(
            app_id="edge",
            display_name="Microsoft Edge",
            executables=["msedge.exe", "msedge"],
            protocols=["microsoft-edge:"],
            aliases=["edge", "msedge", "microsoft edge", "ms edge"],
            window_titles=["Edge", "Microsoft Edge"]
        ))
        self.register(AppDefinition(
            app_id="firefox",
            display_name="Mozilla Firefox",
            executables=["firefox.exe", "firefox"],
            aliases=["firefox", "mozilla firefox", "firefox browser"],
            window_titles=["Mozilla Firefox", "Firefox"]
        ))

        # 9. Developer Tools
        self.register(AppDefinition(
            app_id="code",
            display_name="Visual Studio Code",
            executables=["code.exe", "code", "code.cmd"],
            protocols=["vscode:"],
            aliases=["code", "vs code", "vscode", "visual studio code"],
            window_titles=["Visual Studio Code"]
        ))
        self.register(AppDefinition(
            app_id="terminal",
            display_name="Windows Terminal",
            executables=["wt.exe", "wt"],
            protocols=["ms-terminal:"],
            aliases=["terminal", "windows terminal", "wt"],
            window_titles=["Terminal", "Windows Terminal"]
        ))
        self.register(AppDefinition(
            app_id="powershell",
            display_name="PowerShell",
            executables=["powershell.exe", "pwsh.exe"],
            aliases=["powershell", "power shell", "pwsh"],
            window_titles=["PowerShell", "Windows PowerShell"]
        ))
        self.register(AppDefinition(
            app_id="cmd",
            display_name="Command Prompt",
            executables=["cmd.exe", "cmd"],
            aliases=["cmd", "command prompt", "terminal cmd"],
            window_titles=["Command Prompt"]
        ))

        # 10. Utilities, Media & Windows System Applications
        self.register(AppDefinition(
            app_id="camera",
            display_name="Camera",
            executables=["WindowsCamera.exe"],
            protocols=["microsoft.windows.camera:"],
            aliases=[
                "camera", "kamera", "webcam", "web cam", "cam",
                "windows camera", "system camera", "camera app", "photo camera"
            ],
            window_titles=["Camera", "Windows Camera"]
        ))
        self.register(AppDefinition(
            app_id="notepad",
            display_name="Notepad",
            executables=["notepad.exe", "notepad"],
            aliases=["notepad", "note pad", "text editor", "notepad app"],
            window_titles=["Notepad"]
        ))
        self.register(AppDefinition(
            app_id="calc",
            display_name="Calculator",
            executables=["calc.exe", "calculator.exe", "CalculatorApp.exe", "calc"],
            protocols=["calculator:"],
            aliases=["calc", "calculator", "calculator app", "calci", "hisab kitab"],
            window_titles=["Calculator"]
        ))
        self.register(AppDefinition(
            app_id="vlc",
            display_name="VLC Media Player",
            executables=["vlc.exe", "vlc"],
            aliases=["vlc", "vlc player", "vlc media player"],
            window_titles=["VLC media player"]
        ))
        self.register(AppDefinition(
            app_id="spotify",
            display_name="Spotify",
            executables=["spotify.exe", "spotify"],
            protocols=["spotify:"],
            aliases=["spotify", "spotify music"],
            window_titles=["Spotify"]
        ))
        self.register(AppDefinition(
            app_id="settings",
            display_name="Windows Settings",
            executables=["SystemSettings.exe"],
            protocols=["ms-settings:"],
            aliases=["settings", "setting", "windows settings", "system settings", "pc settings"],
            window_titles=["Settings", "Windows Settings"]
        ))
        self.register(AppDefinition(
            app_id="control_panel",
            display_name="Control Panel",
            executables=["control.exe", "control"],
            aliases=["control panel", "control", "control panel app"],
            window_titles=["Control Panel"]
        ))
        self.register(AppDefinition(
            app_id="taskmgr",
            display_name="Task Manager",
            executables=["taskmgr.exe", "taskmgr"],
            aliases=["task manager", "taskmgr", "task manager app", "task monitor", "processes"],
            window_titles=["Task Manager"]
        ))
        self.register(AppDefinition(
            app_id="paint",
            display_name="Paint",
            executables=["mspaint.exe", "mspaint", "paint.exe"],
            protocols=["ms-paint:"],
            aliases=["paint", "mspaint", "ms paint", "drawing", "paint 3d", "paint app"],
            window_titles=["Paint", "Paint 3D"]
        ))
        self.register(AppDefinition(
            app_id="snipping_tool",
            display_name="Snipping Tool",
            executables=["snippingtool.exe", "snippingtool"],
            protocols=["ms-screenclip:"],
            aliases=["snipping tool", "snippingtool", "snip", "snip and sketch", "screen clip", "screenshot tool"],
            window_titles=["Snipping Tool", "Snip & Sketch"]
        ))
        self.register(AppDefinition(
            app_id="explorer",
            display_name="File Explorer",
            executables=["explorer.exe", "explorer"],
            aliases=["explorer", "file explorer", "windows explorer", "my computer", "this pc", "file manager"],
            window_titles=["File Explorer", "Windows Explorer"]
        ))
        self.register(AppDefinition(
            app_id="clock",
            display_name="Clock",
            executables=["Time.exe"],
            protocols=["ms-clock:"],
            aliases=["clock", "alarms and clock", "alarm", "stopwatch", "timer"],
            window_titles=["Clock", "Alarms & Clock"]
        ))
        self.register(AppDefinition(
            app_id="photos",
            display_name="Photos",
            protocols=["ms-photos:"],
            aliases=["photos", "photo viewer", "picture viewer", "windows photos"],
            window_titles=["Photos"]
        ))
        self.register(AppDefinition(
            app_id="store",
            display_name="Microsoft Store",
            executables=["store.exe"],
            protocols=["ms-windows-store:"],
            aliases=["store", "microsoft store", "windows store", "ms store", "msstore"],
            window_titles=["Microsoft Store"]
        ))
        self.register(AppDefinition(
            app_id="whatsapp",
            display_name="WhatsApp",
            executables=["WhatsApp.exe"],
            protocols=["whatsapp:"],
            aliases=["whatsapp", "whats app"],
            window_titles=["WhatsApp"]
        ))

        # 11. Google Antigravity (App)
        self.register(AppDefinition(
            app_id="antigravity",
            display_name="Antigravity",
            executables=["antigravity.exe", "antigravity", "agy.exe", "agy"],
            aliases=[
                "antigravity", "anti gravity", "antigravity app",
                "google antigravity", "agy"
            ],
            window_titles=["Antigravity"]
        ))

        # 12. Google Antigravity IDE
        self.register(AppDefinition(
            app_id="antigravity_ide",
            display_name="Antigravity IDE",
            executables=["Antigravity IDE.exe", "antigravity ide", "antigravity-ide.cmd", "antigravity-ide"],
            aliases=[
                "antigravity ide", "anti gravity ide", "google antigravity ide",
                "antigravity id", "anti gravity id", "antigravity ide app"
            ],
            window_titles=["Antigravity IDE"]
        ))

        # Index centralized application aliases
        for alias, canonical in APPLICATION_ALIASES.items():
            if canonical in self._apps:
                norm = self._normalize_alias_string(alias)
                if norm and norm not in self._alias_to_app:
                    self._alias_to_app[norm] = self._apps[canonical]

        # Register Windows 11 apps and third-party tools from WindowsAppResolver
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_resolver = get_windows_app_resolver()
            for app_id, win_spec in win_resolver._apps.items():
                if app_id not in self._apps:
                    self.register(AppDefinition(
                        app_id=win_spec.canonical_id,
                        display_name=win_spec.display_name,
                        executables=win_spec.executables,
                        protocols=win_spec.protocols,
                        aliases=win_spec.aliases,
                        window_titles=win_spec.window_titles,
                    ))
                else:
                    existing = self._apps[app_id]
                    for al in win_spec.aliases:
                        if al not in existing.aliases:
                            existing.aliases.append(al)
                            norm = self._normalize_alias_string(al)
                            if norm:
                                self._alias_to_app[norm] = existing
                    for pr in win_spec.protocols:
                        if pr not in existing.protocols:
                            existing.protocols.append(pr)
        except Exception:
            pass


_global_app_registry: Optional[ApplicationRegistry] = None


def get_application_registry() -> ApplicationRegistry:
    """Singleton getter for the central ApplicationRegistry."""
    global _global_app_registry
    if _global_app_registry is None:
        _global_app_registry = ApplicationRegistry()
    return _global_app_registry
