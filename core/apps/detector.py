# core/apps/detector.py
"""Windows installed application detection and executable resolution engine."""

import glob
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

if sys.platform == "win32":
    import winreg
else:
    winreg = None

from core.apps.registry import AppDefinition, ApplicationRegistry, get_application_registry

logger = logging.getLogger("jarvis.apps.detector")


@dataclass
class InstalledAppInfo:
    """Detailed metadata for a locally detected and installed application."""
    app_id: str
    display_name: str
    executable_path: Optional[str] = None
    shortcut_path: Optional[str] = None
    protocol: Optional[str] = None
    launch_strategy: str = "executable"  # "executable", "shortcut", "protocol", "path"
    is_installed: bool = False


class InstalledAppDetector:
    """
    Scans and verifies installed Windows applications using multiple discovery strategies:
    1. Windows App Paths registry keys (HKLM & HKCU)
    2. Start Menu shortcuts (User Roaming & System ProgramData)
    3. Standard and version-agnostic Microsoft Office & Program Files directories
    4. System PATH resolution
    5. Protocol handlers / UWP apps
    """

    def __init__(self, registry: Optional[ApplicationRegistry] = None) -> None:
        self.registry = registry or get_application_registry()
        self._cache: Dict[str, Optional[InstalledAppInfo]] = {}
        self._start_menu_shortcuts: Optional[Dict[str, str]] = None
        self._app_paths_registry: Optional[Dict[str, str]] = None

    def is_installed(self, app_or_id: Union[str, AppDefinition]) -> bool:
        """Check if an application is installed locally on the system."""
        info = self.detect(app_or_id)
        return info is not None and info.is_installed

    def detect(self, app_or_id: Union[str, AppDefinition]) -> Optional[InstalledAppInfo]:
        """Detect and return full installation metadata for an application."""
        app: Optional[AppDefinition] = None
        if isinstance(app_or_id, AppDefinition):
            app = app_or_id
        else:
            app = self.registry.get_app(str(app_or_id)) or self.registry.find_by_alias(str(app_or_id))

        if not app:
            # Check AppResolver first across system apps and discovery tiers
            target_str = str(app_or_id).strip().lower()
            from core.apps.aliases import WEBSITE_ALIASES
            from core.semantic.parsers.windows import WEB_IDENTITIES
            if target_str in WEBSITE_ALIASES or target_str in WEB_IDENTITIES:
                return None

            from core.apps.resolver import get_app_resolver
            resolver = get_app_resolver()
            resolved = resolver.resolve(target_str)
            if resolved:
                info = InstalledAppInfo(
                    app_id=resolved.app_id,
                    display_name=resolved.display_name,
                    executable_path=resolved.executable_path,
                    shortcut_path=resolved.shortcut_path,
                    protocol=resolved.protocol,
                    launch_strategy=resolved.launch_strategy,
                    is_installed=True
                )
                self._cache[resolved.app_id.lower()] = info
                return info

            dynamic_app = self._discover_unregistered_app(target_str)
            if dynamic_app:
                self.registry.register(dynamic_app)
                app = dynamic_app
            else:
                return None

        app_key = app.app_id.lower()
        if app_key in self._cache:
            return self._cache[app_key]

        info = self._resolve_app_installation(app)
        self._cache[app_key] = info
        return info

    def _discover_unregistered_app(self, name_or_id: str) -> Optional[AppDefinition]:
        """Dynamically detect and register installed Windows applications not present in default registry."""
        clean = name_or_id.lower().strip()
        if not clean:
            return None

        from core.apps.aliases import WEBSITE_ALIASES
        from core.semantic.parsers.windows import WEB_IDENTITIES
        if clean in WEBSITE_ALIASES or clean in WEB_IDENTITIES:
            return None

        # 1. Start Menu shortcuts
        shortcuts = self._get_start_menu_shortcuts()
        clean_no_space = clean.replace(" ", "")
        valid_suffixes = ("ide", "app", "desktop", "client", "studio", "editor")
        for s_name, s_path in shortcuts.items():
            s_name_clean = s_name.lower().replace(" ", "")
            is_match = (
                clean_no_space == s_name_clean
                or any(s_name_clean == f"{clean_no_space}{suf}" for suf in valid_suffixes)
                or any(clean_no_space == f"{s_name_clean}{suf}" for suf in valid_suffixes)
            )
            if is_match:
                if os.path.isfile(s_path):
                    return AppDefinition(
                        app_id=clean,
                        display_name=s_name,
                        executables=[f"{clean}.exe", clean],
                        aliases=[clean, s_name.lower()],
                        window_titles=[s_name, clean.capitalize()]
                    )

        # 2. Windows App Paths registry
        app_paths = self._get_app_paths_registry()
        for key, exe_path in app_paths.items():
            key_clean = key.lower().replace(".exe", "").replace(" ", "")
            if clean_no_space == key_clean:
                if os.path.isfile(exe_path):
                    disp = os.path.basename(exe_path).replace(".exe", "").capitalize()
                    return AppDefinition(
                        app_id=clean,
                        display_name=disp,
                        executables=[os.path.basename(exe_path), clean],
                        aliases=[clean],
                        window_titles=[disp]
                    )

        # 3. System PATH
        which_path = shutil.which(f"{clean}.exe") or shutil.which(clean)
        if which_path and os.path.isfile(which_path):
            disp = os.path.basename(which_path).replace(".exe", "").capitalize()
            return AppDefinition(
                app_id=clean,
                display_name=disp,
                executables=[os.path.basename(which_path), clean],
                aliases=[clean],
                window_titles=[disp]
            )

        return None

    def get_launch_command(
        self,
        app_or_id: Union[str, AppDefinition],
        is_new: bool = False,
        file_path: Optional[str] = None
    ) -> Optional[Tuple[str, List[str], str]]:
        """
        Returns (target, args, launch_strategy) for executing the application.
        If application is not installed, returns None.
        """
        info = self.detect(app_or_id)
        if not info or not info.is_installed:
            return None

        app = app_or_id if isinstance(app_or_id, AppDefinition) else self.registry.get_app(info.app_id)
        args: List[str] = []

        if is_new and app and app.new_instance_arg:
            args.append(app.new_instance_arg)

        if file_path:
            args.append(file_path)

        if getattr(info, "launch_strategy", None) == "protocol" and info.protocol:
            return info.protocol, args, "protocol"
        elif info.executable_path and os.path.exists(info.executable_path):
            return info.executable_path, args, "executable"
        elif info.shortcut_path and os.path.exists(info.shortcut_path):
            return info.shortcut_path, args, "shortcut"
        elif info.protocol:
            return info.protocol, args, "protocol"

        return None

    def refresh_cache(self) -> None:
        """Clear the cached detection results to perform a fresh scan."""
        self._cache.clear()
        self._start_menu_shortcuts = None
        self._app_paths_registry = None

    def _resolve_app_installation(self, app: AppDefinition) -> Optional[InstalledAppInfo]:
        """Examine system paths, registry, and shortcuts in priority order."""
        app_id_lower = app.app_id.lower()
        from core.apps.resolver import SYSTEM_APP_DEFINITIONS

        # 0. Check if this is a known Windows system app with protocol launch mechanism (e.g. Camera)
        if app_id_lower in SYSTEM_APP_DEFINITIONS:
            spec = SYSTEM_APP_DEFINITIONS[app_id_lower]
            if spec.primary_launch_strategy == "protocol":
                return InstalledAppInfo(
                    app_id=app.app_id,
                    display_name=app.display_name,
                    protocol=spec.primary_launch_target,
                    launch_strategy="protocol",
                    is_installed=True
                )

        # 1. Strategy 1: Check Windows App Paths Registry
        app_paths = self._get_app_paths_registry()
        for exe in app.executables:
            exe_lower = exe.lower()
            if exe_lower in app_paths:
                resolved_path = app_paths[exe_lower]
                if os.path.isfile(resolved_path):
                    return InstalledAppInfo(
                        app_id=app.app_id,
                        display_name=app.display_name,
                        executable_path=resolved_path,
                        launch_strategy="executable",
                        is_installed=True
                    )

        # 2. Strategy 2: Check standard Office & Program Files directories
        office_exe = self._find_in_known_directories(app.executables)
        if office_exe:
            return InstalledAppInfo(
                app_id=app.app_id,
                display_name=app.display_name,
                executable_path=office_exe,
                launch_strategy="executable",
                is_installed=True
            )

        # 3. Strategy 3: Check Start Menu Shortcuts
        shortcuts = self._get_start_menu_shortcuts()
        for alias in [app.display_name] + app.aliases:
            alias_clean = alias.lower().replace(" ", "")
            for name, shortcut_path in shortcuts.items():
                name_clean = name.lower().replace(" ", "")
                if alias_clean == name_clean or name_clean.startswith(alias_clean):
                    if os.path.isfile(shortcut_path):
                        return InstalledAppInfo(
                            app_id=app.app_id,
                            display_name=app.display_name,
                            shortcut_path=shortcut_path,
                            launch_strategy="shortcut",
                            is_installed=True
                        )

        # 4. Strategy 4: System PATH via shutil.which
        for exe in app.executables:
            which_path = shutil.which(exe)
            if which_path and os.path.isfile(which_path):
                return InstalledAppInfo(
                    app_id=app.app_id,
                    display_name=app.display_name,
                    executable_path=which_path,
                    launch_strategy="executable",
                    is_installed=True
                )

        # 5. Strategy 5: Supported URI Protocol / UWP Built-in check
        # (e.g., Settings, Store, Calculator, Clock, Camera, Photos)
        if app.protocols:
            primary_protocol = app.protocols[0]
            if app_id_lower in SYSTEM_APP_DEFINITIONS or app_id_lower in (
                "settings", "calc", "store", "camera", "paint", "whatsapp",
                "clock", "photos", "snipping_tool", "voice_recorder"
            ):
                return InstalledAppInfo(
                    app_id=app.app_id,
                    display_name=app.display_name,
                    protocol=primary_protocol,
                    launch_strategy="protocol",
                    is_installed=True
                )

        return InstalledAppInfo(
            app_id=app.app_id,
            display_name=app.display_name,
            is_installed=False
        )

    def _get_app_paths_registry(self) -> Dict[str, str]:
        """Query HKLM and HKCU App Paths for registered application executables."""
        if self._app_paths_registry is not None:
            return self._app_paths_registry

        self._app_paths_registry = {}
        if not winreg:
            return self._app_paths_registry

        for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                with winreg.OpenKey(root_key, key_path) as parent_key:
                    num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(parent_key, i)
                            with winreg.OpenKey(parent_key, subkey_name) as subkey:
                                try:
                                    val, _ = winreg.QueryValueEx(subkey, "")
                                    if val and isinstance(val, str):
                                        clean_val = val.strip('"\t ')
                                        self._app_paths_registry[subkey_name.lower()] = clean_val
                                except Exception:
                                    pass
                        except Exception:
                            continue
            except Exception:
                continue

        return self._app_paths_registry

    def _get_start_menu_shortcuts(self) -> Dict[str, str]:
        """Discover all .lnk shortcuts across common and user Start Menu directories."""
        if self._start_menu_shortcuts is not None:
            return self._start_menu_shortcuts

        self._start_menu_shortcuts = {}
        dirs = []

        prog_data = os.environ.get("PROGRAMDATA")
        if prog_data:
            dirs.append(os.path.join(prog_data, r"Microsoft\Windows\Start Menu\Programs"))

        app_data = os.environ.get("APPDATA")
        if app_data:
            dirs.append(os.path.join(app_data, r"Microsoft\Windows\Start Menu\Programs"))

        for d in dirs:
            if not os.path.isdir(d):
                continue
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name_without_ext = f[:-4]
                        self._start_menu_shortcuts[name_without_ext] = os.path.join(root, f)

        return self._start_menu_shortcuts

    def _find_in_known_directories(self, executables: List[str]) -> Optional[str]:
        """Scan standard Office and Program Files directories across all drive variations."""
        known_dirs = [
            r"C:\Program Files\Microsoft Office\root\Office16",
            r"C:\Program Files (x86)\Microsoft Office\root\Office16",
            r"C:\Program Files\Microsoft Office\Office16",
            r"C:\Program Files (x86)\Microsoft Office\Office16",
            r"C:\Program Files\Microsoft Office\Office15",
            r"C:\Program Files (x86)\Microsoft Office\Office15",
            r"C:\Program Files\Microsoft Office\Office14",
            r"C:\Program Files (x86)\Microsoft Office\Office14",
        ]

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            known_dirs.append(os.path.join(local_app_data, "Programs"))

        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            known_dirs.append(prog_files)
        prog_files_x86 = os.environ.get("ProgramFiles(x86)")
        if prog_files_x86:
            known_dirs.append(prog_files_x86)

        for d in known_dirs:
            if not os.path.isdir(d):
                continue
            for exe in executables:
                candidate = os.path.join(d, exe)
                if os.path.isfile(candidate):
                    return candidate

        return None


_global_detector: Optional[InstalledAppDetector] = None


def get_installed_app_detector() -> InstalledAppDetector:
    """Singleton getter for the central InstalledAppDetector."""
    global _global_detector
    if _global_detector is None:
        _global_detector = InstalledAppDetector()
    return _global_detector
