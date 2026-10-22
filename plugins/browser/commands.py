# plugins/browser/commands.py
"""Command actions supported by Browser plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    PluginAction(
        name="open_website",
        description="Resolves a website name or domain and opens its most likely official page",
        keywords=["open website", "website kholo", "site kholo", "official website"],
        parameters=[
            PluginParameter(name="site", type="string", description="Website brand, name, or domain", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="open_url",
        description="Opens a URL in the default or preferred web browser",
        keywords=["open url", "go to website", "browse to", "open link"],
        parameters=[
            PluginParameter(name="url", type="string", description="URL to navigate to", required=True),
            PluginParameter(name="browser", type="string", description="Optional browser override", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="search_google",
        description="Searches Google in the browser",
        keywords=["search google", "google search", "search web", "google karo"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keywords", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="search_website",
        description="Searches on a specific website or the active website with optional filters",
        keywords=["search website", "website search", "site search", "search products", "product search", "dikhao"],
        parameters=[
            PluginParameter(name="query", type="string", description="Search keywords", required=True),
            PluginParameter(name="site", type="string", description="Website brand or domain", required=False, default="google"),
            PluginParameter(name="filters", type="object", description="Optional search filters (e.g. max_price, min_price)", required=False, default={})
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="parse_url",
        description="Decomposes a URL into scheme, domain, path, query parameters, fragment, and security status",
        keywords=["parse url", "breakdown url", "analyze url", "url details"],
        parameters=[
            PluginParameter(name="url", type="string", description="The URL to parse", required=True)
        ],
        required_permission=PermissionLevel.READ
    ),
    PluginAction(
        name="build_url",
        description="Constructs a normalized URL from base path, query parameters, and fragment",
        keywords=["build url", "create url", "make link", "format url"],
        parameters=[
            PluginParameter(name="base_url", type="string", description="Base URL / domain", required=True),
            PluginParameter(name="path", type="string", description="Optional path suffix", required=False, default=""),
            PluginParameter(name="params", type="object", description="Key-value dictionary of query parameters", required=False, default={}),
            PluginParameter(name="fragment", type="string", description="Optional URL fragment/hash", required=False, default="")
        ],
        required_permission=PermissionLevel.READ
    ),
    PluginAction(
        name="check_url_reachable",
        description="Checks whether a URL is online, reachable, and returns response code and headers",
        keywords=["check url", "is site online", "ping url", "site status", "test website"],
        parameters=[
            PluginParameter(name="url", type="string", description="URL to check", required=True),
            PluginParameter(name="timeout", type="int", description="Timeout in seconds", required=False, default=5)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="extract_page_metadata",
        description="Extracts page title, description, and OpenGraph metadata from a webpage",
        keywords=["page metadata", "extract title", "website info", "page preview"],
        parameters=[
            PluginParameter(name="url", type="string", description="URL to inspect", required=True)
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value
    ),
    PluginAction(
        name="save_bookmark",
        description="Saves a website bookmark with title, tags, and category into local storage",
        keywords=["save bookmark", "add bookmark", "bookmark page", "pin site"],
        parameters=[
            PluginParameter(name="url", type="string", description="Website URL", required=True),
            PluginParameter(name="title", type="string", description="Bookmark title", required=True),
            PluginParameter(name="category", type="string", description="Category or tag", required=False, default="General")
        ],
        required_permission=PermissionLevel.WRITE
    ),
    PluginAction(
        name="list_bookmarks",
        description="Lists saved browser bookmarks with optional category or query filter",
        keywords=["list bookmarks", "show bookmarks", "my bookmarks", "saved sites"],
        parameters=[
            PluginParameter(name="category", type="string", description="Optional category filter", required=False, default=""),
            PluginParameter(name="query", type="string", description="Optional title/URL search query", required=False, default="")
        ],
        required_permission=PermissionLevel.READ
    ),
    PluginAction(
        name="delete_bookmark",
        description="Deletes a bookmark by URL or title",
        keywords=["delete bookmark", "remove bookmark"],
        parameters=[
            PluginParameter(name="url_or_title", type="string", description="URL or title of bookmark to remove", required=True)
        ],
        required_permission=PermissionLevel.WRITE
    ),
    PluginAction(
        name="get_browser_info",
        description="Detects installed browsers on the system (Chrome, Edge, Brave, Firefox) and their executable paths",
        keywords=["installed browsers", "browser info", "find browsers", "system browsers"],
        parameters=[],
        required_permission=PermissionLevel.READ
    ),
    PluginAction(
        name="open_incognito",
        description="Opens a URL or new private window in incognito / InPrivate mode",
        keywords=["open incognito", "private browsing", "inprivate", "incognito kholo"],
        parameters=[
            PluginParameter(name="url", type="string", description="URL to open in private mode", required=False, default="https://www.google.com"),
            PluginParameter(name="browser", type="string", description="Preferred browser (brave, chrome, edge, firefox)", required=False, default="")
        ],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.PROCESS.value
    ),
    PluginAction(
        name="clear_browser_cache_info",
        description="Inspects local browser cache directories and calculates size on disk",
        keywords=["browser cache size", "check cache", "browser data size"],
        parameters=[
            PluginParameter(name="browser", type="string", description="Specific browser or 'all'", required=False, default="all")
        ],
        required_permission=PermissionLevel.READ
    )
]
