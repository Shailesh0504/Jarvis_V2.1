# gui/plugins.py
"""Plugin manager GUI controller and state bridge."""

from typing import Any, Dict, List, Optional
from core.app import JarvisCore
from plugins.manifest import PluginStatus


class PluginsPanel:
    """Provides plugin data and toggling operations for the UI."""

    def __init__(self, core: Optional[JarvisCore] = None):
        self.core = core

    def set_core(self, core: JarvisCore) -> None:
        self.core = core

    def get_plugin_list(self) -> List[Dict[str, Any]]:
        """Returns structured plugin list for GUI data grids / lists."""
        if not self.core or not self.core.plugin_manager:
            return []

        mgr = self.core.plugin_manager
        all_names = sorted(set(list(mgr._plugins.keys()) + list(mgr._plugin_errors.keys())))
        results = []
        for name in all_names:
            plugin = mgr._plugins.get(name)
            error_msg = mgr._plugin_errors.get(name)

            if plugin:
                status = plugin.status.value
                display_name = plugin.manifest.name.capitalize()
                version = plugin.manifest.version
                desc = plugin.manifest.description
                perms = plugin.manifest.permissions
                actions_count = len(plugin.manifest.actions)
            else:
                status = PluginStatus.ERROR.value
                display_name = name.capitalize()
                version = "unknown"
                desc = "Failed to load plugin"
                perms = []
                actions_count = 0

            results.append({
                "id": name,
                "name": display_name,
                "version": version,
                "description": desc,
                "status": status,
                "is_enabled": status == PluginStatus.ENABLED.value,
                "permissions": perms,
                "actions_count": actions_count,
                "error": error_msg
            })
        return results

    def toggle_plugin(self, plugin_id: str, enable: bool) -> Dict[str, Any]:
        """Toggles a plugin on or off."""
        if not self.core or not self.core.plugin_manager:
            return {"success": False, "message": "Plugin Manager is not connected."}

        mgr = self.core.plugin_manager
        if enable:
            success, msg = mgr.enable_plugin(plugin_id)
        else:
            success, msg = mgr.disable_plugin(plugin_id)

        return {"success": success, "message": msg}

    def reload_plugin(self, plugin_id: str) -> Dict[str, Any]:
        if not self.core or not self.core.plugin_manager:
            return {"success": False, "message": "Plugin Manager is not connected."}

        success, msg = self.core.plugin_manager.reload_plugin(plugin_id)
        return {"success": success, "message": msg}
