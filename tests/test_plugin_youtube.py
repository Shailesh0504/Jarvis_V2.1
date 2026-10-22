# tests/test_plugin_youtube.py
import os
import pytest
from plugins.youtube.plugin import YouTubePlugin
from plugins.youtube.models import QueueItem


@pytest.fixture
def youtube_plugin(tmp_path):
    plugin = YouTubePlugin()
    # Mock favorites file location into tmp_path
    plugin._get_favorites_path = lambda: str(tmp_path / "youtube_favorites.json")
    return plugin


def test_youtube_extract_video_id(youtube_plugin):
    # Standard watch url
    res = youtube_plugin.execute("extract_video_id", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert res.success is True
    assert res.data["video_id"] == "dQw4w9WgXcQ"

    # Short url
    res2 = youtube_plugin.execute("extract_video_id", {"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert res2.success is True
    assert res2.data["video_id"] == "dQw4w9WgXcQ"

    # Direct ID
    res3 = youtube_plugin.execute("extract_video_id", {"url": "dQw4w9WgXcQ"})
    assert res3.success is True
    assert res3.data["video_id"] == "dQw4w9WgXcQ"


def test_youtube_thumbnails_and_metadata(youtube_plugin):
    res = youtube_plugin.execute("get_thumbnail_url", {"url_or_id": "dQw4w9WgXcQ", "quality": "max"})
    assert res.success is True
    assert "maxresdefault.jpg" in res.data["thumbnail_url"]
    assert "hqdefault.jpg" in res.data["all_thumbnails"]["hq"]

    meta_res = youtube_plugin.execute("get_video_metadata", {"url_or_id": "dQw4w9WgXcQ"})
    assert meta_res.success is True
    assert meta_res.data["video_id"] == "dQw4w9WgXcQ"


def test_youtube_queue_operations(youtube_plugin):
    youtube_plugin.session.queue.append(QueueItem(query="lofi beats", title="Lofi Beats"))
    youtube_plugin.session.queue.append(QueueItem(query="jazz vibes", title="Jazz Vibes"))

    q_res = youtube_plugin.execute("get_queue", {})
    assert q_res.success is True
    assert q_res.data["queue_count"] == 2

    clear_res = youtube_plugin.execute("clear_queue", {})
    assert clear_res.success is True
    assert clear_res.data["cleared_count"] == 2
    assert len(youtube_plugin.session.queue) == 0


def test_youtube_playlist_and_timestamp(youtube_plugin):
    pl_res = youtube_plugin.execute("parse_playlist_url", {"url": "https://www.youtube.com/playlist?list=PL1234567890abcdef"})
    assert pl_res.success is True
    assert pl_res.data["playlist_id"] == "PL1234567890abcdef"

    ts_res = youtube_plugin.execute("generate_timestamped_url", {"url_or_id": "dQw4w9WgXcQ", "seconds": 125})
    assert ts_res.success is True
    assert "t=125s" in ts_res.data["url"]


def test_youtube_embed_and_favorites(youtube_plugin):
    embed_res = youtube_plugin.execute("get_embed_code", {"url_or_id": "dQw4w9WgXcQ", "width": 800, "height": 450})
    assert embed_res.success is True
    assert '<iframe width="800" height="450"' in embed_res.data["embed_html"]
    assert "embed/dQw4w9WgXcQ" in embed_res.data["embed_url"]

    # Save favorite
    fav_res = youtube_plugin.execute("save_favorite_video", {
        "title": "Never Gonna Give You Up",
        "url_or_id": "dQw4w9WgXcQ",
        "category": "Music"
    })
    assert fav_res.success is True
    assert fav_res.data["video_id"] == "dQw4w9WgXcQ"

    # List favorites
    list_res = youtube_plugin.execute("list_favorite_videos", {"category": "Music"})
    assert list_res.success is True
    assert list_res.data["count"] == 1
    assert list_res.data["favorites"][0]["title"] == "Never Gonna Give You Up"
