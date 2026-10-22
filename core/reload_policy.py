# core/reload_policy.py
"""
Classification Policy for Zero-Downtime Live Code Updates in Jarvis V2.1.
Deterministically categorizes modified file paths into:
- HOT_RELOAD_SAFE: in-process module/plugin reload without worker interruption.
- WORKER_RESTART_REQUIRED: quiesce active worker threads/tasks, reload modules, and restart worker.
- FULL_RESTART_REQUIRED: logged and prompted; GUI process is NEVER forcibly killed.
- IGNORE: documentation, test files, logs, caches, database files.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence


class ReloadCategory(Enum):
    HOT_RELOAD_SAFE = "HOT_RELOAD_SAFE"
    WORKER_RESTART_REQUIRED = "WORKER_RESTART_REQUIRED"
    FULL_RESTART_REQUIRED = "FULL_RESTART_REQUIRED"
    IGNORE = "IGNORE"


@dataclass
class ReloadPlan:
    category: ReloadCategory
    target_name: str
    reason: str
    affected_files: List[str] = field(default_factory=list)
    plugin_name: Optional[str] = None
    modules_to_reload: List[str] = field(default_factory=list)


# Plugins that maintain active background worker threads / service loops
WORKER_PLUGINS = {
    "trading_signals",
    "activity_monitor",
    "reminder",
    "voice",
}

# Directories and extensions to ignore for runtime reload
IGNORED_PREFIXES = (
    "logs/",
    "logs\\",
    "data/",
    "data\\",
    "tests/",
    "tests\\",
    ".git/",
    ".git\\",
    ".gemini/",
    ".gemini\\",
    "__pycache__/",
    "__pycache__\\",
    ".venv/",
    ".venv\\",
)

IGNORED_EXTENSIONS = (
    ".log",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyd",
    ".tmp",
    ".temp",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".wav",
    ".mp3",
    ".csv",
)

# Files whose changes fundamentally alter process bootstrapping or Qt application creation
FULL_RESTART_FILES = {
    "main.py",
    "gui/__init__.py",
    "gui\\__init__.py",
}


def normalize_path(path: str) -> str:
    """Normalizes file paths to consistent forward slashes for matching."""
    return path.replace("\\", "/").strip().lstrip("/")


def classify_file_change(rel_path: str) -> ReloadPlan:
    """
    Classifies a modified relative file path into an actionable ReloadPlan.
    Determines category, target component, and reload scope.
    """
    norm = normalize_path(rel_path)
    lower = norm.lower()

    # 1. Ignore checks by directory prefix
    if any(lower.startswith(prefix.replace("\\", "/")) for prefix in IGNORED_PREFIXES):
        return ReloadPlan(
            category=ReloadCategory.IGNORE,
            target_name="ignored",
            reason=f"Path '{rel_path}' is in an ignored directory.",
            affected_files=[rel_path],
        )

    # 2. Check skills directory (skills use SKILL.md and scripts)
    if norm.startswith("skills/"):
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="skills",
            reason=f"Skill definition '{rel_path}' is reload-safe in-memory.",
            affected_files=[rel_path],
        )

    # 2b. Check architecture design files (architecture.txt or plugins/archify spec)
    if norm == "architecture.txt" or norm.endswith("/architecture.txt") or "plugins/archify" in norm:
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="archify",
            reason=f"Architecture design '{rel_path}' changed. Auto-updating Archify visualization.",
            affected_files=[rel_path],
            plugin_name="archify",
        )

    ext = os.path.splitext(lower)[1]
    if ext in IGNORED_EXTENSIONS:
        return ReloadPlan(
            category=ReloadCategory.IGNORE,
            target_name="ignored",
            reason=f"File extension '{ext}' is ignored for code updates.",
            affected_files=[rel_path],
        )

    # 3. Check full restart files
    if norm in FULL_RESTART_FILES or any(norm.endswith("/" + f) for f in FULL_RESTART_FILES):
        return ReloadPlan(
            category=ReloadCategory.FULL_RESTART_REQUIRED,
            target_name="core:bootstrap",
            reason=f"Bootstrapping file '{rel_path}' requires a full application restart to take effect.",
            affected_files=[rel_path],
        )

    # 3. Check plugins directory: plugins/<plugin_name>/...
    if norm.startswith("plugins/"):
        parts = norm.split("/")
        if len(parts) >= 2:
            plugin_name = parts[1].lower()
            if plugin_name in WORKER_PLUGINS:
                return ReloadPlan(
                    category=ReloadCategory.WORKER_RESTART_REQUIRED,
                    target_name=f"plugin:{plugin_name}",
                    reason=f"Plugin '{plugin_name}' maintains background workers. Requires graceful worker stop, reload, and restart.",
                    affected_files=[rel_path],
                    plugin_name=plugin_name,
                )
            else:
                return ReloadPlan(
                    category=ReloadCategory.HOT_RELOAD_SAFE,
                    target_name=f"plugin:{plugin_name}",
                    reason=f"Plugin '{plugin_name}' is reload-safe in-process without worker interruption.",
                    affected_files=[rel_path],
                    plugin_name=plugin_name,
                )

    # 4. Check skills directory
    if norm.startswith("skills/"):
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="skills",
            reason=f"Skill definition '{rel_path}' is reload-safe in-memory.",
            affected_files=[rel_path],
        )

    # 5. Check configuration files
    if norm == "config.yaml" or norm.endswith("/config.yaml") or norm.startswith("config/"):
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="config",
            reason=f"Configuration '{rel_path}' can be reloaded in-process.",
            affected_files=[rel_path],
        )

    # 6. Check brain modules (semantic parser, classifier, intents)
    if norm.startswith("brain/"):
        module_path = norm.replace("/", ".").replace(".py", "")
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="brain",
            reason=f"Brain component '{rel_path}' can be hot-reloaded in-process.",
            affected_files=[rel_path],
            modules_to_reload=[module_path],
        )

    # 7. Check core utilities / helpers
    if norm.startswith("core/"):
        # Reloader and reload_policy themselves
        if "reload" in lower or "watcher" in lower:
            return ReloadPlan(
                category=ReloadCategory.HOT_RELOAD_SAFE,
                target_name="core:reloader",
                reason=f"Reloader component '{rel_path}' updated.",
                affected_files=[rel_path],
            )
        module_path = norm.replace("/", ".").replace(".py", "")
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="core",
            reason=f"Core module '{rel_path}' reloadable in-process.",
            affected_files=[rel_path],
            modules_to_reload=[module_path],
        )

    # 8. Check gui views / styles (do NOT destroy window, reload styles/views if safe)
    if norm.startswith("gui/"):
        if "styles.py" in lower:
            return ReloadPlan(
                category=ReloadCategory.HOT_RELOAD_SAFE,
                target_name="gui:styles",
                reason=f"GUI stylesheet '{rel_path}' reloadable live.",
                affected_files=[rel_path],
            )
        # Any other GUI view file
        return ReloadPlan(
            category=ReloadCategory.HOT_RELOAD_SAFE,
            target_name="gui:view",
            reason=f"GUI view file '{rel_path}' updated.",
            affected_files=[rel_path],
        )

    # Default fallback: classify as HOT_RELOAD_SAFE to avoid process killing
    return ReloadPlan(
        category=ReloadCategory.HOT_RELOAD_SAFE,
        target_name="general",
        reason=f"General file update '{rel_path}' processed with zero downtime.",
        affected_files=[rel_path],
    )


def coalesce_file_changes(rel_paths: Sequence[str]) -> ReloadPlan:
    """
    Coalesces multiple detected file changes from a debounce window into a single unified ReloadPlan.
    Prioritizes FULL_RESTART > WORKER_RESTART > HOT_RELOAD > IGNORE.
    """
    if not rel_paths:
        return ReloadPlan(
            category=ReloadCategory.IGNORE,
            target_name="empty",
            reason="No files changed.",
        )

    plans = [classify_file_change(p) for p in rel_paths]

    # Filter out pure ignores if other changes exist
    non_ignored = [p for p in plans if p.category != ReloadCategory.IGNORE]
    if not non_ignored:
        return plans[0]

    # If any change requires FULL_RESTART_REQUIRED, report that (prompted, NOT killed)
    full_restart = [p for p in non_ignored if p.category == ReloadCategory.FULL_RESTART_REQUIRED]
    if full_restart:
        combined_files = list({f for p in full_restart for f in p.affected_files})
        return ReloadPlan(
            category=ReloadCategory.FULL_RESTART_REQUIRED,
            target_name="core:bootstrap",
            reason="One or more bootstrap files changed: " + ", ".join(combined_files),
            affected_files=combined_files,
        )

    # If any change requires WORKER_RESTART_REQUIRED, run worker restart
    worker_restart = [p for p in non_ignored if p.category == ReloadCategory.WORKER_RESTART_REQUIRED]
    if worker_restart:
        combined_files = list({f for p in non_ignored for f in p.affected_files})
        plugin_names = list({p.plugin_name for p in worker_restart if p.plugin_name})
        primary_plugin = plugin_names[0] if plugin_names else None
        return ReloadPlan(
            category=ReloadCategory.WORKER_RESTART_REQUIRED,
            target_name=f"plugin:{primary_plugin}" if primary_plugin else "workers",
            reason=f"Worker-dependent plugins changed ({', '.join(plugin_names or combined_files)}).",
            affected_files=combined_files,
            plugin_name=primary_plugin,
        )

    # Otherwise, coalesce all HOT_RELOAD_SAFE plans
    combined_files = list({f for p in non_ignored for f in p.affected_files})
    plugins = list({p.plugin_name for p in non_ignored if p.plugin_name})
    modules = list({m for p in non_ignored for m in p.modules_to_reload})

    return ReloadPlan(
        category=ReloadCategory.HOT_RELOAD_SAFE,
        target_name=f"plugin:{plugins[0]}" if len(plugins) == 1 else "hot_reload_batch",
        reason=f"Hot reload batch for {len(combined_files)} file(s).",
        affected_files=combined_files,
        plugin_name=plugins[0] if len(plugins) == 1 else None,
        modules_to_reload=modules,
    )
