# plugins/apps/commands.py
"""Command actions supported by Apps Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="list_installed_apps",
        description="Lists installed Windows applications and desktop programs from registry and registry cache",
        keywords=["list apps", "installed applications", "software list", "apps list karo"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum number of apps to return", required=False, default=50)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="check_app_status",
        description="Checks if a specific application or process is currently running",
        keywords=["is app running", "app chal rahi hai kya", "check process", "app status"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name of application to check", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="launch_app",
        description="Launches any Windows application or program safely",
        keywords=["launch app", "open program", "chalao app", "app open karo"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="App name (e.g. spotify, chrome, notepad, calculator)", required=True),
            PluginParameter(name="arguments", type="string", description="Optional CLI arguments or file path to open", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),

    # 10 New Actions
    PluginAction(
        name="close_app",
        description="Gracefully closes or terminates running instances of an application",
        keywords=["close app", "band karo app", "terminate application", "kill app"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name or process name of application to close", required=True),
            PluginParameter(name="force", type="boolean", description="Force kill without waiting for graceful exit", required=False, default=False)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="restart_app",
        description="Closes and immediately restarts a running application",
        keywords=["restart app", "app dubara chalao", "reboot application", "relaunch app"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name of application to restart", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="get_app_resource_usage",
        description="Measures total CPU percent, RAM in MB, and thread count consumed by an application",
        keywords=["app resource usage", "app ram usage", "kitni memory le rahi hai app", "app cpu"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application name or process", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="list_running_apps",
        description="Returns all active desktop applications with visible windows or active user sessions",
        keywords=["running apps", "konsi apps chal rahi hain", "active programs", "active windows"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Maximum number of running apps to return", required=False, default=30)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="search_installed_apps",
        description="Searches installed applications in Windows Registry by query keyword",
        keywords=["search app", "find app", "kya ye software installed hai", "app dhundo"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keyword for application name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="get_app_version_info",
        description="Retrieves version, publisher, install date, and install directory of an installed app",
        keywords=["app version", "software version", "publisher info", "app details"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name of installed application", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="list_startup_apps",
        description="Lists all desktop applications registered to run automatically at Windows logon",
        keywords=["startup apps", "boot apps", "startup programs", "autostart list"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="bring_app_to_front",
        description="Brings the main window of a running application into the foreground focus",
        keywords=["focus app", "bring to front", "app aage lao", "maximize window app"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Name of application to bring to front", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="find_app_executable_path",
        description="Resolves the exact file path on disk of an application's executable binary",
        keywords=["where is app", "find executable", "app path batao", "app exe location"],
        parameters=[
            PluginParameter(name="app_name", type="string", description="Application or command name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="get_top_resource_apps",
        description="Returns the top applications consuming the most system memory (RAM) or CPU",
        keywords=["top memory apps", "heavy apps", "resource hungry programs", "most ram apps"],
        parameters=[
            PluginParameter(name="sort_by", type="string", description="'memory' or 'cpu'", required=False, default="memory"),
            PluginParameter(name="limit", type="integer", description="Number of top applications to list", required=False, default=10)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    )
]
