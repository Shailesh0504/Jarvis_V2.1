# plugins/games/commands.py
"""Command actions supported by Games Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="open_chess",
        description="Launches the Chess game application",
        keywords=["open chess", "chess kholo", "play chess", "chess game", "chess chalao", "start chess", "chess open karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="launch_game",
        description="Launches a specified game",
        keywords=["open game", "play game", "game chalao", "game start karo", "game kholo"],
        parameters=[
            PluginParameter(name="game_name", type="string", description="Name of the game to launch", required=True, default="chess")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="scan_installed_games",
        description="Scans system drives, Steam libraries, and registry for installed games",
        keywords=["scan games", "installed games", "find games", "list games"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="detect_running_games",
        description="Detects currently running game processes and their resource consumption",
        keywords=["running games", "active game", "what game is playing", "game process"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="enable_game_mode",
        description="Optimizes Windows system performance and process priorities for gaming",
        keywords=["game mode", "boost game", "gaming boost", "turbo mode"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="disable_game_mode",
        description="Restores standard system power and process priorities after gaming",
        keywords=["disable game mode", "normal mode", "stop game boost"],
        parameters=[],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="set_game_priority",
        description="Sets Windows process priority for a specified game process",
        keywords=["game priority", "boost process", "set priority"],
        parameters=[
            PluginParameter(name="process_name", type="string", description="Game process name or executable", required=True),
            PluginParameter(name="priority", type="string", description="Priority level: high, realtime, above_normal, normal", required=False, default="high")
        ],
        required_permission=PermissionLevel.ADMIN,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="log_game_session",
        description="Logs a gaming session with duration and notes into persistent storage",
        keywords=["log game session", "record game time", "save gaming session"],
        parameters=[
            PluginParameter(name="game_name", type="string", description="Game title", required=True),
            PluginParameter(name="duration_minutes", type="float", description="Session duration in minutes", required=True),
            PluginParameter(name="notes", type="string", description="Optional session notes", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="get_game_session_stats",
        description="Returns total playtime statistics and recent history from logged game sessions",
        keywords=["game stats", "gaming playtime", "how much did i play", "game time"],
        parameters=[
            PluginParameter(name="game_name", type="string", description="Optional game name filter", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="take_game_screenshot",
        description="Captures and saves a timestamped screenshot in the gaming screenshot directory",
        keywords=["game screenshot", "gaming screenshot", "capture game screen"],
        parameters=[
            PluginParameter(name="game_name", type="string", description="Game title for categorization", required=False, default="general")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="list_steam_games",
        description="Parses Steam library manifests and lists all installed Steam games",
        keywords=["steam games", "installed steam games", "list steam"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="kill_game_process",
        description="Gracefully or forcefully closes a specified game process",
        keywords=["kill game", "close game", "quit game", "stop game process"],
        parameters=[
            PluginParameter(name="process_name", type="string", description="Game process name or executable", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    )
]
