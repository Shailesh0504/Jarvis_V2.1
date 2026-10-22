# tests/test_wallpaper_engine.py
"""
Comprehensive tests for Jarvis Desktop Wallpaper Subsystem (core/wallpaper).
Verifies:
1. Query enhancement, visual extraction, random detection, context refinement.
2. Image validation (formats, resolutions, aspect ratios, file size safety).
3. Cache management (RGB JPEG conversion, metadata persistence, LRU pruning).
4. Preference tracking (style frequency, conversational TTL, pending clarification).
5. Windows wallpaper service (metrics, registry, verification).
6. Search manager and provider resilience.
7. WallpaperEngine end-to-end processing and offline degradation.
8. Full JarvisCore FastPath and capability question integration.
"""

import io
import os
import shutil
import time
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from core.wallpaper.models import (
    AspectRatioTier,
    CandidateImage,
    DisplayMetrics,
    WallpaperRequest,
    WallpaperResult,
)
from core.wallpaper.query_enhancer import WallpaperQueryEnhancer
from core.wallpaper.image_validator import ImageValidator
from core.wallpaper.wallpaper_cache import WallpaperCacheManager
from core.wallpaper.preference_tracker import WallpaperPreferenceTracker
from core.wallpaper.wallpaper_service import WindowsWallpaperService
from core.wallpaper.search_manager import WallpaperSearchManager
from core.wallpaper.providers.base import WallpaperSearchProvider
from core.wallpaper.wallpaper_engine import WallpaperEngine, get_wallpaper_engine
from main import create_jarvis


@pytest.fixture
def temp_cache_dir(tmp_path):
    cache_dir = tmp_path / "wallpaper_cache"
    cache_dir.mkdir()
    return str(cache_dir)


@pytest.fixture
def sample_valid_image(tmp_path):
    """Creates a sample 1920x1080 valid landscape JPEG image."""
    img_path = tmp_path / "valid_test.jpg"
    img = Image.new("RGB", (1920, 1080), color=(50, 100, 150))
    img.save(str(img_path), "JPEG")
    return str(img_path)


@pytest.fixture
def sample_portrait_image(tmp_path):
    """Creates a 1080x1920 portrait image."""
    img_path = tmp_path / "portrait_test.jpg"
    img = Image.new("RGB", (1080, 1920), color=(100, 50, 50))
    img.save(str(img_path), "JPEG")
    return str(img_path)


@pytest.fixture
def sample_lowres_image(tmp_path):
    """Creates a 400x300 low-resolution image with sufficient size (>4KB) to test resolution gating."""
    img_path = tmp_path / "lowres_test.jpg"
    img = Image.new("RGB", (400, 300))
    pixels = [(i % 256, (i * 3) % 256, (i * 7) % 256) for i in range(400 * 300)]
    img.putdata(pixels)
    img.save(str(img_path), "JPEG", quality=95)
    return str(img_path)


class TestWallpaperQueryEnhancer:
    """Tests semantic visual subject extraction, modifiers, and context refinement."""

    def test_ambiguous_requests(self):
        for phrase in ["wallpaper change karo", "wallpaper badal do", "change wallpaper", "desktop wallpaper badlo"]:
            req = WallpaperQueryEnhancer.enhance_request(phrase)
            assert req.is_ambiguous is True
            assert req.visual_query == ""

    def test_random_requests(self):
        for phrase in ["koi achha wallpaper laga do", "koi sundar wallpaper lagao", "random wallpaper set karo"]:
            req = WallpaperQueryEnhancer.enhance_request(phrase)
            assert req.is_random is True
            assert req.is_ambiguous is False
            assert "4k" in req.modifiers or "landscape" in req.modifiers

    def test_direct_visual_queries(self):
        req = WallpaperQueryEnhancer.enhance_request("ironman 4k wallpaper laga do")
        assert req.visual_query == "iron man"
        assert "4k" in req.modifiers
        assert req.is_ambiguous is False

        req2 = WallpaperQueryEnhancer.enhance_request("cyberpunk dark wallpaper set karo")
        assert "cyberpunk" in req2.visual_query or "dark" in req2.modifiers

    def test_conversational_refinement_with_context(self):
        # Initial topic: 'nature'
        req = WallpaperQueryEnhancer.enhance_request("thoda dark wala", context_topic="nature")
        assert req.context_refinement is True
        assert "dark" in req.visual_query
        assert "nature" in req.visual_query

    def test_context_not_applied_when_new_distinct_topic_given(self):
        # User explicitly changes topic from 'nature' to 'car'
        req = WallpaperQueryEnhancer.enhance_request("car wallpaper lagao", context_topic="nature")
        assert req.context_refinement is False
        assert "nature" not in req.visual_query
        assert "car" in req.visual_query


class TestImageValidator:
    """Tests file verification, Pillow structural inspection, and size bounds."""

    def test_valid_image(self, sample_valid_image):
        valid, reason, meta = ImageValidator.validate_file(sample_valid_image)
        assert valid is True
        assert meta is not None
        assert meta["width"] == 1920
        assert meta["height"] == 1080
        assert meta["aspect_ratio"] >= 1.7

    def test_portrait_rejection(self, sample_portrait_image):
        valid, reason, _ = ImageValidator.validate_file(sample_portrait_image, require_landscape=True)
        assert valid is False
        assert "portrait" in reason.lower() or "landscape" in reason.lower()

    def test_low_resolution_rejection(self, sample_lowres_image):
        valid, reason, _ = ImageValidator.validate_file(sample_lowres_image)
        assert valid is False
        assert "resolution too low" in reason.lower()

    def test_html_stub_rejection(self, tmp_path):
        stub = tmp_path / "stub.jpg"
        stub.write_text("<!DOCTYPE html><html><body>Error 404 Not Found</body></html>" * 200)
        valid, reason, _ = ImageValidator.validate_file(str(stub))
        assert valid is False
        assert "html" in reason.lower()

    def test_tiny_file_rejection(self, tmp_path):
        tiny = tmp_path / "tiny.jpg"
        tiny.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        valid, reason, _ = ImageValidator.validate_file(str(tiny))
        assert valid is False
        assert "too small" in reason.lower()


class TestWallpaperCacheManager:
    """Tests promotion, conversion to RGB JPEG, metadata writing, and pruning."""

    def test_promotion_and_rgb_jpeg_conversion(self, temp_cache_dir, tmp_path):
        cache_mgr = WallpaperCacheManager(temp_cache_dir)

        # Create a PNG image to test automatic conversion to RGB JPEG
        png_path = tmp_path / "source.png"
        png_img = Image.new("RGBA", (1920, 1080), color=(10, 20, 30, 255))
        png_img.save(str(png_path), "PNG")

        cand = CandidateImage(
            image_url="https://example.com/test.png",
            source_name="TestProvider",
            source_url="https://example.com",
            title="Test Candidate",
            width=1920,
            height=1080,
            format="png",
        )

        current_path = cache_mgr.promote_to_current(
            validated_file_path=str(png_path),
            candidate=cand,
            query="test query",
            visual_query="test",
        )

        assert os.path.isfile(current_path)
        assert current_path.endswith("current.jpg")

        # Verify saved file is a genuine JPEG
        with Image.open(current_path) as saved:
            assert saved.format == "JPEG"
            assert saved.size == (1920, 1080)

        # Verify metadata
        meta = cache_mgr.get_current_metadata()
        assert meta is not None
        assert meta["query"] == "test query"
        assert meta["source_name"] == "TestProvider"
        assert meta["format"] == "JPG"

    def test_pruning_limits_archives(self, temp_cache_dir, sample_valid_image):
        cache_mgr = WallpaperCacheManager(temp_cache_dir)
        cand = CandidateImage(
            image_url="https://example.com/t.jpg",
            source_name="Test",
            source_url="https://example.com",
        )

        # Promote 7 times
        for i in range(7):
            cache_mgr.promote_to_current(
                sample_valid_image, cand, f"query_{i}", f"visual_{i}"
            )
            time.sleep(0.01)

        archives = [f for f in os.listdir(temp_cache_dir) if f.startswith("wallpaper_")]
        assert len(archives) <= 5


class TestWallpaperPreferenceTracker:
    """Tests contextual tracking, frequency counts, and clarification lifecycle."""

    def test_preferences_lifecycle(self):
        tracker = WallpaperPreferenceTracker(ttl_seconds=10.0)
        assert tracker.is_context_active() is False

        tracker.record_success(query="galaxy 4k", visual_query="galaxy", modifiers=["4k", "dark"])
        assert tracker.is_context_active() is True
        assert tracker.get_context_topic() == "galaxy"
        assert "4k" in tracker.get_context_modifiers()

        tracker.record_success(query="galaxy minimal", visual_query="galaxy", modifiers=["minimal"])
        top_styles = tracker.get_top_preferred_styles(2)
        assert "galaxy" in top_styles

    def test_clarification_flag(self):
        tracker = WallpaperPreferenceTracker()
        assert tracker.is_awaiting_clarification() is False
        tracker.set_pending_clarification()
        assert tracker.is_awaiting_clarification() is True
        tracker.clear_pending_clarification()
        assert tracker.is_awaiting_clarification() is False


class TestWindowsWallpaperService:
    """Tests display metrics detection and safe verification."""

    def test_display_metrics(self):
        metrics = WindowsWallpaperService.get_display_metrics()
        assert metrics.width > 0
        assert metrics.height > 0
        assert metrics.aspect_ratio > 0
        assert metrics.tier in (
            AspectRatioTier.STANDARD_WIDE,
            AspectRatioTier.WIDE_WORK,
            AspectRatioTier.ULTRAWIDE,
            AspectRatioTier.SUPER_ULTRAWIDE,
            AspectRatioTier.OTHER,
        )

    def test_verify_wallpaper_handles_nonexistent(self):
        assert WindowsWallpaperService.verify_wallpaper("C:\\nonexistent_wallpaper_xyz.jpg") is False


class TestWallpaperSearchManager:
    """Tests search provider orchestration and ranking."""

    def test_ranking_prefers_target_resolution(self):
        sm = WallpaperSearchManager(providers=[])
        metrics = DisplayMetrics(width=1920, height=1080, aspect_ratio=1.777)

        cand_low = CandidateImage(
            image_url="http://example.com/low.jpg",
            source_name="Mock",
            source_url="http://example.com",
            width=1280,
            height=720,
            aspect_ratio=1.777,
        )
        cand_high = CandidateImage(
            image_url="http://example.com/high.jpg",
            source_name="Mock",
            source_url="http://example.com",
            width=2560,
            height=1440,
            aspect_ratio=1.777,
        )

        ranked = sm._rank_candidates([cand_low, cand_high], metrics)
        assert ranked[0].width == 2560


class TestWallpaperEngineEndToEnd:
    """Tests WallpaperEngine coordinator."""

    def test_offline_truthful_refusal(self):
        we = WallpaperEngine()
        we.connectivity_manager.set_forced_offline(True)
        try:
            res = we.process_wallpaper_request("nature wallpaper lagao")
            assert res.success is False
            assert res.is_offline is True
            assert "internet connection" in res.formatted_response.lower()
        finally:
            we.connectivity_manager.set_forced_offline(False)

    def test_ambiguous_request_asks_clarification(self):
        we = WallpaperEngine()
        res = we.process_wallpaper_request("wallpaper change karo")
        assert res.success is False
        assert "Kaunsa wallpaper lagana hai" in res.formatted_response
        assert we.preferences.is_awaiting_clarification() is True

    def test_successful_mocked_flow(self, temp_cache_dir, sample_valid_image):
        mock_provider = MagicMock(spec=WallpaperSearchProvider)
        mock_provider.get_provider_name.return_value = "MockProvider"
        mock_provider.search_images.return_value = [
            CandidateImage(
                image_url="https://example.com/mock.jpg",
                source_name="MockProvider",
                source_url="https://example.com",
                title="Mock Wallpaper",
                width=1920,
                height=1080,
            )
        ]

        mock_downloader = MagicMock()
        def fake_download(url, dest):
            shutil.copy2(sample_valid_image, dest)
            return True, None
        mock_downloader.download_image.side_effect = fake_download

        engine = WallpaperEngine(
            search_manager=WallpaperSearchManager(providers=[mock_provider]),
            cache_manager=WallpaperCacheManager(temp_cache_dir),
            downloader=mock_downloader,
        )

        with patch("core.wallpaper.wallpaper_service.WindowsWallpaperService.apply_wallpaper", return_value=(True, None)):
            res = engine.process_wallpaper_request("nature 4k wallpaper laga do")
            assert res.success is True
            assert "laga diya" in res.formatted_response
            assert res.image_path is not None
            assert os.path.isfile(res.image_path)


class TestJarvisCoreWallpaperIntegration:
    """Tests end-to-end integration through JarvisCore."""

    @pytest.fixture
    def jarvis(self, tmp_path):
        orig_plugins = os.path.abspath("plugins")
        temp_plugins = tmp_path / "plugins"
        shutil.copytree(orig_plugins, temp_plugins)

        db_path = os.path.join(tmp_path, "wall_test.db").replace("\\", "/")
        cfg_content = f"""
system:
  name: "JARVIS_WALLPAPER_TEST"
memory:
  db_path: "{db_path}"
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "{str(temp_plugins).replace('\\', '/')}"
  auto_load: true
"""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(cfg_content)
        return create_jarvis(str(cfg_file))

    def test_capability_question_does_not_change_wallpaper(self, jarvis):
        resp = jarvis.process_input("kya tum wallpaper change kar sakte ho?")
        assert "Haan, main desktop wallpaper change kar sakta hoon" in resp

    def test_ambiguous_command_prompts_clarification(self, jarvis):
        resp = jarvis.process_input("wallpaper change karo")
        assert "Kaunsa wallpaper" in resp
        we = get_wallpaper_engine()
        assert we.preferences.is_awaiting_clarification() is True

    def test_cancellation_during_clarification(self, jarvis):
        jarvis.process_input("wallpaper change karo")
        we = get_wallpaper_engine()
        assert we.preferences.is_awaiting_clarification() is True

        resp = jarvis.process_input("nahi rehne do")
        assert "cancel" in resp.lower() or "theek" in resp.lower()
        assert we.preferences.is_awaiting_clarification() is False
