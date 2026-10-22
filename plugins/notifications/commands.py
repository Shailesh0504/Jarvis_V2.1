# plugins/notifications/commands.py
"""Command actions supported by Notifications Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="show_notification",
        description="Displays a system desktop toast notification",
        keywords=["show notification", "notification dikhao", "alert bhejo", "desktop toast"],
        parameters=[
            PluginParameter(name="title", type="string", description="Notification title", required=True),
            PluginParameter(name="message", type="string", description="Notification message body", required=True),
            PluginParameter(name="duration_ms", type="integer", description="Duration to display in milliseconds", required=False, default=3000)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_notifications",
        description="Lists recent system notification history",
        keywords=["recent notifications", "purani notifications", "notification history", "notification list"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum entries to return", required=False, default=20)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_notifications",
        description="Clears all notification history from the database",
        keywords=["clear notifications", "notifications clear karo", "purge notifications"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="show_warning_notification",
        description="Displays a desktop warning notification banner with warning sound",
        keywords=["warning notification", "warning alert", "khatra notification", "show warning"],
        parameters=[
            PluginParameter(name="title", type="string", description="Warning title", required=True),
            PluginParameter(name="message", type="string", description="Warning message body", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="show_error_notification",
        description="Displays an urgent desktop error alert with error icon",
        keywords=["error notification", "error alert", "system error toast", "show error"],
        parameters=[
            PluginParameter(name="title", type="string", description="Error title", required=True),
            PluginParameter(name="message", type="string", description="Error message body", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="show_actionable_notification",
        description="Creates an actionable notification with associated action targets or buttons",
        keywords=["actionable notification", "action notification", "interactive alert"],
        parameters=[
            PluginParameter(name="title", type="string", description="Notification title", required=True),
            PluginParameter(name="message", type="string", description="Notification message", required=True),
            PluginParameter(name="action_command", type="string", description="Command or URL triggered on click", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_unread_notifications_count",
        description="Returns the total count of unread desktop notifications",
        keywords=["unread notifications", "kitni notifications baki hain", "unread alert count"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="mark_notification_as_read",
        description="Marks a specific notification or all notifications as read",
        keywords=["mark notification read", "read mark karo", "notification padh li"],
        parameters=[
            PluginParameter(name="notification_id", type="integer", description="Notification ID to mark read, or 0 for all", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="search_notifications",
        description="Searches through notification history for matching keywords in title or message",
        keywords=["search notifications", "find notification", "notification dhundo"],
        parameters=[
            PluginParameter(name="query", type="string", description="Text search term", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="delete_notification_by_id",
        description="Deletes an individual notification record from history by ID",
        keywords=["delete notification", "remove notification", "notification hatao"],
        parameters=[
            PluginParameter(name="notification_id", type="integer", description="Notification ID to remove", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="filter_notifications_by_type",
        description="Filters stored notifications by severity type (info, warning, error, action)",
        keywords=["filter notifications", "warning notifications dikhao", "error history"],
        parameters=[
            PluginParameter(name="notification_type", type="string", description="Type to filter: info, warning, error, action", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="export_notification_history",
        description="Exports notification history to a JSON or CSV file",
        keywords=["export notifications", "save notifications log", "download notifications"],
        parameters=[
            PluginParameter(name="destination_path", type="string", description="File path for export (.json or .csv)", required=True),
            PluginParameter(name="format", type="string", description="Export format ('json' or 'csv')", required=False, default="json")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_notification_summary_stats",
        description="Returns statistical breakdown of notifications by severity, unread count, and total",
        keywords=["notification stats", "notification summary", "alert metrics"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
