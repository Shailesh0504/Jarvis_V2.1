# tests/test_plugin_office.py
"""Tests for OfficePlugin covering original and newly added actions."""

import os
import pytest
from PIL import Image
from plugins.office.plugin import OfficePlugin


@pytest.fixture
def plugin():
    p = OfficePlugin()
    p.initialize()
    return p


def test_office_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "office"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "create_word_doc",
        "create_powerpoint",
        "open_office_app",
        "add_slide_to_presentation",
        "get_presentation_summary",
        "convert_text_to_presentation",
        "extract_text_from_presentation",
        "add_table_to_document",
        "insert_image_into_document",
        "get_document_metadata",
        "set_document_metadata",
        "merge_word_documents",
        "export_document_to_text"
    }
    assert expected.issubset(action_names)


def test_office_powerpoint_workflow(plugin, tmp_path):
    pptx_path = str(tmp_path / "presentation.pptx")

    # Create presentation
    res_create = plugin.execute("create_powerpoint", {
        "title": "Jarvis Architecture",
        "slides": [
            {"title": "Core Modules", "bullets": ["EventBus", "PluginManager", "SemanticParser"]},
            {"title": "Voice Pipeline", "bullets": ["Listener", "TTS", "STT"]}
        ],
        "file_path": pptx_path
    })
    assert res_create.success is True
    assert os.path.exists(pptx_path)

    # Add another slide
    res_add = plugin.execute("add_slide_to_presentation", {
        "file_path": pptx_path,
        "title": "Future Roadmap",
        "bullets": ["Autonomous Agents", "Cloud Sync"]
    })
    assert res_add.success is True
    assert res_add.data["total_slides"] >= 3

    # Summarize presentation
    res_sum = plugin.execute("get_presentation_summary", {"file_path": pptx_path})
    assert res_sum.success is True
    assert res_sum.data["slide_count"] >= 3

    # Extract text
    res_ext = plugin.execute("extract_text_from_presentation", {"file_path": pptx_path})
    assert res_ext.success is True
    assert res_ext.data["slides_extracted"] >= 3


def test_office_convert_text_to_presentation(plugin, tmp_path):
    out_pptx = str(tmp_path / "auto_deck.pptx")
    outline = (
        "# Introduction\n"
        "- Welcome to the system\n"
        "- Overview of features\n"
        "# Technical Details\n"
        "- Python 3.12\n"
        "- OpenPyXL and PPTX\n"
    )
    res = plugin.execute("convert_text_to_presentation", {
        "outline_text": outline,
        "output_path": out_pptx,
        "title": "Auto Deck"
    })
    assert res.success is True
    assert os.path.exists(out_pptx)
    assert res.data["slide_count"] >= 3


def test_office_word_workflow(plugin, tmp_path):
    docx_path = str(tmp_path / "document.docx")

    # Create document
    res_create = plugin.execute("create_word_doc", {
        "title": "System Specification",
        "content": "This document specifies the Jarvis plugin architecture.",
        "file_path": docx_path
    })
    assert res_create.success is True
    assert os.path.exists(docx_path)

    # Add table
    table_data = [
        ["Component", "Status", "Version"],
        ["Brain", "Active", "2.1"],
        ["Voice", "Active", "2.0"]
    ]
    res_tbl = plugin.execute("add_table_to_document", {
        "file_path": docx_path,
        "table_data": table_data,
        "has_header": True
    })
    assert res_tbl.success is True
    assert res_tbl.data["rows"] == 3

    # Insert image
    img_path = str(tmp_path / "test_img.png")
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_path)
    res_img = plugin.execute("insert_image_into_document", {
        "file_path": docx_path,
        "image_path": img_path,
        "caption": "Figure 1: Blue Test Square"
    })
    assert res_img.success is True

    # Set metadata
    res_set_meta = plugin.execute("set_document_metadata", {
        "file_path": docx_path,
        "author": "Antigravity",
        "title": "Jarvis Spec Updated"
    })
    assert res_set_meta.success is True

    # Get metadata
    res_get_meta = plugin.execute("get_document_metadata", {"file_path": docx_path})
    assert res_get_meta.success is True
    assert res_get_meta.data["author"] == "Antigravity"
    assert res_get_meta.data["paragraphs"] >= 1

    # Export to text
    txt_path = str(tmp_path / "exported.txt")
    res_txt = plugin.execute("export_document_to_text", {
        "file_path": docx_path,
        "output_path": txt_path
    })
    assert res_txt.success is True
    assert os.path.exists(txt_path)
    assert res_txt.data["paragraphs_count"] >= 1


def test_office_merge_word_documents(plugin, tmp_path):
    doc1 = str(tmp_path / "doc1.docx")
    doc2 = str(tmp_path / "doc2.docx")
    master = str(tmp_path / "merged.docx")

    plugin.execute("create_word_doc", {"title": "Chapter 1", "content": "Beginning...", "file_path": doc1})
    plugin.execute("create_word_doc", {"title": "Chapter 2", "content": "Continuation...", "file_path": doc2})

    res = plugin.execute("merge_word_documents", {
        "file_paths": [doc1, doc2],
        "output_path": master
    })
    assert res.success is True
    assert res.data["merged_count"] == 2
    assert os.path.exists(master)
