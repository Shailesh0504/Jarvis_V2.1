# plugins/youtube/plugin.py
"""Production no-API YouTube search, playback, controls, queue, and session plugin."""

import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from core.connectivity import ConnectivityManager
from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .browser_controller import BrowserOpenResult, YouTubeBrowserController
from .commands import ACTIONS
from .models import PlaybackState, QueueItem, YouTubeResult, YouTubeSession
from .permissions import PERMISSIONS_REQUIRED
from .search import YouTubeSearchResolver

logger = logging.getLogger("jarvis.plugins.youtube")


class YouTubePlugin(BasePlugin):
    """Owns every YouTube-specific execution concern; Core supplies structured actions."""

    ACTION_ALIASES = {
        "OPEN_YOUTUBE": "open_youtube", "SEARCH_YOUTUBE": "search",
        "PLAY_VIDEO": "search_and_play", "PLAY_SONG": "search_and_play",
        "PAUSE": "pause", "RESUME": "resume", "STOP": "stop", "NEXT": "next",
        "PREVIOUS": "previous", "SEEK": "seek", "SET_VOLUME": "set_volume",
        "MUTE": "mute", "UNMUTE": "unmute", "GET_CURRENT_VIDEO": "get_current_video",
        "OPEN_CHANNEL": "open_channel", "PLAY_PLAYLIST": "play_playlist",
        "ADD_TO_QUEUE": "add_to_queue", "REPLAY": "replay",
        "play": "search_and_play", "play_video": "search_and_play", "search_videos": "search",
    }

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self.connectivity = ConnectivityManager()
        self.search_resolver = YouTubeSearchResolver()
        self.browser = YouTubeBrowserController()
        self.session = YouTubeSession()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="youtube", version="2.0.0",
            description="No-API YouTube direct playback, session controls, playlists, channels and queue.",
            author="Jarvis Team", permissions=PERMISSIONS_REQUIRED, actions=ACTIONS,
        )

    def detect_brave_path(self) -> Optional[str]:
        return self.browser.detect_brave_path()

    def get_brave_executable(self) -> Optional[str]:
        return self.browser.get_brave_executable()

    def _open_url(self, url: str) -> BrowserOpenResult:
        if "get_brave_executable" in self.__dict__:
            self.browser._brave_path = self.get_brave_executable()
            self.browser._brave_checked = True
        return self.browser.open_url(url)

    def open_in_preferred_browser(self, url: str) -> Tuple[bool, str]:
        result = self._open_url(url)
        return result.success and result.browser_name == "Brave", result.browser_name

    def _find_top_video(self, query: str) -> Optional[Tuple[str, str]]:
        results = self.search_resolver.search(query)
        selected, reason = self.search_resolver.select_best(query, results)
        if not selected:
            logger.info("PLAYBACK_FAILED reason=%s query=%r", reason, query)
            return None
        return selected.video_id, selected.title

    def _resolve_video(self, query: str) -> Tuple[Optional[YouTubeResult], str, List[YouTubeResult]]:
        logger.info("QUERY_PARSED query=%r", query)
        try:
            results = self.search_resolver.search(query)
        except Exception as exc:
            logger.error("PLAYBACK_FAILED stage=search error=%s", exc)
            return None, f"YouTube search fail hua: {exc}", []
        selected, reason = self.search_resolver.select_best(query, results)
        if not selected:
            if reason == "ambiguous":
                choices = ", ".join(item.title for item in results[:3])
                return None, f"Multiple matching videos mili: {choices}. Kaunsi play karun?", results
            if reason == "low_confidence":
                return None, f"'{query}' ka reliable match nahi mila. Exact title ya channel batayenge?", results
            return None, f"YouTube par '{query}' ke liye koi video nahi mili, Boss.", results
        logger.info("SEARCH_RESULT_SELECTED video_id=%s title=%r score=%.3f", selected.video_id, selected.title, selected.score)
        logger.info("VIDEO_ID_RESOLVED video_id=%s", selected.video_id)
        return selected, "", results

    def _play_query(self, query: str) -> PluginResult:
        query = query.strip()
        if not query:
            return PluginResult(success=False, error="Kaunsa YouTube video ya gaana play karun?")
        self.session.last_search_query = query
        # Backward-compatible test/integration hook.
        if "_find_top_video" in self.__dict__:
            legacy = self._find_top_video(query)
            selected = YouTubeResult(legacy[0], legacy[1], score=1.0) if legacy else None
            error = f"YouTube par '{query}' ke liye koi video nahi mili, Boss." if not selected else ""
        else:
            selected, error, _ = self._resolve_video(query)
        if not selected:
            return PluginResult(success=False, error=error)
        if selected.unavailable:
            return PluginResult(success=False, error=f"'{selected.title}' abhi unavailable ya restricted hai.")
        opened = self._open_url(selected.watch_url)
        if not opened.success:
            self.session.playback_state = PlaybackState.FAILED
            logger.error("PLAYBACK_FAILED stage=browser error=%s", opened.error)
            return PluginResult(success=False, error=f"Video resolve ho gayi, lekin browser open nahi hua: {opened.error}")
        self.session.current_video = selected
        self.session.current_url = selected.watch_url
        self.session.browser_name = opened.browser_name
        self.session.browser_executable = opened.executable
        self.session.playback_state = PlaybackState.OPENED
        self.session.history.append(QueueItem(query, selected.video_id, selected.title, selected.watch_url))
        logger.info("PLAYBACK_STARTED attempted=true confirmed=false reason=browser_dom_unattached")
        logger.info("SESSION_UPDATED video_id=%s state=%s", selected.video_id, self.session.playback_state.value)
        return PluginResult(success=True, data={
            "query": query, "video_id": selected.video_id, "title": selected.title,
            "url": selected.watch_url, "browser": opened.browser_name,
            "in_brave": opened.browser_name == "Brave", "playback_state": self.session.playback_state.value,
            "message": f"{selected.title} ka direct YouTube video {opened.browser_name} mein open kar diya hai. Playback start hone ki koshish karega.",
        })

    def _require_session(self) -> Optional[PluginResult]:
        if not self.session.current_video:
            return PluginResult(success=False, error="Abhi koi active YouTube video nahi hai, Boss.")
        return None

    def _control(self, action: str, parameters: Dict[str, Any]) -> PluginResult:
        missing = self._require_session()
        if missing:
            return missing
        if action == "replay":
            opened = self._open_url(self.session.current_url)
            if not opened.success:
                return PluginResult(success=False, error=f"Video dobara open nahi hua: {opened.error}")
            self.session.playback_state = PlaybackState.OPENED
            return PluginResult(success=True, data={"message": "Wahi video dobara open kar diya hai, Boss."})
        if action == "seek":
            seconds = int(parameters.get("seconds", 0))
            if not seconds:
                return PluginResult(success=False, error="Kitne seconds ya minute aage/piche karna hai?")
            if not self.browser.seek(seconds):
                return PluginResult(success=False, error="Browser ko seek command nahi bhej paya. YouTube tab active kijiye.")
            self.session.last_position_seconds = max(0, self.session.last_position_seconds + seconds)
            return PluginResult(success=True, data={"message": f"Video ko {abs(seconds)} seconds {'aage' if seconds > 0 else 'piche'} karne ka command bhej diya hai."})
        if action == "set_volume":
            level = max(0, min(100, int(parameters.get("level", 50))))
            key = "up" if level >= 50 else "down"
            if not self.browser.send_media_key(key, max(1, abs(level - 50) // 5)):
                return PluginResult(success=False, error="YouTube volume control available nahi hai; browser tab active kijiye.")
            return PluginResult(success=True, data={"message": f"YouTube volume ko lagbhag {level}% set karne ka command bhej diya hai."})
        key_map = {"pause": "k", "resume": "k", "mute": "m", "unmute": "m", "stop": "home"}
        if not self.browser.send_media_key(key_map[action]):
            return PluginResult(success=False, error=f"YouTube {action} command browser tak nahi pahunchi. YouTube tab active kijiye.")
        state_map = {"pause": PlaybackState.PAUSED, "resume": PlaybackState.PLAYING, "stop": PlaybackState.STOPPED}
        if action in state_map:
            self.session.playback_state = state_map[action]
        logger.info("SESSION_UPDATED action=%s state=%s", action, self.session.playback_state.value)
        return PluginResult(success=True, data={"message": f"YouTube {action} command bhej diya hai, Boss."})

    def _play_queue_item(self, previous: bool = False) -> PluginResult:
        if previous:
            if len(self.session.history) < 2:
                return PluginResult(success=False, error="Previous YouTube video history mein nahi hai.")
            self.session.history.pop()
            return self._play_query(self.session.history.pop().query)
        if self.session.queue:
            return self._play_query(self.session.queue.pop(0).query)
        if not self.browser.send_media_key("nexttrack"):
            return PluginResult(success=False, error="Queue empty hai aur YouTube next control available nahi hai.")
        return PluginResult(success=True, data={"message": "YouTube ka next video command bhej diya hai."})

    def execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        action = self.ACTION_ALIASES.get(action_name, self.ACTION_ALIASES.get(action_name.upper(), action_name.lower()))
        if self.connectivity.is_offline:
            return PluginResult(success=False, error="Internet offline hai. YouTube ke liye active connection chahiye, Boss.")
        if action == "search_and_play":
            return self._play_query(str(parameters.get("query", "")))
        if action == "search":
            query = str(parameters.get("query", "")).strip()
            if not query:
                return PluginResult(success=False, error="YouTube par kya search karna hai?")
            self.session.last_search_query = query
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
            opened = self._open_url(url)
            if not opened.success:
                return PluginResult(success=False, error=f"YouTube search page open nahi hui: {opened.error}")
            return PluginResult(success=True, data={"query": query, "url": url, "message": f"YouTube par '{query}' ke search results open kar diye hain."})
        if action == "open_youtube":
            opened = self._open_url("https://www.youtube.com")
            if not opened.success:
                return PluginResult(success=False, error=f"YouTube open nahi hua: {opened.error}")
            return PluginResult(success=True, data={"url": "https://www.youtube.com", "message": f"YouTube {opened.browser_name} mein open kar diya hai."})
        if action in {"pause", "resume", "stop", "seek", "set_volume", "mute", "unmute", "replay"}:
            return self._control(action, parameters)
        if action == "next":
            return self._play_queue_item()
        if action == "previous":
            return self._play_queue_item(previous=True)
        if action == "get_current_video":
            if not self.session.current_video:
                return PluginResult(success=False, error="YouTube pe abhi kuch nahi chal raha, Boss.")
            video = self.session.current_video
            return PluginResult(success=True, data={"message": f"Current YouTube video: {video.title}. State: {self.session.playback_state.value}."})
        if action == "add_to_queue":
            query = str(parameters.get("query", "")).strip()
            if not query:
                return PluginResult(success=False, error="Queue mein kaunsa video add karna hai?")
            self.session.queue.append(QueueItem(query=query))
            logger.info("SESSION_UPDATED queue_size=%d", len(self.session.queue))
            return PluginResult(success=True, data={"message": f"'{query}' YouTube queue mein add kar diya hai."})
        if action == "open_channel":
            channel = str(parameters.get("query") or parameters.get("channel", "")).strip()
            if not channel:
                return PluginResult(success=False, error="Kaunsa YouTube channel open karun?")
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(channel)}&sp=EgIQAg%253D%253D"
            opened = self._open_url(url)
            if not opened.success:
                return PluginResult(success=False, error=f"Channel open nahi hua: {opened.error}")
            return PluginResult(success=True, data={"message": f"'{channel}' ke channel results open kar diye hain.", "url": url})
        if action == "play_playlist":
            query, url = str(parameters.get("query", "")).strip(), str(parameters.get("url", "")).strip()
            if url and "youtube.com/playlist" in url and "list=" in url:
                opened = self._open_url(url)
                if not opened.success:
                    return PluginResult(success=False, error=f"Playlist open nahi hui: {opened.error}")
                return PluginResult(success=True, data={"message": "YouTube playlist open kar di hai.", "url": url})
            if not query:
                return PluginResult(success=False, error="Kaunsi YouTube playlist play karun?")
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}&sp=EgIQAw%253D%253D"
            opened = self._open_url(search_url)
            if not opened.success:
                return PluginResult(success=False, error=f"Playlist results open nahi hue: {opened.error}")
            return PluginResult(success=True, data={"message": f"'{query}' ke playlist results open kar diye hain; playlist choose karna hoga.", "url": search_url})
        if action == "extract_video_id":
            raw = str(parameters.get("url", parameters.get("url_or_id", ""))).strip()
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Valid YouTube video ID could not be found in '{raw}'")
            return PluginResult(success=True, data={"video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}"})

        if action == "get_video_metadata":
            raw = str(parameters.get("url_or_id", parameters.get("url", ""))).strip()
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Invalid YouTube URL or ID: '{raw}'")
            meta = self._fetch_video_metadata(vid)
            return PluginResult(success=True, data=meta)

        if action == "get_thumbnail_url":
            raw = str(parameters.get("url_or_id", parameters.get("url", ""))).strip()
            quality = str(parameters.get("quality", "max")).lower()
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Invalid YouTube URL or ID: '{raw}'")
            quality_map = {
                "max": f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
                "hq": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                "mq": f"https://img.youtube.com/vi/{vid}/mqdefault.jpg",
                "sd": f"https://img.youtube.com/vi/{vid}/sddefault.jpg",
            }
            selected_thumb = quality_map.get(quality, quality_map["max"])
            return PluginResult(success=True, data={
                "video_id": vid,
                "quality": quality,
                "thumbnail_url": selected_thumb,
                "all_thumbnails": quality_map
            })

        if action == "get_queue":
            queue_items = [{"query": item.query, "title": item.title, "url": item.url} for item in self.session.queue]
            return PluginResult(success=True, data={
                "queue": queue_items,
                "queue_count": len(self.session.queue),
                "history_count": len(self.session.history),
            })

        if action == "clear_queue":
            count = len(self.session.queue)
            self.session.queue.clear()
            return PluginResult(success=True, data={
                "cleared_count": count,
                "message": f"YouTube queue cleared ({count} items removed)."
            })

        if action == "parse_playlist_url":
            raw = str(parameters.get("url", "")).strip()
            pid = self._extract_playlist_id(raw)
            if not pid:
                return PluginResult(success=False, error=f"Could not find valid playlist ID in '{raw}'")
            return PluginResult(success=True, data={
                "playlist_id": pid,
                "url": f"https://www.youtube.com/playlist?list={pid}"
            })

        if action == "generate_timestamped_url":
            raw = str(parameters.get("url_or_id", parameters.get("url", ""))).strip()
            seconds = int(parameters.get("seconds", 0))
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Invalid video URL or ID: '{raw}'")
            ts_url = f"https://www.youtube.com/watch?v={vid}&t={max(0, seconds)}s"
            return PluginResult(success=True, data={
                "video_id": vid,
                "seconds": max(0, seconds),
                "url": ts_url
            })

        if action == "get_embed_code":
            raw = str(parameters.get("url_or_id", parameters.get("url", ""))).strip()
            width = int(parameters.get("width", 560))
            height = int(parameters.get("height", 315))
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Invalid video URL or ID: '{raw}'")
            embed_url = f"https://www.youtube.com/embed/{vid}"
            embed_html = f'<iframe width="{width}" height="{height}" src="{embed_url}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
            return PluginResult(success=True, data={
                "video_id": vid,
                "embed_url": embed_url,
                "embed_html": embed_html
            })

        if action == "save_favorite_video":
            raw = str(parameters.get("url_or_id", parameters.get("url", ""))).strip()
            title = str(parameters.get("title", "")).strip()
            category = str(parameters.get("category", "General")).strip()
            vid = self._extract_id(raw)
            if not vid:
                return PluginResult(success=False, error=f"Invalid video URL or ID: '{raw}'")
            fav = self._save_favorite(vid, title or f"Video {vid}", category)
            return PluginResult(success=True, data=fav)

        if action == "list_favorite_videos":
            category = parameters.get("category")
            favs = self._load_favorites(category=str(category).strip() if category else None)
            return PluginResult(success=True, data={"favorites": favs, "count": len(favs)})

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in YouTube plugin.")

    def _extract_id(self, text: str) -> Optional[str]:
        import re
        text = text.strip()
        if re.match(r"^[0-9A-Za-z_-]{11}$", text):
            return text
        patterns = [
            r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([0-9A-Za-z_-]{11})",
            r"[?&]v=([0-9A-Za-z_-]{11})",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    def _extract_playlist_id(self, text: str) -> Optional[str]:
        import re
        m = re.search(r"[?&]list=([0-9A-Za-z_-]+)", text.strip())
        if m:
            return m.group(1)
        if text.startswith("PL") and len(text) >= 10:
            return text
        return None

    def _fetch_video_metadata(self, video_id: str) -> Dict[str, Any]:
        import json
        import urllib.request
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(canonical_url)}&format=json"
        try:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                data["video_id"] = video_id
                data["watch_url"] = canonical_url
                return data
        except Exception:
            return {
                "video_id": video_id,
                "title": f"YouTube Video ({video_id})",
                "author_name": "Unknown",
                "author_url": "",
                "watch_url": canonical_url,
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            }

    def _get_favorites_path(self) -> str:
        import os
        return os.path.join(os.getcwd(), "data", "youtube_favorites.json")

    def _load_favorites(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        import json
        import os
        path = self._get_favorites_path()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            if category:
                items = [it for it in items if it.get("category", "").lower() == category.lower()]
            return items
        except Exception:
            return []

    def _save_favorite(self, video_id: str, title: str, category: str) -> Dict[str, Any]:
        import json
        import os
        import time
        path = self._get_favorites_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        items = self._load_favorites()
        entry = {
            "video_id": video_id,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "category": category,
            "saved_at": time.time(),
        }
        # Update or append
        existing = [i for i, it in enumerate(items) if it.get("video_id") == video_id]
        if existing:
            items[existing[0]] = entry
        else:
            items.append(entry)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        return entry
