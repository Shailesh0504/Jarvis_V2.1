# plugins/browser/__init__.py
"""Browser Plugin Package."""

from .plugin import BrowserPlugin
from .website_resolver import WebsiteResolver, WebsiteResolution

__all__ = ["BrowserPlugin", "WebsiteResolver", "WebsiteResolution"]
