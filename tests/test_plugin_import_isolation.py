# tests/test_plugin_import_isolation.py
"""Regression coverage for plugin names that collide with Python stdlib modules."""

import calendar
import sys

from plugins.manager import PluginManager


def test_plugin_discovery_does_not_shadow_stdlib_calendar(tmp_path):
    original_path = list(sys.path)
    manager = PluginManager(plugin_dir=str(tmp_path))
    manager.discover_and_load()

    assert sys.path == original_path
    assert callable(calendar.timegm)
