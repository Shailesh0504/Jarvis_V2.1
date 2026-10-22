# tests/test_speech_repair_and_window_recovery.py
"""
Comprehensive tests for:
1. Speech Repair Engine (ASR Misrecognition Recovery):
   - Demonstrative repair ('se window' -> 'is window', 'se app' -> 'is app', 'se close' -> 'isse close')
   - Instrumental postposition preservation ('mouse se click karo', 'keyboard se type karo' untouched)
   - N-best hypothesis ranking and confidence scoring
   - Structured audit logging
2. Visual Search Gating:
   - Gating UI object commands ('is window ko close karo', 'isko band karo') out of screen text locator
   - Validating legitimate visual queries ('Paramhans aashram kahan likha hai')
3. End-to-End Pipeline Execution:
   - 'se window ko close karo' -> repaired to 'is window' -> active window close -> "Ji Sir, current window close kar diya."
   - 'is window ko close karo' -> active window close -> "Ji Sir, current window close kar diya."
   - Preservation of existing tab close logic
"""

import pytest
from unittest.mock import MagicMock, patch

from core.speech_repair import (
    SpeechRepairEngine,
    get_speech_repair_engine,
    SuspiciousTokenDetector,
    PhoneticCandidateGenerator,
    CommandPatternValidator,
)
from core.screen_text_locator import ScreenTextLocator
from core.target_engine import TargetRequest, UniversalTargetDiscoveryEngine


# ==============================================================================
# 1. SPEECH REPAIR ENGINE UNIT TESTS
# ==============================================================================

class TestSpeechRepairEngine:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        self.engine = SpeechRepairEngine()

    def test_repair_se_window_to_is_window(self):
        """Rule 1: Distorted demonstrative 'se window' repaired to 'is window'."""
        res = self.engine.repair_transcript("se window ko close karo")
        assert res.repaired is True
        assert res.final_text == "is window ko close karo"
        assert res.original_text == "se window ko close karo"
        assert res.confidence >= 0.85
        assert len(res.candidates) > 0

    def test_repair_se_app_to_is_app(self):
        """Rule 1: 'se app' repaired to 'is app'."""
        res = self.engine.repair_transcript("se app ko kholo")
        assert res.repaired is True
        assert res.final_text == "is app ko kholo"

    def test_repair_se_action_to_isse_action(self):
        """Rule 1: 'se close karo' repaired to 'isse close karo'."""
        res = self.engine.repair_transcript("se close karo")
        assert res.repaired is True
        assert res.final_text == "isse close karo"

    def test_repair_se_band_to_isse_band(self):
        """Rule 1: 'se band kar do' repaired to 'isse band kar do'."""
        res = self.engine.repair_transcript("se band kar do")
        assert res.repaired is True
        assert res.final_text == "isse band kar do"

    def test_preserve_instrumental_mouse_se(self):
        """Rule 2: 'mouse se click karo' must NEVER be modified (instrumental postposition)."""
        res = self.engine.repair_transcript("mouse se click karo")
        assert res.repaired is False
        assert res.final_text == "mouse se click karo"

    def test_preserve_instrumental_keyboard_se(self):
        """Rule 2: 'keyboard se type karo' must NEVER be modified."""
        res = self.engine.repair_transcript("keyboard se type karo")
        assert res.repaired is False
        assert res.final_text == "keyboard se type karo"

    def test_preserve_instrumental_mic_se(self):
        """Rule 2: 'mic se bolo' must NEVER be modified."""
        res = self.engine.repair_transcript("mic se bolo")
        assert res.repaired is False
        assert res.final_text == "mic se bolo"

    def test_preserve_instrumental_chrome_se(self):
        """Rule 2: 'chrome se download karo' must NEVER be modified."""
        res = self.engine.repair_transcript("chrome se download karo")
        assert res.repaired is False
        assert res.final_text == "chrome se download karo"

    def test_preserve_already_valid_is_window(self):
        """Already correct phrasing 'is window ko close karo' remains unchanged."""
        res = self.engine.repair_transcript("is window ko close karo")
        assert res.repaired is False
        assert res.final_text == "is window ko close karo"

    def test_nbest_hypothesis_reranking(self):
        """Rule 4: N-best hypothesis list promotes syntactically valid candidates over raw STT."""
        n_best = [
            ("se window ko close karo", 0.92),
            ("is window ko close karo", 0.88),
            ("the window ko close karo", 0.70)
        ]
        res = self.engine.repair_transcript("se window ko close karo", n_best=n_best)
        assert res.repaired is True
        assert res.final_text == "is window ko close karo"
        assert res.candidates[0].text == "is window ko close karo"


# ==============================================================================
# 2. VISUAL SEARCH GATING UNIT TESTS
# ==============================================================================

class TestVisualSearchGating:
    @pytest.fixture(autouse=True)
    def setup_locator(self):
        self.locator = ScreenTextLocator()

    def test_gate_rejects_window_close_command(self):
        """Gating: 'is window ko close karo' must NOT be treated as on-screen text query."""
        cleaned = self.locator._clean_query_text("is window ko close karo")
        assert cleaned == ""

    def test_gate_rejects_distorted_se_window_command(self):
        """Gating: 'se window ko close karo' must NOT be treated as on-screen text query."""
        cleaned = self.locator._clean_query_text("se window ko close karo")
        assert cleaned == ""

    def test_gate_rejects_isko_band_karo(self):
        """Gating: 'isko band karo' must NOT be treated as on-screen text query."""
        cleaned = self.locator._clean_query_text("isko band karo")
        assert cleaned == ""

    def test_gate_rejects_pure_deictic_references(self):
        """Gating: 'ye window', 'is window' alone must not trigger text search."""
        assert self.locator._clean_query_text("ye window") == ""
        assert self.locator._clean_query_text("is window") == ""
        assert self.locator._clean_query_text("isko") == ""

    def test_gate_allows_legitimate_visual_query(self):
        """Legitimate search like 'Paramhans aashram kahan likha hai' must be preserved."""
        cleaned = self.locator._clean_query_text("Paramhans aashram kahan likha hai")
        assert cleaned.lower() == "paramhans aashram"

    def test_gate_allows_button_query(self):
        """Legitimate search like 'Submit button kahan hai' must be preserved."""
        cleaned = self.locator._clean_query_text("Submit button kahan hai")
        assert cleaned.lower() == "submit button"


# ==============================================================================
# 3. TARGET ENGINE RELATIVE WINDOW RESOLUTION TESTS
# ==============================================================================

class TestTargetEngineWindowResolution:
    def test_target_engine_resolves_current_window_close(self):
        """TargetEngine directly handles 'current' window close without 'desktop par nahi mila'."""
        mock_wm = MagicMock()
        mock_wm.get_foreground_window.return_value = None
        mock_wm.execute_operation.return_value = {"success": True}

        engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm)
        req = TargetRequest(target="current", action="close")
        outcome = engine.execute(req)

        assert outcome.success is True
        assert outcome.message == "Ji Sir, current window close kar diya."

    def test_target_engine_resolves_is_window_target(self):
        """TargetEngine directly handles 'is window' as foreground window."""
        mock_wm = MagicMock()
        mock_win = MagicMock()
        mock_win.hwnd = 12345
        mock_win.title = "Notepad"
        mock_win.process_name = "notepad.exe"
        mock_wm.get_foreground_window.return_value = mock_win

        engine = UniversalTargetDiscoveryEngine(window_manager=mock_wm)
        req = TargetRequest(target="is window", action="close")
        outcome = engine.execute(req)

        assert outcome.success is True
        assert outcome.message == "Ji Sir, current window close kar diya."


# ==============================================================================
# 4. END-TO-END PIPELINE TESTS
# ==============================================================================

class TestPipelineEndToEnd:
    @pytest.fixture
    def jarvis_core(self):
        from core.app import JarvisCore
        # Initialize core in headless mode
        core = JarvisCore()
        return core

    def test_se_window_close_repaired_and_executed(self, jarvis_core):
        """End-to-end: 'se window ko close karo' -> repaired to 'is window' -> returns 'Ji Sir, current window close kar diya.'"""
        resp = jarvis_core.process_input("se window ko close karo")
        assert resp == "Ji Sir, current window close kar diya."

    def test_is_window_close_executed(self, jarvis_core):
        """End-to-end: 'is window ko close karo' -> returns 'Ji Sir, current window close kar diya.'"""
        resp = jarvis_core.process_input("is window ko close karo")
        assert resp == "Ji Sir, current window close kar diya."

    def test_iss_window_close_executed(self, jarvis_core):
        """End-to-end: 'iss window ko close karo' -> returns 'Ji Sir, current window close kar diya.'"""
        resp = jarvis_core.process_input("iss window ko close karo")
        assert resp == "Ji Sir, current window close kar diya."

    def test_current_window_close_executed(self, jarvis_core):
        """End-to-end: 'current window close karo' -> returns 'Ji Sir, current window close kar diya.'"""
        resp = jarvis_core.process_input("current window close karo")
        assert resp == "Ji Sir, current window close kar diya."

    def test_ye_window_band_karo_executed(self, jarvis_core):
        """End-to-end: 'ye window band karo' -> returns 'Ji Sir, current window close kar diya.'"""
        resp = jarvis_core.process_input("ye window band karo")
        assert resp == "Ji Sir, current window close kar diya."

    def test_preserve_tab_close_behavior(self, jarvis_core):
        """Regression test: 'tab close karo' still closes tab and does not collide with window close."""
        resp = jarvis_core.process_input("tab close karo")
        assert "tab" in resp.lower() or "band" in resp.lower()
