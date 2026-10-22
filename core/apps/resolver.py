# core/apps/resolver.py
"""
Priority-Based Application Resolver Architecture for Jarvis V2.
[DELEGATED / SHARED COMPONENT]
Authoritative Owner: core.windows.app_resolver (core/windows_app_resolver.py)

Provides high-level ResolvedApp dataclasses, query parsing, and legacy fallback
while delegating entity extraction, fuzzy matching, and system app definitions directly
to the authoritative owner WindowsAppResolver.

Executes a 5-tier resolution strategy:
1. Tier 1 (system_app): Known Windows/system apps with authoritative launch mechanisms
   (delegated to WindowsAppResolver with UWP protocol fallback).
2. Tier 2 (known_alias): Centralized aliases from ApplicationRegistry (Office, Browsers, VS Code, etc.).
3. Tier 3 (start_menu_or_registration): Start Menu shortcuts (.lnk) and Windows App Paths registry keys.
4. Tier 4 (executable_path): Standard Program Files, LocalAppData, System32, and Office installation paths.
5. Tier 5 (installed_search): System PATH resolution via shutil.which and dynamic discovery.
"""

from dataclasses import dataclass, field
import logging
import os
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

if sys.platform == "win32":
    import winreg
else:
    winreg = None

logger = logging.getLogger("jarvis.apps.resolver")


# =====================================================================
# Data Models
# =====================================================================

@dataclass
class ResolvedApp:
    """Represents an authoritatively resolved application ready for execution and verification."""
    app_id: str
    display_name: str
    launch_strategy: str                         # "protocol", "executable", "shortcut", "shell_start"
    launch_target: str                           # e.g., "microsoft.windows.camera:", "C:\\...\\notepad.exe"
    launch_args: List[str] = field(default_factory=list)
    resolution_strategy: str = ""                # "system_app", "known_alias", "start_menu_or_registration", "executable_path", "installed_search"
    executable_path: Optional[str] = None
    shortcut_path: Optional[str] = None
    protocol: Optional[str] = None
    process_names: List[str] = field(default_factory=list)
    window_titles: List[str] = field(default_factory=list)
    is_system_app: bool = False
    confidence: float = 1.0


@dataclass
class SystemAppSpec:
    """Specification for known built-in Windows applications and utilities."""
    canonical_id: str
    display_name: str
    primary_launch_strategy: str                 # "protocol", "executable"
    primary_launch_target: str
    protocols: List[str] = field(default_factory=list)
    executables: List[str] = field(default_factory=list)
    process_names: List[str] = field(default_factory=list)
    window_titles: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)


# =====================================================================
# Centralized Known Windows / System Apps Definitions
# =====================================================================

SYSTEM_APP_DEFINITIONS: Dict[str, SystemAppSpec] = {
    "camera": SystemAppSpec(
        canonical_id="camera",
        display_name="Camera",
        primary_launch_strategy="protocol",
        primary_launch_target="microsoft.windows.camera:",
        protocols=["microsoft.windows.camera:"],
        executables=["WindowsCamera.exe"],
        process_names=["WindowsCamera.exe", "WindowsCamera", "Camera.exe"],
        window_titles=["Camera", "Windows Camera"],
        aliases=[
            "camera", "kamera", "webcam", "web cam", "cam",
            "windows camera", "system camera", "camera app", "photo camera"
        ]
    ),
    "calc": SystemAppSpec(
        canonical_id="calc",
        display_name="Calculator",
        primary_launch_strategy="protocol",
        primary_launch_target="calculator:",
        protocols=["calculator:"],
        executables=["calc.exe", "CalculatorApp.exe", "Calculator.exe", "calc"],
        process_names=["CalculatorApp.exe", "calc.exe", "Calculator.exe", "Calculator"],
        window_titles=["Calculator"],
        aliases=[
            "calc", "calculator", "calculator app", "calci",
            "hisab kitab", "calculator kholo"
        ]
    ),
    "settings": SystemAppSpec(
        canonical_id="settings",
        display_name="Windows Settings",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-settings:",
        protocols=["ms-settings:"],
        executables=["SystemSettings.exe"],
        process_names=["SystemSettings.exe", "SystemSettings"],
        window_titles=["Settings", "Windows Settings"],
        aliases=[
            "settings", "setting", "windows settings", "system settings",
            "pc settings", "control settings"
        ]
    ),
    "notepad": SystemAppSpec(
        canonical_id="notepad",
        display_name="Notepad",
        primary_launch_strategy="executable",
        primary_launch_target="notepad.exe",
        executables=["notepad.exe", "notepad"],
        process_names=["notepad.exe", "Notepad.exe", "Notepad"],
        window_titles=["Notepad"],
        aliases=[
            "notepad", "note pad", "text editor", "notepad app"
        ]
    ),
    "paint": SystemAppSpec(
        canonical_id="paint",
        display_name="Paint",
        primary_launch_strategy="executable",
        primary_launch_target="mspaint.exe",
        protocols=["ms-paint:"],
        executables=["mspaint.exe", "paint.exe", "mspaint"],
        process_names=["mspaint.exe", "PaintStudio.View.exe", "mspaint"],
        window_titles=["Paint", "Paint 3D"],
        aliases=[
            "paint", "mspaint", "ms paint", "drawing", "paint 3d", "paint app"
        ]
    ),
    "taskmgr": SystemAppSpec(
        canonical_id="taskmgr",
        display_name="Task Manager",
        primary_launch_strategy="executable",
        primary_launch_target="taskmgr.exe",
        executables=["taskmgr.exe", "taskmgr"],
        process_names=["taskmgr.exe", "Taskmgr.exe", "taskmgr"],
        window_titles=["Task Manager"],
        aliases=[
            "task manager", "taskmgr", "task manager app", "task monitor",
            "processes", "process manager"
        ]
    ),
    "explorer": SystemAppSpec(
        canonical_id="explorer",
        display_name="File Explorer",
        primary_launch_strategy="executable",
        primary_launch_target="explorer.exe",
        executables=["explorer.exe", "explorer"],
        process_names=["explorer.exe"],
        window_titles=["File Explorer", "Windows Explorer"],
        aliases=[
            "file explorer", "explorer", "windows explorer", "my computer",
            "this pc", "file manager", "files app"
        ]
    ),
    "control_panel": SystemAppSpec(
        canonical_id="control_panel",
        display_name="Control Panel",
        primary_launch_strategy="executable",
        primary_launch_target="control.exe",
        executables=["control.exe", "control"],
        process_names=["control.exe"],
        window_titles=["Control Panel"],
        aliases=[
            "control panel", "control", "control panel app"
        ]
    ),
    "cmd": SystemAppSpec(
        canonical_id="cmd",
        display_name="Command Prompt",
        primary_launch_strategy="executable",
        primary_launch_target="cmd.exe",
        executables=["cmd.exe", "cmd"],
        process_names=["cmd.exe"],
        window_titles=["Command Prompt"],
        aliases=[
            "cmd", "command prompt", "command prompt app", "cmd prompt",
            "dos prompt", "command line"
        ]
    ),
    "powershell": SystemAppSpec(
        canonical_id="powershell",
        display_name="PowerShell",
        primary_launch_strategy="executable",
        primary_launch_target="powershell.exe",
        executables=["powershell.exe", "pwsh.exe", "powershell"],
        process_names=["powershell.exe", "pwsh.exe"],
        window_titles=["PowerShell", "Windows PowerShell"],
        aliases=[
            "powershell", "power shell", "pwsh", "windows powershell"
        ]
    ),
    "snipping_tool": SystemAppSpec(
        canonical_id="snipping_tool",
        display_name="Snipping Tool",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-screenclip:",
        protocols=["ms-screenclip:"],
        executables=["snippingtool.exe", "snippingtool"],
        process_names=["SnippingTool.exe", "ScreenClippingHost.exe", "snippingtool.exe"],
        window_titles=["Snipping Tool", "Snip & Sketch"],
        aliases=[
            "snipping tool", "snippingtool", "snip", "snip and sketch",
            "screen clip", "screenshot tool"
        ]
    ),
    "clock": SystemAppSpec(
        canonical_id="clock",
        display_name="Clock",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-clock:",
        protocols=["ms-clock:"],
        executables=["Time.exe"],
        process_names=["Time.exe"],
        window_titles=["Clock", "Alarms & Clock"],
        aliases=["clock", "alarms and clock", "alarm", "stopwatch", "timer"]
    ),
    "photos": SystemAppSpec(
        canonical_id="photos",
        display_name="Photos",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-photos:",
        protocols=["ms-photos:"],
        process_names=["Microsoft.Photos.exe"],
        window_titles=["Photos"],
        aliases=["photos", "photo viewer", "picture viewer", "windows photos", "image viewer"]
    ),
    "store": SystemAppSpec(
        canonical_id="store",
        display_name="Microsoft Store",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-windows-store:",
        protocols=["ms-windows-store:"],
        process_names=["WinStore.App.exe"],
        window_titles=["Microsoft Store"],
        aliases=["microsoft store", "windows store", "ms store", "msstore", "store"]
    ),
    "voice_recorder": SystemAppSpec(
        canonical_id="voice_recorder",
        display_name="Voice Recorder",
        primary_launch_strategy="protocol",
        primary_launch_target="ms-soundrecorder:",
        protocols=["ms-soundrecorder:"],
        process_names=["SoundRec.exe"],
        window_titles=["Voice Recorder", "Sound Recorder"],
        aliases=["voice recorder", "sound recorder", "audio recorder", "recorder"]
    ),
    "weather": SystemAppSpec(
        canonical_id="weather",
        display_name="Weather",
        primary_launch_strategy="protocol",
        primary_launch_target="bingweather:",
        protocols=["bingweather:"],
        window_titles=["Weather"],
        aliases=["weather", "mausam"]
    ),
    "maps": SystemAppSpec(
        canonical_id="maps",
        display_name="Maps",
        primary_launch_strategy="protocol",
        primary_launch_target="bingmaps:",
        protocols=["bingmaps:"],
        window_titles=["Maps"],
        aliases=["maps", "naksha"]
    ),
}


# =====================================================================
# App Resolver Implementation
# =====================================================================

class AppResolver:
    """
    Authoritative application resolver prioritizing:
    1. Known Windows/System apps (proper UWP protocols, shell commands)
    2. Known app aliases (ApplicationRegistry, Office suite, Browsers)
    3. Start Menu shortcuts & Windows App Paths registrations
    4. Known filesystem executable paths (Program Files, LocalAppData, System32)
    5. Normal installed-app search (System PATH)
    """

    def __init__(self, registry: Optional[Any] = None, detector: Optional[Any] = None) -> None:
        self._registry = registry
        self._detector = detector
        self._system_alias_index: Dict[str, SystemAppSpec] = {}
        self._build_system_alias_index()

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from core.apps.registry import get_application_registry
            self._registry = get_application_registry()
        return self._registry

    @property
    def detector(self) -> Any:
        if self._detector is None:
            from core.apps.detector import get_installed_app_detector
            self._detector = get_installed_app_detector()
        return self._detector

    def _build_system_alias_index(self) -> None:
        """Indexes all normalized aliases for system apps."""
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_resolver = get_windows_app_resolver()
            for app_id, win_spec in win_resolver._apps.items():
                if win_spec.is_system_app and app_id not in SYSTEM_APP_DEFINITIONS:
                    SYSTEM_APP_DEFINITIONS[app_id] = SystemAppSpec(
                        canonical_id=win_spec.canonical_id,
                        display_name=win_spec.display_name,
                        primary_launch_strategy=win_spec.primary_launch_strategy,
                        primary_launch_target=win_spec.primary_launch_target,
                        protocols=win_spec.protocols,
                        executables=win_spec.executables,
                        process_names=win_spec.process_names,
                        window_titles=win_spec.window_titles,
                        aliases=win_spec.aliases,
                    )
        except Exception as e:
            logger.debug("Could not load windows_apps into SYSTEM_APP_DEFINITIONS: %s", e)

        for app_spec in SYSTEM_APP_DEFINITIONS.values():
            self._system_alias_index[app_spec.canonical_id.lower()] = app_spec
            for alias in app_spec.aliases:
                clean = self._normalize(alias)
                if clean:
                    self._system_alias_index[clean] = app_spec

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize query or alias for comparison."""
        if not text:
            return ""
        s = text.lower().strip()
        s = re.sub(r'[^\w\s.-]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def resolve(
        self,
        target_or_query: str,
        is_new: bool = False,
        file_path: Optional[str] = None
    ) -> Optional[ResolvedApp]:
        """
        Resolves an application target through the 5-tier resolution strategy.
        Returns a concrete ResolvedApp or None if all tiers are exhausted.
        """
        raw = str(target_or_query or "").strip()
        clean = self._normalize(raw)
        if not clean:
            logger.debug("APP_RESOLVER_EMPTY: Target string is empty.")
            return None

        # Exclude explicit websites or web identities
        from core.apps.aliases import WEBSITE_ALIASES
        from core.semantic.parsers.windows import WEB_IDENTITIES
        if clean in WEBSITE_ALIASES or clean in WEB_IDENTITIES:
            logger.debug("APP_RESOLVER_BYPASS: '%s' is registered as a website target.", clean)
            return None

        logger.info("APP_RESOLVER_START: Resolving query/target='%s' (is_new=%s)", raw, is_new)

        args: List[str] = []
        if file_path:
            args.append(file_path)

        # -------------------------------------------------------------
        # Tier 1: Known Windows / System Apps
        # -------------------------------------------------------------
        resolved_sys = self._resolve_tier1_system_app(clean, raw, args)
        if resolved_sys:
            logger.info(
                "RESOLVER_STRATEGY_SUCCESS: Tier 1 (system_app) resolved '%s' -> app_id='%s' strategy='%s' target='%s'",
                raw, resolved_sys.app_id, resolved_sys.launch_strategy, resolved_sys.launch_target
            )
            return resolved_sys
        logger.debug("RESOLVER_STRATEGY_FAILED: Tier 1 (system_app) did not match '%s'", clean)

        # -------------------------------------------------------------
        # Tier 2: Known App Aliases via ApplicationRegistry
        # -------------------------------------------------------------
        resolved_alias = self._resolve_tier2_known_alias(clean, raw, is_new, args)
        if resolved_alias:
            logger.info(
                "RESOLVER_STRATEGY_SUCCESS: Tier 2 (known_alias) resolved '%s' -> app_id='%s' strategy='%s' target='%s'",
                raw, resolved_alias.app_id, resolved_alias.launch_strategy, resolved_alias.launch_target
            )
            return resolved_alias
        logger.debug("RESOLVER_STRATEGY_FAILED: Tier 2 (known_alias) did not match '%s'", clean)

        # -------------------------------------------------------------
        # Tier 3: Start Menu & App Registrations
        # -------------------------------------------------------------
        resolved_reg = self._resolve_tier3_start_menu_and_registration(clean, raw, args)
        if resolved_reg:
            logger.info(
                "RESOLVER_STRATEGY_SUCCESS: Tier 3 (start_menu_or_registration) resolved '%s' -> target='%s'",
                raw, resolved_reg.launch_target
            )
            return resolved_reg
        logger.debug("RESOLVER_STRATEGY_FAILED: Tier 3 (start_menu_or_registration) did not match '%s'", clean)

        # -------------------------------------------------------------
        # Tier 4: Executable Paths
        # -------------------------------------------------------------
        resolved_path = self._resolve_tier4_executable_paths(clean, raw, args)
        if resolved_path:
            logger.info(
                "RESOLVER_STRATEGY_SUCCESS: Tier 4 (executable_path) resolved '%s' -> path='%s'",
                raw, resolved_path.launch_target
            )
            return resolved_path
        logger.debug("RESOLVER_STRATEGY_FAILED: Tier 4 (executable_path) did not match '%s'", clean)

        # -------------------------------------------------------------
        # Tier 5: Normal Installed-App Search (System PATH / which)
        # -------------------------------------------------------------
        resolved_search = self._resolve_tier5_installed_search(clean, raw, args)
        if resolved_search:
            logger.info(
                "RESOLVER_STRATEGY_SUCCESS: Tier 5 (installed_search) resolved '%s' -> target='%s'",
                raw, resolved_search.launch_target
            )
            return resolved_search
        logger.debug("RESOLVER_STRATEGY_FAILED: Tier 5 (installed_search) did not match '%s'", clean)

        # All 5 resolution tiers exhausted
        logger.warning(
            "APP_RESOLUTION_EXHAUSTED: All 5 resolution tiers failed for target='%s'. Application is not installed or recognized.",
            raw
        )
        return None

    def _resolve_tier1_system_app(self, clean: str, raw: str, args: List[str]) -> Optional[ResolvedApp]:
        """Resolves known Windows built-in system utilities using their correct launch mechanism."""
        # Check WindowsAppResolver for direct or fuzzy matches
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_match = get_windows_app_resolver().resolve_application(clean, allow_fuzzy=True)
            if win_match and win_match.canonical_id in SYSTEM_APP_DEFINITIONS:
                launch_strat = win_match.launch_strategy
                target = win_match.launch_target
                exec_path = target if launch_strat == "executable" else None
                protocol = target if launch_strat == "protocol" else None
                return ResolvedApp(
                    app_id=win_match.canonical_id,
                    display_name=win_match.display_name,
                    launch_strategy=launch_strat,
                    launch_target=target,
                    launch_args=args,
                    resolution_strategy="system_app",
                    executable_path=exec_path,
                    protocol=protocol,
                    process_names=win_match.process_names,
                    window_titles=win_match.window_titles,
                    is_system_app=True,
                    confidence=win_match.confidence
                )
        except Exception:
            pass

        spec: Optional[SystemAppSpec] = self._system_alias_index.get(clean)

        # If not direct match, try token matching
        if not spec:
            for alias, app_spec in self._system_alias_index.items():
                if clean == alias or clean.startswith(f"{alias} ") or clean.endswith(f" {alias}"):
                    spec = app_spec
                    break

        if not spec:
            return None

        # Determine launch strategy
        launch_strat = spec.primary_launch_strategy
        target = spec.primary_launch_target
        exec_path = None
        protocol = None

        if launch_strat == "protocol":
            protocol = target
        elif launch_strat == "executable":
            # Check if executable path can be resolved via which or System32
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            candidate = os.path.join(system_root, "System32", target)
            if os.path.isfile(candidate):
                exec_path = candidate
                target = candidate
            else:
                which_p = shutil.which(target)
                if which_p and os.path.isfile(which_p):
                    exec_path = which_p
                    target = which_p

        return ResolvedApp(
            app_id=spec.canonical_id,
            display_name=spec.display_name,
            launch_strategy=launch_strat,
            launch_target=target,
            launch_args=args,
            resolution_strategy="system_app",
            executable_path=exec_path,
            protocol=protocol,
            process_names=list(spec.process_names),
            window_titles=list(spec.window_titles),
            is_system_app=True,
            confidence=1.0
        )

    def _resolve_tier2_known_alias(
        self,
        clean: str,
        raw: str,
        is_new: bool,
        args: List[str]
    ) -> Optional[ResolvedApp]:
        """Resolves known applications registered in ApplicationRegistry."""
        reg = self.registry
        app_def = reg.get_app(clean) or reg.find_by_alias(clean)
        if not app_def:
            return None

        # Verify installation status via detector
        det = self.detector
        info = det.detect(app_def)
        if not info or not info.is_installed:
            return None

        final_args = list(args)
        if is_new and getattr(app_def, "new_instance_arg", None):
            final_args.insert(0, app_def.new_instance_arg)

        launch_cmd = det.get_launch_command(app_def, is_new=is_new)
        if launch_cmd:
            cmd_target, cmd_args, cmd_strat = launch_cmd
            return ResolvedApp(
                app_id=app_def.app_id,
                display_name=app_def.display_name,
                launch_strategy=cmd_strat,
                launch_target=cmd_target,
                launch_args=final_args or cmd_args,
                resolution_strategy="known_alias",
                executable_path=info.executable_path,
                shortcut_path=info.shortcut_path,
                protocol=info.protocol,
                process_names=[e.replace(".exe", "") for e in app_def.executables] + [e for e in app_def.executables],
                window_titles=list(app_def.window_titles),
                is_system_app=False,
                confidence=1.0
            )

        return None

    def _resolve_tier3_start_menu_and_registration(
        self,
        clean: str,
        raw: str,
        args: List[str]
    ) -> Optional[ResolvedApp]:
        """Resolves through Start Menu shortcuts (.lnk) and App Paths registry."""
        det = self.detector
        clean_no_space = clean.replace(" ", "")

        # 1. Start Menu Shortcuts
        shortcuts = det._get_start_menu_shortcuts() if hasattr(det, "_get_start_menu_shortcuts") else {}
        valid_suffixes = ("ide", "app", "desktop", "client", "studio", "editor")
        for s_name, s_path in shortcuts.items():
            s_name_clean = s_name.lower().replace(" ", "")
            is_match = (
                clean_no_space == s_name_clean
                or any(s_name_clean == f"{clean_no_space}{suf}" for suf in valid_suffixes)
                or any(clean_no_space == f"{s_name_clean}{suf}" for suf in valid_suffixes)
            )
            if is_match and os.path.isfile(s_path):
                return ResolvedApp(
                    app_id=clean,
                    display_name=s_name,
                    launch_strategy="shortcut",
                    launch_target=s_path,
                    launch_args=args,
                    resolution_strategy="start_menu_or_registration",
                    shortcut_path=s_path,
                    window_titles=[s_name, clean.capitalize()],
                    confidence=0.9
                )

        # 2. Windows App Paths registry
        app_paths = det._get_app_paths_registry() if hasattr(det, "_get_app_paths_registry") else {}
        for key, exe_path in app_paths.items():
            key_clean = key.lower().replace(".exe", "").replace(" ", "")
            if clean_no_space == key_clean and os.path.isfile(exe_path):
                disp = os.path.basename(exe_path).replace(".exe", "").capitalize()
                return ResolvedApp(
                    app_id=clean,
                    display_name=disp,
                    launch_strategy="executable",
                    launch_target=exe_path,
                    launch_args=args,
                    resolution_strategy="start_menu_or_registration",
                    executable_path=exe_path,
                    window_titles=[disp],
                    confidence=0.9
                )

        return None

    def _resolve_tier4_executable_paths(
        self,
        clean: str,
        raw: str,
        args: List[str]
    ) -> Optional[ResolvedApp]:
        """Resolves through known installation directories."""
        det = self.detector
        candidates = [clean, f"{clean}.exe", clean.replace(" ", ""), f"{clean.replace(' ', '')}.exe"]
        resolved_exe = det._find_in_known_directories(candidates) if hasattr(det, "_find_in_known_directories") else None
        if resolved_exe and os.path.isfile(resolved_exe):
            disp = os.path.basename(resolved_exe).replace(".exe", "").capitalize()
            return ResolvedApp(
                app_id=clean,
                display_name=disp,
                launch_strategy="executable",
                launch_target=resolved_exe,
                launch_args=args,
                resolution_strategy="executable_path",
                executable_path=resolved_exe,
                window_titles=[disp],
                confidence=0.85
            )

        # Check System32
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        for c in candidates:
            sys32_path = os.path.join(system_root, "System32", c if c.endswith(".exe") else f"{c}.exe")
            if os.path.isfile(sys32_path):
                disp = os.path.basename(sys32_path).replace(".exe", "").capitalize()
                return ResolvedApp(
                    app_id=clean,
                    display_name=disp,
                    launch_strategy="executable",
                    launch_target=sys32_path,
                    launch_args=args,
                    resolution_strategy="executable_path",
                    executable_path=sys32_path,
                    window_titles=[disp],
                    confidence=0.85
                )

        return None

    def _resolve_tier5_installed_search(
        self,
        clean: str,
        raw: str,
        args: List[str]
    ) -> Optional[ResolvedApp]:
        """Resolves application via System PATH search."""
        for candidate in (f"{clean}.exe", clean, clean.replace(" ", ""), f"{clean.replace(' ', '')}.exe"):
            which_path = shutil.which(candidate)
            if which_path and os.path.isfile(which_path):
                disp = os.path.basename(which_path).replace(".exe", "").capitalize()
                return ResolvedApp(
                    app_id=clean,
                    display_name=disp,
                    launch_strategy="executable",
                    launch_target=which_path,
                    launch_args=args,
                    resolution_strategy="installed_search",
                    executable_path=which_path,
                    window_titles=[disp],
                    confidence=0.8
                )

        return None

    def resolve_from_query(self, query: str) -> Tuple[Optional[ResolvedApp], Dict[str, Any]]:
        """
        Parses a natural user query (e.g. 'open camera', 'camera kholo', 'camera chalao',
        'launch camera', 'start camera') and resolves the intended application.
        Returns (resolved_app, metadata_dict).
        """
        # First check WindowsAppResolver
        try:
            from core.windows_app_resolver import get_windows_app_resolver
            win_resolver = get_windows_app_resolver()
            extracted = win_resolver.extract_app_entity_from_text(query)
            if extracted:
                win_match, _ = extracted
                resolved = self.resolve(target_or_query=win_match.canonical_id)
                if resolved:
                    return resolved, {
                        "cleaned_target": win_match.canonical_id,
                        "display_name": win_match.display_name,
                        "is_new": False,
                        "target_type": "application"
                    }
        except Exception:
            pass

        reg = self.registry
        matched_app, meta = reg.parse_query(query)
        target_name = (matched_app.app_id if matched_app else meta.get("cleaned_target", "")).strip()

        if not target_name:
            return None, meta

        resolved = self.resolve(
            target_or_query=target_name,
            is_new=meta.get("is_new", False)
        )
        return resolved, meta


# =====================================================================
# Singleton Management
# =====================================================================

_global_app_resolver: Optional[AppResolver] = None


def get_app_resolver() -> AppResolver:
    """Returns the singleton instance of AppResolver."""
    global _global_app_resolver
    if _global_app_resolver is None:
        _global_app_resolver = AppResolver()
    return _global_app_resolver
