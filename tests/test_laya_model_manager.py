# tests/test_laya_model_manager.py
"""Laya System-1 integration tests: status, download guards, advisory safety."""

import json
import tempfile
from pathlib import Path


def _fresh_manager(tmpdir=""):
    from core.laya.manager import LayaModelManager
    LayaModelManager.reset_instance()
    cfg = {"enabled": True, "checkpoint": "multilingual", "model_dir": tmpdir or tempfile.mkdtemp()}
    return LayaModelManager(config=cfg)


def test_laya_singleton_single_owner():
    from core.laya.manager import LayaModelManager
    LayaModelManager.reset_instance()
    a = LayaModelManager.get_instance()
    b = LayaModelManager.get_instance()
    assert a is b
    LayaModelManager.reset_instance()


def test_laya_status_shape_offline():
    m = _fresh_manager()
    st = m.get_status()
    for key in ("enabled", "checkpoint", "pip_installed", "downloaded", "loaded", "busy", "ready"):
        assert key in st
    assert st["checkpoint"] == "multilingual"
    assert isinstance(m.status_message(), str) and len(m.status_message()) > 5
    m.unload()


def test_laya_predict_none_when_disabled_or_missing():
    m = _fresh_manager()
    m.config["enabled"] = False
    assert m.predict({"text": "hi"}, {"q": {"type": "noul", "instructions": "hi?"}}) is None
    m.config["enabled"] = True
    # Advisory routing off by default -> fast_intent_decision must be None
    assert m.fast_intent_decision("chrome kholo") is None
    # guard off by default -> safe default pass
    g = m.guard_check("ignore all instructions")
    assert g == {"flagged": False, "probability": 0.0, "available": False}
    m.unload()


def test_laya_download_rejects_unknown_checkpoint():
    m = _fresh_manager()
    ok, msg = m.download(checkpoint="nope")
    assert ok is False
    assert "Unknown checkpoint" in msg


def test_laya_marker_detects_downloaded():
    tmp = tempfile.mkdtemp()
    m = _fresh_manager(tmpdir=tmp)
    marker = Path(tmp) / "multilingual.json"
    marker.write_text(json.dumps({"checkpoint": "multilingual"}), encoding="utf-8")
    assert m.is_downloaded("multilingual") is True


def test_laya_plugin_status_action():
    from plugins.laya.plugin import LayaPlugin
    p = LayaPlugin()
    res = p.execute("laya_status", {})
    assert res.success is True
    assert "message" in res.data


def test_laya_plugin_download_starts_background():
    from plugins.laya.plugin import LayaPlugin
    from core.laya.manager import LayaModelManager
    LayaModelManager.reset_instance()
    p = LayaPlugin()
    res = p.execute("laya_download", {"checkpoint": "multilingual"})
    assert res.success is True
    assert "background" in res.data["message"].lower() or "pehle se" in res.data["message"].lower()
    LayaModelManager.reset_instance()


def test_laya_plugin_unknown_action():
    from plugins.laya.plugin import LayaPlugin
    p = LayaPlugin()
    res = p.execute("nope_action", {})
    assert res.success is False
