# tests/test_browser_descriptor_resolution.py
"""
Regression and unit tests for compound browser descriptor resolution and verification.
Ensures:
1. Brand-qualified descriptors (e.g. 'brave browser', 'edge browser', 'chrome browser')
   are NOT blindly replaced with default browser names like 'chrome'.
2. Standalone descriptors (e.g. 'browser open karo') continue to resolve to the default browser.
3. MultiEntityCommandParser does not falsely treat single compound entities as multi-target commands.
4. WindowManager & ExecutionVerificationLayer filter out auxiliary background crash daemons
   so closing Brave/Chrome/Edge is accurately verified without false-positive failures.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from memory.database import DatabaseManager
from learning.vocabulary_layer import VocabularyLayer
from core.semantic.multi_entity import MultiEntityCommandParser
from brain.semantic_parser import HinglishNLUParser
from plugins.windows.window_manager import WindowManager
from core.execution.verifier import ExecutionVerificationLayer


@pytest.fixture
def temp_vocab_layer(tmp_path):
    db_path = str(tmp_path / "test_vocab.db")
    db = DatabaseManager(db_path=db_path)
    vl = VocabularyLayer(db)
    return vl


class TestBrowserDescriptorResolution:
    """Tests for VocabularyLayer descriptor guards and compound phrase protection."""

    def test_brave_browser_not_corrupted_to_chrome(self, temp_vocab_layer):
        text = "brave browser close karo"
        resolved = temp_vocab_layer.resolve_text(text)
        assert resolved == "brave browser close karo"
        assert "chrome" not in resolved.lower()

    def test_edge_and_firefox_browsers_not_corrupted(self, temp_vocab_layer):
        assert temp_vocab_layer.resolve_text("edge browser open karo") == "edge browser open karo"
        assert temp_vocab_layer.resolve_text("firefox browser band karo") == "firefox browser band karo"
        assert temp_vocab_layer.resolve_text("opera browser chalao") == "opera browser chalao"

    def test_chrome_browser_does_not_duplicate(self, temp_vocab_layer):
        resolved = temp_vocab_layer.resolve_text("chrome browser close karo")
        assert resolved == "chrome browser close karo"
        assert "chrome chrome" not in resolved.lower()

    def test_standalone_browser_resolves_to_chrome(self, temp_vocab_layer):
        assert temp_vocab_layer.resolve_text("open browser") == "open chrome"
        assert temp_vocab_layer.resolve_text("browser kholo") == "chrome kholo"
        assert temp_vocab_layer.resolve_text("browser band karo") == "chrome band karo"

    def test_sheet_guards_prevent_duplicates(self, temp_vocab_layer):
        assert temp_vocab_layer.resolve_text("excel sheet open karo") == "excel sheet open karo"
        assert temp_vocab_layer.resolve_text("google sheet open karo") == "google sheet open karo"
        assert temp_vocab_layer.resolve_text("sheet open karo") == "excel open karo"

    def test_recording_guards_prevent_duplicates(self, temp_vocab_layer):
        assert temp_vocab_layer.resolve_text("screen recording start karo") == "screen recording start karo"
        assert temp_vocab_layer.resolve_text("recording start karo") == "screen recording start karo"


class TestMultiEntityParserCompoundGuards:
    """Tests ensuring single compound browser requests do not trigger multi-entity plans."""

    def test_brave_browser_single_entity_returns_none(self):
        parser = MultiEntityCommandParser()
        plan = parser.parse("brave browser close karo")
        assert plan is None

    def test_edge_browser_single_entity_returns_none(self):
        parser = MultiEntityCommandParser()
        plan = parser.parse("edge browser open karo")
        assert plan is None

    def test_genuine_multi_browser_still_creates_plan(self):
        parser = MultiEntityCommandParser()
        plan = parser.parse("chrome aur brave band karo")
        assert plan is not None
        assert len(plan.actions) == 2
        targets = [a.target for a in plan.actions]
        assert "chrome" in targets
        assert "brave" in targets


class TestSemanticParserAppResolution:
    """Tests verifying HinglishNLUParser correctly maps 'brave browser close karo' to Brave."""

    def test_brave_browser_close_action(self):
        act = HinglishNLUParser.parse("brave browser close karo")
        assert act is not None
        assert act.intent == "WINDOW_CLOSE"
        assert act.action == "close_app"
        assert act.parameters.get("app_name") == "brave"

    def test_edge_browser_close_action(self):
        act = HinglishNLUParser.parse("edge browser close karo")
        assert act is not None
        assert act.intent == "WINDOW_CLOSE"
        assert act.action == "close_app"
        assert act.parameters.get("app_name") in ("edge", "Microsoft Edge")


class TestProcessVerificationCrashHandlerFiltering:
    """Tests ensuring background crash handlers and daemon helpers do not fool process verification."""

    def test_auxiliary_crash_handlers_ignored_in_process_check(self):
        wm = WindowManager()
        # Even if BraveCrashHandler.exe is running on the Windows host, brave itself should be False when closed
        with patch("plugins.windows.window_manager.psutil.process_iter") as mock_piter:
            mock_proc1 = MagicMock()
            mock_proc1.info = {"pid": 9704, "name": "BraveCrashHandler.exe"}
            mock_proc2 = MagicMock()
            mock_proc2.info = {"pid": 3760, "name": "BraveCrashHandler64.exe"}
            mock_piter.return_value = [mock_proc1, mock_proc2]

            is_running, pids = wm.is_process_running("brave")
            assert is_running is False
            assert pids == []

    def test_genuine_brave_process_detected(self):
        wm = WindowManager()
        with patch("plugins.windows.window_manager.psutil.process_iter") as mock_piter:
            mock_crash = MagicMock()
            mock_crash.info = {"pid": 9704, "name": "BraveCrashHandler.exe"}
            mock_brave = MagicMock()
            mock_brave.info = {"pid": 1234, "name": "brave.exe"}
            mock_piter.return_value = [mock_crash, mock_brave]

            is_running, pids = wm.is_process_running("brave")
            assert is_running is True
            assert 1234 in pids
            assert 9704 not in pids

    def test_close_verification_succeeds_when_only_crash_handler_running(self):
        verifier = ExecutionVerificationLayer()
        with patch.object(verifier.window_manager, "find_windows_for_app", return_value=[]):
            with patch("plugins.windows.window_manager.psutil.process_iter") as mock_piter:
                mock_crash = MagicMock()
                mock_crash.info = {"pid": 9704, "name": "BraveCrashHandler.exe"}
                mock_piter.return_value = [mock_crash]

                res = verifier.verify_window_operation("brave", "close")
                assert res.verified is True
                assert "band ho gaya" in res.message
