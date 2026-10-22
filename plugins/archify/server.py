# plugins/archify/server.py
"""Archify Live Auto-Update Server & Background File Watcher for Jarvis V2.1.

Provides zero-dependency, local-first live server (127.0.0.1:8766) that:
1. Serves the interactive Archify architecture visualization (HTML/JSON) with no-cache headers.
2. Watches architecture.txt and jarvis-architecture.json continuously.
3. Automatically triggers compile_archify_html() upon any file change.
4. Exposes /api/poll and /api/sync endpoints with CORS headers for live browser auto-reload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.plugins.archify.server")

DEFAULT_PORT = 8766
DEFAULT_HOST = "127.0.0.1"


def compute_file_hash(file_path: str) -> str:
    """Computes SHA-256 hash or mtime fallback for change detection."""
    if not os.path.isfile(file_path):
        return ""
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        try:
            return str(os.path.getmtime(file_path))
        except Exception:
            return ""


class ArchifyHTTPHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for live Archify visualization and auto-reload polling."""

    server_instance: Optional[ArchifyLiveServer] = None

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress routine GET logging to keep console clean
        pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Cache-Control")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        srv = self.server_instance
        if not srv:
            self.send_error(500, "Server instance unavailable")
            return

        path = self.path.split("?")[0].rstrip("/")

        # 1. API: Live Poll & Version Check
        if path in ("/api/poll", "/api/version"):
            payload = {
                "status": "online",
                "version": srv.current_version,
                "timestamp": time.time(),
                "live_auto_update": True,
                "server_uptime_sec": round(time.time() - srv.start_time, 1),
                "recompile_count": srv.recompile_count,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 2. API: Manual Sync & Recompile Trigger
        if path == "/api/sync":
            ok, msg = srv.force_sync()
            payload = {
                "success": ok,
                "message": msg,
                "version": srv.current_version,
                "recompile_count": srv.recompile_count,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 3. Serve jarvis-architecture.json
        if path in ("/jarvis-architecture.json", "/api/architecture.json"):
            json_file = srv.arch_json_path
            if os.path.isfile(json_file):
                try:
                    with open(json_file, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self._send_cors_headers()
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self.send_error(500, f"Error reading json: {e}")
                    return
            else:
                self.send_error(404, "Architecture JSON not found")
                return

        # 4. Serve jarvis-architecture.html (Root or direct)
        if path in ("", "/", "/jarvis-architecture.html"):
            html_file = srv.arch_html_path
            if os.path.isfile(html_file):
                try:
                    with open(html_file, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self._send_cors_headers()
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self.send_error(500, f"Error reading html: {e}")
                    return
            else:
                self.send_error(404, "Architecture HTML viewer not found")
                return

        # Fallback 404
        self.send_error(404, "Not Found")


class ArchifyLiveServer:
    """Singleton background server providing live auto-updating Archify visualization."""

    _instance: Optional[ArchifyLiveServer] = None
    _lock = threading.RLock()

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        project_root: str = ".",
    ):
        self.host = host
        self.port = port
        self.project_root = os.path.abspath(project_root)
        self.arch_html_path = os.path.join(self.project_root, "plugins", "archify", "jarvis-architecture.html")
        self.arch_json_path = os.path.join(self.project_root, "plugins", "archify", "jarvis-architecture.json")
        self.arch_txt_path = os.path.join(self.project_root, "architecture.txt")

        self.http_server: Optional[ThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.watcher_thread: Optional[threading.Thread] = None
        self._running = False

        self.start_time = time.time()
        self.recompile_count = 0
        self.last_txt_mtime = self._get_mtime(self.arch_txt_path)
        self.last_json_mtime = self._get_mtime(self.arch_json_path)
        self.current_version = self._calculate_current_version()

    @classmethod
    def get_instance(cls, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ArchifyLiveServer:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(host=host, port=port)
            return cls._instance

    @staticmethod
    def _get_mtime(path: str) -> float:
        try:
            return os.path.getmtime(path) if os.path.isfile(path) else 0.0
        except Exception:
            return 0.0

    def _calculate_current_version(self) -> str:
        """Generates unified version hash across architecture.txt and json spec."""
        h1 = compute_file_hash(self.arch_json_path)
        h2 = compute_file_hash(self.arch_html_path)
        txt_mtime = str(self._get_mtime(self.arch_txt_path))
        raw = f"{h1}:{h2}:{txt_mtime}:{self.recompile_count}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]

    def start(self) -> bool:
        """Starts the live HTTP server and file watcher in background daemon threads."""
        with self._lock:
            if self._running and self.http_server:
                return True

            try:
                ArchifyHTTPHandler.server_instance = self
                self.http_server = ThreadingHTTPServer((self.host, self.port), ArchifyHTTPHandler)
                self._running = True

                self.server_thread = threading.Thread(
                    target=self.http_server.serve_forever,
                    name="ArchifyLiveHTTPServer",
                    daemon=True,
                )
                self.server_thread.start()

                self.watcher_thread = threading.Thread(
                    target=self._file_watcher_loop,
                    name="ArchifyLiveFileWatcher",
                    daemon=True,
                )
                self.watcher_thread.start()

                logger.info(
                    "Archify Live Auto-Update Server active at http://%s:%d/ (Auto-Watcher active)",
                    self.host,
                    self.port,
                )
                return True

            except OSError as e:
                if e.errno == 10048 or "Address already in use" in str(e):
                    logger.info("Archify Live Server port %d is already in use by active instance.", self.port)
                    self._running = True
                    return True
                logger.warning("Could not bind Archify Live Server on %s:%d: %s", self.host, self.port, e)
                return False
            except Exception as e:
                logger.error("Failed to start Archify Live Server: %s", e, exc_info=True)
                return False

    def stop(self) -> None:
        """Gracefully terminates the live server and watcher."""
        with self._lock:
            self._running = False
            if self.http_server:
                try:
                    self.http_server.shutdown()
                    self.http_server.server_close()
                except Exception:
                    pass
                self.http_server = None
            logger.info("Archify Live Server stopped.")

    def is_running(self) -> bool:
        return self._running and self.http_server is not None

    def get_url(self, target_view: Optional[str] = None) -> str:
        """Returns the live browser URL with optional view parameter."""
        url = f"http://{self.host}:{self.port}/"
        if target_view:
            url += f"#view={target_view}"
        return url

    def force_sync(self) -> Tuple[bool, str]:
        """Manually forces re-compilation of Archify HTML viewer."""
        try:
            from plugins.archify.builder import compile_archify_html
            ok, msg = compile_archify_html(
                json_path=self.arch_json_path,
                html_path=self.arch_html_path,
            )
            if ok:
                self.recompile_count += 1
                self.current_version = self._calculate_current_version()
                logger.info("[ArchifyLiveServer] Recompiled successfully (Version: %s)", self.current_version)
            return ok, msg
        except Exception as e:
            logger.error("[ArchifyLiveServer] Error in force_sync: %s", e)
            return False, str(e)

    def _file_watcher_loop(self) -> None:
        """Continuous background loop checking for changes to architecture specs."""
        while self._running:
            try:
                time.sleep(1.0)
                cur_txt_mtime = self._get_mtime(self.arch_txt_path)
                cur_json_mtime = self._get_mtime(self.arch_json_path)

                changed = False
                if cur_txt_mtime > self.last_txt_mtime:
                    self.last_txt_mtime = cur_txt_mtime
                    changed = True

                if cur_json_mtime > self.last_json_mtime:
                    self.last_json_mtime = cur_json_mtime
                    changed = True

                if changed:
                    logger.info("[ArchifyLiveServer] Detected change on disk. Auto-compiling live architecture...")
                    self.force_sync()

            except Exception as e:
                logger.debug("Archify watcher loop note: %s", e)


def get_archify_server() -> ArchifyLiveServer:
    """Convenience accessor for ArchifyLiveServer singleton."""
    return ArchifyLiveServer.get_instance()
