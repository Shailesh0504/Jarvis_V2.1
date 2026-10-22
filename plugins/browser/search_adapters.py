# plugins/browser/search_adapters.py
"""
Site-aware Search Registry and URL Adapters for Product Discovery & Web Search.
Supports site-specific query formatting, price constraint filters, URL encoding,
and safe fallbacks for arbitrary websites.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse

logger = logging.getLogger("jarvis.plugins.browser.search_adapters")


@dataclass
class SearchUrlResult:
    """Result of building a search URL for a target site."""
    site_key: str
    site_name: str
    url: str
    adapter_used: str  # "specific", "fallback_domain", "fallback_google"
    query: str
    filters: Dict[str, Any] = field(default_factory=dict)


class BaseSearchAdapter:
    """Base class for site-specific search URL adapters."""

    def __init__(self, site_name: str = "", base_url: str = ""):
        self.site_name = site_name
        self.base_url = base_url

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        """Construct the search results URL for the given query and optional filters."""
        raise NotImplementedError


class FlipkartSearchAdapter(BaseSearchAdapter):
    """Search adapter for Flipkart India with price filter parameter handling."""

    def __init__(self):
        super().__init__(site_name="Flipkart", base_url="https://www.flipkart.com/search")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        max_price = filters.get("max_price")
        min_price = filters.get("min_price")

        params = {"q": query}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}"

        # Flipkart price facet facets.price_range.to=MAX and facets.price_range.from=MIN
        if max_price or min_price:
            price_parts = []
            if min_price:
                price_parts.append(f"facets.price_range.from={min_price}")
            if max_price:
                price_parts.append(f"facets.price_range.to={max_price}")
            facet_val = urllib.parse.quote_plus("&".join(price_parts))
            url += f"&p%5B%5D={facet_val}"

        return SearchUrlResult(
            site_key="flipkart",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class AmazonSearchAdapter(BaseSearchAdapter):
    """Search adapter for Amazon India with price filter (paise) handling."""

    def __init__(self):
        super().__init__(site_name="Amazon", base_url="https://www.amazon.in/s")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        max_price = filters.get("max_price")
        min_price = filters.get("min_price")

        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?k={encoded_query}"

        # Amazon India rh=p_36:MIN-MAX where price is in paise (1 INR = 100 paise)
        if max_price or min_price:
            min_paise = int(min_price * 100) if min_price else ""
            max_paise = int(max_price * 100) if max_price else ""
            rh_val = urllib.parse.quote_plus(f"p_36:{min_paise}-{max_paise}")
            url += f"&rh={rh_val}"

        return SearchUrlResult(
            site_key="amazon",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class BlinkitSearchAdapter(BaseSearchAdapter):
    """Search adapter for Blinkit quick commerce."""

    def __init__(self):
        super().__init__(site_name="Blinkit", base_url="https://blinkit.com/s/")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}"

        return SearchUrlResult(
            site_key="blinkit",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class MyntraSearchAdapter(BaseSearchAdapter):
    """Search adapter for Myntra fashion."""

    def __init__(self):
        super().__init__(site_name="Myntra", base_url="https://www.myntra.com/")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        slug = urllib.parse.quote_plus(query).replace("+", "-")
        url = f"{self.base_url}{slug}"
        if filters.get("max_price") or filters.get("min_price"):
            min_p = filters.get("min_price", 0)
            max_p = filters.get("max_price", "")
            url += f"?f=Price%3A{min_p}.0_to_{max_p}.0"

        return SearchUrlResult(
            site_key="myntra",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class MeeshoSearchAdapter(BaseSearchAdapter):
    """Search adapter for Meesho."""

    def __init__(self):
        super().__init__(site_name="Meesho", base_url="https://www.meesho.com/search")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}"

        return SearchUrlResult(
            site_key="meesho",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class ZeptoSearchAdapter(BaseSearchAdapter):
    """Search adapter for Zepto quick commerce."""

    def __init__(self):
        super().__init__(site_name="Zepto", base_url="https://www.zeptonow.com/search")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?query={encoded_query}"

        return SearchUrlResult(
            site_key="zepto",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class YouTubeSearchAdapter(BaseSearchAdapter):
    """Search adapter for YouTube."""

    def __init__(self):
        super().__init__(site_name="YouTube", base_url="https://www.youtube.com/results")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?search_query={encoded_query}"

        return SearchUrlResult(
            site_key="youtube",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class GoogleSearchAdapter(BaseSearchAdapter):
    """Search adapter for Google."""

    def __init__(self):
        super().__init__(site_name="Google", base_url="https://www.google.com/search")

    def build_search_url(self, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        encoded_query = urllib.parse.quote_plus(query)
        url = f"{self.base_url}?q={encoded_query}"

        return SearchUrlResult(
            site_key="google",
            site_name=self.site_name,
            url=url,
            adapter_used="specific",
            query=query,
            filters=filters
        )


class GenericFallbackAdapter:
    """
    Fallback search adapter for unknown sites or arbitrary domains.
    Uses safe Google site search (e.g. google.com/search?q=site:example.com+query)
    or standard domain search.
    """

    @classmethod
    def build_search_url(cls, site: str, query: str, filters: Optional[Dict[str, Any]] = None) -> SearchUrlResult:
        filters = filters or {}
        clean_site = site.lower().strip()

        # Check if site contains domain extension
        if "." in clean_site:
            domain = clean_site.replace("https://", "").replace("http://", "").split("/")[0]
        else:
            domain = f"{re.sub(r'[^a-z0-9-]', '', clean_site)}.com"

        display_name = clean_site.capitalize()
        # Add price keywords into query if present for generic fallback
        full_query = query
        if filters.get("max_price"):
            full_query += f" under {filters['max_price']}"
        if filters.get("min_price"):
            full_query += f" above {filters['min_price']}"

        encoded_query = urllib.parse.quote_plus(full_query)
        url = f"https://www.google.com/search?q=site:{domain}+{encoded_query}"

        return SearchUrlResult(
            site_key=clean_site,
            site_name=display_name,
            url=url,
            adapter_used="fallback_google",
            query=query,
            filters=filters
        )


class SearchSiteRegistry:
    """
    Configurable site registry for product and web searches.
    Allows registering custom site adapters dynamically without changing the intent detector.
    """

    _adapters: Dict[str, BaseSearchAdapter] = {}
    _aliases: Dict[str, str] = {}

    @classmethod
    def initialize_defaults(cls) -> None:
        """Populate built-in search adapters."""
        cls._adapters.clear()
        cls._aliases.clear()

        # Flipkart
        cls.register_adapter("flipkart", FlipkartSearchAdapter(), aliases=["fk", "flipcart", "flipkart.com"])

        # Amazon India
        cls.register_adapter("amazon", AmazonSearchAdapter(), aliases=["amzn", "amazon in", "amazon india", "amazon.in", "amazon.com"])

        # Blinkit
        cls.register_adapter("blinkit", BlinkitSearchAdapter(), aliases=["grofers", "blink it", "blinkit.com"])

        # Myntra
        cls.register_adapter("myntra", MyntraSearchAdapter(), aliases=["myntra.com"])

        # Meesho
        cls.register_adapter("meesho", MeeshoSearchAdapter(), aliases=["meesho.com"])

        # Zepto
        cls.register_adapter("zepto", ZeptoSearchAdapter(), aliases=["zeptonow", "zepto.com"])

        # YouTube
        cls.register_adapter("youtube", YouTubeSearchAdapter(), aliases=["yt", "youtube.com"])

        # Google
        cls.register_adapter("google", GoogleSearchAdapter(), aliases=["google.com", "google.co.in", "web"])

    @classmethod
    def register_adapter(
        cls,
        site_key: str,
        adapter: BaseSearchAdapter,
        aliases: Optional[List[str]] = None
    ) -> None:
        """Register a search adapter with optional aliases."""
        key = site_key.lower().strip()
        cls._adapters[key] = adapter
        cls._aliases[key] = key
        if aliases:
            for alias in aliases:
                cls._aliases[alias.lower().strip()] = key

    @classmethod
    def get_adapter(cls, site: str) -> Optional[BaseSearchAdapter]:
        """Look up a search adapter by site name or alias."""
        norm_site = site.lower().strip()
        resolved_key = cls._aliases.get(norm_site, norm_site)
        return cls._adapters.get(resolved_key)

    @classmethod
    def build_search_url(
        cls,
        site: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchUrlResult:
        """Build search results URL using registered adapter or safe fallback."""
        if not cls._adapters:
            cls.initialize_defaults()

        norm_site = (site or "google").lower().strip()
        adapter = cls.get_adapter(norm_site)
        if adapter:
            return adapter.build_search_url(query, filters)

        # Fallback to generic domain / Google search
        return GenericFallbackAdapter.build_search_url(norm_site, query, filters)


# Initialize default adapters on module import
SearchSiteRegistry.initialize_defaults()
