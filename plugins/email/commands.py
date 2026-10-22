# plugins/email/commands.py
"""Command actions supported by Email Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="send_email",
        description="Sends an email message via configured SMTP or opens native mail composer",
        keywords=["send email", "email bhejo", "mail karo", "send mail", "email dispatch"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient email address", required=True),
            PluginParameter(name="subject", type="string", description="Email subject", required=True),
            PluginParameter(name="body", type="string", description="Email message body", required=True),
            PluginParameter(name="smtp_server", type="string", description="Optional SMTP server host", required=False),
            PluginParameter(name="smtp_port", type="integer", description="Optional SMTP port (e.g. 587 or 465)", required=False),
            PluginParameter(name="sender_email", type="string", description="Optional sender email address", required=False),
            PluginParameter(name="sender_password", type="string", description="Optional sender password/app-token", required=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="check_unread_emails",
        description="Checks status of email drafts and inbox connectivity",
        keywords=["check email", "unread emails", "inbox check karo", "check inbox"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="compose_draft",
        description="Composes and saves an email draft persistently to local storage",
        keywords=["draft email", "draft likho", "save draft", "create email draft"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient email address", required=False, default=""),
            PluginParameter(name="subject", type="string", description="Subject line", required=True),
            PluginParameter(name="body", type="string", description="Body text", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),

    # 10 New Actions
    PluginAction(
        name="open_email_client",
        description="Launches the system default email client (Outlook, Thunderbird, Windows Mail)",
        keywords=["open email client", "open outlook", "open mail", "email kholo", "outlook kholo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Optional recipient email", required=False, default=""),
            PluginParameter(name="subject", type="string", description="Optional subject line", required=False, default=""),
            PluginParameter(name="body", type="string", description="Optional body content", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="create_mailto_url",
        description="Generates an RFC-compliant mailto URI with subject, body, and cc fields",
        keywords=["mailto url", "create mail link", "mailto banao", "generate mailto"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient email address", required=True),
            PluginParameter(name="subject", type="string", description="Email subject", required=False, default=""),
            PluginParameter(name="body", type="string", description="Email body text", required=False, default=""),
            PluginParameter(name="cc", type="string", description="Optional CC recipient", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="validate_email_address",
        description="Validates the syntax and structure of an email address",
        keywords=["validate email", "check email valid", "email check karo", "verify email address"],
        parameters=[
            PluginParameter(name="email", type="string", description="Email address to validate", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="save_local_draft",
        description="Persistently stores an email draft with an assigned ID and timestamp",
        keywords=["save local draft", "store draft", "draft save karo", "keep email draft"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient email", required=False, default=""),
            PluginParameter(name="subject", type="string", description="Subject line", required=True),
            PluginParameter(name="body", type="string", description="Draft message text", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="list_local_drafts",
        description="Lists all saved email drafts stored on the local system",
        keywords=["list drafts", "show drafts", "saved email drafts", "mere drafts dikhao"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Max drafts to return", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="delete_local_draft",
        description="Deletes a saved email draft by its ID",
        keywords=["delete draft", "remove draft", "draft delete karo", "draft hatao"],
        parameters=[
            PluginParameter(name="draft_id", type="integer", description="ID of draft to delete", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="export_draft_to_eml",
        description="Exports an email draft to an RFC 822 standard .eml file readable by Outlook/Thunderbird",
        keywords=["export eml", "save as eml", "email to file", "draft to eml"],
        parameters=[
            PluginParameter(name="draft_id", type="integer", description="ID of draft or -1 for params", required=False, default=-1),
            PluginParameter(name="recipient", type="string", description="Recipient email", required=False, default=""),
            PluginParameter(name="subject", type="string", description="Subject line", required=False, default=""),
            PluginParameter(name="body", type="string", description="Body text", required=False, default=""),
            PluginParameter(name="output_path", type="string", description="Destination .eml file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="send_smtp_email",
        description="Sends an email directly through an authenticated SMTP host with TLS/SSL",
        keywords=["smtp send", "send via smtp", "direct smtp mail", "asli email bhejo"],
        parameters=[
            PluginParameter(name="recipient", type="string", description="Recipient email", required=True),
            PluginParameter(name="subject", type="string", description="Subject line", required=True),
            PluginParameter(name="body", type="string", description="Body text", required=True),
            PluginParameter(name="smtp_server", type="string", description="SMTP host", required=True),
            PluginParameter(name="smtp_port", type="integer", description="SMTP port", required=False, default=587),
            PluginParameter(name="username", type="string", description="SMTP username/email", required=True),
            PluginParameter(name="password", type="string", description="SMTP password or app-password", required=True),
            PluginParameter(name="use_tls", type="boolean", description="Enable STARTTLS", required=False, default=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="verify_smtp_connection",
        description="Verifies network connectivity and authentication handshake to an SMTP mail server",
        keywords=["test smtp", "check smtp", "verify smtp", "smtp connection check"],
        parameters=[
            PluginParameter(name="smtp_server", type="string", description="SMTP host", required=True),
            PluginParameter(name="smtp_port", type="integer", description="SMTP port", required=False, default=587),
            PluginParameter(name="username", type="string", description="Optional username", required=False, default=""),
            PluginParameter(name="password", type="string", description="Optional password", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="create_email_template",
        description="Creates and stores a reusable email template",
        keywords=["email template", "create template", "email format banao", "save template"],
        parameters=[
            PluginParameter(name="name", type="string", description="Template identifier name", required=True),
            PluginParameter(name="subject_template", type="string", description="Subject with {placeholders}", required=True),
            PluginParameter(name="body_template", type="string", description="Body text with {placeholders}", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
