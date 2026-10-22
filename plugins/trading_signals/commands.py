# plugins/trading_signals/commands.py
"""Action definitions for Trading Signals Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel

ACTIONS = [
    PluginAction(
        name="start_signal_monitor",
        description="Starts the background screen-only trading signal engine.",
        keywords=["start trading monitor", "start signal engine", "options signal on", "trading monitor chalu karo"],
        parameters=[
            PluginParameter(name="window_filter", type="string", description="Optional window title filter", required=False, default=None)
        ],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="stop_signal_monitor",
        description="Stops the background trading signal engine.",
        keywords=["stop trading monitor", "stop signal engine", "options signal band karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="get_signal_status",
        description="Returns the current trading recommendation lifecycle and data feed status.",
        keywords=["trading status", "signal status", "current trade recommendation"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="set_strategy_mode",
        description="Configures the strategy mode (REGIME_CONFIRMED_OPTION_LEAD or DUAL_FRESH_TRIGGER).",
        keywords=["set strategy mode", "change trading mode"],
        parameters=[
            PluginParameter(name="mode", type="string", description="Strategy mode name", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="reset_signal_state",
        description="Resets the recommendation lifecycle state to FLAT.",
        keywords=["reset signal state", "clear active signal"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="pause_session",
        description="Pauses active trading chart analysis session.",
        keywords=["pause analysis", "pause trading", "pause chart analysis", "trading pause karo"],
        parameters=[
            PluginParameter(name="reason", type="string", description="Reason for pause", required=False, default="user_command")
        ],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="resume_session",
        description="Resumes paused trading chart analysis session.",
        keywords=["resume analysis", "resume trading", "resume chart analysis", "trading resume karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    ),
    PluginAction(
        name="analyze_this_chart",
        description="Forces visual chart analysis on the current foreground window.",
        keywords=["analyze this chart", "analyze current chart", "is chart ko analyze karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability="screen"
    )
]
