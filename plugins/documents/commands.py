# plugins/documents/commands.py
"""Command actions supported by Documents Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="read_document",
        description="Reads and extracts text from a text, markdown, or docx document",
        keywords=["read doc", "document padho", "file read karo", "open document"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to document file", required=True),
            PluginParameter(name="max_chars", type="integer", description="Maximum characters to read", required=False, default=2000)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="create_document",
        description="Creates a new text or markdown note/document",
        keywords=["create note", "note likho", "document banao", "make document"],
        parameters=[
            PluginParameter(name="title", type="string", description="Document title", required=True),
            PluginParameter(name="content", type="string", description="Document content text", required=True),
            PluginParameter(name="format", type="string", description="File format (txt, md)", required=False, default="txt")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="search_documents",
        description="Searches for keywords inside documents in a folder",
        keywords=["search documents", "documents mein dhoondo", "notes search karo"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keyword", required=True),
            PluginParameter(name="directory", type="string", description="Folder path to search", required=False, default=".")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),

    # 10 New Actions
    PluginAction(
        name="create_docx_document",
        description="Creates a professional Word document (.docx) with heading, styled paragraphs, and bullet points",
        keywords=["create word doc", "docx banao", "word document banao", "make docx"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Output .docx file path", required=True),
            PluginParameter(name="title", type="string", description="Document main title", required=True),
            PluginParameter(name="paragraphs", type="array", description="List of paragraph strings", required=True),
            PluginParameter(name="bullet_points", type="array", description="Optional list of bullet points", required=False, default=[])
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="append_to_document",
        description="Appends new text content or sections to an existing document (.txt, .md, .docx)",
        keywords=["append document", "doc mein jodo", "add to document", "note mein add karo"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Target document file path", required=True),
            PluginParameter(name="content", type="string", description="Content to append", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="convert_document_format",
        description="Converts between document formats (e.g. txt to docx, docx to txt, md to txt)",
        keywords=["convert document", "document convert karo", "txt to docx", "docx to txt"],
        parameters=[
            PluginParameter(name="source_file", type="string", description="Source document path", required=True),
            PluginParameter(name="target_format", type="string", description="Target format: 'docx', 'txt', 'md'", required=True),
            PluginParameter(name="output_path", type="string", description="Optional output path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_document_statistics",
        description="Calculates detailed statistics: word count, lines, characters, and reading time",
        keywords=["document stats", "word count", "kitne words hain", "document length"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Document file path", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="search_and_replace_text",
        description="Searches and replaces text patterns inside a document with backup support",
        keywords=["replace text in doc", "find and replace doc", "word badlo document mein"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Document file path", required=True),
            PluginParameter(name="find_text", type="string", description="Text to find", required=True),
            PluginParameter(name="replace_text", type="string", description="Replacement text", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="compare_documents",
        description="Compares two text/markdown documents and outputs diff metrics and modified lines",
        keywords=["compare docs", "document diff", "do documents compare karo", "diff check"],
        parameters=[
            PluginParameter(name="file_a", type="string", description="First document path", required=True),
            PluginParameter(name="file_b", type="string", description="Second document path", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_document_sections",
        description="Extracts heading outline / table of contents from markdown or Word document",
        keywords=["document outline", "document headings", "toc extract karo", "document sections"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Document file path", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="export_text_to_docx",
        description="Exports plain text or markdown directly into a styled Word document",
        keywords=["export to docx", "save as word doc", "docx export"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text to format into docx", required=True),
            PluginParameter(name="destination_path", type="string", description="Output .docx file path", required=True),
            PluginParameter(name="title", type="string", description="Document title", required=False, default="Exported Document")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="merge_text_documents",
        description="Combines multiple text or markdown files into a single consolidated document",
        keywords=["merge documents", "documents jodo", "combine files", "concat documents"],
        parameters=[
            PluginParameter(name="file_paths", type="array", description="List of file paths to merge", required=True),
            PluginParameter(name="output_path", type="string", description="Consolidated document path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="inspect_document_metadata",
        description="Inspects file size, encoding, modified timestamp, and Word document core properties",
        keywords=["document metadata", "file info doc", "doc properties", "document details"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to document file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
