# tests/test_network_speed.py
"""Network speed-test NLU routing and response regression tests."""

from brain.semantic_parser import HinglishNLUParser
from plugins.network.plugin import NetworkPlugin


def test_hinglish_internet_speed_queries_route_to_network_plugin():
    for query in (
        "internet ki speed kitani hai",
        "wifi speed check karo",
        "speed test chalao",
        "download speed kya hai",
    ):
        action = HinglishNLUParser.parse(query)
        assert action is not None
        assert action.service == "network"
        assert action.action == "measure_speed"


def test_network_speed_returns_natural_structured_result(monkeypatch):
    plugin = NetworkPlugin()
    monkeypatch.setattr(plugin, "_measure_latency_ms", lambda: 18.4)
    monkeypatch.setattr(plugin, "_measure_download_mbps", lambda: 92.75)
    monkeypatch.setattr(plugin, "_measure_upload_mbps", lambda: 31.25)

    result = plugin.execute("measure_speed", {})

    assert result.success is True
    assert result.data["download_mbps"] == 92.8
    assert result.data["upload_mbps"] == 31.2
    assert result.data["ping_ms"] == 18.4
    assert "92.8 Mbps download" in result.data["message"]
    assert "31.2 Mbps upload" in result.data["message"]
    assert "http" not in result.data["message"]


def test_wifi_password_query_routes_to_secure_clipboard_action():
    action = HinglishNLUParser.parse("wifi ka password batao")

    assert action is not None
    assert action.service == "network"
    assert action.action == "copy_wifi_password"
    assert action.parameters["ssid"] == ""


def test_wifi_password_is_copied_but_never_returned_or_logged(monkeypatch):
    plugin = NetworkPlugin()
    copied = []
    secret = "SuperSecret123"
    monkeypatch.setattr(plugin, "_get_connected_wifi_ssid", lambda: "Home WiFi")
    monkeypatch.setattr(plugin, "_get_saved_wifi_password", lambda _ssid: secret)
    monkeypatch.setattr(plugin, "_copy_secret_to_clipboard", copied.append)

    result = plugin.execute("copy_wifi_password", {})

    assert result.success is True
    assert copied == [secret]
    assert secret not in result.data["message"]
    assert "clipboard" in result.data["message"].lower()
    assert result.data["sensitive_display"]["items"] == [
        {"ssid": "Home WiFi", "password": secret}
    ]


def test_all_saved_wifi_passwords_use_sensitive_display_channel(monkeypatch):
    plugin = NetworkPlugin()
    monkeypatch.setattr(plugin, "_get_saved_wifi_profiles", lambda: ["Home", "Office"])
    monkeypatch.setattr(plugin, "_get_saved_wifi_password", lambda ssid: {"Home": "HomeSecret", "Office": "OfficeSecret"}[ssid])

    result = plugin.execute("list_saved_wifi_passwords", {})

    assert result.success is True
    assert "HomeSecret" not in result.data["message"]
    assert "OfficeSecret" not in result.data["message"]
    assert result.data["sensitive_display"]["items"][0]["password"] == "HomeSecret"


def test_all_wifi_password_query_routes_to_list_action():
    action = HinglishNLUParser.parse("sabhi past connected wifi ke SSID and password dikhao")

    assert action is not None
    assert action.action == "list_saved_wifi_passwords"


def test_wifi_password_common_spelling_mistakes_are_understood():
    for query in ("wifi ka pasword batao", "wifi passward dikhao", "wifi paswrd kya hai"):
        action = HinglishNLUParser.parse(query)
        assert action is not None
        assert action.action == "copy_wifi_password"
        assert action.needs_clarification is False


def test_ambiguous_wifi_pass_query_asks_confirmation():
    action = HinglishNLUParser.parse("wifi ka pass batao")

    assert action is not None
    assert action.needs_clarification is True
    assert action.missing_slot == "confirmation"
    assert "password jaanana" in action.clarification_prompt
