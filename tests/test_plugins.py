# tests/test_plugins.py
import pytest
from unittest.mock import patch
import time
from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginAction, PluginResult
from plugins.manager import PluginManager
from plugins.system import SystemPlugin
from plugins.files import FilesPlugin
from plugins.browser.plugin import BrowserPlugin
from plugins.browser.website_resolver import WebsiteResolver
from brain.semantic_parser import HinglishNLUParser


def test_system_plugin_execution():
    plugin = SystemPlugin()
    assert plugin.initialize() is True

    manifest = plugin.get_manifest()
    assert manifest.name == "system"
    assert len(manifest.actions) >= 2

    res = plugin.execute("get_time", {})
    assert res.success is True
    assert "datetime" in res.data


def test_files_plugin_execution(tmp_path):
    # Create temporary file
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello Jarvis")

    plugin = FilesPlugin()
    plugin.initialize()

    # List dir
    res = plugin.execute("list_dir", {"path": str(tmp_path)})
    assert res.success is True
    assert "hello.txt" in res.data["files"]

    # File info
    info_res = plugin.execute("get_file_info", {"path": str(test_file)})
    assert info_res.success is True
    assert info_res.data["size_bytes"] > 0


def test_plugin_manager_registration():
    mgr = PluginManager()
    sys_plugin = SystemPlugin()
    assert mgr.register_plugin(sys_plugin) is True

    manifests = mgr.get_all_manifests()
    assert "system" in manifests

    res = mgr.execute_action("system", "get_time", {})
    assert res.success is True


def test_unknown_open_target_routes_to_generic_website_resolver():
    action = HinglishNLUParser.parse("open acmesample")
    assert action is not None
    assert action.service == "browser"
    assert action.action == "open_website"
    assert action.parameters == {"site": "acmesample"}


def test_website_resolver_uses_explicit_domains_and_canonical_destinations():
    direct_url, direct = BrowserPlugin.resolve_website_url("example.com")
    assert direct is True
    assert direct_url == "https://example.com/"

    resolved_url, direct = BrowserPlugin.resolve_website_url("acmesample")
    assert direct is False
    assert resolved_url == ""

    dhan_url, direct = BrowserPlugin.resolve_website_url("dhan")
    assert direct is True
    assert dhan_url == "https://dhan.co/"

    instagram_url, direct = BrowserPlugin.resolve_website_url("instagram")
    assert direct is True
    assert instagram_url == "https://www.instagram.com/"


def test_browser_refuses_to_guess_an_unknown_brand_domain():
    plugin = BrowserPlugin()
    plugin.connectivity._cached_status = True
    plugin.connectivity._last_checked = time.time()
    with patch("webbrowser.open") as open_browser:
        result = plugin.execute("open_website", {"site": "acmesample"})
    assert result.success is False
    assert "URL confirm" in result.error
    open_browser.assert_not_called()


def test_instagram_opens_official_url_and_reports_browser_failure():
    plugin = BrowserPlugin()
    plugin.connectivity._cached_status = True
    plugin.connectivity._last_checked = time.time()

    with patch("webbrowser.open", return_value=True) as open_browser:
        result = plugin.execute("open_website", {"site": "instagram"})
    assert result.success is True
    open_browser.assert_called_once_with("https://www.instagram.com/")

    with patch("webbrowser.open", return_value=False):
        failed = plugin.execute("open_website", {"site": "instagram"})
    assert failed.success is False
    assert "accept nahi ki" in failed.error


def test_flipkart_open_is_always_direct_and_logs_resolution(caplog):
    action = HinglishNLUParser.parse("Flipkart open karo")
    assert action is not None
    assert action.action == "open_website"

    plugin = BrowserPlugin()
    plugin.connectivity._cached_status = True
    plugin.connectivity._last_checked = time.time()
    with patch("webbrowser.open", return_value=True) as navigate, caplog.at_level("INFO"):
        result = plugin.execute("open_website", action.parameters)

    assert result.success is True
    assert result.data["url"] == "https://www.flipkart.com/"
    navigate.assert_called_once_with("https://www.flipkart.com/")
    assert "google.com/url" not in result.data["url"]
    for event in ("WEBSITE_QUERY", "URL_RESOLVED", "REDIRECT_UNWRAPPED", "FINAL_URL", "BROWSER_NAVIGATE"):
        assert event in caplog.text


@pytest.mark.parametrize(
    ("brand", "url"),
    [
        ("flipkart", "https://www.flipkart.com/"),
        ("amazon", "https://www.amazon.in/"),
        ("youtube", "https://www.youtube.com/"),
        ("gmail", "https://mail.google.com/"),
        ("google", "https://www.google.com/"),
        ("facebook", "https://www.facebook.com/"),
        ("instagram", "https://www.instagram.com/"),
        ("linkedin", "https://www.linkedin.com/"),
        ("reddit", "https://www.reddit.com/"),
        ("github", "https://github.com/"),
        ("microsoft", "https://www.microsoft.com/"),
        ("dhan", "https://dhan.co/"),
    ],
)
def test_common_sites_have_canonical_direct_urls(brand, url):
    assert WebsiteResolver.resolve(brand).final_url == url


def test_redirect_unwrap_tracking_cleanup_and_duplicate_slashes():
    wrapped = (
        "https://www.google.com/url?q="
        "https%3A%2F%2Fwww.flipkart.com%2F%2Fmobiles%3Futm_source%3Dgoogle%26pid%3D123"
    )
    result = WebsiteResolver.resolve(wrapped)
    assert result.redirect_unwrapped is True
    assert result.final_url == "https://www.flipkart.com/mobiles?pid=123"


def test_explicit_brand_search_remains_a_search_action():
    action = HinglishNLUParser.parse("Flipkart search karo")
    assert action is not None
    assert action.service == "browser"
    assert action.action == "search_google"
    assert action.parameters == {"query": "flipkart"}
