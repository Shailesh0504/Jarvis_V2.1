# tests/test_visual_text_interaction.py
"""
Comprehensive Test Suite for Visual Text Interaction Engine:
1. Cross-Script Matching:
   - English user -> Devanagari screen ('Paramhans aashram' <-> 'परमहंस आश्रम')
   - Devanagari user -> English screen ('परमहंस आश्रम' <-> 'PARAMHANS AASHRAM')
   - Devanagari user -> Devanagari screen
2. Case, Whitespace, and Punctuation Tolerance:
   - 'PARAMHANS AASHRAM' vs 'paramhans aashram' vs 'PaRaMhAnS AaShRaM'
   - Extra spaces ('Paramhans  Aashram')
   - Peripheral punctuation ('Paramhans Aashram.', 'Rahul?')
3. Spatial Multi-Word Phrase Construction:
   - Adjacent OCR tokens ('Paramhans' + 'Aashram') merged into unified bounding box
4. Semantic Command Parsing & Sub-action Determination:
   - FIND_TEXT ('kahan likha hai', 'kahan hai', 'dhundo')
   - CLICK_TEXT ('par click karo', 'pe click karo')
   - DOUBLE_CLICK_TEXT ('double click karo')
   - SELECT_TEXT ('select karo')
   - Target text isolation (strips preambles and suffixes)
5. Click Safety Invariant:
   - FIND_TEXT exclusively moves cursor and NEVER clicks
   - CLICK_TEXT moves cursor and clicks
6. Visual Reference Memory & Deictic Resolution:
   - 'ab is par click karo', 'isko select karo' reusing previous search
   - 'Rahul ke doosre wale par click karo' selecting ordinal index 1
7. End-to-End Pipeline Execution in JarvisCore
"""

import pytest
from unittest.mock import MagicMock, patch

from core.cross_script_matcher import get_cross_script_matcher
from core.text_matcher import BoundingBox, OCRToken, VisualTextMatch, get_text_matcher
from core.visual_context import VisualContext, get_visual_context_manager
from core.visual_reference import get_visual_reference_manager
from core.visual_interaction import VisualInteractionEngine, get_visual_interaction_engine
from core.semantic.parsers.visual import extract_target_text, parse_visual_text_interaction


# ==============================================================================
# 1. CROSS-SCRIPT MATCHING UNIT TESTS
# ==============================================================================

class TestCrossScriptMatching:
    @pytest.fixture(autouse=True)
    def setup_matcher(self):
        self.matcher = get_cross_script_matcher()

    def test_english_to_devanagari_paramhans_aashram(self):
        """User English 'Paramhans aashram' matches Devanagari 'परमहंस आश्रम' with high score."""
        score, m_type = self.matcher.score("Paramhans aashram", "परमहंस आश्रम")
        assert score >= 0.88
        assert "cross_script" in m_type

    def test_devanagari_to_english_uppercase(self):
        """User Devanagari 'परमहंस आश्रम' matches English 'PARAMHANS AASHRAM'."""
        score, m_type = self.matcher.score("परमहंस आश्रम", "PARAMHANS AASHRAM")
        assert score >= 0.88
        assert "cross_script" in m_type

    def test_rahul_cross_script(self):
        """'Rahul' matches 'राहुल'."""
        score, m_type = self.matcher.score("Rahul", "राहुल")
        assert score >= 0.95
        assert "cross_script" in m_type

    def test_google_cross_script(self):
        """'Google' matches 'गूगल'."""
        score, m_type = self.matcher.score("Google", "गूगल")
        assert score >= 0.90
        assert "cross_script" in m_type

    def test_devanagari_exact_match(self):
        """Devanagari query 'परमहंस आश्रम' matches Devanagari screen 'परमहंस आश्रम'."""
        score, m_type = self.matcher.score("परमहंस आश्रम", "परमहंस आश्रम")
        assert score == 1.0
        assert m_type == "exact"


# ==============================================================================
# 2. CASE, WHITESPACE & PUNCTUATION TOLERANCE
# ==============================================================================

class TestTextMatcherTolerance:
    @pytest.fixture(autouse=True)
    def setup_text_matcher(self):
        self.matcher = get_text_matcher()

    def test_case_insensitive_matching(self):
        """Case must never prevent a match: uppercase, lowercase, mixed case."""
        score1, _ = self.matcher.compare_strings("paramhans aashram", "PARAMHANS AASHRAM")
        score2, _ = self.matcher.compare_strings("PaRaMhAnS AaShRaM", "paramhans aashram")
        assert score1 >= 0.98
        assert score2 >= 0.98

    def test_whitespace_normalization(self):
        """Multiple spaces, tabs, and newlines collapse into single space."""
        score, _ = self.matcher.compare_strings("Paramhans    Aashram", "Paramhans Aashram")
        assert score >= 0.98

    def test_punctuation_tolerance(self):
        """Non-essential peripheral punctuation is ignored."""
        score1, _ = self.matcher.compare_strings("Paramhans Aashram.", "PARAMHANS AASHRAM")
        score2, _ = self.matcher.compare_strings("Rahul?", "Rahul")
        assert score1 >= 0.98
        assert score2 == 1.0

    def test_spatial_phrase_merging(self):
        """Adjacent OCR tokens on the same line merge into a single phrase bounding box."""
        t1 = OCRToken("Paramhans", BoundingBox(420, 310, 550, 355), 0.98)
        t2 = OCRToken("Aashram", BoundingBox(560, 310, 690, 355), 0.98)

        matches = self.matcher.match_spatial_tokens("Paramhans Aashram", [t1, t2])
        assert len(matches) > 0
        best = matches[0]
        assert best.matched_text == "Paramhans Aashram"
        assert best.bbox.left == 420
        assert best.bbox.top == 310
        assert best.bbox.right == 690
        assert best.bbox.bottom == 355
        assert best.bbox.center_x == (420 + 690) // 2
        assert best.bbox.center_y == (310 + 355) // 2


# ==============================================================================
# 3. SEMANTIC COMMAND PARSER TESTS
# ==============================================================================

class TestSemanticVisualParser:
    def test_parse_kahan_likha_hai_find_action(self):
        act = parse_visual_text_interaction(
            "Paramhans aashram kahan likha hai",
            "paramhans aashram kahan likha hai"
        )
        assert act is not None
        assert act.intent == "VISUAL_TEXT_INTERACTION"
        assert act.action == "find_text"
        assert act.parameters["sub_action"] == "FIND_TEXT"
        assert act.parameters["target"] == "Paramhans aashram"

    def test_parse_uppercase_kahan_hai(self):
        act = parse_visual_text_interaction(
            "PARAMHANS AASHRAM KAHAN HAI",
            "paramhans aashram kahan hai"
        )
        assert act is not None
        assert act.action == "find_text"
        assert act.parameters["target"].upper() == "PARAMHANS AASHRAM"

    def test_parse_devanagari_find_query(self):
        act = parse_visual_text_interaction(
            "परमहंस आश्रम कहाँ लिखा है",
            "परमहंस आश्रम कहाँ लिखा है"
        )
        assert act is not None
        assert act.action == "find_text"
        assert "परमहंस आश्रम" in act.parameters["target"]

    def test_parse_click_karo_action(self):
        act = parse_visual_text_interaction(
            "Paramhans aashram par click karo",
            "paramhans aashram par click karo"
        )
        assert act is not None
        assert act.action == "click_text"
        assert act.parameters["sub_action"] == "CLICK_TEXT"
        assert act.parameters["target"] == "Paramhans aashram"

    def test_parse_devanagari_click_action(self):
        act = parse_visual_text_interaction(
            "परमहंस आश्रम पर क्लिक करो",
            "परमहंस आश्रम पर क्लिक करो"
        )
        assert act is not None
        assert act.action == "click_text"
        assert "परमहंस आश्रम" in act.parameters["target"]

    def test_parse_rahul_word_par_click(self):
        act = parse_visual_text_interaction(
            "Rahul word par click karo",
            "rahul word par click karo"
        )
        assert act is not None
        assert act.action == "click_text"
        assert act.parameters["target"] == "Rahul"

    def test_parse_ordinal_selection(self):
        act = parse_visual_text_interaction(
            "Rahul ke doosre wale par click karo",
            "rahul ke doosre wale par click karo"
        )
        assert act is not None
        assert act.action == "click_text"
        assert act.parameters["ordinal_index"] == 1


# ==============================================================================
# 4. VISUAL INTERACTION ENGINE & CLICK SAFETY
# ==============================================================================

class TestVisualInteractionEngine:
    @pytest.fixture(autouse=True)
    def setup_engine(self):
        self.engine = get_visual_interaction_engine()
        self.ref_mgr = get_visual_reference_manager()
        self.ref_mgr.clear()

    def test_click_safety_find_text_never_clicks(self):
        """Rule 17: Default action FIND_TEXT moves pointer but NEVER clicks."""
        fake_match = VisualTextMatch(
            text="Paramhans aashram",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.99,
            match_type="casefold",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch.object(self.engine.locator, "locate", return_value=[fake_match]), \
             patch.object(self.engine.mouse, "move_to") as mock_move, \
             patch.object(self.engine.mouse, "click") as mock_click:

            res = self.engine.execute(
                target_text="Paramhans aashram",
                sub_action="FIND_TEXT",
                raw_utterance="Paramhans aashram kahan likha hai"
            )

            assert res.success is True
            assert res.action == "FIND_TEXT"
            mock_move.assert_called_once()
            mock_click.assert_not_called()
            assert "Sir, 'Paramhans Aashram' yahan likha hai" in res.message

    def test_click_text_moves_and_clicks(self):
        """Rule 15: CLICK_TEXT moves pointer and clicks with verified feedback."""
        fake_match = VisualTextMatch(
            text="Paramhans aashram",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.99,
            match_type="casefold",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch.object(self.engine.locator, "locate", return_value=[fake_match]), \
             patch.object(self.engine.mouse, "click") as mock_click:

            mock_click.return_value = MagicMock(success=True, verified=True)
            res = self.engine.execute(
                target_text="Paramhans aashram",
                sub_action="CLICK_TEXT",
                raw_utterance="Paramhans aashram par click karo"
            )

            assert res.success is True
            assert res.action == "CLICK_TEXT"
            mock_click.assert_called_once()
            assert res.message == "Ji Sir, 'Paramhans Aashram' par click kar diya."

    def test_cross_script_devanagari_to_english_click(self):
        """User Hindi 'परमहंस आश्रम पर क्लिक करो' locates screen English and clicks."""
        fake_match = VisualTextMatch(
            text="परमहंस आश्रम",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.98,
            match_type="cross_script_exact",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch.object(self.engine.locator, "locate", return_value=[fake_match]), \
             patch.object(self.engine.mouse, "click") as mock_click:

            mock_click.return_value = MagicMock(success=True, verified=True)
            res = self.engine.execute(
                target_text="परमहंस आश्रम",
                sub_action="CLICK_TEXT",
                raw_utterance="परमहंस आश्रम पर क्लिक करो"
            )

            assert res.success is True
            mock_click.assert_called_once()
            assert "परमहंस आश्रम" in res.message and "click kar diya" in res.message

    def test_follow_up_deictic_reference_ab_is_par_click_karo(self):
        """Rule 20: Follow-up 'ab is par click karo' uses previous visual search context."""
        fake_match = VisualTextMatch(
            text="Paramhans Aashram",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.99,
            match_type="casefold",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        # Store previous search
        self.ref_mgr.store_search(
            query="Paramhans Aashram",
            window_hwnd=12345,
            application="Chrome",
            matches=[fake_match],
            selected_index=0
        )

        with patch.object(self.engine.mouse, "click") as mock_click:
            mock_click.return_value = MagicMock(success=True, verified=True)
            res = self.engine.execute(
                target_text="current_reference",
                sub_action="CLICK_TEXT",
                raw_utterance="ab is par click karo"
            )

            assert res.success is True
            assert res.display_name == "Paramhans Aashram"
            mock_click.assert_called_once()
            assert res.message == "Ji Sir, 'Paramhans Aashram' par click kar diya."

    def test_multiple_matches_reports_count_and_ordinal_navigation(self):
        """Rule 18: Multiple matches report count, and follow-up chooses match #2."""
        m1 = VisualTextMatch("Rahul", "Rahul", 0.98, 1.0, "exact", BoundingBox(100, 100, 150, 120))
        m2 = VisualTextMatch("Rahul", "Rahul", 0.98, 1.0, "exact", BoundingBox(100, 300, 150, 320))
        m3 = VisualTextMatch("Rahul", "Rahul", 0.98, 1.0, "exact", BoundingBox(100, 500, 150, 520))

        with patch.object(self.engine.locator, "locate", return_value=[m1, m2, m3]), \
             patch.object(self.engine.mouse, "move_to"):

            res1 = self.engine.execute(
                target_text="Rahul",
                sub_action="FIND_TEXT",
                raw_utterance="Rahul kahan hai"
            )
            assert "teen jagah mila hai" in res1.message

        # Follow-up: 'Rahul ke doosre wale par click karo'
        with patch.object(self.engine.mouse, "click") as mock_click:
            mock_click.return_value = MagicMock(success=True, verified=True)
            res2 = self.engine.execute(
                target_text="Rahul",
                sub_action="CLICK_TEXT",
                ordinal_index=1,
                raw_utterance="Rahul ke doosre wale par click karo"
            )
            assert res2.success is True
            # Verified it clicked m2 (center_y = 310)
            mock_click.assert_called_once_with(125, 310, hitbox=None)


# ==============================================================================
# 5. END-TO-END PIPELINE TESTS
# ==============================================================================

class TestEndToEndVisualPipeline:
    @pytest.fixture
    def jarvis_core(self):
        from core.app import JarvisCore
        return JarvisCore()

    def test_pipeline_find_text(self, jarvis_core):
        fake_match = VisualTextMatch(
            text="Paramhans aashram",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.99,
            match_type="casefold",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch("core.text_locator.TextLocatorEngine.locate", return_value=[fake_match]), \
             patch("core.mouse_controller.MouseController.move_to", return_value=MagicMock(success=True, verified=True)):

            resp = jarvis_core.process_input("Paramhans aashram kahan likha hai")
            assert "Paramhans Aashram" in resp
            assert "yahan likha hai" in resp

    def test_pipeline_click_text(self, jarvis_core):
        fake_match = VisualTextMatch(
            text="Paramhans aashram",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.99,
            match_type="casefold",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch("core.text_locator.TextLocatorEngine.locate", return_value=[fake_match]), \
             patch("core.mouse_controller.MouseController.click", return_value=MagicMock(success=True, verified=True)):

            resp = jarvis_core.process_input("Paramhans aashram par click karo")
            assert resp == "Ji Sir, 'Paramhans Aashram' par click kar diya."

    def test_pipeline_cross_script_hindi_click(self, jarvis_core):
        fake_match = VisualTextMatch(
            text="परमहंस आश्रम",
            matched_text="PARAMHANS AASHRAM",
            confidence=0.98,
            match_score=0.98,
            match_type="cross_script_exact",
            bbox=BoundingBox(420, 310, 690, 355)
        )

        with patch("core.text_locator.TextLocatorEngine.locate", return_value=[fake_match]), \
             patch("core.mouse_controller.MouseController.click", return_value=MagicMock(success=True, verified=True)):

            resp = jarvis_core.process_input("परमहंस आश्रम पर क्लिक करो")
            assert "परमहंस आश्रम" in resp and "click kar diya" in resp
