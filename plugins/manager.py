# plugins/manager.py
"""Memory-bounded plugin catalog, lazy loader, lifecycle manager, and router."""

import importlib
import inspect
import json
import logging
import os
import sys
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from .base import BasePlugin
from .manifest import PluginManifest, PluginResult, PluginStatus
from core.permissions import PermissionGuard, PermissionLevel

logger = logging.getLogger("jarvis.plugins.manager")


class PluginManager:
    """Catalog all capabilities, but keep only recently used implementations in RAM."""

    def __init__(self, plugin_dir="plugins", config=None, event_bus=None):
        self.plugin_dir, self.config, self.event_bus = plugin_dir, config or {}, event_bus
        self._plugins: Dict[str, BasePlugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._plugin_errors: Dict[str, str] = {}
        self._plugin_modules: Dict[str, str] = {}
        self._plugin_paths: Dict[str, str] = {}
        self._keyword_index: Dict[str, List[Tuple[str, Any]]] = {}
        self._loaded_lru = OrderedDict()
        settings = self.config.get("plugins", {})
        self.lazy_load = bool(settings.get("lazy_load", True))
        self.max_loaded_plugins = max(1, int(settings.get("max_loaded_plugins", 24)))
        self.resident_plugins = {str(x).lower() for x in settings.get("resident_plugins", ["system", "reminder"])}
        permission_settings = self.config.get("permissions", {})
        configured_level = str(permission_settings.get("default_level", "EXECUTE")).upper()
        self.permission_guard = PermissionGuard(
            default_level=getattr(PermissionLevel, configured_level, PermissionLevel.EXECUTE),
            enforce=bool(permission_settings.get("enforce_permissions", True)),
            admin_mode=bool(permission_settings.get("admin_mode", False)),
        )

    def discover_and_load(self):
        if not os.path.isdir(self.plugin_dir):
            logger.warning("Plugin directory '%s' does not exist.", self.plugin_dir)
            return
        self._keyword_index.clear()
        for name in sorted(os.listdir(self.plugin_dir)):
            path = os.path.join(self.plugin_dir, name)
            if os.path.isdir(path) and not name.startswith(("_", ".")):
                (self._discover_plugin if self.lazy_load else self._load_plugin_from_dir)(name, path)
        # Pre-load resident plugins so background schedulers and system hooks start immediately
        for resident in self.resident_plugins:
            if resident in self._manifests and resident not in self._plugins:
                path = self._plugin_paths.get(resident, os.path.join(self.plugin_dir, resident))
                self._load_plugin_from_dir(resident, path)
        self.print_startup_banner()

    def _discover_plugin(self, name, path):
        """Read metadata and validate syntax without importing implementation code."""
        key = name.lower()
        try:
            manifest_path = os.path.join(path, "plugin.json")
            if not os.path.isfile(manifest_path):
                raise FileNotFoundError("plugin.json is required")
            manifest = PluginManifest.from_json_file(manifest_path)
            key = manifest.name.lower()
            source_path = os.path.join(path, "plugin.py")
            if os.path.isfile(source_path):
                with open(source_path, "r", encoding="utf-8") as source:
                    compile(source.read(), source_path, "exec")
            # Legacy V2 metadata lives in lightweight commands.py. New plugins should
            # put actions in plugin.json, which makes discovery completely import-free.
            if not manifest.actions:
                commands = importlib.import_module(f"plugins.{name}.commands")
                manifest.actions = list(getattr(commands, "ACTIONS", []))
            self._manifests[key], self._plugin_paths[key] = manifest, path
            self._index_manifest(key, manifest)
            self._plugin_errors.pop(key, None)
            return True
        except Exception as exc:
            logger.error("Failed to catalog plugin '%s': %s", name, exc)
            self._plugin_errors[key] = str(exc)
            return False

    def _index_manifest(self, name, manifest):
        for action in manifest.actions:
            for keyword in action.keywords:
                keyword = str(keyword).strip().lower()
                if keyword:
                    self._keyword_index.setdefault(keyword, []).append((name, action))

    def match_action(self, text):
        """Return the most specific enabled action using the keyword index."""
        lowered, matches = text.lower(), []
        for keyword, targets in self._keyword_index.items():
            if keyword in lowered:
                for name, action in targets:
                    manifest = self._manifests.get(name)
                    if manifest and manifest.enabled and name not in self._plugin_errors:
                        matches.append((len(keyword), name, action))
        if not matches:
            return None
        _, name, action = max(matches, key=lambda row: row[0])
        return name, action

    def _load_plugin_from_dir(self, name, path):
        key = name.lower()
        try:
            manifest = self._manifests.get(key)
            if manifest is None:
                manifest_path = os.path.join(path, "plugin.json")
                manifest = PluginManifest.from_json_file(manifest_path) if os.path.exists(manifest_path) else None
            module_name = f"plugins.{name}.plugin"
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name != module_name:
                    raise
                module_name = f"plugins.{name}"
                module = importlib.import_module(module_name)
            plugin_class = next((cls for _, cls in inspect.getmembers(module, inspect.isclass)
                                 if issubclass(cls, BasePlugin) and cls is not BasePlugin), None)
            if plugin_class is None:
                raise TypeError(f"No BasePlugin implementation found in '{name}'")
            try:
                sig = inspect.signature(plugin_class.__init__)
                supports_event_bus = (
                    "event_bus" in sig.parameters
                    or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                )
            except (ValueError, TypeError):
                supports_event_bus = True

            if supports_event_bus:
                try:
                    instance = plugin_class(manifest=manifest, config=self.config.get(name, {}), event_bus=self.event_bus)
                except TypeError:
                    instance = plugin_class(manifest=manifest, config=self.config.get(name, {}))
            else:
                instance = plugin_class(manifest=manifest, config=self.config.get(name, {}))
            if hasattr(instance, "event_bus") and not getattr(instance, "event_bus", None) and self.event_bus:
                instance.event_bus = self.event_bus
            if hasattr(instance, "scheduler") and hasattr(instance.scheduler, "event_bus") and not instance.scheduler.event_bus and self.event_bus:
                instance.scheduler.event_bus = self.event_bus
            instance.permission_guard = self.permission_guard
            effective = instance.get_manifest()
            if manifest:
                manifest.actions = effective.actions
                manifest.description = manifest.description or effective.description
                instance.manifest = manifest
            else:
                instance.manifest = effective
            key = instance.manifest.name.lower()
            self._plugins[key] = instance
            self._manifests[key] = instance.manifest
            self._plugin_paths[key], self._plugin_modules[key] = path, module_name
            if instance.manifest.enabled:
                if not instance.initialize():
                    instance.status = PluginStatus.ERROR
                    raise RuntimeError("Initialization hook returned False")
                self._plugin_errors.pop(key, None)
                self._touch_loaded(key)
                self._index_manifest(key, instance.manifest)
            else:
                instance.status = PluginStatus.DISABLED
            return True
        except Exception as exc:
            logger.error("Crash while loading plugin '%s': %s", name, exc, exc_info=True)
            self._plugin_errors[key] = str(exc)
            return False

    def _touch_loaded(self, key):
        self._loaded_lru.pop(key, None)
        self._loaded_lru[key] = time.monotonic()
        while len(self._loaded_lru) > self.max_loaded_plugins:
            victim = next((x for x in self._loaded_lru if x not in self.resident_plugins), None)
            if victim is None:
                break
            self._loaded_lru.pop(victim, None)
            plugin = self._plugins.pop(victim, None)
            if plugin:
                try:
                    plugin.shutdown()
                except Exception:
                    logger.exception("Failed to unload plugin '%s'", victim)

    def register_plugin(self, plugin_instance):
        key = plugin_instance.get_manifest().name.lower()
        try:
            plugin_instance.permission_guard = self.permission_guard
            if not plugin_instance.initialize():
                plugin_instance.status = PluginStatus.ERROR
                self._plugin_errors[key] = "Plugin initialization returned False."
                self._plugins[key] = plugin_instance
                return False
            self._plugins[key] = plugin_instance
            self._manifests[key] = plugin_instance.manifest
            self._index_manifest(key, plugin_instance.manifest)
            self._plugin_errors.pop(key, None)
            self._touch_loaded(key)
            return True
        except Exception as exc:
            self._plugin_errors[key] = str(exc)
            return False

    def get_plugin(self, name):
        key = name.lower()
        plugin = self._plugins.get(key)
        if plugin is None and key in self._manifests:
            self._load_plugin_from_dir(key, self._plugin_paths.get(key, os.path.join(self.plugin_dir, key)))
            plugin = self._plugins.get(key)
        if plugin:
            self._touch_loaded(key)
        return plugin

    def get_all_plugins(self):
        return dict(self._plugins)

    def get_enabled_plugins(self):
        return [p for p in self._plugins.values() if p.status == PluginStatus.ENABLED]

    def get_all_manifests(self):
        return {n: m for n, m in self._manifests.items() if m.enabled and n not in self._plugin_errors}

    def get_catalog(self):
        """Return metadata for UI/diagnostics without forcing implementation loads."""
        return dict(self._manifests)

    def get_available_plugins(self):
        return sorted(self.get_all_manifests())

    def enable_plugin(self, name):
        key = name.lower()
        manifest = self._manifests.get(key)
        if not manifest:
            path = os.path.join(self.plugin_dir, name)
            if not os.path.isdir(path) or not self._discover_plugin(name, path):
                return False, f"Plugin '{name}' not found."
            manifest = self._manifests[key]
        manifest.enabled = True
        plugin = self._plugins.get(key)
        if plugin:
            try:
                if not plugin.initialize():
                    return False, f"Plugin '{name}' initialization failed."
                plugin.status = PluginStatus.ENABLED
            except Exception as exc:
                return False, f"Error enabling plugin '{name}': {exc}"
        self._plugin_errors.pop(key, None)
        return True, f"Plugin '{name}' is now enabled."

    def disable_plugin(self, name):
        key, manifest = name.lower(), self._manifests.get(name.lower())
        if not manifest:
            return False, f"Plugin '{name}' not found."
        manifest.enabled = False
        plugin = self._plugins.get(key)
        if plugin:
            try:
                plugin.shutdown()
                plugin.status = PluginStatus.DISABLED
            except Exception as exc:
                return False, f"Error disabling plugin '{name}': {exc}"
        return True, f"Plugin '{name}' is now disabled."

    def reload_plugin(self, name):
        """
        Safely reloads a plugin in-process with transactional quiescing,
        EventBus subscription cleanup, submodule reloading, and rollback on error.
        """
        key = name.lower()
        old_plugin = self._plugins.get(key)
        old_manifest = self._manifests.get(key)

        # 1. Clean up old EventBus subscriptions for this plugin's modules
        if self.event_bus and hasattr(self.event_bus, "remove_handlers_by_module"):
            self.event_bus.remove_handlers_by_module(f"plugins.{key}")
            if key != name:
                self.event_bus.remove_handlers_by_module(f"plugins.{name}")

        # 2. Clean up old keyword index entries for this plugin
        for kw in list(self._keyword_index.keys()):
            remaining = [item for item in self._keyword_index[kw] if item[0] != key]
            if remaining:
                self._keyword_index[kw] = remaining
            else:
                del self._keyword_index[kw]

        # 3. Graceful shutdown of old plugin instance (quiescing workers/threads)
        if old_plugin:
            try:
                old_plugin.shutdown()
            except Exception as exc:
                logger.warning("Error during shutdown of plugin '%s': %s", name, exc)

        # Remove from active plugins and LRU during reload
        self._plugins.pop(key, None)
        self._loaded_lru.pop(key, None)

        # 4. Reload or purge submodules in sys.modules
        prefixes = (f"plugins.{key}.", f"plugins.{name}.")
        exact_matches = {f"plugins.{key}", f"plugins.{name}"}
        matching_modules = [
            m for m in list(sys.modules.keys())
            if m in exact_matches or any(m.startswith(p) for p in prefixes)
        ]
        # Deeper modules first
        matching_modules.sort(key=lambda x: x.count("."), reverse=True)
        for mod_name in matching_modules:
            try:
                mod_obj = sys.modules.get(mod_name)
                if mod_obj is not None:
                    importlib.reload(mod_obj)
            except Exception:
                # Pop broken or changed modules so they can be freshly imported
                sys.modules.pop(mod_name, None)

        # 5. Load the new plugin from its directory
        path = self._plugin_paths.get(key, os.path.join(self.plugin_dir, name))
        if not os.path.isdir(path):
            if old_plugin:
                self._plugins[key] = old_plugin
                if old_manifest:
                    self._manifests[key] = old_manifest
                    self._index_manifest(key, old_manifest)
            return False, f"Plugin directory not found: {path}"

        try:
            success = self._load_plugin_from_dir(name, path)
            if success:
                new_plugin = self._plugins.get(key)
                if new_plugin:
                    logger.info("Plugin '%s' reloaded successfully with zero downtime.", name)
                    return True, f"Plugin '{name}' reloaded successfully."
                else:
                    raise RuntimeError(f"Plugin '{name}' loaded but instance not found.")
            else:
                err = self._plugin_errors.get(key, "Unknown error")
                raise RuntimeError(err)
        except Exception as exc:
            logger.error("Failed to reload plugin '%s': %s. Preserving previous version.", name, exc)
            if old_plugin:
                try:
                    old_plugin.initialize()
                except Exception:
                    pass
                self._plugins[key] = old_plugin
                if old_manifest:
                    self._manifests[key] = old_manifest
                    self._index_manifest(key, old_manifest)
            return False, f"Failed to reload plugin '{name}': {exc} (previous version preserved)"

    def execute_action(self, plugin_name, action_name, parameters):
        manifest = self._manifests.get(plugin_name.lower())
        if manifest and not manifest.enabled:
            return PluginResult(success=False, error=f"Plugin '{plugin_name}' is currently DISABLED.")
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            return PluginResult(success=False, error=f"Plugin '{plugin_name}' is not registered.")
        action = plugin.manifest.get_action(action_name)
        if action and not self.permission_guard.is_action_allowed(
            plugin_name=plugin_name,
            action_name=action_name,
            required_level=action.required_permission,
        ):
            return PluginResult(
                success=False,
                error=(
                    f"Permission denied for {plugin_name}.{action_name}: "
                    f"requires {action.required_permission.value} access."
                ),
            )
        res = plugin.safe_execute(action_name=action_name, parameters=parameters)
        try:
            from core.logger import JarvisEvent, log_event
            log_event(JarvisEvent.PLUGIN_EXECUTED, {
                "plugin": plugin_name,
                "action": action_name,
                "success": getattr(res, "success", True)
            })
        except Exception:
            pass
        return res

    def print_startup_banner(self):
        print("\nFound plugins:")
        for name, manifest in sorted(self._manifests.items()):
            mode = "lazy" if name not in self._plugins else "loaded"
            print(f"  [+] {manifest.name.capitalize()} ({'Enabled' if manifest.enabled else 'Disabled'}, {mode})")
        for name, error in sorted(self._plugin_errors.items()):
            if name not in self._manifests:
                print(f"  [x] {name.capitalize()} (Error: {error})")
        print("")

    def get_plugin_status_table(self):
        lines = ["=========================================", "             PLUGIN MANAGER              ", "========================================="]
        for name in sorted(set(self._manifests) | set(self._plugin_errors)):
            manifest = self._manifests.get(name)
            display = (manifest.name if manifest else name).capitalize()
            if name in self._plugin_errors:
                status = f"✖ Error ({self._plugin_errors[name]})"
            elif manifest and manifest.enabled:
                status = "● Enabled"
            else:
                status = "○ Disabled"
            lines.append(f"{display:<16} {status}")
        lines.append("=========================================")
        return "\n".join(lines)

    def get_health_report(self) -> Dict[str, Any]:
        """Aggregate health and availability reports across all registered and cataloged plugins."""
        report = {}
        for name in sorted(set(self._manifests) | set(self._plugin_errors)):
            if name in self._plugin_errors:
                report[name] = {
                    "plugin": name,
                    "status": "ERROR",
                    "available": False,
                    "dependencies_met": False,
                    "error": self._plugin_errors[name]
                }
                continue

            manifest = self._manifests.get(name)
            plugin = self._plugins.get(name)
            if plugin and hasattr(plugin, "get_health_status"):
                try:
                    report[name] = plugin.get_health_status()
                except Exception as exc:
                    report[name] = {
                        "plugin": name,
                        "status": "ERROR",
                        "available": False,
                        "error": str(exc)
                    }
            elif manifest:
                report[name] = {
                    "plugin": name,
                    "status": "ENABLED" if manifest.enabled else "DISABLED",
                    "available": manifest.enabled,
                    "version": manifest.version,
                    "actions_count": len(manifest.actions)
                }
        return report

    def get_plugin_health_table(self) -> str:
        """Formatted human-readable health summary for voice or UI status queries."""
        report = self.get_health_report()
        lines = [
            "===========================================================",
            "                 JARVIS PLUGIN HEALTH REPORT               ",
            "==========================================================="
        ]
        for name, info in sorted(report.items()):
            status = info.get("status", "UNKNOWN")
            display = name.capitalize()
            actions = info.get("actions_count", 0)
            if status == "ENABLED":
                badge = "[READY]"
            elif status == "DEGRADED":
                badge = "[DEGRADED]"
            elif status == "DISABLED":
                badge = "[DISABLED]"
            else:
                badge = f"[ERR: {info.get('error', 'ERROR')[:15]}]"
            lines.append(f"{display:<20} {badge:<14} ({actions} actions)")
        lines.append("===========================================================")
        return "\n".join(lines)

    def get_plugins_summary_json(self, query=None, limit=20):
        manifests = list(self.get_all_manifests().items())
        if query:
            words = set(query.lower().split())
            manifests.sort(key=lambda item: sum(bool(words & set(str(k).lower().split()))
                           for action in item[1].actions for k in action.keywords), reverse=True)
            manifests = manifests[:limit]
        summary = [{"plugin": name, "description": manifest.description, "actions": [{
            "action": action.name, "description": action.description, "keywords": action.keywords,
            "parameters": [{"name": p.name, "type": p.type, "required": p.required,
                            "description": p.description} for p in action.parameters]
        } for action in manifest.actions]} for name, manifest in manifests]
        return json.dumps(summary, separators=(",", ":"))

    def shutdown_all(self):
        for name, plugin in list(self._plugins.items()):
            try:
                plugin.shutdown()
            except Exception as exc:
                logger.error("Error shutting down plugin '%s': %s", name, exc)
        self._plugins.clear()
        self._loaded_lru.clear()
