# plugins/printer/commands.py
"""Command actions supported by Printer Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="list_printers",
        description="Lists installed printers and printing devices",
        keywords=["list printers", "printers dikhao", "available printers", "printer list"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_default_printer",
        description="Returns the current default Windows printer",
        keywords=["default printer", "default printer konsa hai", "current printer"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="print_file",
        description="Sends a document to the printer",
        keywords=["print document", "print karo", "file print karo", "print paper"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to file to print", required=True),
            PluginParameter(name="printer_name", type="string", description="Specific printer name", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="set_default_printer",
        description="Sets a specified printer as the system default printer",
        keywords=["set default printer", "default printer badlo", "make default printer"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Name of printer to set as default", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_printer_queue_status",
        description="Inspects active print queue jobs and pending documents for a printer",
        keywords=["printer queue", "print jobs", "pending prints", "queue status"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name (leave empty for default)", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="cancel_print_job",
        description="Cancels an individual print job by job ID",
        keywords=["cancel print job", "print cancel karo", "stop print job"],
        parameters=[
            PluginParameter(name="job_id", type="integer", description="Print Job ID to cancel", required=True),
            PluginParameter(name="printer_name", type="string", description="Printer name", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_print_queue",
        description="Purges and clears all pending jobs in a printer's spooler queue",
        keywords=["clear print queue", "purge print queue", "saaf karo print queue", "cancel all prints"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name (leave empty for default)", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="pause_printer",
        description="Temporarily pauses a printer queue from processing jobs",
        keywords=["pause printer", "printer roko", "hold printer"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="resume_printer",
        description="Resumes a paused printer queue",
        keywords=["resume printer", "printer shuru karo", "unpause printer"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_printer_properties",
        description="Retrieves detailed driver, port, location, and status properties of a printer",
        keywords=["printer properties", "printer details", "printer driver info", "printer specs"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name (leave empty for default)", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="print_text_direct",
        description="Prints raw text or notes directly by creating a temporary document",
        keywords=["print text", "text print karo", "quick print note", "print message"],
        parameters=[
            PluginParameter(name="text", type="string", description="Text content to print", required=True),
            PluginParameter(name="printer_name", type="string", description="Optional specific printer name", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="print_pdf_file",
        description="Prints a PDF document with optional copy count and printer targeting",
        keywords=["print pdf", "pdf print karo", "send pdf to printer"],
        parameters=[
            PluginParameter(name="pdf_path", type="string", description="Path to PDF file", required=True),
            PluginParameter(name="printer_name", type="string", description="Target printer name", required=False, default=""),
            PluginParameter(name="copies", type="integer", description="Number of copies", required=False, default=1)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="check_printer_online_status",
        description="Checks if a printer is currently online, ready, or experiencing an error state",
        keywords=["is printer online", "printer ready hai kya", "printer health", "printer check"],
        parameters=[
            PluginParameter(name="printer_name", type="string", description="Printer name (leave empty for default)", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
