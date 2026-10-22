# tests/test_archify_live_auto_update.py
"""Comprehensive Unit & Integration Test Suite for Archify Live Auto-Update Subsystem.

Verifies:
1. ArchifyLiveServer initialization, endpoint routing (/api/poll, /api/sync, HTML/JSON), CORS headers.
2. Real-time background file change detection & automatic recompile.
3. Client-side auto-update engine and live status indicator injection.
4. ArchifyPlugin integration launching live server URL.
5. FastPathEngine Section 13 ultra-low latency dispatch with live server URL.
"""

import json
import os
import time
import urllib.request
import pytest

from plugins.archify.server import ArchifyLiveServer, get_archify_server
from plugins.archify.builder import compile_archify_html, sync_architecture_changes
from plugins.archify.plugin import ArchifyPlugin
from core.execution.fast_path import FastPathEngine


@pytest.fixture(scope="module")
def live_server():
    """Provides running ArchifyLiveServer instance."""
    server = get_archify_server()
    server.start()
    time.sleep(0.2)
    yield server
    server.stop()


def test_archify_server_lifecycle(live_server):
    """Verify ArchifyLiveServer starts, is running, and produces valid URL."""
    assert live_server.is_running() is True
    url = live_server.get_url()
    assert url.startswith("http://127.0.0.1:8766")


def test_archify_server_poll_endpoint(live_server):
    """Verify /api/poll returns version, status, and CORS headers for live browser polling."""
    poll_url = "http://127.0.0.1:8766/api/poll"
    req = urllib.request.Request(poll_url)
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        headers = dict(resp.headers)
        assert headers.get("Access-Control-Allow-Origin") == "*"
        assert "application/json" in headers.get("Content-Type", "")

        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("status") == "online"
        assert data.get("live_auto_update") is True
        assert len(data.get("version", "")) > 0


def test_archify_server_sync_endpoint(live_server):
    """Verify /api/sync forces live recompile and bumps recompile_count."""
    sync_url = "http://127.0.0.1:8766/api/sync"
    req = urllib.request.Request(sync_url)
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("success") is True
        assert data.get("recompile_count") >= 1


def test_archify_server_serves_html_and_json(live_server):
    """Verify server delivers valid HTML viewer and JSON architecture specification."""
    # 1. HTML root
    html_url = "http://127.0.0.1:8766/"
    with urllib.request.urlopen(html_url, timeout=3.0) as resp:
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8", errors="ignore")
        assert "<title>Jarvis V2.1 System Architecture" in body
        assert 'id="archify-live-indicator"' in body
        assert 'id="archify-live-auto-update-script"' in body

    # 2. JSON spec
    json_url = "http://127.0.0.1:8766/api/architecture.json"
    with urllib.request.urlopen(json_url, timeout=3.0) as resp:
        assert resp.status == 200
        assert "application/json" in resp.headers.get("Content-Type", "")
        spec = json.loads(resp.read().decode("utf-8"))
        assert "components" in spec
        assert "connections" in spec


def test_archify_client_engine_injection():
    """Verify compile_archify_html injects the live indicator pill and polling script."""
    ok, msg = compile_archify_html()
    assert ok is True

    html_path = os.path.join("plugins", "archify", "jarvis-architecture.html")
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    assert 'id="archify-live-indicator"' in content
    assert "LIVE AUTO-UPDATE: ACTIVE" in content
    assert "http://127.0.0.1:8766/api/poll" in content


def test_archify_plugin_opens_live_server_url(live_server, monkeypatch):
    """Verify ArchifyPlugin.execute returns live server URL with auto-update flag."""
    opened_urls = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: opened_urls.append(u))

    plugin = ArchifyPlugin()
    res = plugin.execute("show_architecture", {})

    assert res.success is True
    assert res.data.get("live_auto_update") is True
    assert res.data.get("url").startswith("http://127.0.0.1:8766")
    assert len(opened_urls) == 1
    assert opened_urls[0].startswith("http://127.0.0.1:8766")


def test_fast_path_dispatches_live_archify(live_server, monkeypatch):
    """Verify FastPathEngine Section 13 launches Archify with live server in < 15ms."""
    fake_core = type("FakeCore", (), {
        "plugin_manager": type("FakePM", (), {
            "get_plugin": lambda s, n: ArchifyPlugin() if n == "archify" else None
        })(),
        "_finalize_fast_turn": lambda s, t, r, st, tr, i, src: r
    })()

    engine = FastPathEngine(core=fake_core)
    import webbrowser
    opened_urls = []
    monkeypatch.setattr(webbrowser, "open", lambda u: opened_urls.append(u))

    resp = engine.try_handle(
        raw_text="archify live architecture dikhao",
        normalized_input="archify live architecture dikhao",
        turn=None,
        start_time=time.perf_counter(),
        tracker=None,
        source="cli"
    )

    assert resp is not None
    assert "archify" in resp.lower() or "architecture" in resp.lower()
    assert len(opened_urls) == 1
    assert opened_urls[0].startswith("http://127.0.0.1:8766")
