# core/windows_app_resolver.py
"""
Windows Application Resolver & Alias System for Jarvis V2.1.
[AUTHORITATIVE OWNER / SINGLE SOURCE OF TRUTH (SSOT)]
Delegated Components: core.apps.resolver, core.apps.registry

Authoritative Single Source of Truth for all Windows application resolution,
canonical app specifications (data/windows_apps.json), process termination rules,
and entity-aware fuzzy matching.

Implements multi-tier resolution:
  1. User learned mapping (CustomAliasManager / SQLite custom_aliases)
  2. Known Windows application registry (data/windows_apps.json)
  3. Installed application discovery (InstalledAppDetector / Start Menu / App Paths)
  4. App execution aliases (%LOCALAPPDATA%\\Microsoft\\WindowsApps)
  5. System PATH / Executable lookup (shutil.which, Program Files, System32)
  6. Safe fallback

Provides context-aware fuzzy entity detection, process name resolution for safe closing,
and structured execution result contracts.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
import logging
import os
import re
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.apps.windows_resolver")


def _levenshtein(s1: str, s2: str) -> int:
    """Computes exact Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


@dataclass
class WindowsAppSpec:
    """Specification of a known Windows application."""
    canonical_id: str
    display_name: str
    primary_launch_strategy: str  # "protocol", "executable", "msc", "shell"
    primary_launch_target: str
    protocols: List[str] = field(default_factory=list)
    executables: List[str] = field(default_factory=list)
    process_names: List[str] = field(default_factory=list)
    window_titles: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    is_system_app: bool = False


@dataclass
class WindowsAppMatch:
    """Result of resolving an application query."""
    canonical_id: str
    display_name: str
    launch_strategy: str
    launch_target: str
    protocols: List[str] = field(default_factory=list)
    executables: List[str] = field(default_factory=list)
    process_names: List[str] = field(default_factory=list)
    window_titles: List[str] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "registry"  # "user_learned", "registry", "installed_discovery", "app_alias", "system_path"
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None

    @property
    def clarification(self) -> Optional[str]:
        return self.clarification_prompt


class WindowsAppResolver:
    """
    Dedicated Windows Application Resolver, Alias Resolver, and Entity Detection subsystem.
    """

    _instance: Optional["WindowsAppResolver"] = None
    _REGISTRY_JSON_CACHE: Optional[List[Dict[str, Any]]] = None
    _REGISTRY_CACHE_MTIME: float = 0.0

    _NORM_CLEAN_RE = re.compile(r"[^\w\s.-]")
    _WHITESPACE_RE = re.compile(r"\s+")
    _WORDS_RE = re.compile(r"[a-zA-Z]+")
    _TIER2_STRIP_RE = re.compile(r"\b(?:app|application|kholo|open|chalao|start|band\s+karo|close|please|ko|ka|ki|dost|bhai|yaar|re|ji|sahib|toh|karo|kar|na|boss|oye|zara|jaldi)\b", re.IGNORECASE)

    _EXTRACT_VERBS_OPEN_RE = re.compile(
        r"\b(?:kholo|khol\s+do|khol\s+de|kholiye|open\s+karo|open\s+kar\s+do|chalao|chala\s+do|chalu\s+karo|start\s+karo|run\s+karo|open|launch|start|run|play)\b",
        re.IGNORECASE
    )
    _EXTRACT_VERBS_CLOSE_RE = re.compile(
        r"\b(?:close\s+karo|close\s+kar\s+do|band\s+karo|band\s+kar\s+do|band\s+kar|band|close|kill|terminate|exit)\b",
        re.IGNORECASE
    )
    _EXTRACT_POLITE_RE = re.compile(
        r"\b(?:please|zara|thoda|thodi|na|toh|ko|ka|ki|ke|par|pe|me|mein"
        r"|boss|yaar|bhai|dost|re|ji|sahib|oye|arre|arrey|jaldi"
        r"|karo|kar|karo\s+na|app|application|the)\b",
        re.IGNORECASE
    )

    def __init__(self, registry_path: str = "data/windows_apps.json") -> None:
        self.registry_path = registry_path
        self._apps: Dict[str, WindowsAppSpec] = {}
        self._alias_index: Dict[str, WindowsAppSpec] = {}
        self._all_known_app_terms: Set[str] = set()
        self._start_menu_cache: Optional[Dict[str, str]] = None
        self._app_aliases_cache: Optional[Dict[str, str]] = None
        self._app_paths_cache: Optional[Dict[str, str]] = None
        self._app_paths_cache_timestamp: float = 0.0
        self._cache_timestamp: float = 0.0
        self.load_registry()

    @classmethod
    def get_instance(cls) -> "WindowsAppResolver":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        else:
            real_path = os.path.abspath(cls._instance.registry_path)
            if os.path.exists(real_path):
                current_mtime = os.path.getmtime(real_path)
                if cls._REGISTRY_CACHE_MTIME != current_mtime:
                    cls._instance.load_registry()
        return cls._instance

    def load_registry(self) -> None:
        """Loads or reloads application definitions from JSON registry with process-level caching."""
        self._apps.clear()
        self._alias_index.clear()
        self._all_known_app_terms.clear()

        real_path = os.path.abspath(self.registry_path)
        if not os.path.exists(real_path):
            logger.warning("Windows apps registry JSON not found at %s", real_path)
            return

        try:
            current_mtime = os.path.getmtime(real_path)
            if WindowsAppResolver._REGISTRY_JSON_CACHE is None or WindowsAppResolver._REGISTRY_CACHE_MTIME != current_mtime:
                with open(real_path, "r", encoding="utf-8") as f:
                    WindowsAppResolver._REGISTRY_JSON_CACHE = json.load(f)
                WindowsAppResolver._REGISTRY_CACHE_MTIME = current_mtime
            data = WindowsAppResolver._REGISTRY_JSON_CACHE

            for item in data:
                spec = WindowsAppSpec(
                    canonical_id=item["canonical_id"],
                    display_name=item["display_name"],
                    primary_launch_strategy=item.get("primary_launch_strategy", "executable"),
                    primary_launch_target=item.get("primary_launch_target", ""),
                    protocols=item.get("protocols", []),
                    executables=item.get("executables", []),
                    process_names=item.get("process_names", []),
                    window_titles=item.get("window_titles", []),
                    aliases=item.get("aliases", []),
                    is_system_app=bool(item.get("is_system_app", False))
                )
                self._apps[spec.canonical_id.lower()] = spec
                self._alias_index[spec.canonical_id.lower()] = spec
                self._alias_index[self._normalize(spec.display_name)] = spec

                # Add display name and canonical ID words to known terms
                for w in self._WORDS_RE.findall(spec.display_name.lower()):
                    if len(w) >= 3:
                        self._all_known_app_terms.add(w)
                self._all_known_app_terms.add(spec.canonical_id.lower())

                for alias in spec.aliases:
                    clean_alias = self._normalize(alias)
                    if clean_alias:
                        self._alias_index[clean_alias] = spec
                        for w in clean_alias.split():
                            if len(w) >= 3:
                                self._all_known_app_terms.add(w)

            logger.info("Loaded %d Windows application specifications from %s", len(self._apps), real_path)
        except Exception as e:
            logger.error("Failed to load Windows application registry: %s", e)

    @classmethod
    def _normalize(cls, text: str) -> str:
        """Standardizes a query string for comparison with precompiled regexes."""
        if not text:
            return ""
        s = text.lower().strip()
        s = cls._NORM_CLEAN_RE.sub(" ", s)
        s = cls._WHITESPACE_RE.sub(" ", s).strip()
        return s

    def get_known_terms(self) -> Set[str]:
        """Returns all distinct words belonging to known applications and aliases."""
        return set(self._all_known_app_terms)

    def get_app_spec(self, canonical_id_or_name: str) -> Optional[WindowsAppSpec]:
        """Retrieves specification by canonical ID or exact alias."""
        clean = self._normalize(canonical_id_or_name)
        if clean in self._apps:
            return self._apps[clean]
        return self._alias_index.get(clean)

    def get_process_names(self, app_id_or_name: str) -> List[str]:
        """
        Retrieves known process names for an application to enable safe closing
        and process monitoring without terminating unrelated processes.
        """
        spec = self.get_app_spec(app_id_or_name)
        if spec and spec.process_names:
            return list(spec.process_names)
        clean = self._normalize(app_id_or_name)
        return [f"{clean}.exe", clean]

    # -------------------------------------------------------------------------
    # Core 6-Tier Resolution
    # -------------------------------------------------------------------------

    def resolve_application(
        self,
        query: str,
        active_context: Optional[Any] = None,
        allow_fuzzy: bool = True
    ) -> Optional[WindowsAppMatch]:
        """
        Resolves an application query through the prioritized multi-tier hierarchy:
          1. User learned mapping (CustomAliasManager / SQLite custom_aliases)
          2. Known Windows application registry (data/windows_apps.json)
          3. Installed application discovery (InstalledAppDetector / Start Menu / App Paths)
          4. App execution aliases (%LOCALAPPDATA%\\Microsoft\\WindowsApps)
          5. Executable lookup (shutil.which, Program Files, System32)
          6. Safe fallback
        """
        raw = str(query or "").strip()
        clean = self._normalize(raw)
        if not clean:
            return None

        # Exclude explicit websites/web identities
        from core.apps.aliases import WEBSITE_ALIASES
        from core.semantic.parsers.windows import WEB_IDENTITIES
        if clean in WEBSITE_ALIASES or clean in WEB_IDENTITIES:
            logger.debug("WIN_APP_RESOLVER_BYPASS: '%s' is registered as a website target.", clean)
            return None

        # Tier 1: User Learned Mapping
        match_user = self._resolve_tier1_user_learned(clean)
        if match_user:
            return match_user

        # Tier 2: Known Windows Application Registry (Exact & High-Confidence Fuzzy)
        match_reg = self._resolve_tier2_registry(clean, raw, allow_fuzzy=allow_fuzzy)
        if match_reg:
            return match_reg

        # Tier 3: Installed Application Discovery (Start Menu shortcuts & App Paths)
        match_inst = self._resolve_tier3_installed_discovery(clean, raw)
        if match_inst:
            return match_inst

        # Tier 4: App Execution Aliases
        match_alias = self._resolve_tier4_app_execution_alias(clean)
        if match_alias:
            return match_alias

        # Tier 5: System PATH / Executable Lookup
        match_path = self._resolve_tier5_executable_lookup(clean)
        if match_path:
            return match_path

        # Tier 6: Safe Fallback
        return None

    resolve_app = resolve_application

    @classmethod
    def is_application(cls, query: str) -> bool:
        """Checks if a name or phrase resolves to an application."""
        return cls.get_instance().resolve_application(query) is not None

    def _resolve_tier1_user_learned(self, clean: str) -> Optional[WindowsAppMatch]:
        """Tier 1: Check user-taught custom aliases from CustomAliasManager."""
        try:
            from core.alias_manager import get_alias_manager
            alias_mgr = get_alias_manager()
            entry = alias_mgr.resolve_alias(clean)
            if entry and entry.get("action_type") in ("OPEN_APPLICATION", "launch_app"):
                target_name = entry.get("target", "").strip()
                spec = self.get_app_spec(target_name)
                if spec:
                    return WindowsAppMatch(
                        canonical_id=spec.canonical_id,
                        display_name=spec.display_name,
                        launch_strategy=spec.primary_launch_strategy,
                        launch_target=spec.primary_launch_target,
                        protocols=spec.protocols,
                        executables=spec.executables,
                        process_names=spec.process_names,
                        window_titles=spec.window_titles,
                        confidence=1.0,
                        source="user_learned"
                    )
                # Custom app target not in registry
                return WindowsAppMatch(
                    canonical_id=self._normalize(target_name),
                    display_name=target_name,
                    launch_strategy="executable",
                    launch_target=target_name,
                    process_names=[f"{target_name}.exe"],
                    confidence=1.0,
                    source="user_learned"
                )
        except Exception as e:
            logger.debug("Error checking user learned aliases: %s", e)
        return None

    def _resolve_tier2_registry(self, clean: str, raw: str, allow_fuzzy: bool = True) -> Optional[WindowsAppMatch]:
        """Tier 2: Direct or fuzzy lookup in data/windows_apps.json."""
        # 1. Direct alias match
        if clean in self._alias_index:
            spec = self._alias_index[clean]
            # Disambiguation check for generic bare words like "store"
            is_ambiguous = (clean == "store" and not any(k in raw.lower() for k in ("microsoft", "ms", "windows")))
            clarification = "Store se aap Microsoft Store ki baat kar rahe hain?" if is_ambiguous else None
            return WindowsAppMatch(
                canonical_id=spec.canonical_id,
                display_name=spec.display_name,
                launch_strategy=spec.primary_launch_strategy,
                launch_target=spec.primary_launch_target,
                protocols=spec.protocols,
                executables=spec.executables,
                process_names=spec.process_names,
                window_titles=spec.window_titles,
                confidence=1.0,
                source="registry",
                is_ambiguous=is_ambiguous,
                clarification_prompt=clarification
            )

        # 2. Token / Prefix match (e.g. "microsoft store app", "calculator kholo")
        clean_stripped = self._TIER2_STRIP_RE.sub("", clean).strip()
        clean_stripped = self._WHITESPACE_RE.sub(" ", clean_stripped).strip()
        if clean_stripped and clean_stripped in self._alias_index:
            spec = self._alias_index[clean_stripped]
            return WindowsAppMatch(
                canonical_id=spec.canonical_id,
                display_name=spec.display_name,
                launch_strategy=spec.primary_launch_strategy,
                launch_target=spec.primary_launch_target,
                protocols=spec.protocols,
                executables=spec.executables,
                process_names=spec.process_names,
                window_titles=spec.window_titles,
                confidence=0.98,
                source="registry"
            )

        # 3. Context-aware fuzzy matching for STT / transcription errors
        # (e.g. "microsft store", "task managr", "notpad", "calculatr", "microsft edge")
        if allow_fuzzy:
            best_spec: Optional[WindowsAppSpec] = None
            best_score = 0.0
            query_len = len(clean)

            # Strict guard: "storage" must never match Microsoft Store!
            if clean == "storage" or clean.startswith("storage ") or clean.endswith(" storage"):
                return None

            for alias, spec in self._alias_index.items():
                alias_len = len(alias)
                # Single word aliases below 4 chars should not be fuzzy matched aggressively
                if alias_len < 4 and clean != alias:
                    continue

                # Length difference check
                if abs(query_len - alias_len) > 3:
                    continue

                # First letter check (or prefix match)
                if clean[0] != alias[0]:
                    continue

                ratio = SequenceMatcher(None, clean, alias).ratio()
                dist = _levenshtein(clean, alias)

                # High-confidence threshold
                # Edit distance <= 2 on longer phrases represents minor STT mistake
                is_confident = (ratio >= 0.85 and dist <= 2) or (ratio >= 0.90 and dist <= 3)

                if is_confident and ratio > best_score:
                    best_score = ratio
                    best_spec = spec

            if best_spec and best_score >= 0.85:
                logger.info(
                    "WIN_APP_FUZZY_MATCH: '%s' matched '%s' (%s) with score=%.3f",
                    clean, best_spec.display_name, best_spec.canonical_id, best_score
                )
                return WindowsAppMatch(
                    canonical_id=best_spec.canonical_id,
                    display_name=best_spec.display_name,
                    launch_strategy=best_spec.primary_launch_strategy,
                    launch_target=best_spec.primary_launch_target,
                    protocols=best_spec.protocols,
                    executables=best_spec.executables,
                    process_names=best_spec.process_names,
                    window_titles=best_spec.window_titles,
                    confidence=best_score,
                    source="registry"
                )

        return None

    def _resolve_tier3_installed_discovery(self, clean: str, raw: str) -> Optional[WindowsAppMatch]:
        """Tier 3: Dynamic installed application discovery via Start Menu and App Paths."""
        shortcuts = self._get_start_menu_shortcuts()
        clean_no_space = clean.replace(" ", "")

        for s_name, s_path in shortcuts.items():
            s_name_norm = self._normalize(s_name)
            s_no_space = s_name_norm.replace(" ", "")

            if clean_no_space == s_no_space or clean == s_name_norm:
                if os.path.isfile(s_path):
                    return WindowsAppMatch(
                        canonical_id=clean,
                        display_name=s_name,
                        launch_strategy="shortcut",
                        launch_target=s_path,
                        executables=[s_path],
                        process_names=[f"{clean}.exe"],
                        confidence=0.95,
                        source="installed_discovery"
                    )

        # Windows App Paths (HKLM/HKCU)
        app_paths = self._get_app_paths()
        for exe_key, full_path in app_paths.items():
            key_clean = exe_key.lower().replace(".exe", "").replace(" ", "")
            if clean_no_space == key_clean:
                if os.path.isfile(full_path):
                    disp = os.path.basename(full_path).replace(".exe", "").capitalize()
                    return WindowsAppMatch(
                        canonical_id=clean,
                        display_name=disp,
                        launch_strategy="executable",
                        launch_target=full_path,
                        executables=[full_path],
                        process_names=[os.path.basename(full_path)],
                        confidence=0.95,
                        source="installed_discovery"
                    )

        return None

    def _resolve_tier4_app_execution_alias(self, clean: str) -> Optional[WindowsAppMatch]:
        """Tier 4: Windows App execution aliases in %LOCALAPPDATA%\\Microsoft\\WindowsApps."""
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            return None

        win_apps_dir = os.path.join(local_app_data, "Microsoft", "WindowsApps")
        if not os.path.isdir(win_apps_dir):
            return None

        candidates = [clean, f"{clean}.exe", clean.replace(" ", "")]
        for cand in candidates:
            target_file = os.path.join(win_apps_dir, cand if cand.endswith(".exe") else f"{cand}.exe")
            if os.path.isfile(target_file):
                return WindowsAppMatch(
                    canonical_id=clean,
                    display_name=clean.capitalize(),
                    launch_strategy="executable",
                    launch_target=target_file,
                    executables=[target_file],
                    process_names=[os.path.basename(target_file)],
                    confidence=0.92,
                    source="app_alias"
                )
        return None

    def _resolve_tier5_executable_lookup(self, clean: str) -> Optional[WindowsAppMatch]:
        """Tier 5: System PATH resolution via shutil.which or System32 check."""
        cand = clean if clean.endswith(".exe") else f"{clean}.exe"
        resolved_which = shutil.which(cand) or shutil.which(clean)
        if resolved_which and os.path.isfile(resolved_which):
            disp = os.path.basename(resolved_which).replace(".exe", "").capitalize()
            return WindowsAppMatch(
                canonical_id=clean,
                display_name=disp,
                launch_strategy="executable",
                launch_target=resolved_which,
                executables=[resolved_which],
                process_names=[os.path.basename(resolved_which)],
                confidence=0.90,
                source="system_path"
            )
        return None

    # -------------------------------------------------------------------------
    # Reusable Cached Discovery
    # -------------------------------------------------------------------------

    def _get_start_menu_shortcuts(self) -> Dict[str, str]:
        """Retrieves and caches Start Menu shortcuts across user and system profiles."""
        now = time.time()
        if self._start_menu_cache is not None and (now - self._cache_timestamp) < 300:
            return self._start_menu_cache

        shortcuts: Dict[str, str] = {}
        paths = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"))
        progdata = os.environ.get("ProgramData")
        if progdata:
            paths.append(os.path.join(progdata, r"Microsoft\Windows\Start Menu\Programs"))

        for p in paths:
            if os.path.exists(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(".lnk"):
                            name = f[:-4].strip()
                            if name and name not in shortcuts:
                                shortcuts[name] = os.path.join(root, f)

        self._start_menu_cache = shortcuts
        self._cache_timestamp = now
        return shortcuts

    def _get_app_paths(self) -> Dict[str, str]:
        """Retrieves Windows App Paths from registry (HKLM and HKCU) with 300s cache."""
        now = time.time()
        if self._app_paths_cache is not None and (now - self._app_paths_cache_timestamp) < 300:
            return self._app_paths_cache

        app_paths: Dict[str, str] = {}
        if sys.platform != "win32":
            self._app_paths_cache = app_paths
            self._app_paths_cache_timestamp = now
            return app_paths

        try:
            import winreg
            keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            ]
            for root, subkey in keys:
                try:
                    with winreg.OpenKey(root, subkey) as pkey:
                        num_subkeys, _, _ = winreg.QueryInfoKey(pkey)
                        for i in range(num_subkeys):
                            try:
                                sub = winreg.EnumKey(pkey, i)
                                with winreg.OpenKey(pkey, sub) as akey:
                                    val, _ = winreg.QueryValueEx(akey, "")
                                    if val and os.path.exists(str(val).strip('"')):
                                        app_paths[sub.lower()] = str(val).strip('"')
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass

        self._app_paths_cache = app_paths
        self._app_paths_cache_timestamp = now
        return app_paths

    # -------------------------------------------------------------------------
    # Entity Extraction from Sentences
    # -------------------------------------------------------------------------

    def extract_app_entity_from_text(self, text: str) -> Optional[Tuple[WindowsAppMatch, str]]:
        """
        Extracts an application entity from an utterance (e.g. 'open microsft store' -> (Match, 'microsft store')).
        Returns (match, matched_phrase) or None.
        """
        raw = text.strip()
        lowered = raw.lower()

        # 1. Strip open/close verbs and polite particles with precompiled regexes
        clean = self._EXTRACT_VERBS_OPEN_RE.sub("", lowered)
        clean = self._EXTRACT_VERBS_CLOSE_RE.sub("", clean)
        clean = self._EXTRACT_POLITE_RE.sub("", clean)
        clean = self._NORM_CLEAN_RE.sub(" ", clean)
        clean = self._WHITESPACE_RE.sub(" ", clean).strip()

        if not clean:
            return None

        match = self.resolve_application(clean, allow_fuzzy=True)
        if match:
            return match, clean

        return None

    # -------------------------------------------------------------------------
    # Execution Result Contract Builder
    # -------------------------------------------------------------------------

    @staticmethod
    def build_execution_result(
        app_name: str,
        success: bool,
        status: Optional[str] = None,
        target: Optional[str] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Constructs standardized application execution result contract:
          Success: {"success": True, "status": "opened", "application": "Microsoft Store", "target": "Microsoft Store"}
          Failure: {"success": False, "status": "not_found", "application": "Microsoft Store"}
        """
        if success:
            return {
                "success": True,
                "status": status or "opened",
                "application": app_name,
                "target": target or app_name,
                "message": message or f"{app_name} open ho gaya, Boss."
            }
        else:
            return {
                "success": False,
                "status": status or "not_found",
                "application": app_name,
                "target": target or app_name,
                "message": message or f"{app_name} installed nahi mila, Boss."
            }


_global_windows_app_resolver: Optional[WindowsAppResolver] = None


def get_windows_app_resolver() -> WindowsAppResolver:
    """Returns the singleton instance of WindowsAppResolver."""
    global _global_windows_app_resolver
    if _global_windows_app_resolver is None:
        _global_windows_app_resolver = WindowsAppResolver()
    return _global_windows_app_resolver
