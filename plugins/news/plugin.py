# plugins/news/plugin.py
"""
Live News Plugin implementation for Jarvis V2.1.
Delegates to authoritative LiveNewsEngine.
"""

import logging
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.knowledge.news import get_live_news_engine, NewsCategory
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.news")


class NewsPlugin(BasePlugin):
    """Fetches real-time internet news headlines across diverse topics."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(manifest=manifest, config=config)
        self.news_engine = get_live_news_engine()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="news",
            version="1.0.0",
            description="Live internet news headlines across general, tech, sports, business, and world news.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}
        limit = int(parameters.get("limit", 5))

        try:
            if action_name == "get_top_news":
                query_str = str(parameters.get("query", "latest news"))
                res = self.news_engine.query(query_str, limit=limit)
                return PluginResult(
                    success=res.found,
                    data={
                        "message": res.formatted_text,
                        "spoken": res.spoken_text,
                        "count": len(res.headlines),
                        "cached": res.cached
                    },
                    error=res.error
                )

            elif action_name == "get_category_news":
                cat_str = str(parameters.get("category", "top")).upper()
                try:
                    category = NewsCategory[cat_str]
                except KeyError:
                    category = NewsCategory.TOP
                res = self.news_engine.query(f"{cat_str} news", limit=limit)
                return PluginResult(
                    success=res.found,
                    data={
                        "message": res.formatted_text,
                        "spoken": res.spoken_text,
                        "count": len(res.headlines),
                        "category": category.value
                    },
                    error=res.error
                )

            elif action_name == "search_news":
                search_q = str(parameters.get("query", "")).strip()
                if not search_q:
                    return PluginResult(success=False, error="Search query is required.")
                res = self.news_engine.query(f"{search_q} news", limit=limit)
                return PluginResult(
                    success=res.found,
                    data={
                        "message": res.formatted_text,
                        "spoken": res.spoken_text,
                        "count": len(res.headlines),
                        "query": search_q
                    },
                    error=res.error
                )

            return PluginResult(success=False, error=f"Unknown news action: {action_name}")

        except Exception as e:
            logger.error("[NEWS_PLUGIN] Error executing %s: %s", action_name, e)
            return PluginResult(success=False, error=f"News retrieval failed: {e}")
