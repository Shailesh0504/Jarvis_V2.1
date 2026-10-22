# plugins/browser/website_resolver.py
"""Canonical direct-website resolution and redirect/tracking URL sanitization."""

from dataclasses import dataclass
import base64
import re
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit, unquote


@dataclass(frozen=True)
class WebsiteResolution:
    query: str
    normalized_query: str
    resolved_url: str
    final_url: str
    redirect_unwrapped: bool = False
    source: str = ""
    confidence: float = 1.0
    canonical_name: str = ""


class UnknownWebsiteError(ValueError):
    """A name was not safe enough to navigate without user confirmation."""


class AmbiguousWebsiteError(ValueError):
    """More than one learned website is an equally plausible match."""


class WebsiteResolver:
    """Resolve an open/navigation request to one safe final HTTP(S) URL."""

    CANONICAL_SITES = {
        "flipkart": "https://www.flipkart.com/",
        "amazon": "https://www.amazon.in/",
        "youtube": "https://www.youtube.com/",
        "gmail": "https://mail.google.com/",
        "google": "https://www.google.com/",
        "facebook": "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/",
        "insta": "https://www.instagram.com/",
        "linkedin": "https://www.linkedin.com/",
        "reddit": "https://www.reddit.com/",
        "github": "https://github.com/",
        "microsoft": "https://www.microsoft.com/",
        "chatgpt": "https://chatgpt.com/",
        "chat gpt": "https://chatgpt.com/",
        "openai": "https://openai.com/",
        "claude": "https://claude.ai/",
        "claude ai": "https://claude.ai/",
        "claudeai": "https://claude.ai/",
        "cloude": "https://claude.ai/",
        "cloude ai": "https://claude.ai/",
        "cloud ai": "https://claude.ai/",
        "gemini": "https://gemini.google.com/",
        "gemini ai": "https://gemini.google.com/",
        "perplexity": "https://www.perplexity.ai/",
        "perplexity ai": "https://www.perplexity.ai/",
        "dhan": "https://dhan.co/",
        "dhan app": "https://dhan.co/",
        "dhan trading": "https://dhan.co/",
        "zerodha": "https://zerodha.com/",
        "kite": "https://kite.zerodha.com/",
        "groww": "https://groww.in/",
        "upstox": "https://upstox.com/",
        "angelone": "https://www.angelone.in/",
        "angel one": "https://www.angelone.in/",
    }
    TRACKING_KEYS = {
        "gclid", "dclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
        "igshid", "yclid", "_ga", "_gl",
    }
    REDIRECT_HOSTS = {
        "google.com", "www.google.com", "google.co.in", "www.google.co.in",
        "bing.com", "www.bing.com", "l.facebook.com", "lm.facebook.com",
        "youtube.com", "www.youtube.com",
    }
    _knowledge_store = None

    @classmethod
    def configure_knowledge_store(cls, store) -> None:
        """Bind the resolver to Jarvis's active authoritative SQLite store."""
        cls._knowledge_store = store

    @classmethod
    def normalize_query(cls, query: str) -> str:
        from core.website_knowledge import normalize_website_phrase
        raw = str(query or "").strip()
        # Preserve percent-encoding inside redirect URLs; decoding the entire
        # wrapper early can turn an embedded destination's '&' into an outer
        # query separator and silently drop destination parameters.
        cleaned = (raw if raw.lower().startswith(("http://", "https://")) else unquote(raw)).lower()
        cleaned = re.sub(r"\b(?:please|official|website|site|app)\b", " ", cleaned)
        cleaned = re.sub(r"^(?:open|launch|start|visit|browse)\s+", "", cleaned)
        cleaned = re.sub(r"\s+(?:open|launch|start|visit|kholo|open\s+karo|khol\s+do)$", "", cleaned)
        return normalize_website_phrase(cleaned).strip(" ./")

    @classmethod
    def resolve(cls, query: str, search_candidates: Optional[Iterable[str]] = None) -> WebsiteResolution:
        raw_query = str(query or "").strip()
        # An explicit URL is already an unambiguous navigation target. Keep it
        # intact; entity normalization is only for natural-language requests.
        normalized = raw_query.lower() if cls._looks_like_url_or_domain(raw_query) else cls.normalize_query(raw_query)
        if not normalized:
            raise ValueError("Website name is required.")

        # Priority 1: the structured, user-learned website store.
        from core.website_knowledge import WebsiteKnowledgeStore
        knowledge_store = cls._knowledge_store or WebsiteKnowledgeStore()
        learned = knowledge_store.resolve(normalized)
        if learned:
            if learned.ambiguous:
                raise AmbiguousWebsiteError(f"'{query}' ke liye ek se zyada website saved hain.")
            knowledge_store.record_usage(learned.entry["id"])
            resolved = learned.entry["url"]
            unwrapped, changed = cls.unwrap_redirect(resolved)
            final = cls.sanitize_url(unwrapped)
            return WebsiteResolution(
                query, normalized, resolved, final, changed, "user_learned",
                learned.confidence, learned.entry["canonical_name"],
            )

        # Priority 2: legacy custom aliases remain readable for compatibility.
        try:
            from core.alias_manager import get_alias_manager
            alias_mgr = get_alias_manager()
            alias_entry = alias_mgr.get_alias(normalized) or alias_mgr.resolve_alias(normalized)
            if alias_entry and alias_entry.get("action_type") in ("OPEN_WEBSITE", "open_website", None):
                alias_mgr.record_usage(alias_entry["alias"])
                resolved, source = alias_entry["target"], "custom_alias"
                unwrapped, changed = cls.unwrap_redirect(resolved)
                final = cls.sanitize_url(unwrapped)
                return WebsiteResolution(query, normalized, resolved, final, changed, source, 1.0, alias_entry.get("description", ""))
        except Exception:
            pass

        # Priority 3: Built-in Canonical Sites
        if normalized in cls.CANONICAL_SITES:
            resolved, source = cls.CANONICAL_SITES[normalized], "canonical"
        elif cls._looks_like_url_or_domain(normalized):
            resolved, source = cls._ensure_scheme(normalized), "domain"
        else:
            resolved = cls._first_valid_candidate(search_candidates or ())
            if resolved:
                source = "search_result"
            else:
                # Never manufacture a domain from an unknown phrase. A typo or
                # a private portal name must enter the learning/clarification
                # flow instead of opening an unrelated public website.
                raise UnknownWebsiteError("Website ke liye URL confirm karna hoga.")

        unwrapped, changed = cls.unwrap_redirect(resolved)
        final = cls.sanitize_url(unwrapped)
        return WebsiteResolution(query, normalized, resolved, final, changed, source, 1.0, normalized.title())

    @classmethod
    def unwrap_redirect(cls, url: str) -> tuple[str, bool]:
        current = cls._ensure_scheme(url)
        changed = False
        for _ in range(3):
            parts = urlsplit(current)
            host = (parts.hostname or "").lower()
            if host not in cls.REDIRECT_HOSTS:
                break
            params = parse_qs(parts.query)
            wrapped = next((params[key][0] for key in ("url", "q", "target", "dest", "destination", "u") if params.get(key)), "")
            if host.endswith("bing.com") and wrapped.startswith("a1"):
                try:
                    payload = wrapped[2:] + "=" * (-len(wrapped[2:]) % 4)
                    wrapped = base64.urlsafe_b64decode(payload).decode("utf-8")
                except Exception:
                    wrapped = ""
            wrapped = unquote(wrapped)
            if not wrapped.startswith(("http://", "https://")):
                break
            current, changed = wrapped, True
        return current, changed

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        parts = urlsplit(cls._ensure_scheme(url))
        if parts.scheme not in ("http", "https"):
            raise ValueError("Only HTTP(S) website URLs are allowed.")
        host = (parts.hostname or "").lower().rstrip(".")
        if not cls._valid_domain(host):
            raise ValueError("Website domain is invalid.")
        netloc = host
        if parts.port:
            netloc += f":{parts.port}"
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        kept = []
        for key, value in parse_qs(parts.query, keep_blank_values=True).items():
            lower_key = key.lower()
            if lower_key.startswith("utm_") or lower_key in cls.TRACKING_KEYS:
                continue
            kept.extend((key, item) for item in value)
        return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(kept, doseq=True), ""))

    @staticmethod
    def _valid_domain(host: str) -> bool:
        if len(host) > 253 or "." not in host:
            return False
        return all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))

    @classmethod
    def _looks_like_url_or_domain(cls, value: str) -> bool:
        if value.startswith(("http://", "https://")):
            candidate = urlsplit(value).hostname or ""
        else:
            candidate = value.split("/", 1)[0].strip("/")
        return "." in candidate and " " not in candidate

    @staticmethod
    def _ensure_scheme(url: str) -> str:
        value = str(url).strip()
        return value if value.startswith(("http://", "https://")) else f"https://{value.lstrip('/')}"

    @classmethod
    def _first_valid_candidate(cls, candidates: Iterable[str]) -> str:
        for candidate in candidates:
            try:
                final, _ = cls.unwrap_redirect(candidate)
                cls.sanitize_url(final)
                return candidate
            except (TypeError, ValueError):
                continue
        return ""
