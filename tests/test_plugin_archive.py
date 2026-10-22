# tests/test_plugin_archive.py
"""Automated unit and verification tests for upgraded Archive plugin."""

import os
import pytest
from plugins.archive.plugin import ArchivePlugin


@pytest.fixture
def archive_plugin():
    return ArchivePlugin()


def test_archive_manifest_and_health(archive_plugin):
    manifest = archive_plugin.get_manifest()
    assert manifest.name == "archive"
    assert len(manifest.actions) == 13

    health = archive_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_create_list_and_extract_zip(archive_plugin, tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "file1.txt").write_text("Hello World Archive", encoding="utf-8")
    (src_dir / "file2.txt").write_text("Second Archive File", encoding="utf-8")

    out_zip = str(tmp_path / "test.zip")
    res_create = archive_plugin.execute("create_zip", {
        "source_path": str(src_dir),
        "output_zip": out_zip
    })
    assert res_create.success is True
    assert os.path.exists(out_zip)

    # Verify state hook
    v = archive_plugin.verify_state("create_zip", {}, res_create.data)
    assert v is not None
    assert v.verified is True

    # List contents
    res_list = archive_plugin.execute("list_archive_contents", {"archive_path": out_zip})
    assert res_list.success is True
    assert res_list.data["count"] >= 2

    # Extract zip
    dest_dir = str(tmp_path / "extracted")
    res_ext = archive_plugin.execute("extract_zip", {
        "zip_path": out_zip,
        "extract_to": dest_dir
    })
    assert res_ext.success is True
    assert os.path.exists(os.path.join(dest_dir, "file1.txt"))


def test_tar_archive_and_extract(archive_plugin, tmp_path):
    src_dir = tmp_path / "tar_src"
    src_dir.mkdir()
    (src_dir / "alpha.txt").write_text("Alpha content", encoding="utf-8")

    tar_path = str(tmp_path / "archive.tar.gz")
    res_tar = archive_plugin.execute("create_tar_archive", {
        "source_path": str(src_dir),
        "output_path": tar_path,
        "compression": "gz"
    })
    assert res_tar.success is True
    assert os.path.exists(tar_path)

    # Extract tar
    dest_tar = str(tmp_path / "tar_out")
    res_ext = archive_plugin.execute("extract_tar_archive", {
        "archive_path": tar_path,
        "extract_to": dest_tar
    })
    assert res_ext.success is True
    assert os.path.exists(dest_tar)


def test_single_file_extract_and_integrity(archive_plugin, tmp_path):
    src_file = tmp_path / "single_doc.txt"
    src_file.write_text("Unique text", encoding="utf-8")

    zip_file = str(tmp_path / "single_test.zip")
    archive_plugin.execute("create_zip", {"source_path": str(src_file), "output_zip": zip_file})

    # Integrity
    res_ver = archive_plugin.execute("verify_archive_integrity", {"archive_path": zip_file})
    assert res_ver.success is True
    assert res_ver.data["valid"] is True

    # Extract single file
    single_dest = str(tmp_path / "single_dest")
    res_s = archive_plugin.execute("extract_single_file_from_archive", {
        "archive_path": zip_file,
        "member_name": "single_doc.txt",
        "destination_dir": single_dest
    })
    assert res_s.success is True
    assert os.path.exists(os.path.join(single_dest, "single_doc.txt"))


def test_add_and_delete_archive_file(archive_plugin, tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_text("Content 1", encoding="utf-8")
    zip_path = str(tmp_path / "dynamic.zip")
    archive_plugin.execute("create_zip", {"source_path": str(f1), "output_zip": zip_path})

    # Add second file
    f2 = tmp_path / "f2.txt"
    f2.write_text("Content 2", encoding="utf-8")
    res_add = archive_plugin.execute("add_file_to_archive", {
        "archive_path": zip_path,
        "file_to_add": str(f2)
    })
    assert res_add.success is True

    # Search
    res_search = archive_plugin.execute("search_files_in_archive", {
        "archive_path": zip_path,
        "pattern": "f2"
    })
    assert res_search.success is True
    assert res_search.data["count"] == 1

    # Delete first file
    res_del = archive_plugin.execute("delete_file_from_archive", {
        "archive_path": zip_path,
        "member_name": "f1.txt"
    })
    assert res_del.success is True

    res_list = archive_plugin.execute("list_archive_contents", {"archive_path": zip_path})
    assert "f1.txt" not in res_list.data["files"]
    assert "f2.txt" in res_list.data["files"]


def test_compression_ratio_and_metadata(archive_plugin, tmp_path):
    f = tmp_path / "compressible.txt"
    f.write_text("A" * 5000, encoding="utf-8")
    zip_path = str(tmp_path / "ratio.zip")
    archive_plugin.execute("create_zip", {"source_path": str(f), "output_zip": zip_path})

    res_ratio = archive_plugin.execute("get_archive_compression_ratio", {"archive_path": zip_path})
    assert res_ratio.success is True
    assert res_ratio.data["savings_percent"] > 50

    res_meta = archive_plugin.execute("get_archive_metadata", {"archive_path": zip_path})
    assert res_meta.success is True
    assert res_meta.data["metadata"]["is_zip"] is True
    assert res_meta.data["metadata"]["items_count"] >= 1
