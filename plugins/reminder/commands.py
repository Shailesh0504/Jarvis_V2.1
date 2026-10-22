# plugins/reminder/commands.py
"""Command actions supported by Reminder Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="create_reminder",
        description="Schedules a new persistent reminder with optional recurrence",
        keywords=["create reminder", "remind me", "yaad dilana", "reminder lagao", "reminder set karo", "yaad dila do"],
        parameters=[
            PluginParameter(name="title", type="string", description="Reminder message/task to remember", required=True),
            PluginParameter(name="remind_time", type="string", description="ISO-8601 timestamp with timezone or relative offset", required=True),
            PluginParameter(name="recurrence", type="string", description="Recurrence type (none, daily, weekly, weekdays, monthly)", required=False, default="none"),
            PluginParameter(name="recurrence_rule", type="string", description="Recurrence rule details", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_reminders",
        description="Lists reminders with optional filter (pending, today, completed, recurring, missed, all)",
        keywords=["list reminders", "show reminders", "mere reminders dikhao", "aaj ke reminders", "saare reminders"],
        parameters=[
            PluginParameter(name="filter", type="string", description="Filter (all, pending, today, completed, recurring, missed)", required=False, default="pending")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="cancel_reminder",
        description="Cancels a scheduled reminder by ID or title keyword",
        keywords=["cancel reminder", "delete reminder", "reminder cancel karo", "reminder hatao"],
        parameters=[
            PluginParameter(name="reminder_id", type="integer", description="ID of reminder to cancel", required=False, default=0),
            PluginParameter(name="title", type="string", description="Title keyword of reminder", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="snooze_reminder",
        description="Snoozes an active or due reminder by specified minutes",
        keywords=["snooze reminder", "snooze karo", "thodi der baad yaad dilao"],
        parameters=[
            PluginParameter(name="reminder_id", type="integer", description="ID of reminder", required=False, default=0),
            PluginParameter(name="minutes", type="integer", description="Snooze duration in minutes", required=False, default=10)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="edit_reminder",
        description="Edits the scheduled time or title of an existing reminder",
        keywords=["edit reminder", "change reminder", "reminder shift karo"],
        parameters=[
            PluginParameter(name="reminder_id", type="integer", description="ID of reminder", required=True),
            PluginParameter(name="new_time", type="string", description="New ISO timestamp", required=False, default=""),
            PluginParameter(name="new_title", type="string", description="New title", required=False, default=""),
            PluginParameter(name="new_recurrence", type="string", description="New recurrence type (none, daily, weekly, weekdays, monthly)", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="toggle_reminders",
        description="Enables or disables reminder notifications system-wide",
        keywords=["enable reminders", "disable reminders", "reminders band karo", "reminder on", "reminder off"],
        parameters=[
            PluginParameter(name="enabled", type="boolean", description="Whether reminders are active", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="complete_reminder",
        description="Marks an active or due reminder as completed",
        keywords=["complete reminder", "mark reminder done", "reminder poora hua", "finish reminder"],
        parameters=[
            PluginParameter(name="reminder_id", type="integer", description="ID of reminder", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_next_upcoming",
        description="Retrieves the single earliest upcoming pending reminder with countdown time",
        keywords=["next reminder", "agla reminder", "upcoming reminder", "kya aane wala hai"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="search_reminders",
        description="Searches reminder database by keyword or regex in title/rule",
        keywords=["search reminders", "find reminder", "reminder dhoondo"],
        parameters=[
            PluginParameter(name="query", type="string", description="Keywords to match", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="bulk_cancel_reminders",
        description="Cancels all reminders matching a status (e.g. pending, missed)",
        keywords=["bulk cancel", "cancel all pending reminders", "saare pending reminder cancel"],
        parameters=[
            PluginParameter(name="status", type="string", description="Status to cancel (pending, missed)", required=False, default="pending")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="export_reminders",
        description="Exports reminders into an iCalendar (.ics) or JSON file",
        keywords=["export reminders", "backup reminders", "save reminders ics"],
        parameters=[
            PluginParameter(name="output_path", type="string", description="Output file path", required=False, default=""),
            PluginParameter(name="format", type="string", description="Format ('json' or 'ics')", required=False, default="json")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="import_reminders",
        description="Imports reminders from a JSON file or list",
        keywords=["import reminders", "restore reminders", "load reminders"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="JSON file path to import", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_reminder_stats",
        description="Calculates analytics on reminder completion rates, missed counts, and status distribution",
        keywords=["reminder stats", "reminder summary", "reminder report", "kitne reminder bache hain"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="reschedule_missed_reminders",
        description="Pushes missed reminders forward by a given number of minutes",
        keywords=["reschedule missed", "missed reminders aage badhao", "shift missed reminders"],
        parameters=[
            PluginParameter(name="minutes_ahead", type="integer", description="Minutes forward from now", required=False, default=60)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="clear_completed_reminders",
        description="Deletes old completed or cancelled reminders from the database",
        keywords=["clear completed reminders", "purge reminders", "clean old reminders"],
        parameters=[
            PluginParameter(name="older_than_days", type="integer", description="Purge items older than X days", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="calculate_countdown",
        description="Calculates remaining days, hours, minutes, and seconds until a reminder",
        keywords=["reminder countdown", "kitna time bacha hai", "time left for reminder"],
        parameters=[
            PluginParameter(name="reminder_id", type="integer", description="ID of reminder", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
