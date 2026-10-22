# plugins/youtube/commands.py
"""Dynamically registered structured actions supported by YouTube Plugin v2."""

from core.permissions import PermissionLevel, PluginCapability
from plugins.manifest import PluginAction, PluginParameter


def action(name, description, keywords, parameters=None):
    return PluginAction(
        name=name, description=description, keywords=keywords,
        parameters=parameters or [], required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.NETWORK.value,
    )


QUERY = [PluginParameter("query", "string", "Video, song, channel, or playlist query", True)]
ACTIONS = [
    action("open_youtube", "Open YouTube", ["open youtube", "youtube kholo"]),
    action("search", "Open YouTube search results without playing", ["youtube search", "search youtube"], QUERY),
    action("search_and_play", "Resolve the best actual video and open its watch URL", ["youtube play", "play video", "play song"], QUERY),
    action("pause", "Pause active YouTube playback", ["youtube pause", "pause karo"]),
    action("resume", "Resume active YouTube playback", ["youtube resume", "phir se chalao"]),
    action("stop", "Stop active YouTube playback", ["youtube stop", "rok do"]),
    action("next", "Play queue item or YouTube next", ["next video", "agla video"]),
    action("previous", "Play previous session video", ["previous video", "pichhla video"]),
    action("seek", "Seek active video", ["seek video", "aage karo", "piche karo"], [PluginParameter("seconds", "int", "Signed seek offset in seconds", True)]),
    action("set_volume", "Adjust YouTube player volume", ["youtube volume", "volume kam karo", "volume badhao"], [PluginParameter("level", "int", "Target volume 0-100", True)]),
    action("mute", "Mute YouTube player", ["youtube mute", "awaaz band karo"]),
    action("unmute", "Unmute YouTube player", ["youtube unmute", "awaaz chalu karo"]),
    action("replay", "Replay the current video", ["same video again", "yahi video dobara chalao"]),
    action("get_current_video", "Report current YouTube session", ["current youtube video", "youtube pe kya chal raha"]),
    action("open_channel", "Open matching YouTube channel results", ["youtube channel kholo", "open channel"], QUERY),
    action("play_playlist", "Open a playlist URL or playlist results", ["play youtube playlist", "playlist chalao"], QUERY),
    action("add_to_queue", "Add a future video to session queue", ["add to youtube queue", "iske baad chalao"], QUERY),
    action("extract_video_id", "Extracts YouTube video ID from any YouTube URL", ["extract video id", "get video id"], [PluginParameter("url", "string", "YouTube video URL", True)]),
    action("get_video_metadata", "Fetches title, author, and oEmbed metadata for a YouTube video", ["video metadata", "youtube metadata", "video info"], [PluginParameter("url_or_id", "string", "Video URL or ID", True)]),
    action("get_thumbnail_url", "Generates direct high-resolution thumbnail images for a video", ["video thumbnail", "youtube thumbnail", "get thumbnail"], [PluginParameter("url_or_id", "string", "Video URL or ID", True), PluginParameter("quality", "string", "Quality: max, hq, mq", False, "max")]),
    action("get_queue", "Lists all pending videos in the current playback queue", ["view queue", "youtube queue", "queued videos"]),
    action("clear_queue", "Clears all pending items from the playback queue", ["clear queue", "empty queue", "reset youtube queue"]),
    action("parse_playlist_url", "Parses a YouTube playlist URL and returns canonical details", ["parse playlist", "playlist info"], [PluginParameter("url", "string", "Playlist URL", True)]),
    action("generate_timestamped_url", "Generates a watch URL that begins at a specific timestamp", ["timestamp link", "timestamp url", "start video at"], [PluginParameter("url_or_id", "string", "Video URL or ID", True), PluginParameter("seconds", "int", "Start time in seconds", True)]),
    action("get_embed_code", "Generates HTML iframe embed code for a video", ["embed code", "youtube embed", "iframe embed"], [PluginParameter("url_or_id", "string", "Video URL or ID", True), PluginParameter("width", "int", "Embed width", False, 560), PluginParameter("height", "int", "Embed height", False, 315)]),
    action("save_favorite_video", "Saves a YouTube video into local favorites collection", ["save favorite video", "bookmark youtube", "star video"], [PluginParameter("title", "string", "Video title", True), PluginParameter("url_or_id", "string", "Video URL or ID", True), PluginParameter("category", "string", "Category / Tag", False, "General")]),
    action("list_favorite_videos", "Lists all saved favorite YouTube videos", ["favorite videos", "youtube bookmarks", "saved videos"])
]
