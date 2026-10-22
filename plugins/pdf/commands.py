# plugins/pdf/commands.py
"""Command actions supported by PDF plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="read_pdf",
        description="Reads and extracts text from a PDF file",
        keywords=["read pdf", "pdf text", "extract pdf", "pdf padho", "read document pdf"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="max_pages", type="integer", description="Max pages to extract", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="summarize_pdf",
        description="Extracts and summarizes text from a PDF document",
        keywords=["summarize pdf", "pdf summary", "pdf overview", "pdf ka summary batao"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),

    # 10 New Actions
    PluginAction(
        name="get_pdf_metadata",
        description="Extracts document metadata such as title, author, creation date, and page count",
        keywords=["pdf metadata", "pdf info", "pdf author", "pdf details", "pdf ki details"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_text_from_pdf",
        description="Extracts clean text with page number breakdown from a PDF",
        keywords=["extract text pdf", "pdf to text", "dump pdf text", "pdf ka text nikalo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="output_path", type="string", description="Optional path to save extracted text", required=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_single_page_text",
        description="Extracts text strictly from one specific page of a PDF",
        keywords=["extract page text", "pdf page padho", "single page text", "pdf specific page"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="page_number", type="integer", description="1-based page number", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="search_text_in_pdf",
        description="Searches for a keyword or phrase across all pages of a PDF and returns matching pages and snippets",
        keywords=["search pdf", "find in pdf", "pdf mein dhoondho", "pdf search keyword"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="query", type="string", description="Search keyword or phrase", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="merge_pdfs",
        description="Merges multiple PDF files into a single unified output PDF",
        keywords=["merge pdf", "combine pdf", "join pdf", "pdf merge karo", "pdf jodo"],
        parameters=[
            PluginParameter(name="pdf_paths", type="list", description="List of PDF file paths to merge", required=True),
            PluginParameter(name="output_path", type="string", description="Destination output PDF path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="split_pdf",
        description="Splits a multi-page PDF into separate single-page PDF files",
        keywords=["split pdf", "separate pdf", "pdf split karo", "pdf tukde karo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="output_dir", type="string", description="Directory to save split pages", required=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="rotate_pdf_pages",
        description="Rotates all or selected pages in a PDF document by 90, 180, or 270 degrees",
        keywords=["rotate pdf", "turn pdf", "pdf ghumao", "pdf orientation"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="rotation", type="integer", description="Clockwise rotation degrees (90, 180, 270)", required=False, default=90),
            PluginParameter(name="output_path", type="string", description="Optional output path (defaults to overwriting or suffixed)", required=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_pdf_pages",
        description="Extracts a specific range of pages (e.g. 1-3) from a PDF into a new PDF",
        keywords=["extract pdf pages", "pdf page range", "subset pdf", "pdf pages nikalo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="start_page", type="integer", description="1-based start page", required=True),
            PluginParameter(name="end_page", type="integer", description="1-based end page", required=True),
            PluginParameter(name="output_path", type="string", description="Destination PDF path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="verify_pdf_validity",
        description="Verifies that a PDF file exists, is non-empty, and has a valid, non-corrupted PDF structure",
        keywords=["verify pdf", "check pdf", "validate pdf", "is pdf valid", "pdf check karo"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_pdf_page_count",
        description="Quickly returns the total page count of a PDF document",
        keywords=["pdf page count", "how many pages pdf", "count pdf pages", "pdf kitne page hain"],
        parameters=[
            PluginParameter(name="path", type="string", description="Path to PDF file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
