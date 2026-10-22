# tests/test_plugin_backup.py
"""Automated unit and verification tests for upgraded Backup plugin."""

import os
import time
import pytest
from plugins.backup.plugin import BackupPlugin


@pytest.fixture
def backup_plugin(tmp_path):
    plugin = BackupPlugin()
    return plugin


def test_backup_manifest_and_health(backup_plugin):
    manifest = backup_plugin.get_manifest()
    assert manifest.name == "backup"
    assert len(manifest.actions) == 12

    health = backup_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 12


def test_create_list_and_verify_backup(backup_plugin, tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "sample.txt").write_text("Hello Jarvis Backup World", encoding="utf-8")
    (source_dir / "data.json").write_text('{"status": "ok"}', encoding="utf-8")

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create backup
    res = backup_plugin.execute("create_backup", {
        "source_dir": str(source_dir),
        "backup_dir": str(backup_dir)
    })
    assert res.success is True
    backup_path = res.data["backup_path"]
    assert os.path.exists(backup_path)

    # List backups
    res_list = backup_plugin.execute("list_backups", {
        "backup_dir": str(backup_dir)
    })
    assert res_list.success is True
    assert res_list.data["count"] >= 1

    # Verify backup
    res_ver = backup_plugin.execute("verify_backup", {
        "backup_file": backup_path
    })
    assert res_ver.success is True
    assert res_ver.data["valid"] is True
    assert res_ver.data["file_count"] >= 2


def test_backup_contents_and_diff(backup_plugin, tmp_path):
    source_dir = tmp_path / "source_diff"
    source_dir.mkdir()
    (source_dir / "file1.txt").write_text("file 1 content", encoding="utf-8")
    backup_dir = tmp_path / "backups_diff"
    backup_dir.mkdir()

    res = backup_plugin.execute("create_backup", {
        "source_dir": str(source_dir),
        "backup_dir": str(backup_dir)
    })
    assert res.success is True
    backup_path = res.data["backup_path"]

    # Contents inspection
    res_contents = backup_plugin.execute("get_backup_contents", {
        "backup_file": backup_path
    })
    assert res_contents.success is True
    assert any("file1.txt" in item["filename"] for item in res_contents.data["contents"])

    # Modify source dir to check diff
    (source_dir / "file2.txt").write_text("new file added", encoding="utf-8")
    res_diff = backup_plugin.execute("compare_backup_with_source", {
        "backup_file": backup_path,
        "source_dir": str(source_dir)
    })
    assert res_diff.success is True
    assert any("file2.txt" in f for f in res_diff.data["new_files"])


def test_restore_and_export_backup(backup_plugin, tmp_path):
    source_dir = tmp_path / "source_restore"
    source_dir.mkdir()
    (source_dir / "important.txt").write_text("Restore me safely", encoding="utf-8")
    backup_dir = tmp_path / "backups_restore"
    backup_dir.mkdir()

    res_create = backup_plugin.execute("create_backup", {
        "source_dir": str(source_dir),
        "backup_dir": str(backup_dir)
    })
    assert res_create.success is True
    backup_path = res_create.data["backup_path"]

    # Restore
    dest_dir = tmp_path / "restored_output"
    res_restore = backup_plugin.execute("restore_backup", {
        "backup_file": backup_path,
        "restore_dir": str(dest_dir)
    })
    assert res_restore.success is True
    assert (dest_dir / "important.txt").exists()
    assert (dest_dir / "important.txt").read_text(encoding="utf-8") == "Restore me safely"

    # Export
    export_dest = tmp_path / "exported_backups"
    res_export = backup_plugin.execute("export_backup_to_path", {
        "backup_file": backup_path,
        "destination_path": str(export_dest)
    })
    assert res_export.success is True
    assert os.path.exists(res_export.data["destination_path"])


def test_stats_prune_and_delete(backup_plugin, tmp_path):
    source_dir = tmp_path / "source_stats"
    source_dir.mkdir()
    (source_dir / "test.txt").write_text("dummy", encoding="utf-8")
    backup_dir = tmp_path / "backups_stats"
    backup_dir.mkdir()

    paths = []
    for i in range(4):
        res = backup_plugin.execute("create_backup", {
            "source_dir": str(source_dir),
            "backup_dir": str(backup_dir)
        })
        assert res.success is True
        paths.append(res.data["backup_path"])
        time.sleep(0.05)

    # Get stats
    res_stats = backup_plugin.execute("get_backup_stats", {
        "backup_dir": str(backup_dir)
    })
    assert res_stats.success is True
    assert res_stats.data["count"] == 4
    assert res_stats.data["total_size_mb"] >= 0

    # Prune keep 2
    res_prune = backup_plugin.execute("prune_old_backups", {
        "backup_dir": str(backup_dir),
        "keep_latest": 2
    })
    assert res_prune.success is True
    assert res_prune.data["pruned_count"] == 2
    assert res_prune.data["kept_count"] == 2

    # Delete single remaining
    remaining_files = [os.path.join(str(backup_dir), f) for f in os.listdir(str(backup_dir)) if f.endswith(".zip")]
    assert len(remaining_files) == 2
    res_del = backup_plugin.execute("delete_backup", {
        "backup_file": remaining_files[0],
        "backup_dir": str(backup_dir)
    })
    assert res_del.success is True
    assert not os.path.exists(remaining_files[0])

