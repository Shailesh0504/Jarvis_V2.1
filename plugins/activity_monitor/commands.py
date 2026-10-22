# plugins/activity_monitor/commands.py
"""Action declarations for Activity Monitor plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="get_current_activity",
        description="Retrieves the currently visible/active application, website, or media playing.",
        keywords=["current activity", "abhi kya chal raha hai", "active window", "kya dekh raha hoon"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_past_activity",
        description="Queries past activity or media (e.g. YouTube video watched) by temporal reference.",
        keywords=["past activity", "konsi video dekhi", "pichla video", "what was playing", "kya dekh raha tha"],
        parameters=[
            PluginParameter(name="website", type="string", description="Website filter (e.g. youtube)", required=False, default=""),
            PluginParameter(name="temporal", type="string", description="Temporal reference (abhi, last, thodi_der_pehle)", required=False, default="current"),
            PluginParameter(name="offset_minutes", type="integer", description="Minutes ago offset", required=False, default=0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_activity_history",
        description="Lists recent activity events history in chronological order.",
        keywords=["activity history", "recent activities", "activity log"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum number of events", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="poll_activity",
        description="Synchronously polls foreground screen state and updates activity memory.",
        keywords=["poll activity", "check screen now"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_idle_time",
        description="Measures current user inactivity / idle time in seconds and minutes.",
        keywords=["idle time", "system idle", "kitni der se shant hai", "inactivity"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_top_applications",
        description="Ranks applications by total active time and session count.",
        keywords=["top apps", "most used apps", "sabse zyada kya chalaya", "app usage"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum apps to return", required=False, default=5)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_productivity_score",
        description="Analyzes application usage and calculates productivity percentage.",
        keywords=["productivity score", "productivity report", "kitna kaam kiya", "productivity check"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_idle_alert",
        description="Sets an idle threshold in minutes and checks if system is currently idle past that limit.",
        keywords=["idle alert", "inactivity threshold", "check idle limit"],
        parameters=[
            PluginParameter(name="threshold_minutes", type="integer", description="Threshold in minutes", required=False, default=15)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="export_activity_log",
        description="Exports recorded activity history into a JSON or CSV file.",
        keywords=["export activity", "save activity log", "backup activity", "activity report export"],
        parameters=[
            PluginParameter(name="output_path", type="string", description="Destination file path", required=False, default=""),
            PluginParameter(name="format", type="string", description="File format ('json' or 'csv')", required=False, default="json")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="clear_activity_history",
        description="Clears all recorded activity events from memory.",
        keywords=["clear activity history", "reset activity log", "delete activity records"],
        parameters=[],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_session_summary",
        description="Provides a comprehensive statistical breakdown of monitored user sessions.",
        keywords=["session summary", "activity summary", "overall usage", "day summary"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="track_website_domain",
        description="Tallies total active duration spent on specific website domains.",
        keywords=["website domain tracking", "sites visited", "time on websites", "domain usage"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_focus_switches",
        description="Calculates window switching frequency to assess multitasking or distraction level.",
        keywords=["focus switches", "window switches", "multitasking rate", "distraction check"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="get_break_recommendation",
        description="Evaluates continuous active working duration and suggests ergonomic rest breaks.",
        keywords=["break recommendation", "should i take a break", "rest alert", "break chahiye"],
        parameters=[
            PluginParameter(name="max_continuous_minutes", type="integer", description="Target work interval in minutes", required=False, default=50)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    )
]
