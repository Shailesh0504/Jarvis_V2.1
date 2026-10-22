# learning/vocabulary_layer.py
"""Layer 2: User Vocabulary & Domain Term Mappings."""

import json
import logging
import re
import time
from typing import Dict, List, Optional
from memory.database import DatabaseManager

logger = logging.getLogger("jarvis.learning.vocabulary")


class VocabularyLayer:
    """Layer 2: Custom user vocabulary & synonym mappings backed by entities table."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._cache: Dict[str, str] = {}
        self._load_cache()
        self._init_default_vocabulary()

    def _init_default_vocabulary(self) -> None:
        """Seed baseline vocabulary mappings."""
        defaults = {
            "browser": "chrome",
            "movie": "vlc",
            "video player": "vlc",
            "media player": "vlc",
            "recording": "screen recording",
            "code editor": "code",
            "sheet": "excel",
            "spreadsheet": "excel"
        }
        for term, mapping in defaults.items():
            if not self.get_term(term):
                self.learn_term(term, mapping, category="default")

    def _load_cache(self) -> None:
        try:
            sql = "SELECT name, normalized_value FROM entities WHERE entity_type = 'vocabulary'"
            rows = self.db.execute_query(sql)
            for r in rows:
                self._cache[r["name"].lower()] = r["normalized_value"]
        except Exception as e:
            logger.error(f"Failed to load vocabulary cache: {e}")

    def learn_term(self, term: str, target_mapping: str, category: str = "custom") -> None:
        """Learns or updates a vocabulary mapping in entities table."""
        clean_term = term.strip().lower()
        clean_target = target_mapping.strip()
        sql = """
        INSERT INTO entities (entity_type, name, normalized_value, context_id, metadata, updated_at)
        VALUES ('vocabulary', ?, ?, '', ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            normalized_value = excluded.normalized_value,
            entity_type = 'vocabulary',
            updated_at = excluded.updated_at
        """
        meta_json = json.dumps({"category": category})
        self.db.execute_update(sql, (clean_term, clean_target, meta_json, time.time()))
        self._cache[clean_term] = clean_target
        logger.info(f"Layer 2 Vocabulary learned: '{clean_term}' -> '{clean_target}'")

    def get_term(self, term: str) -> Optional[str]:
        return self._cache.get(term.strip().lower())

    DESCRIPTOR_GUARDS = {
        "browser": {
            "preceded_by": (
                "brave", "chrome", "google chrome", "google", "edge",
                "microsoft edge", "ms edge", "firefox", "mozilla firefox",
                "opera", "tor", "safari", "vivaldi", "duckduckgo",
                "arc", "chromium", "web", "default"
            ),
            "followed_by": (
                "history", "cache", "extension", "extensions", "tab",
                "tabs", "window", "windows", "data"
            ),
        },
        "sheet": {
            "preceded_by": ("excel", "google", "balance", "data", "style", "cheat", "spread", "ms excel"),
            "followed_by": (),
        },
        "spreadsheet": {
            "preceded_by": ("excel", "google", "ms excel"),
            "followed_by": (),
        },
        "recording": {
            "preceded_by": ("screen", "voice", "audio", "video", "call"),
            "followed_by": (),
        },
        "movie": {
            "preceded_by": ("vlc", "hindi", "english", "watch"),
            "followed_by": ("folder", "directory", "name", "ticket", "tickets"),
        },
        "media player": {
            "preceded_by": ("vlc", "windows", "mx", "pot"),
            "followed_by": (),
        },
        "video player": {
            "preceded_by": ("vlc", "windows", "mx", "pot"),
            "followed_by": (),
        },
        "code editor": {
            "preceded_by": ("vs", "vscode", "visual studio", "code", "sublime", "cursor"),
            "followed_by": (),
        },
    }

    def _should_skip_substitution(self, term: str, match: re.Match, text: str, target: str) -> bool:
        start = match.start()
        end = match.end()
        prefix = text[:start].rstrip().lower()
        suffix = text[end:].lstrip().lower()
        target_lower = target.lower().strip()

        term_clean = term.lower().strip()

        # 0. Prevent singular -> plural or plural -> singular corruption (e.g. video -> videos)
        if target_lower in (f"{term_clean}s", f"{term_clean}es") or term_clean in (f"{target_lower}s", f"{target_lower}es"):
            return True

        # 1. Prevent duplicate adjacency (e.g. 'chrome' before 'browser' -> 'chrome chrome')
        if prefix.endswith(target_lower) or suffix.startswith(target_lower):
            return True

        # Context-aware guards for 'movie' -> 'vlc'
        if term_clean == "movie":
            # A. If sentence relates to folders, files, locations, search, or inquiries
            if re.search(r"\b(?:folder|directory|dir|path|location|drive|disk|file|files|konse|kaunse|kahan|kaha|where|which|check|search|find|dhoondo|dhundo|locate)\b", text, re.IGNORECASE):
                return True
            # B. If preceded by a title or descriptor (e.g. "iron movie", "avatar movie")
            prefix_tokens = prefix.split()
            if prefix_tokens:
                last_token = prefix_tokens[-1]
                if last_token not in ("play", "open", "watch", "start", "chala", "chalao", "bajao", "khol", "kholo", "the", "a", "an", "and"):
                    return True
            # C. If related to cinema tickets, reviews, cast
            if re.search(r"\b(?:ticket|tickets|theatre|cinema|review|rating|trailer|cast|actor|actress|download)\b", text, re.IGNORECASE):
                return True

        # 2. Check descriptor / hypernym guards
        guards = self.DESCRIPTOR_GUARDS.get(term_clean)
        if guards:
            for p in guards.get("preceded_by", ()):
                if prefix.endswith(p) and (len(prefix) == len(p) or prefix[-len(p) - 1] in " \t\n\r-_,"):
                    return True
            for s in guards.get("followed_by", ()):
                if suffix.startswith(s) and (len(suffix) == len(s) or suffix[len(s)] in " \t\n\r-_,"):
                    return True

        return False

    def resolve_text(self, text: str) -> str:
        if not text:
            return ""

        resolved = text
        sorted_terms = sorted(self._cache.keys(), key=len, reverse=True)
        for term in sorted_terms:
            target = self._cache[term]
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            matches = list(pattern.finditer(resolved))
            if not matches:
                continue

            chunks = []
            last_idx = 0
            for m in matches:
                chunks.append(resolved[last_idx:m.start()])
                if self._should_skip_substitution(term, m, resolved, target):
                    chunks.append(m.group(0))
                else:
                    chunks.append(target)
                last_idx = m.end()
            chunks.append(resolved[last_idx:])
            resolved = "".join(chunks)

        return resolved

    def get_all_vocabulary(self) -> Dict[str, str]:
        return dict(self._cache)

