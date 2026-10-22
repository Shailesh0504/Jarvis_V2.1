# plugins/office/commands.py
"""Command actions supported by Office Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="create_word_doc",
        description="Creates a new Word (.docx) document with specified title and content",
        keywords=["create word doc", "word document banao", "word file banao"],
        parameters=[
            PluginParameter(name="title", type="string", description="Title or heading of the document", required=True),
            PluginParameter(name="content", type="string", description="Body text content", required=False, default=""),
            PluginParameter(name="file_path", type="string", description="Target file path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="create_powerpoint",
        description="Creates a new PowerPoint (.pptx) presentation with slides",
        keywords=["create presentation", "powerpoint presentation banao", "ppt banao"],
        parameters=[
            PluginParameter(name="title", type="string", description="Title of the presentation", required=True),
            PluginParameter(name="slides", type="array", description="List of slide titles and bullets", required=False, default=[]),
            PluginParameter(name="file_path", type="string", description="Target file path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="open_office_app",
        description="Opens Microsoft Word, PowerPoint, or Outlook",
        keywords=["open word", "open powerpoint", "word kholo", "ppt kholo"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="App name (word, powerpoint, outlook)", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="add_slide_to_presentation",
        description="Adds a new slide with title and bullet points to a PowerPoint presentation",
        keywords=["add slide", "slide jodo", "ppt slide add", "insert slide"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .pptx presentation", required=True),
            PluginParameter(name="title", type="string", description="Slide title", required=True),
            PluginParameter(name="bullets", type="list", description="List of bullet points or string", required=False, default=[]),
            PluginParameter(name="layout_index", type="integer", description="Slide layout index (default 1)", required=False, default=1)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_presentation_summary",
        description="Summarizes slides, titles, and word count of a PowerPoint presentation",
        keywords=["presentation summary", "ppt summary", "slide count", "read ppt"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .pptx presentation", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="convert_text_to_presentation",
        description="Converts outline text or Markdown into PowerPoint slides",
        keywords=["text to ppt", "markdown to presentation", "convert outline to ppt"],
        parameters=[
            PluginParameter(name="outline_text", type="string", description="Markdown or indented text outline", required=True),
            PluginParameter(name="output_path", type="string", description="Output .pptx presentation path", required=True),
            PluginParameter(name="title", type="string", description="Main presentation title", required=False, default="Presentation")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="extract_text_from_presentation",
        description="Extracts all textual content from a PowerPoint presentation",
        keywords=["extract ppt text", "read presentation text", "ppt text"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .pptx presentation", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="add_table_to_document",
        description="Appends a styled table to a Word document",
        keywords=["add table word", "word table", "insert table docx"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .docx document", required=True),
            PluginParameter(name="table_data", type="list", description="Rows of table data", required=True),
            PluginParameter(name="has_header", type="boolean", description="Whether first row is header", required=False, default=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="insert_image_into_document",
        description="Inserts an image into a Word document with optional caption",
        keywords=["insert image word", "add image docx", "picture in word"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .docx document", required=True),
            PluginParameter(name="image_path", type="string", description="Path to image file", required=True),
            PluginParameter(name="caption", type="string", description="Optional image caption", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_document_metadata",
        description="Retrieves metadata properties (author, title, stats) of a Word document",
        keywords=["doc metadata", "word properties", "docx stats"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .docx document", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="set_document_metadata",
        description="Sets author, title, and comments metadata on a Word document",
        keywords=["set doc properties", "update word author", "change doc title"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .docx document", required=True),
            PluginParameter(name="author", type="string", description="Author name", required=False, default=""),
            PluginParameter(name="title", type="string", description="Document title", required=False, default=""),
            PluginParameter(name="comments", type="string", description="Document comments/description", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="merge_word_documents",
        description="Combines multiple Word documents into a single master document",
        keywords=["merge docx", "combine word files", "join word docs"],
        parameters=[
            PluginParameter(name="file_paths", type="list", description="List of .docx paths to merge", required=True),
            PluginParameter(name="output_path", type="string", description="Output .docx file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="export_document_to_text",
        description="Exports paragraphs and tables from a Word document to plain text",
        keywords=["export word text", "docx to txt", "word text extract"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .docx document", required=True),
            PluginParameter(name="output_path", type="string", description="Optional output .txt path", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    )
]
