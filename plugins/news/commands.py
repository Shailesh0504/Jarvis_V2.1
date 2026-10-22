# plugins/news/commands.py
"""
Command actions for the Live News Plugin.
"""

from core.permissions import PermissionLevel
from plugins.manifest import PluginAction, PluginParameter

ACTIONS = [
    PluginAction(
        name="get_top_news",
        description="Fetches and displays live top news headlines from internet feed",
        keywords=["news", "news batao", "abhi ki news", "aaj ki news", "latest news", "headlines", "samachar", "taza khabar"],
        parameters=[
            PluginParameter(name="limit", type="integer", description="Number of headlines to return (default 5)", required=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="get_category_news",
        description="Fetches live news headlines for a specific category (technology, sports, business, world)",
        keywords=["tech news", "sports news", "business news", "world news", "khel samachar", "cricket news"],
        parameters=[
            PluginParameter(name="category", type="string", description="Category name (technology, sports, business, world)", required=True),
            PluginParameter(name="limit", type="integer", description="Number of headlines", required=False)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
    PluginAction(
        name="search_news",
        description="Searches live news headlines by custom keyword or topic",
        keywords=["search news", "news search", "topic news"],
        parameters=[
            PluginParameter(name="query", type="string", description="Keyword or subject to search in live news", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=None
    ),
]
