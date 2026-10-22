# plugins/equity_research/commands.py
"""Command definitions for Equity Research Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="research_shortlist",
        description="Screens liquid Indian equities and generates a multi-factor 1-month investment research shortlist",
        keywords=[
            "1 month ke liye best stock batao",
            "ek mahine ke liye stock suggest karo",
            "swing trading shortlist dikhao",
            "equity research report",
            "stock ideas batao",
            "short term investment research",
            "top stock picks 1 month",
        ],
        parameters=[
            PluginParameter(name="capital", type="float", description="Total investment capital in INR", required=False, default=100000.0),
            PluginParameter(name="risk_tolerance", type="string", description="Risk tolerance (CONSERVATIVE, MODERATE, AGGRESSIVE)", required=False, default="MODERATE"),
            PluginParameter(name="strategy", type="string", description="Preferred strategy (trend_following, breakout, mean_reversion, or any)", required=False, default="any"),
            PluginParameter(name="sector_preference", type="string", description="Optional sector filter", required=False, default=None),
            PluginParameter(name="output_mode", type="string", description="Output depth (QUICK, STANDARD, DETAILED)", required=False, default="STANDARD"),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="analyze_stock",
        description="Performs comprehensive multi-factor technical, fundamental, and risk analysis for a specific Indian stock",
        keywords=[
            "reliance ka analysis karo",
            "tcs ka 1 month outlook kya hai",
            "hdfc bank stock research",
            "infy technical setup kaisa hai",
            "analyze stock",
        ],
        parameters=[
            PluginParameter(name="symbol", type="string", description="NSE Stock ticker (e.g. RELIANCE, TCS, INFY)", required=True),
            PluginParameter(name="output_mode", type="string", description="Output depth (QUICK, STANDARD, DETAILED)", required=False, default="STANDARD"),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="market_regime",
        description="Checks current Indian market regime, NIFTY trend, India VIX, and breadth conditions",
        keywords=[
            "aaj market kaisa hai",
            "market regime kya hai",
            "nifty trend kaisa hai",
            "market condition kaisi hai",
            "india vix kaisa hai",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="monitor_stock",
        description="Adds a stock setup to active 30-day thesis monitoring or checks thesis status",
        keywords=[
            "is stock ko monitor karo",
            "track this setup",
            "monitor list dikhao",
            "thesis update check karo",
        ],
        parameters=[
            PluginParameter(name="symbol", type="string", description="Stock ticker to track or check", required=False),
            PluginParameter(name="action_type", type="string", description="add, check, or list", required=False, default="list"),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="update_profile",
        description="Updates user investment profile (capital, risk tolerance, sector preference, loss tolerance)",
        keywords=[
            "mera investment budget update karo",
            "risk profile change karo",
            "investment preference set karo",
        ],
        parameters=[
            PluginParameter(name="capital", type="float", description="Total capital in INR", required=False),
            PluginParameter(name="risk_tolerance", type="string", description="CONSERVATIVE, MODERATE, or AGGRESSIVE", required=False),
            PluginParameter(name="max_loss_tolerance_pct", type="float", description="Max portfolio loss tolerance %", required=False),
            PluginParameter(name="sector_preference", type="string", description="Preferred sector", required=False),
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="open_wizard",
        description="Opens the professional Stock Query Wizard web interface in the browser",
        keywords=[
            "stock wizard kholo",
            "open stock wizard",
            "stock selection window open karo",
            "stock decision ui",
        ],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
    PluginAction(
        name="suggest_stocks",
        description="Scans and suggests actionable intraday momentum or multi-day swing trades with technical confluence and entry/target/SL levels",
        keywords=[
            "stock suggest karo",
            "stock suggestions",
            "stock suggestion",
            "intraday ke liye stock suggest karo",
            "intraday trading ke liye stock batao",
            "swing trade ke liye stock batao",
            "swing trading ke liye stock suggest karo",
            "aaj intraday ke liye kaunsa stock le",
            "best stock for intraday",
            "best stock for swing trade",
            "stocks suggest karo",
            "stock trade suggestions dikhao",
            "intraday stock",
            "swing stock",
        ],
        parameters=[
            PluginParameter(name="trade_type", type="string", description="Trade type filter: intraday, swing, or all", required=False, default="all"),
            PluginParameter(name="capital", type="float", description="Capital in INR", required=False, default=50000.0),
            PluginParameter(name="risk_pct", type="float", description="Risk percentage per trade", required=False, default=1.0),
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value,
    ),
]

