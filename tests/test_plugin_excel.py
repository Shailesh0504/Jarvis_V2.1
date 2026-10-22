# tests/test_plugin_excel.py
"""Tests for ExcelPlugin covering original and newly added actions."""

import csv
import json
import os
import pytest
from plugins.excel.plugin import ExcelPlugin


@pytest.fixture
def plugin():
    p = ExcelPlugin()
    p.initialize()
    return p


def test_excel_manifest(plugin):
    manifest = plugin.get_manifest()
    assert manifest.name == "excel"
    action_names = {a.name for a in manifest.actions}
    expected = {
        "read_sheet",
        "write_sheet",
        "create_sheet",
        "calculate_column",
        "clean_sheet",
        "create_chart",
        "csv_to_excel",
        "excel_to_csv",
        "get_sheet_names",
        "merge_sheets",
        "find_and_replace",
        "add_formula",
        "filter_rows",
        "sort_sheet",
        "export_sheet_to_json",
        "get_workbook_summary"
    }
    assert expected.issubset(action_names)


def test_excel_create_and_write_and_read(plugin, tmp_path):
    xlsx_path = str(tmp_path / "test_book.xlsx")
    # Create workbook
    res_create = plugin.execute("create_sheet", {"path": xlsx_path})
    assert res_create.success is True
    assert os.path.exists(xlsx_path)

    # Write data
    data = [
        ["Month", "Sales", "Category"],
        ["Jan", 100, "Electronics"],
        ["Feb", 200, "Apparel"],
        ["Mar", 300, "Electronics"],
    ]
    res_write = plugin.execute("write_sheet", {"path": xlsx_path, "data": data})
    assert res_write.success is True
    assert res_write.data["rows_written"] == 4

    # Read data back
    res_read = plugin.execute("read_sheet", {"path": xlsx_path})
    assert res_read.success is True
    assert res_read.data["rows_read"] >= 4
    assert "Sales" in res_read.data["headers"]


def test_excel_calculate_and_formula(plugin, tmp_path):
    xlsx_path = str(tmp_path / "calc_test.xlsx")
    plugin.execute("create_sheet", {"path": xlsx_path})
    data = [
        ["Product", "Revenue"],
        ["Laptop", 1200],
        ["Phone", 800],
        ["Mouse", 50],
    ]
    plugin.execute("write_sheet", {"path": xlsx_path, "data": data})

    # Calculate sum
    res_sum = plugin.execute("calculate_column", {"path": xlsx_path, "column_name": "Revenue", "operation": "sum"})
    assert res_sum.success is True
    assert res_sum.data["result"] == 2050

    # Calculate avg
    res_avg = plugin.execute("calculate_column", {"path": xlsx_path, "column_name": "Revenue", "operation": "avg"})
    assert res_avg.success is True
    assert round(res_avg.data["result"], 1) == 683.3

    # Add formula
    res_formula = plugin.execute("add_formula", {"path": xlsx_path, "cell": "B5", "formula": "=SUM(B2:B4)"})
    assert res_formula.success is True
    assert res_formula.data["formula"] == "=SUM(B2:B4)"


def test_excel_csv_conversions(plugin, tmp_path):
    csv_path = str(tmp_path / "sample.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Age", "Role"])
        writer.writerow(["Alice", 28, "Engineer"])
        writer.writerow(["Bob", 34, "Manager"])

    # CSV to Excel
    xlsx_path = str(tmp_path / "converted.xlsx")
    res_to_excel = plugin.execute("csv_to_excel", {"csv_path": csv_path, "excel_path": xlsx_path})
    assert res_to_excel.success is True
    assert os.path.exists(xlsx_path)

    # Excel back to CSV
    csv_out = str(tmp_path / "exported.csv")
    res_to_csv = plugin.execute("excel_to_csv", {"excel_path": xlsx_path, "csv_path": csv_out})
    assert res_to_csv.success is True
    assert os.path.exists(csv_out)
    assert res_to_csv.data["rows_exported"] == 3


def test_excel_filter_and_sort_and_json(plugin, tmp_path):
    csv_path = str(tmp_path / "data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Price", "Status"])
        writer.writerow(["Desk", 250, "In Stock"])
        writer.writerow(["Chair", 80, "Out of Stock"])
        writer.writerow(["Lamp", 30, "In Stock"])

    # Filter
    res_filter = plugin.execute("filter_rows", {
        "path": csv_path,
        "column_name": "Status",
        "condition": "equals",
        "value": "in stock"
    })
    assert res_filter.success is True
    assert res_filter.data["count"] == 2

    # Sort
    res_sort = plugin.execute("sort_sheet", {
        "path": csv_path,
        "column_name": "Price",
        "ascending": True
    })
    assert res_sort.success is True
    assert res_sort.data["rows_sorted"] == 3

    # Export to JSON
    json_path = str(tmp_path / "output.json")
    res_json = plugin.execute("export_sheet_to_json", {"path": csv_path, "output_json": json_path})
    assert res_json.success is True
    assert res_json.data["count"] == 3
    assert os.path.exists(json_path)


def test_excel_summary_and_find_replace_and_chart(plugin, tmp_path):
    xlsx_path = str(tmp_path / "summary_test.xlsx")
    plugin.execute("create_sheet", {"path": xlsx_path})
    data = [
        ["City", "Population"],
        ["New York", 8000000],
        ["Old York", 200000],
    ]
    plugin.execute("write_sheet", {"path": xlsx_path, "data": data})

    # Find and Replace
    res_fr = plugin.execute("find_and_replace", {
        "path": xlsx_path,
        "find_text": "Old York",
        "replace_text": "York"
    })
    assert res_fr.success is True
    assert res_fr.data["replaced_count"] == 1

    # Clean sheet
    res_clean = plugin.execute("clean_sheet", {"path": xlsx_path, "operation": "all"})
    assert res_clean.success is True

    # Create Chart
    res_chart = plugin.execute("create_chart", {"path": xlsx_path, "chart_type": "bar"})
    assert res_chart.success is True

    # Workbook Summary
    res_summary = plugin.execute("get_workbook_summary", {"path": xlsx_path})
    assert res_summary.success is True
    assert res_summary.data["sheets_count"] >= 1
    assert res_summary.data["size_bytes"] > 0
