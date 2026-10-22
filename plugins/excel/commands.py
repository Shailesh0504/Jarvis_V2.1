# plugins/excel/commands.py
"""Command actions supported by Excel plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="read_sheet",
        description="Reads data from an Excel worksheet",
        keywords=["read excel", "open excel sheet", "view excel", "excel padho"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to excel or csv file", required=True),
            PluginParameter(name="sheet_name", type="string", description="Sheet name (optional)", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="write_sheet",
        description="Writes rows of data into an Excel spreadsheet",
        keywords=["write excel", "save excel", "update excel", "excel likho"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to excel or csv file", required=True),
            PluginParameter(name="data", type="list", description="Rows to append or write", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="create_sheet",
        description="Creates a new Excel or CSV workbook file",
        keywords=["create sheet", "new excel", "create excel", "nayi excel", "excel banao"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to create new excel or csv file", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="calculate_column",
        description="Calculates sum, average, min, max, or count of a specific column in an Excel/CSV spreadsheet",
        keywords=["calculate column", "sum column", "total of column", "sales total", "column total", "average of"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to excel or csv file", required=True),
            PluginParameter(name="column_name", type="string", description="Target column name (e.g. Sales, Total, Revenue)", required=True),
            PluginParameter(name="operation", type="string", description="Operation: sum, avg, count, max, min", required=False, default="sum")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="clean_sheet",
        description="Performs formatting & sanitization steps (autofit, alignment, borders, blanks removal)",
        keywords=["clean sheet", "excel clean", "format sheet", "sanitize excel"],
        parameters=[
            PluginParameter(name="operation", type="string", description="Step: select_used_range, autofit, alignment, borders, remove_blanks, save", required=True),
            PluginParameter(name="path", type="string", description="Path to workbook", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="create_chart",
        description="Creates a chart (bar, line, pie) from worksheet columns",
        keywords=["create chart", "excel chart", "chart banao", "graph banao", "generate chart"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to workbook", required=False, default=""),
            PluginParameter(name="chart_type", type="string", description="Type of chart (bar, line, pie)", required=False, default="bar"),
            PluginParameter(name="x_col", type="string", description="X-axis column", required=False, default="Month"),
            PluginParameter(name="y_col", type="string", description="Y-axis column", required=False, default="Sales")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="csv_to_excel",
        description="Converts a CSV file to a formatted Excel .xlsx workbook",
        keywords=["csv to excel", "convert csv to xlsx", "import csv to excel"],
        parameters=[
            PluginParameter(name="csv_path", type="string", description="Path to input CSV file", required=True),
            PluginParameter(name="excel_path", type="string", description="Output Excel file path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="excel_to_csv",
        description="Exports an Excel worksheet to a CSV file",
        keywords=["excel to csv", "convert excel to csv", "export sheet csv"],
        parameters=[
            PluginParameter(name="excel_path", type="string", description="Path to Excel workbook", required=True),
            PluginParameter(name="csv_path", type="string", description="Output CSV path", required=False, default=""),
            PluginParameter(name="sheet_name", type="string", description="Sheet to export", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_sheet_names",
        description="Lists all worksheet names in an Excel workbook with dimensions",
        keywords=["sheet names", "list sheets", "workbook sheets"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="merge_sheets",
        description="Merges multiple sheets into a consolidated master worksheet",
        keywords=["merge sheets", "combine sheets", "consolidate excel"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel file", required=True),
            PluginParameter(name="target_sheet", type="string", description="Name for the merged sheet", required=False, default="Consolidated")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="find_and_replace",
        description="Searches for text in a worksheet and replaces occurrences",
        keywords=["excel find and replace", "replace in sheet", "change cell value"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel file", required=True),
            PluginParameter(name="find_text", type="string", description="Text to search for", required=True),
            PluginParameter(name="replace_text", type="string", description="Replacement text", required=True),
            PluginParameter(name="sheet_name", type="string", description="Sheet name", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="add_formula",
        description="Inserts a formula into a specified cell in an Excel sheet",
        keywords=["add formula", "insert formula", "excel formula"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel file", required=True),
            PluginParameter(name="cell", type="string", description="Cell coordinate (e.g. C10, B15)", required=True),
            PluginParameter(name="formula", type="string", description="Formula string starting with '='", required=True),
            PluginParameter(name="sheet_name", type="string", description="Sheet name", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="filter_rows",
        description="Filters rows in a worksheet based on a column condition",
        keywords=["filter sheet", "filter rows", "query excel"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel or CSV file", required=True),
            PluginParameter(name="column_name", type="string", description="Column to evaluate", required=True),
            PluginParameter(name="condition", type="string", description="Condition: equals, contains, greater_than, less_than", required=False, default="equals"),
            PluginParameter(name="value", type="string", description="Filter comparison value", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="sort_sheet",
        description="Sorts worksheet rows by a specified column",
        keywords=["sort excel", "sort sheet", "order rows"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel or CSV file", required=True),
            PluginParameter(name="column_name", type="string", description="Column name to sort by", required=True),
            PluginParameter(name="ascending", type="boolean", description="Sort ascending if true, descending if false", required=False, default=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="export_sheet_to_json",
        description="Converts worksheet rows into a structured JSON file or JSON array",
        keywords=["excel to json", "sheet to json", "convert sheet to json"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel or CSV file", required=True),
            PluginParameter(name="output_json", type="string", description="Optional output JSON path", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_workbook_summary",
        description="Generates comprehensive statistics and metadata for an Excel workbook",
        keywords=["workbook summary", "excel stats", "sheet details"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to Excel file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    )
]
