# plugins/archify/plugin.py
"""
Archify Plugin for Jarvis V2.1.
Renders and displays the complete interactive Archify architecture visualization of the Jarvis system.
"""

import logging
import os
import webbrowser
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS

logger = logging.getLogger("jarvis.plugins.archify")


class ArchifyPlugin(BasePlugin):
    """
    Archify Architecture Viewer Plugin.
    Opens the self-contained interactive Archify viewer for the Jarvis project.
    """

    def __init__(
        self,
        manifest: Optional[PluginManifest] = None,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(manifest=manifest, config=config, event_bus=event_bus, **kwargs)
        self.arch_html_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "jarvis-architecture.html")
        )

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="archify",
            version="1.0.0",
            description="Interactive Archify architecture visualization viewer for Jarvis V2.1.",
            author="Jarvis Team",
            permissions=["filesystem", "process"],
            actions=ACTIONS,
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        try:
            if action_name in ("show_architecture", "open_archify", "display_archify"):
                # Ensure the architecture diagram is synced with latest specifications
                try:
                    from plugins.archify.builder import compile_archify_html
                    compile_archify_html(html_path=self.arch_html_path)
                except Exception as sync_err:
                    logger.debug("Archify pre-launch sync notice: %s", sync_err)

                if not os.path.isfile(self.arch_html_path):
                    return PluginResult(
                        success=False,
                        error=f"Architecture viewer file not found at {self.arch_html_path}",
                    )

                # Start the background live server & watcher for instant auto-reload
                view_target = parameters.get("target")
                url = None
                try:
                    from plugins.archify.server import get_archify_server
                    server = get_archify_server()
                    server.start()
                    if server.is_running():
                        url = server.get_url(target_view=view_target)
                except Exception as srv_err:
                    logger.warning("Could not launch Archify live server: %s", srv_err)

                # Fallback to local file URL if server is unavailable
                if not url:
                    url = f"file:///{self.arch_html_path.replace(os.sep, '/')}"
                    if view_target:
                        url += f"#view={view_target}"

                # Open via webbrowser / os.startfile on Windows
                try:
                    if url.startswith("http://"):
                        webbrowser.open(url)
                    elif hasattr(os, "startfile"):
                        os.startfile(self.arch_html_path)
                    else:
                        webbrowser.open(url)
                except Exception as open_err:
                    logger.warning("os.startfile failed, falling back to webbrowser.open: %s", open_err)
                    webbrowser.open(url)

                msg = "Jarvis ka live interactive Archify viewer open kar diya hai. Auto-update active hai, Boss."
                return PluginResult(
                    success=True,
                    data={
                        "message": msg,
                        "file_path": self.arch_html_path,
                        "url": url,
                        "status": "displayed",
                        "live_auto_update": True,
                    },
                )

            elif action_name == "sync_architecture":
                from plugins.archify.builder import sync_architecture_changes
                ok, msg = sync_architecture_changes()
                return PluginResult(
                    success=ok,
                    data={"message": msg, "status": "synced" if ok else "failed"},
                    error=None if ok else msg,
                )

            else:
                return PluginResult(
                    success=False,
                    error=f"Unknown action '{action_name}' for Archify Plugin.",
                )

        except Exception as e:
            logger.error("Error executing Archify action '%s': %s", action_name, e, exc_info=True)
            return PluginResult(
                success=False,
                error=f"Archify execution failed: {e}",
            )
