# plugins/youtube/search.py
"""No-API YouTube HTML search and deterministic result ranking."""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Iterable, List, Optional, Tuple

from .models import YouTubeResult

logger = logging.getLogger("jarvis.plugins.youtube.search")


class YouTubeSearchResolver:
    SEARCH_ENDPOINT = "https://www.youtube.com/results?search_query={}"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    )

    @staticmethod
    def normalize_query(query: str) -> str:
        text = query.casefold().strip()
        text = re.sub(r"[^\w\s'-]", " ", text, flags=re.UNICODE)
        text = re.sub(
            r"\b(?:jarvis|please|plz|bhai|yaar|zara|youtube|yt|pe|par|mein|me|"
            r"play|chalao|chala|bajao|baja|laga|do|karo|karna|wala|wali|video|gaana|gana|song)\b",
            " ", text, flags=re.IGNORECASE,
        )
        return re.sub(r"\s+", " ", text).strip()

    def search(self, query: str, limit: int = 12) -> List[YouTubeResult]:
        normalized = self.normalize_query(query) or query.strip()
        logger.info("SEARCH_STARTED query=%r", normalized)
        url = self.SEARCH_ENDPOINT.format(urllib.parse.quote_plus(normalized))
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.USER_AGENT, "Accept-Language": "en-US,en;q=0.9,hi;q=0.8"},
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
        initial_data = self._extract_initial_data(html)
        results = self._collect_results(initial_data) if initial_data else []
        if not results:
            results = self._regex_fallback(html)
        return self.rank(normalized, results)[:limit]

    @staticmethod
    def parse_views(text: str) -> int:
        """Parses human-readable view counts (e.g. '15M views', '2.4 crore', '850K') to integer."""
        if not text:
            return 0
        clean = text.lower().replace(",", "").strip()
        match = re.search(r"([\d.]+)\s*([kmb]|million|billion|crore|cr|lakh|lac)?", clean)
        if not match:
            return 0
        val_str, unit = match.groups()
        try:
            val = float(val_str)
        except ValueError:
            return 0
        unit = (unit or "").lower()
        if unit in ("k",):
            return int(val * 1_000)
        elif unit in ("m", "million"):
            return int(val * 1_000_000)
        elif unit in ("b", "billion"):
            return int(val * 1_000_000_000)
        elif unit in ("crore", "cr"):
            return int(val * 10_000_000)
        elif unit in ("lakh", "lac"):
            return int(val * 100_000)
        return int(val)

    def select_best(self, query: str, results: List[YouTubeResult]) -> Tuple[Optional[YouTubeResult], str]:
        """
        Selects the best YouTube video for playback. When multiple matching results exist,
        automatically picks the most viewed / highest popularity video without asking the user.
        """
        if not results:
            return None, "no_results"
        ranked = self.rank(self.normalize_query(query) or query, results)
        if not ranked:
            return None, "no_results"

        # Filter out unavailable
        available = [r for r in ranked if not r.unavailable]
        if not available:
            return None, "unavailable"

        # Among top relevance candidates (within 0.15 of highest score), pick the most viewed
        top_score = available[0].score
        candidates = [r for r in available if (top_score - r.score) <= 0.15]
        if len(candidates) > 1:
            best = max(candidates, key=lambda item: (self.parse_views(item.view_count), item.score))
        else:
            best = available[0]

        return best, "selected"

    def rank(self, query: str, results: Iterable[YouTubeResult]) -> List[YouTubeResult]:
        import difflib
        query_norm = self._token_text(query)
        query_tokens = set(query_norm.split())
        query_compact = re.sub(r"\s+", "", query_norm)

        ranked = []
        for index, result in enumerate(results):
            title_norm = self._token_text(result.title)
            title_tokens = set(title_norm.split())
            title_compact = re.sub(r"\s+", "", title_norm)

            overlap = len(query_tokens & title_tokens) / max(1, len(query_tokens))
            precision = len(query_tokens & title_tokens) / max(1, len(title_tokens))
            phrase = 1.0 if query_norm and query_norm in title_norm else 0.0

            compact_match = 1.0 if (query_compact and query_compact in title_compact) else 0.0
            fuzzy_ratio = difflib.SequenceMatcher(None, query_norm, title_norm[:len(query_norm) + 15]).ratio()

            channel_tokens = set(self._token_text(result.channel).split())
            channel_overlap = len(query_tokens & channel_tokens) / max(1, len(query_tokens))
            latest_bonus = 0.08 if "latest" in query_tokens and result.published else 0.0
            unavailable_penalty = 1.0 if result.unavailable else 0.0
            position_bonus = max(0.0, 0.05 - index * 0.004)

            # View count popularity bonus
            views = self.parse_views(result.view_count)
            if views > 50_000_000:
                view_bonus = 0.15
            elif views > 10_000_000:
                view_bonus = 0.10
            elif views > 1_000_000:
                view_bonus = 0.06
            elif views > 100_000:
                view_bonus = 0.03
            else:
                view_bonus = 0.0

            score = max(
                0.0,
                0.40 * overlap
                + 0.22 * channel_overlap
                + 0.18 * compact_match
                + 0.15 * phrase
                + 0.10 * precision
                + 0.10 * fuzzy_ratio
                + view_bonus
                + latest_bonus
                + position_bonus
                - unavailable_penalty
            )
            ranked.append(YouTubeResult(**{**result.__dict__, "score": round(score, 4)}))
        return sorted(ranked, key=lambda item: (-item.score, item.title.casefold(), item.video_id))

    @staticmethod
    def _token_text(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.casefold())).strip()

    @staticmethod
    def _extract_initial_data(html: str) -> Optional[Any]:
        markers = ("var ytInitialData = ", 'window["ytInitialData"] = ', "ytInitialData = ")
        decoder = json.JSONDecoder()
        for marker in markers:
            start = html.find(marker)
            if start < 0:
                continue
            fragment = html[start + len(marker):].lstrip()
            try:
                return decoder.raw_decode(fragment)[0]
            except (ValueError, json.JSONDecodeError):
                continue
        return None

    @classmethod
    def _collect_results(cls, data: Any) -> List[YouTubeResult]:
        found = []
        seen = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                renderer = value.get("videoRenderer")
                if isinstance(renderer, dict):
                    video_id = renderer.get("videoId", "")
                    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) and video_id not in seen:
                        seen.add(video_id)
                        title = cls._text(renderer.get("title"))
                        owner = cls._text(renderer.get("ownerText")) or cls._text(renderer.get("longBylineText"))
                        found.append(YouTubeResult(
                            video_id=video_id,
                            title=title or video_id,
                            channel=owner,
                            duration=cls._text(renderer.get("lengthText")),
                            view_count=cls._text(renderer.get("viewCountText")),
                            published=cls._text(renderer.get("publishedTimeText")),
                            unavailable=bool(renderer.get("isUpcoming")),
                        ))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(data)
        return found

    @staticmethod
    def _text(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        if value.get("simpleText"):
            return str(value["simpleText"])
        return "".join(str(run.get("text", "")) for run in value.get("runs", []) if isinstance(run, dict))

    @staticmethod
    def _regex_fallback(html: str) -> List[YouTubeResult]:
        ids = list(dict.fromkeys(re.findall(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)))
        return [YouTubeResult(video_id=video_id, title=video_id) for video_id in ids[:20]]
