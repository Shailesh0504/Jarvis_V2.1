# tests/test_plugin_clipboard.py
"""Automated unit and verification tests for upgraded Clipboard plugin."""

import os
import pytest
from plugins.clipboard.plugin import ClipboardPlugin


@pytest.fixture
def clip_plugin():
    return ClipboardPlugin()


def test_clipboard_manifest_and_health(clip_plugin):
    manifest = clip_plugin.get_manifest()
    assert manifest.name == "clipboard"
    assert len(manifest.actions) == 13

    health = clip_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_set_get_and_clear(clip_plugin):
    test_str = "Jarvis Clipboard Test 123"
    res_set = clip_plugin.execute("set_clipboard_text", {"text": test_str})
    assert res_set.success is True

    # Get
    res_get = clip_plugin.execute("get_clipboard_text")
    assert res_get.success is True
    assert test_str in res_get.data["text"]

    # Verify state hook
    v = clip_plugin.verify_state("set_clipboard_text", {}, res_set.data)
    assert v is not None
    assert v.verified is True

    # Clear
    res_clear = clip_plugin.execute("clear_clipboard")
    assert res_clear.success is True


def test_append_and_metrics(clip_plugin):
    clip_plugin.execute("set_clipboard_text", {"text": "Hello"})
    res_app = clip_plugin.execute("append_to_clipboard", {"text": "World", "delimiter": " "})
    assert res_app.success is True
    assert "Hello World" in res_app.data["text"]

    # Metrics
    res_met = clip_plugin.execute("get_clipboard_metrics")
    assert res_met.success is True
    assert res_met.data["word_count"] == 2
    assert res_met.data["char_count"] == 11
    assert res_met.data["detected_type"] == "plain_text"


def test_transformations(clip_plugin):
    clip_plugin.execute("set_clipboard_text", {"text": "apple banana"})

    # Uppercase
    res_up = clip_plugin.execute("transform_clipboard_text", {"transformation": "uppercase"})
    assert res_up.success is True
    assert res_up.data["transformed_text"] == "APPLE BANANA"

    # Base64
    res_b64 = clip_plugin.execute("transform_clipboard_text", {"transformation": "base64_encode"})
    assert res_b64.success is True

    # Decode
    res_dec = clip_plugin.execute("transform_clipboard_text", {"transformation": "base64_decode"})
    assert res_dec.success is True
    assert res_dec.data["transformed_text"] == "APPLE BANANA"


def test_history_search_and_restore(clip_plugin):
    clip_plugin.execute("set_clipboard_text", {"text": "Alpha Token"})
    clip_plugin.execute("set_clipboard_text", {"text": "Beta Secret"})

    # History
    res_hist = clip_plugin.execute("get_clipboard_history")
    assert res_hist.success is True
    assert res_hist.data["count"] >= 2

    # Search
    res_search = clip_plugin.execute("search_clipboard_history", {"query": "Alpha"})
    assert res_search.success is True
    assert res_search.data["count"] >= 1

    # Restore item 1 (Alpha Token)
    res_res = clip_plugin.execute("restore_clipboard_from_history", {"history_index": 1})
    assert res_res.success is True
    assert res_res.data["text"] == "Alpha Token"

    # Clear history
    res_cl = clip_plugin.execute("clear_clipboard_history")
    assert res_cl.success is True


def test_file_save_load_and_formats(clip_plugin, tmp_path):
    clip_plugin.execute("set_clipboard_text", {"text": "Dump this content to file"})
    dump_path = str(tmp_path / "dump.txt")

    # Save
    res_save = clip_plugin.execute("save_clipboard_to_file", {"file_path": dump_path})
    assert res_save.success is True
    assert os.path.exists(dump_path)

    # Modify file and load
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write("New loaded file string")

    res_load = clip_plugin.execute("load_file_to_clipboard", {"file_path": dump_path})
    assert res_load.success is True

    res_get = clip_plugin.execute("get_clipboard_text")
    assert "New loaded file string" in res_get.data["text"]

    # Formats inspection
    res_fmt = clip_plugin.execute("inspect_clipboard_formats")
    assert res_fmt.success is True
    assert res_fmt.data["count"] >= 1
