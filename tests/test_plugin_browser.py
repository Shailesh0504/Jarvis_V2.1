# tests/test_plugin_browser.py
import pytest
from unittest.mock import patch, MagicMock
from plugins.browser.plugin import BrowserPlugin


@pytest.fixture
def browser_plugin(tmp_path):
    plugin = BrowserPlugin()
    plugin._get_bookmarks_path = lambda: str(tmp_path / "browser_bookmarks.json")
    return plugin


def test_browser_parse_url(browser_plugin):
    url = "https://www.example.com:8080/search?q=test+query&lang=en#results"
    res = browser_plugin.execute("parse_url", {"url": url})
    assert res.success is True
    assert res.data["scheme"] == "https"
    assert res.data["netloc"] == "www.example.com:8080"
    assert res.data["hostname"] == "www.example.com"
    assert res.data["port"] == 8080
    assert res.data["path"] == "/search"
    assert res.data["query_params"]["q"] == "test query"
    assert res.data["query_params"]["lang"] == "en"
    assert res.data["fragment"] == "results"
    assert res.data["is_secure"] is True


def test_browser_build_url(browser_plugin):
    res = browser_plugin.execute("build_url", {
        "base_url": "https://api.github.com",
        "path": "repos/owner/repo/issues",
        "params": {"state": "open", "sort": "created"},
        "fragment": "issue-12"
    })
    assert res.success is True
    constructed = res.data["url"]
    assert constructed.startswith("https://api.github.com/repos/owner/repo/issues?")
    assert "state=open" in constructed
    assert "sort=created" in constructed
    assert constructed.endswith("#issue-12")


def test_browser_bookmarks(browser_plugin):
    # Save bookmarks
    r1 = browser_plugin.execute("save_bookmark", {
        "url": "https://github.com",
        "title": "GitHub",
        "category": "Development"
    })
    assert r1.success is True

    r2 = browser_plugin.execute("save_bookmark", {
        "url": "https://news.ycombinator.com",
        "title": "Hacker News",
        "category": "Tech News"
    })
    assert r2.success is True

    # List bookmarks
    list_all = browser_plugin.execute("list_bookmarks", {})
    assert list_all.success is True
    assert list_all.data["count"] == 2

    # Filter by category
    list_cat = browser_plugin.execute("list_bookmarks", {"category": "Development"})
    assert list_cat.success is True
    assert list_cat.data["count"] == 1
    assert list_cat.data["bookmarks"][0]["title"] == "GitHub"

    # Filter by query
    list_q = browser_plugin.execute("list_bookmarks", {"query": "Hacker"})
    assert list_q.success is True
    assert list_q.data["count"] == 1
    assert list_q.data["bookmarks"][0]["url"] == "https://news.ycombinator.com"

    # Delete bookmark
    del_res = browser_plugin.execute("delete_bookmark", {"url_or_title": "GitHub"})
    assert del_res.success is True
    assert del_res.data["removed_count"] == 1
    assert del_res.data["remaining_count"] == 1


def test_browser_info_and_cache(browser_plugin):
    # Detect installed browsers
    info_res = browser_plugin.execute("get_browser_info", {})
    assert info_res.success is True
    assert "browsers" in info_res.data
    assert "Microsoft Edge" in info_res.data["browsers"]

    # Cache info
    cache_res = browser_plugin.execute("clear_browser_cache_info", {"browser": "edge"})
    assert cache_res.success is True
    assert "edge" in cache_res.data["cache_locations"]


def test_browser_network_features(browser_plugin):
    # Test reachability with mock
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.headers = {"Content-Type": "text/html"}
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        reach_res = browser_plugin.execute("check_url_reachable", {"url": "https://example.com"})
        assert reach_res.success is True
        assert reach_res.data["reachable"] is True
        assert reach_res.data["status_code"] == 200

    # Test metadata extraction with mock html
    mock_html = MagicMock()
    mock_html.read.return_value = b"<html><head><title>Example Domain</title><meta name='description' content='This domain is for examples.'></head><body></body></html>"
    mock_html.__enter__.return_value = mock_html
    with patch("urllib.request.urlopen", return_value=mock_html):
        meta_res = browser_plugin.execute("extract_page_metadata", {"url": "https://example.com"})
        assert meta_res.success is True
        assert meta_res.data["title"] == "Example Domain"
        assert meta_res.data["description"] == "This domain is for examples."


def test_browser_incognito(browser_plugin):
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        with patch.object(browser_plugin, "_detect_installed_browsers", return_value={"Microsoft Edge": {"path": "msedge.exe", "installed": True}}):
            incog_res = browser_plugin.execute("open_incognito", {"url": "https://duckduckgo.com"})
            assert incog_res.success is True
            assert incog_res.data["browser"] == "Microsoft Edge"
            mock_popen.assert_called_once()
