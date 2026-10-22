# plugins/calendar/commands.py
"""Command actions supported by Calendar Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="add_event",
        description="Schedules a new event or meeting on the calendar",
        keywords=["add event", "meeting schedule karo", "calendar event", "event add karo"],
        parameters=[
            PluginParameter(name="title", type="string", description="Event or meeting title", required=True),
            PluginParameter(name="start_time", type="string", description="Start time/date (YYYY-MM-DD HH:MM or relative)", required=True),
            PluginParameter(name="duration_minutes", type="integer", description="Duration in minutes", required=False, default=60),
            PluginParameter(name="description", type="string", description="Optional meeting notes", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="list_events",
        description="Lists upcoming events and appointments",
        keywords=["list events", "appointments dikhao", "upcoming schedule", "calendar dikhao"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum number of events", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_today_agenda",
        description="Returns today's complete schedule and agenda",
        keywords=["today agenda", "aaj ka schedule", "aaj kya meetings hain", "today schedule"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),

    # 10 New Actions
    PluginAction(
        name="delete_event",
        description="Deletes an event by its ID or title",
        keywords=["delete event", "cancel meeting", "meeting cancel karo", "event hatao"],
        parameters=[
            PluginParameter(name="event_id", type="integer", description="ID of event to delete", required=False, default=-1),
            PluginParameter(name="title", type="string", description="Title of event to delete", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="update_event",
        description="Updates start time, title, or duration of an existing calendar event",
        keywords=["update event", "reschedule meeting", "meeting aage badhao", "event edit karo"],
        parameters=[
            PluginParameter(name="event_id", type="integer", description="ID of event", required=True),
            PluginParameter(name="title", type="string", description="New title", required=False, default=""),
            PluginParameter(name="start_time", type="string", description="New start time", required=False, default=""),
            PluginParameter(name="duration_minutes", type="integer", description="New duration in minutes", required=False, default=-1)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_upcoming_events",
        description="Returns all events scheduled within the next N days",
        keywords=["upcoming events", "agle dino ka schedule", "next week schedule", "future events"],
        parameters=[
            PluginParameter(name="days", type="integer", description="Number of days forward to search", required=False, default=7)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="search_events",
        description="Searches calendar events matching a keyword in title or description",
        keywords=["search events", "find meeting", "calendar search", "meeting dhoondho"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keyword", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="clear_past_events",
        description="Removes expired past events from calendar storage",
        keywords=["clear past events", "purge old meetings", "purane events hatao"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="export_events_ics",
        description="Exports calendar events to an industry-standard iCalendar (.ics) file",
        keywords=["export ics", "calendar to ics", "export calendar", "google calendar export"],
        parameters=[
            PluginParameter(name="output_path", type="string", description="Destination .ics file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="import_events_ics",
        description="Imports calendar events from an iCalendar (.ics) file",
        keywords=["import ics", "load ics calendar", "import calendar"],
        parameters=[
            PluginParameter(name="file_path", type="string", description="Path to .ics file", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="check_conflict",
        description="Checks if a prospective meeting time slot conflicts with existing appointments",
        keywords=["check meeting conflict", "is time free", "slot available", "kya main free hoon"],
        parameters=[
            PluginParameter(name="start_time", type="string", description="Proposed start time", required=True),
            PluginParameter(name="duration_minutes", type="integer", description="Proposed duration in minutes", required=False, default=60)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="get_weekly_agenda",
        description="Returns an overview of all meetings grouped by day for the current calendar week",
        keywords=["weekly agenda", "this week schedule", "is hafte ka schedule", "week overview"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.OFFICE.value
    ),
    PluginAction(
        name="init_persistent_storage",
        description="Initializes or verifies the persistent SQLite calendar database",
        keywords=["init calendar db", "check calendar database", "calendar storage status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
