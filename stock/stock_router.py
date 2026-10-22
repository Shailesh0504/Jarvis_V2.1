# stock/stock_router.py
"""
HTTP Router and Web Server for Stock Query Wizard & REST API.
Hosts endpoints:
  - GET / or /wizard: Serves responsive financial dashboard UI
  - POST /api/stocks/analyze: Validates criteria and returns shortlisted candidates
  - GET /api/stocks/status: Returns market status and data timestamp
  - GET /api/stocks/profile: Returns active user profile and parameters
  - GET /api/stocks/workflow/state: Returns current workflow state
  - POST /api/stocks/workflow/complete: Receives completion event from UI
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import socket
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
from pydantic import ValidationError
from .stock_models import StockQueryParams
from .stock_service import StockService

logger = logging.getLogger("jarvis.stock.router")
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


class StockRequestHandler(BaseHTTPRequestHandler):
    """Custom HTTP Request Handler serving wizard frontend and REST API."""

    def _send_json(self, data: Any, status_code: int = 200) -> None:
        """Helper to send JSON response with CORS headers."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: str, content_type: str = "text/html; charset=utf-8") -> None:
        """Helper to serve static HTML/CSS/JS file."""
        if not os.path.exists(file_path):
            self.send_error(404, f"File not found: {os.path.basename(file_path)}")
            return
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Route GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/wizard", "/index.html"):
            index_path = os.path.join(UI_DIR, "index.html")
            self._send_file(index_path, "text/html; charset=utf-8")
            return

        service = StockService.get_instance()

        if path == "/api/stocks/status":
            now_dt = service.screener.data_provider.get_current_time_ist()
            status, session = service.screener.data_provider.get_market_status()
            idx = service.screener.data_provider.get_index_metrics()
            self._send_json({
                "market_status": status.value if hasattr(status, "value") else str(status),
                "last_session": session,
                "timestamp": now_dt.strftime("%d %b %Y, %H:%M IST"),
                "indices": idx,
            })
            return

        if path == "/api/stocks/profile":
            prof = service.equity_manager.get_profile()
            self._send_json({
                "investment_amount": prof.investment_amount,
                "risk_tolerance": prof.risk_tolerance.value if hasattr(prof.risk_tolerance, "value") else str(prof.risk_tolerance),
                "sector_preferences": prof.sector_preferences,
                "active_params": service.active_params,
            })
            return

        if path == "/api/stocks/workflow/state":
            state = service.get_workflow_state()
            self._send_json(state.model_dump())
            return

        if path == "/api/stocks/history":
            recs = service.get_recommendation_history(limit=50)
            self._send_json({"success": True, "recommendations": [r.model_dump() for r in recs]})
            return

        if path == "/api/stocks/history/latest":
            latest = service.history_db.get_latest_recommendation()
            if latest:
                self._send_json({"success": True, "recommendation": latest.model_dump()})
            else:
                self._send_json({"success": False, "recommendation": None, "message": "No historical recommendations found"})
            return

        if path.startswith("/api/stocks/recommendation/"):
            rec_id = path.replace("/api/stocks/recommendation/", "").strip()
            detail = service.get_recommendation_detail(rec_id)
            if detail:
                self._send_json({"success": True, **detail})
            else:
                self._send_json({"success": False, "error": f"Recommendation '{rec_id}' not found"}, 404)
            return

        self.send_error(404, f"Endpoint {path} not found")

    def do_POST(self) -> None:
        """Route POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        service = StockService.get_instance()

        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except json.JSONDecodeError:
            self._send_json({"success": False, "error": "Invalid JSON format"}, 400)
            return

        if path.startswith("/api/stocks/recommendation/") and path.endswith("/track"):
            parts = path.split("/")
            if len(parts) >= 5:
                rec_id = parts[4]
                try:
                    price = float(payload.get("price") or 0.0)
                    source = payload.get("source", "NSE_LIVE")
                    data_ts = payload.get("data_timestamp", "")
                    rec, perf, evt = service.track_live_price(rec_id, current_price=price, source=source, data_timestamp=data_ts)
                    self._send_json({
                        "success": True,
                        "recommendation": rec.model_dump() if rec else None,
                        "performance": perf.model_dump() if perf else None,
                        "event": evt.model_dump() if evt else None,
                    }, 200)
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)}, 400)
                return

        if path == "/api/stocks/analyze":
            try:
                response = service.analyze(payload)
                self._send_json(response.model_dump(), 200)
            except ValidationError as ve:
                errors = ve.errors()
                err_msg = "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errors])
                clean_details = [
                    {"loc": [str(x) for x in e.get("loc", [])], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
                    for e in errors
                ]
                self._send_json({
                    "success": False,
                    "error": f"Validation Error: {err_msg}",
                    "details": clean_details,
                }, 422)
            except Exception as e:
                logger.error(f"Error during stock analysis: {e}", exc_info=True)
                self._send_json({"success": False, "error": f"Analysis failed: {str(e)}"}, 500)
            return

        if path == "/api/stocks/workflow/complete":
            service.complete_workflow()
            self._send_json({"success": True, "message": "Workflow marked complete"})
            return

        if path == "/api/stocks/workflow/update":
            key = payload.get("key")
            val = payload.get("value")
            if key:
                updated = service.update_active_param(key, val)
                self._send_json({"success": True, "active_params": updated})
            else:
                self._send_json({"success": False, "error": "Missing key"}, 400)
            return

        self.send_error(404, f"Endpoint {path} not found")

    def log_message(self, format: str, *args: Any) -> None:
        """Silence normal HTTP logging to avoid cluttering stdout."""
        pass


class StockWebServer:
    """Thread-safe background web server hosting the Stock Query Wizard."""

    _instance: Optional["StockWebServer"] = None
    _server_lock = threading.Lock()

    def __init__(self, port: int = 8765):
        self.port = port
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    @classmethod
    def get_instance(cls, port: int = 8765) -> "StockWebServer":
        with cls._server_lock:
            if cls._instance is None:
                cls._instance = cls(port=port)
            return cls._instance

    @staticmethod
    def _find_free_port(start_port: int = 8765, max_attempts: int = 20) -> int:
        """Finds an available local port starting from start_port."""
        for p in range(start_port, start_port + max_attempts):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        return start_port

    def start(self) -> str:
        """Starts the server in a background daemon thread if not already running."""
        with self._server_lock:
            if self.is_running and self.server:
                return f"http://127.0.0.1:{self.port}/wizard"

            free_port = self._find_free_port(self.port)
            self.port = free_port

            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", self.port), StockRequestHandler)
                self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.thread.start()
                self.is_running = True
                logger.info(f"Stock Query Wizard server started on http://127.0.0.1:{self.port}/wizard")
            except Exception as e:
                logger.error(f"Failed to start StockWebServer on port {self.port}: {e}")
                raise

            return f"http://127.0.0.1:{self.port}/wizard"

    def stop(self) -> None:
        """Stops the server gracefully."""
        with self._server_lock:
            if self.server and self.is_running:
                self.server.shutdown()
                self.server.server_close()
                self.is_running = False
                logger.info("Stock Query Wizard server stopped.")

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/wizard"
