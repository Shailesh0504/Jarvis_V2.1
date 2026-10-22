# tests/test_plugin_files.py
import os
import pytest
from plugins.files.plugin import FilesPlugin


@pytest.fixture
def files_plugin():
    return FilesPlugin()


def test_files_hash_and_size(files_plugin, tmp_path):
    sample = tmp_path / "hello.txt"
    sample.write_text("Hello, World! Jarvis V2.1 Files Plugin", encoding="utf-8")

    # Hash
    hash_res = files_plugin.execute("calculate_hash", {"path": str(sample), "algorithm": "sha256"})
    assert hash_res.success is True
    assert "hash" in hash_res.data
    assert len(hash_res.data["hash"]) == 64

    # Directory size
    dir_res = files_plugin.execute("get_directory_size", {"path": str(tmp_path)})
    assert dir_res.success is True
    assert dir_res.data["file_count"] >= 1
    assert dir_res.data["size_bytes"] > 0


def test_files_search_and_batch_rename(files_plugin, tmp_path):
    f1 = tmp_path / "doc1.txt"
    f1.write_text("Target phrase is here: alpha beta gamma", encoding="utf-8")
    f2 = tmp_path / "doc2.txt"
    f2.write_text("Nothing special here", encoding="utf-8")

    # Search content
    search_res = files_plugin.execute("search_files_by_content", {
        "directory": str(tmp_path),
        "query": "alpha beta"
    })
    assert search_res.success is True
    assert search_res.data["match_count"] >= 1
    assert search_res.data["matches"][0]["name"] == "doc1.txt"

    # Batch rename
    rename_res = files_plugin.execute("batch_rename", {
        "directory": str(tmp_path),
        "prefix": "backup_",
        "replace_from": "doc",
        "replace_to": "file"
    })
    assert rename_res.success is True
    assert rename_res.data["renamed_count"] == 2
    assert os.path.exists(tmp_path / "backup_file1.txt")


def test_files_compare_and_touch(files_plugin, tmp_path):
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("Line 1\nLine 2\nLine 3", encoding="utf-8")
    p2.write_text("Line 1\nLine Modified\nLine 3", encoding="utf-8")

    comp_res = files_plugin.execute("compare_files", {"path1": str(p1), "path2": str(p2)})
    assert comp_res.success is True
    assert comp_res.data["are_identical"] is False
    assert comp_res.data["similarity_ratio"] > 0.5

    # Touch file
    p3 = tmp_path / "c.txt"
    touch_res = files_plugin.execute("touch_file", {"path": str(p3)})
    assert touch_res.success is True
    assert os.path.isfile(p3)


def test_files_empty_folders_and_shred(files_plugin, tmp_path):
    sub = tmp_path / "empty_child"
    sub.mkdir()

    # Find empty
    find_res = files_plugin.execute("find_empty_folders", {"directory": str(tmp_path), "delete": True})
    assert find_res.success is True
    assert find_res.data["count"] >= 1
    assert not os.path.exists(sub)

    # Secure delete
    secret = tmp_path / "secret.txt"
    secret.write_text("Top secret credentials content", encoding="utf-8")
    shred_res = files_plugin.execute("secure_delete", {"path": str(secret), "passes": 2})
    assert shred_res.success is True
    assert not os.path.exists(secret)


def test_files_disk_space_and_large_files(files_plugin, tmp_path):
    # Large files check
    lf_res = files_plugin.execute("find_large_files", {"directory": str(tmp_path), "min_size_mb": 0.0})
    assert lf_res.success is True

    # Disk space
    disk_res = files_plugin.execute("get_disk_free_space", {"path": str(tmp_path)})
    assert disk_res.success is True
    assert disk_res.data["total_gb"] > 0
    assert disk_res.data["free_gb"] > 0
