# tests/test_plugin_pdf.py
"""Automated unit and verification tests for upgraded PDF plugin."""

import os
import pytest
from plugins.pdf.plugin import PDFPlugin
from plugins.manifest import PluginResult


@pytest.fixture
def sample_pdf(tmp_path):
    """Generates a small valid multi-page PDF file for testing."""
    import pypdf
    pdf_path = str(tmp_path / "sample.pdf")
    writer = pypdf.PdfWriter()

    # Create 2 simple pages
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)

    with open(pdf_path, "wb") as f:
        writer.write(f)

    return pdf_path


def test_pdf_health_and_dependencies():
    plugin = PDFPlugin()
    assert plugin.check_dependencies() is True
    health = plugin.get_health_status()
    assert health["status"] == "ENABLED"
    assert health["actions_count"] == 12


def test_pdf_page_count_and_metadata(sample_pdf):
    plugin = PDFPlugin()
    res = plugin.execute("get_pdf_page_count", {"path": sample_pdf})
    assert res.success is True
    assert res.data["page_count"] == 2

    res_meta = plugin.execute("get_pdf_metadata", {"path": sample_pdf})
    assert res_meta.success is True
    assert res_meta.data["metadata"]["page_count"] == 2


def test_pdf_validity_check(sample_pdf, tmp_path):
    plugin = PDFPlugin()
    res = plugin.execute("verify_pdf_validity", {"path": sample_pdf})
    assert res.success is True
    assert res.data["valid"] is True

    # Corrupt file test
    fake_file = str(tmp_path / "corrupt.pdf")
    with open(fake_file, "w") as f:
        f.write("NOT A PDF")
    res_corrupt = plugin.execute("verify_pdf_validity", {"path": fake_file})
    assert res_corrupt.success is False


def test_pdf_extract_and_search(sample_pdf):
    plugin = PDFPlugin()
    res_extract = plugin.execute("extract_single_page_text", {"path": sample_pdf, "page_number": 1})
    assert res_extract.success is True
    assert res_extract.data["page_number"] == 1

    # Out of bounds page
    res_bad = plugin.execute("extract_single_page_text", {"path": sample_pdf, "page_number": 99})
    assert res_bad.success is False

    res_search = plugin.execute("search_text_in_pdf", {"path": sample_pdf, "query": "hello"})
    assert res_search.success is True


def test_pdf_rotate_and_extract_pages(sample_pdf, tmp_path):
    plugin = PDFPlugin()
    out_rotated = str(tmp_path / "rotated.pdf")
    res_rot = plugin.execute("rotate_pdf_pages", {"path": sample_pdf, "rotation": 90, "output_path": out_rotated})
    assert res_rot.success is True
    assert os.path.exists(out_rotated)

    out_subset = str(tmp_path / "subset.pdf")
    res_sub = plugin.execute("extract_pdf_pages", {"path": sample_pdf, "start_page": 1, "end_page": 1, "output_path": out_subset})
    assert res_sub.success is True
    assert os.path.exists(out_subset)


def test_pdf_merge_and_split(sample_pdf, tmp_path):
    plugin = PDFPlugin()
    # Merge sample with itself
    merged_path = str(tmp_path / "merged.pdf")
    res_merge = plugin.execute("merge_pdfs", {"pdf_paths": [sample_pdf, sample_pdf], "output_path": merged_path})
    assert res_merge.success is True
    assert os.path.exists(merged_path)

    # Split merged
    split_dir = str(tmp_path / "split_output")
    res_split = plugin.execute("split_pdf", {"path": merged_path, "output_dir": split_dir})
    assert res_split.success is True
    assert res_split.data["split_pages_count"] == 4
    for p in res_split.data["files"]:
        assert os.path.exists(p)
