# tests/test_plugin_documents.py
"""Automated unit and verification tests for upgraded Documents plugin."""

import os
import pytest
from plugins.documents.plugin import DocumentsPlugin


@pytest.fixture
def doc_plugin():
    return DocumentsPlugin()


def test_documents_manifest_and_health(doc_plugin):
    manifest = doc_plugin.get_manifest()
    assert manifest.name == "documents"
    assert len(manifest.actions) == 13

    health = doc_plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 13


def test_create_read_and_search(doc_plugin, tmp_path):
    txt_file = str(tmp_path / "sample_note.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("Jarvis AI system architecture notes and plugins.")

    # Read
    res_read = doc_plugin.execute("read_document", {"file_path": txt_file})
    assert res_read.success is True
    assert "Jarvis AI system" in res_read.data["text"]

    # Search
    res_search = doc_plugin.execute("search_documents", {"query": "plugins", "directory": str(tmp_path)})
    assert res_search.success is True
    assert res_search.data["count"] >= 1


def test_docx_creation_and_stats(doc_plugin, tmp_path):
    docx_file = str(tmp_path / "project_report.docx")
    res_create = doc_plugin.execute("create_docx_document", {
        "file_path": docx_file,
        "title": "Jarvis V2.1 Status",
        "paragraphs": [
            "The plugin ecosystem upgrade is progressing systematically.",
            "All 33 plugins receive real, domain-specific features."
        ],
        "bullet_points": ["Zero breakage", "Full test coverage", "Real implementation"]
    })
    assert res_create.success is True
    assert os.path.exists(docx_file)

    # Verify state hook
    v = doc_plugin.verify_state("create_docx_document", {}, res_create.data)
    assert v is not None
    assert v.verified is True

    # Stats
    res_stats = doc_plugin.execute("get_document_statistics", {"file_path": docx_file})
    assert res_stats.success is True
    assert res_stats.data["words"] > 10
    assert res_stats.data["characters"] > 50


def test_append_and_search_replace(doc_plugin, tmp_path):
    note_path = str(tmp_path / "meeting.md")
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("# Meeting Notes\nOriginal discussion point.")

    # Append
    res_app = doc_plugin.execute("append_to_document", {
        "file_path": note_path,
        "content": "Action item: Finalize batch 3."
    })
    assert res_app.success is True

    # Search and replace
    res_rep = doc_plugin.execute("search_and_replace_text", {
        "file_path": note_path,
        "find_text": "Original",
        "replace_text": "Updated"
    })
    assert res_rep.success is True
    assert res_rep.data["replacements_count"] == 1

    # Verify content
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Updated discussion point" in content
    assert "Finalize batch 3" in content


def test_compare_and_sections(doc_plugin, tmp_path):
    fa = str(tmp_path / "doc_v1.md")
    fb = str(tmp_path / "doc_v2.md")
    with open(fa, "w", encoding="utf-8") as f:
        f.write("# Overview\nLine 1\nLine 2\n")
    with open(fb, "w", encoding="utf-8") as f:
        f.write("# Overview\n## Details\nLine 1\nLine 2 Modified\nLine 3\n")

    # Sections extraction
    res_sec = doc_plugin.execute("extract_document_sections", {"file_path": fb})
    assert res_sec.success is True
    assert res_sec.data["section_count"] == 2
    assert res_sec.data["sections"][0]["title"] == "Overview"
    assert res_sec.data["sections"][1]["title"] == "Details"

    # Compare
    res_comp = doc_plugin.execute("compare_documents", {"file_a": fa, "file_b": fb})
    assert res_comp.success is True
    assert res_comp.data["identical"] is False
    assert res_comp.data["added_lines"] >= 1


def test_merge_and_metadata(doc_plugin, tmp_path):
    f1 = str(tmp_path / "part1.txt")
    f2 = str(tmp_path / "part2.txt")
    merged = str(tmp_path / "merged.txt")

    with open(f1, "w", encoding="utf-8") as f:
        f.write("Chapter 1")
    with open(f2, "w", encoding="utf-8") as f:
        f.write("Chapter 2")

    res_merge = doc_plugin.execute("merge_text_documents", {
        "file_paths": [f1, f2],
        "output_path": merged
    })
    assert res_merge.success is True
    assert os.path.exists(merged)
    with open(merged, "r", encoding="utf-8") as f:
        text = f.read()
    assert "Chapter 1" in text
    assert "Chapter 2" in text

    # Metadata
    res_meta = doc_plugin.execute("inspect_document_metadata", {"file_path": merged})
    assert res_meta.success is True
    assert res_meta.data["metadata"]["extension"] == ".txt"
    assert res_meta.data["metadata"]["size_kb"] >= 0
