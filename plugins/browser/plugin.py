# plugins/browser/plugin.py
"""Browser Plugin implementation with Offline-First Guard."""

import urllib.parse
import urllib.request
import webbrowser
import logging
from typing import Any, Dict
from core.connectivity import ConnectivityManager
from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED
from .website_resolver import WebsiteResolver
from .search_adapters import SearchSiteRegistry

logger = logging.getLogger("jarvis.plugins.browser")


class BrowserPlugin(BasePlugin):
    """Web browser controller with offline awareness."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self.connectivity = ConnectivityManager()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="browser",
            version="1.0.0",
            description="Default web browser controller and URL opener.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    @staticmethod
    def resolve_website_url(site: str) -> tuple[str, bool]:
        """Backward-compatible wrapper returning the resolver's final URL."""
        try:
            result = WebsiteResolver.resolve(site)
            return result.final_url, result.source in {"canonical", "domain"}
        except ValueError:
            return "", False

    def execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        ONLINE_ACTIONS = {
            "open_website", "open_url", "search_google", "search_website",
            "check_url_reachable", "extract_page_metadata", "open_incognito"
        }
        if action_name in ONLINE_ACTIONS and self.connectivity.is_offline:
            return PluginResult(
                success=False,
                error="Internet connection is currently offline. Web browser navigation requires internet access, Boss."
            )

        if action_name == "open_website":
            site = parameters.get("site", "").strip()
            logger.info("WEBSITE_QUERY query=%r", site)
            try:
                resolution = WebsiteResolver.resolve(site, parameters.get("search_candidates"))
            except ValueError as exc:
                return PluginResult(success=False, error=str(exc))
            logger.info("URL_RESOLVED url=%s source=%s", resolution.resolved_url, resolution.source)
            logger.info("REDIRECT_UNWRAPPED changed=%s url=%s", resolution.redirect_unwrapped, resolution.final_url)
            logger.info("FINAL_URL url=%s", resolution.final_url)
            logger.info("BROWSER_NAVIGATE url=%s", resolution.final_url)
            pref_browser = parameters.get("browser") or parameters.get("container") or ""
            force_new = bool(parameters.get("force_new") or parameters.get("new_tab"))
            opened = False
            if pref_browser:
                opened = self._launch_in_browser(resolution.final_url, pref_browser)
            if not opened:
                opened = bool(webbrowser.open_new_tab(resolution.final_url) if force_new else webbrowser.open(resolution.final_url))
            if not opened:
                return PluginResult(success=False, error=f"Browser ne '{site}' open request accept nahi ki.")
            return PluginResult(success=True, data={
                "site": site,
                "url": resolution.final_url,
                "browser": pref_browser,
                "resolution": resolution.source,
                "status": "opened",
                # Browser APIs acknowledge a navigation request, but cannot
                # reliably inspect a page DOM/title across every browser.
                "verification": "unknown",
                "force_new": force_new,
                "message": f"Opening {resolution.canonical_name or site}." if not pref_browser else f"Opening {resolution.canonical_name or site} in {pref_browser.capitalize()}."
            })

        if action_name == "open_url":
            url = parameters.get("url", "").strip()
            if not url:
                return PluginResult(success=False, error="URL parameter is required.")
            try:
                url = WebsiteResolver.sanitize_url(url)
            except ValueError as exc:
                return PluginResult(success=False, error=str(exc))

            pref_browser = parameters.get("browser") or parameters.get("container") or ""
            force_new = bool(parameters.get("force_new") or parameters.get("new_tab"))
            opened = False
            if pref_browser:
                opened = self._launch_in_browser(url, pref_browser)
            if not opened:
                opened = bool(webbrowser.open_new_tab(url) if force_new else webbrowser.open(url))
            if not opened:
                return PluginResult(success=False, error=f"Browser ne URL open request accept nahi ki: {url}")
            return PluginResult(
                success=True,
                data={
                    "url": url,
                    "browser": pref_browser,
                    "status": "opened",
                    "verification": "unknown",
                    "force_new": force_new,
                    "message": f"Opened {url} in {pref_browser.capitalize()}." if pref_browser else f"Opened {url} in browser."
                }
            )

        elif action_name == "search_google":
            query = parameters.get("query", "").strip()
            if not query:
                return PluginResult(success=False, error="Query parameter is required.")
            encoded = urllib.parse.quote_plus(query)
            url = f"https://www.google.com/search?q={encoded}"
            webbrowser.open(url)
            return PluginResult(
                success=True,
                data={"query": query, "url": url, "message": f"Searched Google for '{query}' in browser."}
            )

        elif action_name == "search_website":
            query = parameters.get("query", "").strip()
            site = parameters.get("site", "google").strip().lower()
            filters = dict(parameters.get("filters") or {})
            if "max_price" in parameters and "max_price" not in filters:
                filters["max_price"] = parameters["max_price"]
            if "min_price" in parameters and "min_price" not in filters:
                filters["min_price"] = parameters["min_price"]

            if not query:
                return PluginResult(
                    success=False,
                    error="Query parameter is required for website search.",
                    data={"site": site, "query": "", "url": "", "success": False, "error": "Query parameter is required"}
                )

            search_result = SearchSiteRegistry.build_search_url(site=site, query=query, filters=filters)
            final_url = search_result.url
            display_site = search_result.site_name

            logger.info("WEBSITE_SEARCH site=%s display=%s url=%s query=%r filters=%s", site, display_site, final_url, query, filters)
            force_new = bool(parameters.get("force_new") or parameters.get("new_tab"))
            try:
                opened = bool(webbrowser.open_new_tab(final_url) if force_new else webbrowser.open(final_url))
            except Exception as exc:
                logger.error("Browser launch error for search: %s", exc)
                opened = False

            if not opened:
                return PluginResult(
                    success=False,
                    error=f"Browser ne '{display_site}' par '{query}' search page open karne se mana kar diya.",
                    data={
                        "site": display_site,
                        "query": query,
                        "url": final_url,
                        "filters": filters,
                        "success": False,
                        "error": f"Browser navigation failed for {final_url}",
                        "message": f"Browser ne '{display_site}' par search open karne se mana kar diya."
                    }
                )

            price_info = ""
            if filters.get("max_price"):
                price_info = f" ({filters['max_price']} ke andar)"
            elif filters.get("min_price"):
                price_info = f" ({filters['min_price']} se upar)"

            msg = f"{display_site} par '{query}'{price_info} search karke results dikha diye hain, Boss."
            return PluginResult(
                success=True,
                data={
                    "site": display_site,
                    "query": query,
                    "url": final_url,
                    "filters": filters,
                    "success": True,
                    "error": None,
                    "message": msg
                }
            )

        elif action_name == "parse_url":
            raw_url = str(parameters.get("url", "")).strip()
            if not raw_url:
                return PluginResult(success=False, error="URL parameter is required.")
            parsed = urllib.parse.urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
            qs = urllib.parse.parse_qs(parsed.query)
            # Flatten single-item query parameters
            query_dict = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
            return PluginResult(success=True, data={
                "original_url": raw_url,
                "scheme": parsed.scheme,
                "netloc": parsed.netloc,
                "hostname": parsed.hostname or "",
                "port": parsed.port,
                "path": parsed.path,
                "query_params": query_dict,
                "fragment": parsed.fragment,
                "is_secure": parsed.scheme.lower() == "https"
            })

        elif action_name == "build_url":
            base = str(parameters.get("base_url", "")).strip()
            if not base:
                return PluginResult(success=False, error="base_url parameter is required.")
            if not (base.startswith("http://") or base.startswith("https://")):
                base = "https://" + base
            path = str(parameters.get("path", "")).strip()
            params = parameters.get("params") or {}
            fragment = str(parameters.get("fragment", "")).strip()

            parsed = urllib.parse.urlparse(base)
            combined_path = (parsed.path.rstrip("/") + "/" + path.lstrip("/")) if path else parsed.path
            query_str = urllib.parse.urlencode(params) if params else parsed.query
            constructed = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                combined_path,
                parsed.params,
                query_str,
                fragment or parsed.fragment
            ))
            return PluginResult(success=True, data={"url": constructed})

        elif action_name == "check_url_reachable":
            url = str(parameters.get("url", "")).strip()
            if not url:
                return PluginResult(success=False, error="URL parameter is required.")
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url
            timeout = int(parameters.get("timeout", 5))
            import time
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    code = resp.getcode()
                    content_type = resp.headers.get("Content-Type", "")
                    elapsed_ms = round((time.time() - t0) * 1000, 2)
                    return PluginResult(success=True, data={
                        "url": url,
                        "reachable": True,
                        "status_code": code,
                        "content_type": content_type,
                        "response_time_ms": elapsed_ms
                    })
            except Exception as exc:
                elapsed_ms = round((time.time() - t0) * 1000, 2)
                return PluginResult(success=True, data={
                    "url": url,
                    "reachable": False,
                    "error": str(exc),
                    "response_time_ms": elapsed_ms
                })

        elif action_name == "extract_page_metadata":
            url = str(parameters.get("url", "")).strip()
            if not url:
                return PluginResult(success=False, error="URL parameter is required.")
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url
            meta = self._extract_metadata(url)
            return PluginResult(success=True, data=meta)

        elif action_name == "save_bookmark":
            url = str(parameters.get("url", "")).strip()
            title = str(parameters.get("title", "")).strip()
            category = str(parameters.get("category", "General")).strip()
            if not url or not title:
                return PluginResult(success=False, error="Both 'url' and 'title' are required to save a bookmark.")
            item = self._add_bookmark(url, title, category)
            return PluginResult(success=True, data=item)

        elif action_name == "list_bookmarks":
            category = parameters.get("category")
            query = parameters.get("query")
            items = self._get_bookmarks(
                category=str(category).strip() if category else None,
                query=str(query).strip() if query else None
            )
            return PluginResult(success=True, data={"bookmarks": items, "count": len(items)})

        elif action_name == "delete_bookmark":
            key = str(parameters.get("url_or_title", "")).strip()
            if not key:
                return PluginResult(success=False, error="'url_or_title' parameter is required.")
            removed, remaining = self._remove_bookmark(key)
            return PluginResult(success=True, data={
                "removed_count": removed,
                "remaining_count": remaining,
                "message": f"Removed {removed} bookmark(s) matching '{key}'."
            })

        elif action_name == "get_browser_info":
            browsers = self._detect_installed_browsers()
            return PluginResult(success=True, data={"browsers": browsers, "count": len(browsers)})

        elif action_name == "open_incognito":
            url = str(parameters.get("url", "https://www.google.com")).strip()
            pref = str(parameters.get("browser", "")).strip().lower()
            launched, browser_name, err = self._launch_incognito(url, pref)
            if not launched:
                return PluginResult(success=False, error=f"Failed to launch incognito browser: {err}")
            return PluginResult(success=True, data={
                "browser": browser_name,
                "url": url,
                "message": f"Launched incognito window in {browser_name} for {url}."
            })

        elif action_name == "clear_browser_cache_info":
            pref = str(parameters.get("browser", "all")).strip().lower()
            cache_info = self._get_cache_locations(pref)
            return PluginResult(success=True, data={"cache_locations": cache_info})

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Browser plugin.")

    def _extract_metadata(self, url: str) -> Dict[str, Any]:
        import re
        import urllib.request
        result = {"url": url, "title": "", "description": "", "og_title": "", "og_image": ""}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                chunk = resp.read(100000).decode("utf-8", errors="ignore")
                m_title = re.search(r"<title[^>]*>(.*?)</title>", chunk, re.IGNORECASE | re.DOTALL)
                if m_title:
                    result["title"] = m_title.group(1).strip()
                m_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', chunk, re.IGNORECASE)
                if m_desc:
                    result["description"] = m_desc.group(1).strip()
                m_og_t = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)["\']', chunk, re.IGNORECASE)
                if m_og_t:
                    result["og_title"] = m_og_t.group(1).strip()
                m_og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']*)["\']', chunk, re.IGNORECASE)
                if m_og_img:
                    result["og_image"] = m_og_img.group(1).strip()
        except Exception as exc:
            result["error"] = str(exc)
        return result

    def _get_bookmarks_path(self) -> str:
        import os
        return os.path.join(os.getcwd(), "data", "browser_bookmarks.json")

    def _load_bookmarks(self) -> list:
        import json
        import os
        path = self._get_bookmarks_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_bookmarks(self, items: list) -> None:
        import json
        import os
        path = self._get_bookmarks_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)

    def _add_bookmark(self, url: str, title: str, category: str) -> Dict[str, Any]:
        import time
        items = self._load_bookmarks()
        entry = {
            "url": url,
            "title": title,
            "category": category,
            "created_at": time.time()
        }
        # Update if exists with same url, else append
        for i, it in enumerate(items):
            if it.get("url") == url:
                items[i] = entry
                break
        else:
            items.append(entry)
        self._save_bookmarks(items)
        return entry

    def _get_bookmarks(self, category: str = None, query: str = None) -> list:
        items = self._load_bookmarks()
        if category:
            items = [it for it in items if it.get("category", "").lower() == category.lower()]
        if query:
            q = query.lower()
            items = [it for it in items if q in it.get("title", "").lower() or q in it.get("url", "").lower()]
        return items

    def _remove_bookmark(self, key: str) -> tuple[int, int]:
        items = self._load_bookmarks()
        k = key.lower()
        kept = [it for it in items if it.get("url", "").lower() != k and it.get("title", "").lower() != k]
        removed = len(items) - len(kept)
        if removed > 0:
            self._save_bookmarks(kept)
        return removed, len(kept)

    def _detect_installed_browsers(self) -> Dict[str, Any]:
        import os
        candidates = {
            "Google Chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
            ],
            "Microsoft Edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
            ],
            "Brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
            ],
            "Mozilla Firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
            ]
        }
        found = {}
        for name, paths in candidates.items():
            for p in paths:
                if os.path.isfile(p):
                    found[name] = {"path": p, "installed": True}
                    break
            if name not in found:
                found[name] = {"path": None, "installed": False}
        return found

    def _launch_in_browser(self, url: str, preferred_browser: str = "") -> bool:
        """Launch URL in a specific browser if preferred, else return False to fallback."""
        if not preferred_browser:
            return False
        import subprocess
        browsers = self._detect_installed_browsers()
        norm = preferred_browser.strip().lower()
        for b_name, b_info in browsers.items():
            if norm in b_name.lower() and b_info.get("installed") and b_info.get("path"):
                try:
                    subprocess.Popen([b_info["path"], url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info("BROWSER_LAUNCHED_DIRECTLY browser=%s path=%s url=%s", b_name, b_info["path"], url)
                    return True
                except Exception as e:
                    logger.warning("FAILED_TO_LAUNCH_PREFERRED_BROWSER browser=%s error=%s", b_name, e)
                    break
        return False

    def _launch_incognito(self, url: str, preferred: str = "") -> tuple[bool, str, str]:
        import subprocess
        browsers = self._detect_installed_browsers()
        order = ["Brave", "Google Chrome", "Microsoft Edge", "Mozilla Firefox"]
        if preferred:
            for b in browsers:
                if preferred in b.lower() and browsers[b]["installed"]:
                    order = [b] + [x for x in order if x != b]
                    break

        for b in order:
            info = browsers.get(b)
            if info and info.get("installed"):
                exe = info["path"]
                flag = "-inprivate" if "edge" in b.lower() else ("-private-window" if "firefox" in b.lower() else "--incognito")
                try:
                    subprocess.Popen([exe, flag, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, b, ""
                except Exception as e:
                    return False, b, str(e)
        return False, "None", "No supported browser executable found on system."

    def _get_cache_locations(self, browser_pref: str = "all") -> Dict[str, Any]:
        import os
        paths = {
            "chrome": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache"),
            "edge": os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache"),
            "brave": os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Cache"),
            "firefox": os.path.expandvars(r"%LOCALAPPDATA%\Mozilla\Firefox\Profiles"),
        }
        res = {}
        for k, p in paths.items():
            if browser_pref != "all" and k != browser_pref:
                continue
            exists = os.path.exists(p)
            size_bytes = 0
            if exists:
                try:
                    for root, _, files in os.walk(p):
                        for f in files:
                            fp = os.path.join(root, f)
                            try:
                                size_bytes += os.path.getsize(fp)
                            except OSError:
                                pass
                except Exception:
                    pass
            res[k] = {
                "path": p,
                "exists": exists,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2)
            }
        return res
