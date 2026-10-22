# tests/test_plugin_network.py
"""Tests for NetworkPlugin covering original and newly added actions."""

import pytest
from unittest.mock import patch, MagicMock
from plugins.network.plugin import NetworkPlugin


@pytest.fixture
def plugin():
    p = NetworkPlugin()
    p.initialize()
    return p


def test_network_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "network"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "list_saved_wifi_passwords",
        "copy_wifi_password",
        "measure_speed",
        "check_connection",
        "get_ip_address",
        "ping_host",
        "dns_lookup",
        "get_bandwidth_stats",
        "scan_local_network",
        "check_port_open",
        "flush_dns_cache",
        "list_active_connections",
        "get_network_adapter_details",
        "get_public_ip_details",
        "traceroute",
        "get_wifi_network_list",
    }
    assert expected.issubset(action_names)


def test_network_check_connection_and_ip(plugin):
    res_conn = plugin.execute("check_connection", {})
    assert res_conn.success is True
    assert "connected" in res_conn.data

    res_ip = plugin.execute("get_ip_address", {})
    assert res_ip.success is True
    assert "local_ip" in res_ip.data


def test_network_dns_lookup(plugin):
    # Test resolving localhost
    res = plugin.execute("dns_lookup", {"domain": "localhost"})
    assert res.success is True
    assert "ip_addresses" in res.data
    assert len(res.data["ip_addresses"]) > 0

    # Test empty domain
    res_empty = plugin.execute("dns_lookup", {"domain": ""})
    assert res_empty.success is False


def test_network_bandwidth_and_adapters(plugin):
    res_stats = plugin.execute("get_bandwidth_stats", {})
    assert res_stats.success is True
    assert "total_bytes_sent" in res_stats.data
    assert "total_bytes_recv" in res_stats.data
    assert "adapters" in res_stats.data

    res_adapters = plugin.execute("get_network_adapter_details", {})
    assert res_adapters.success is True
    assert "adapters" in res_adapters.data
    assert isinstance(res_adapters.data["adapters"], list)


def test_network_active_connections_and_port(plugin):
    res_conns = plugin.execute("list_active_connections", {"limit": 5})
    assert res_conns.success is True
    assert "connections" in res_conns.data
    assert len(res_conns.data["connections"]) <= 5

    # Check port on localhost
    res_port = plugin.execute("check_port_open", {"host": "127.0.0.1", "port": 65530, "timeout": 0.5})
    assert res_port.success is True
    assert "is_open" in res_port.data
    assert res_port.data["port"] == 65530


def test_network_system_commands(plugin):
    # scan_local_network
    res_scan = plugin.execute("scan_local_network", {})
    assert res_scan.success is True
    assert "devices" in res_scan.data

    # get_wifi_network_list
    res_wifi = plugin.execute("get_wifi_network_list", {})
    assert res_wifi.success is True
    assert "networks" in res_wifi.data

    # public IP details (with fallback guarantee)
    res_pub = plugin.execute("get_public_ip_details", {})
    assert res_pub.success is True
    assert "public_ip" in res_pub.data


def test_network_mocked_traceroute_and_flush(plugin):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Successfully flushed the DNS Resolver Cache.\n")
        res_flush = plugin.execute("flush_dns_cache", {})
        assert res_flush.success is True

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Tracing route to 8.8.8.8\n1  <1 ms  192.168.1.1\n")
        res_trace = plugin.execute("traceroute", {"host": "8.8.8.8", "max_hops": 5})
        assert res_trace.success is True
        assert "output" in res_trace.data
