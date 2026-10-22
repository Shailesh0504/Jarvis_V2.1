# tests/test_multi_turn_equity_slot_filling.py
"""
Unit and regression tests for multi-turn equity research slot filling,
compound parameter extraction, Hindi textual numbers, interruption handling,
and input quality gating for numeric amounts (e.g. 50000).
"""

import pytest
from unittest.mock import MagicMock

from core.speech_understanding import InputQualityEvaluator, InputQuality
from core.semantic.slot_extractor import SemanticSlotExtractor
from core.dialog_manager import DialogManager, WorkflowLock
from core.context import ActiveTargetContext


class TestInputQualityRepetitionFix:
    def test_50000_does_not_trigger_character_repetition(self):
        """Zero repetition in numbers like 50000 must NOT trigger keyboard mash / UNINTELLIGIBLE."""
        raw_text = "1 month ke liye or mera budget 50000 and risk moderate"
        quality, score, meta = InputQualityEvaluator.evaluate_quality(raw_text, raw_text)
        assert quality == InputQuality.CLEAN
        assert score >= 0.80

    def test_genuine_character_repetition_still_detected(self):
        """Alphabetic character repetition like 'aaaaa' or 'hellooooo' must still be caught."""
        raw_text = "aaaaa"
        quality, score, meta = InputQualityEvaluator.evaluate_quality(raw_text, raw_text)
        assert quality == InputQuality.UNINTELLIGIBLE
        assert meta.get("reason") == "character_repetition"


class TestSemanticSlotExtractor:
    def test_compound_slot_extraction_english_hinglish(self):
        """Tests compound extraction of horizon, capital, and risk_profile in one utterance."""
        text = "1 month ke liye or mera budget 50000 and risk moderate"
        slots = SemanticSlotExtractor.extract_slots(text)

        assert slots.get("horizon") == "1_MONTH"
        assert slots.get("capital") == 50000.0
        assert slots.get("risk_profile") == "MODERATE"

    def test_hindi_textual_numbers(self):
        """Tests extraction of Hindi number words like 'pachaas hazaar' and 'ek mahina'."""
        text = "ek mahina ke liye, pachaas hazaar budget aur conservative risk"
        slots = SemanticSlotExtractor.extract_slots(text)

        assert slots.get("horizon") == "1_MONTH"
        assert slots.get("capital") == 50000.0
        assert slots.get("risk_profile") == "CONSERVATIVE"

    def test_lakh_multiplier(self):
        """Tests '2 lakh' or '2.5 lac' multiplier."""
        text = "2.5 lakh budget hai aur aggressive risk"
        slots = SemanticSlotExtractor.extract_slots(text)

        assert slots.get("capital") == 250000.0
        assert slots.get("risk_profile") == "AGGRESSIVE"

    def test_interruption_detection(self):
        """Interruption commands like 'volume 50 kar do' or 'stop' must be detected as interruptions."""
        assert SemanticSlotExtractor.is_interruption("volume 50 kar do") is True
        assert SemanticSlotExtractor.is_interruption("awaaz kam karo") is True
        assert SemanticSlotExtractor.is_interruption("stop") is True
        assert SemanticSlotExtractor.is_interruption("pause") is True

        # Valid slot utterances must NOT be flagged as interruptions
        assert SemanticSlotExtractor.is_interruption("1 month ke liye or mera budget 50000 and risk moderate") is False
        assert SemanticSlotExtractor.is_interruption("moderate risk") is False
        assert SemanticSlotExtractor.is_interruption("50000") is False


class TestMultiTurnDialogManagerSlotFilling:
    @pytest.fixture
    def mock_core(self):
        core = MagicMock()
        core.active_context = ActiveTargetContext()
        core.plugin_manager = None
        return core

    def test_full_compound_slot_completion(self, mock_core):
        """Tests completing the pending equity research workflow in Turn 2."""
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="FIND_OR_SUGGEST_EQUITY",
            missing_slots=["horizon", "capital", "risk_profile"],
            active_question="Pehle ye confirm kar leta hoon ki aap short-term (1 month) ke liye dekh rahe hain ya long-term? Aur aapka budget/capital ya risk preference kya hai?",
            language="hi",
        )

        assert dm.has_active_lock() is True
        assert dm.awaits_user_followup() is True

        user_turn_2 = "1 month ke liye or mera budget 50000 and risk moderate"
        handled, response = dm.process_locked_turn(user_turn_2, mock_core)

        assert handled is True
        assert "1 month horizon" in response or "1 month" in response
        assert "₹50,000" in response
        assert "moderate" in response
        # Lock should now be released
        assert dm.has_active_lock() is False

    def test_partial_slot_filling_multi_turn(self, mock_core):
        """Tests partial slot filling where user provides horizon first, then capital and risk."""
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="FIND_OR_SUGGEST_EQUITY",
            missing_slots=["horizon", "capital", "risk_profile"],
            active_question="Duration, budget aur risk preference batayein.",
            language="hi",
        )

        # Turn 2a: Only horizon provided
        handled, resp1 = dm.process_locked_turn("1 month ke liye", mock_core)
        assert handled is True
        assert dm.has_active_lock() is True
        assert "horizon" in dm.active_lock.filled_slots
        assert "capital" in dm.active_lock.all_missing_slots
        assert "budget / capital" in resp1
        assert "risk preference" in resp1

        # Turn 2b: Remaining slots provided
        handled, resp2 = dm.process_locked_turn("budget 50000 and risk moderate", mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert "₹50,000" in resp2

    def test_interruption_suspends_and_resumes_lock(self, mock_core):
        """Tests that an interruption command suspends the workflow lock and can be resumed."""
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="FIND_OR_SUGGEST_EQUITY",
            missing_slots=["horizon", "capital", "risk_profile"],
            active_question="Duration, budget aur risk preference batayein.",
            language="hi",
        )

        # User interrupts with volume command
        handled, _ = dm.process_locked_turn("volume 50 kar do", mock_core)
        assert handled is False
        assert dm.has_active_lock() is False
        assert dm.has_suspended_lock() is True

        # Next turn: resumed by interpret_turn_n_plus_1 and immediately processed
        turn_mock = MagicMock()
        turn_mock.normalized_input = "1 month ke liye or mera budget 50000 and risk moderate"
        handled, resp = dm.interpret_turn_n_plus_1(turn_mock, mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert "₹50,000" in resp


class TestTypeSafeSlotValidator:
    def test_capital_validation_success_numbers(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val, expected in [
            (50000, 50000.0),
            ("50000", 50000.0),
            ("50k", 50000.0),
            ("2.5 lakh", 250000.0),
            ("pachaas hazaar", 50000.0),
        ]:
            status, norm, _ = TypeSafeSlotValidator.validate_slot("capital", val)
            assert status == ValidationStatus.VALID
            assert norm == expected

    def test_capital_validation_rejects_non_numeric(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val in ["moderate", "conservative", "aggressive", "high risk", "xyz"]:
            status, norm, reason = TypeSafeSlotValidator.validate_slot("capital", val)
            assert status == ValidationStatus.INVALID
            assert norm is None
            assert reason is not None

    def test_risk_profile_validation_success(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val, expected in [
            ("moderate", "MODERATE"),
            ("conservative", "CONSERVATIVE"),
            ("aggressive", "AGGRESSIVE"),
            ("kam risk", "CONSERVATIVE"),
            ("zyada risk", "AGGRESSIVE"),
        ]:
            status, norm, _ = TypeSafeSlotValidator.validate_slot("risk_profile", val)
            assert status == ValidationStatus.VALID
            assert norm == expected

    def test_risk_profile_validation_rejects_numeric(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val in [50000, "50000", "50k", 100000.0]:
            status, norm, reason = TypeSafeSlotValidator.validate_slot("risk_profile", val)
            assert status == ValidationStatus.INVALID
            assert norm is None
            assert "cannot be numeric" in reason

    def test_horizon_validation_success(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val, expected in [
            ("1 month", "1_MONTH"),
            ("1_MONTH", "1_MONTH"),
            ("short term", "1_MONTH"),
            ("long term", "LONG_TERM"),
            ("ek mahina", "1_MONTH"),
        ]:
            status, norm, _ = TypeSafeSlotValidator.validate_slot("horizon", val)
            assert status == ValidationStatus.VALID
            assert norm == expected

    def test_horizon_validation_rejects_invalid(self):
        from core.semantic.slot_extractor import TypeSafeSlotValidator, ValidationStatus
        for val in [50000, "50000", "random_gibberish"]:
            status, norm, reason = TypeSafeSlotValidator.validate_slot("horizon", val)
            assert status == ValidationStatus.INVALID
            assert norm is None


class TestPluginSafeExecution:
    def test_plugin_execute_with_sentence_capital_never_crashes(self):
        from plugins.equity_research.plugin import EquityResearchPlugin
        plugin = EquityResearchPlugin()
        # Even if raw sentence was passed into capital, plugin must safely extract 50000.0 and succeed
        res = plugin.execute("research_shortlist", {
            "capital": "1 month ke liye or mera budget 50000 and risk moderate",
            "risk_profile": "moderate",
        })
        assert res.success is True
        assert res.data is not None
        assert "candidate_count" in res.data

    def test_plugin_execute_with_non_numeric_capital_defaults_gracefully(self):
        from plugins.equity_research.plugin import EquityResearchPlugin
        plugin = EquityResearchPlugin()
        res = plugin.execute("research_shortlist", {
            "capital": "moderate",
            "risk_profile": "moderate",
        })
        assert res.success is True
        assert res.data is not None

    def test_plugin_update_profile_safe_conversions(self):
        from plugins.equity_research.plugin import EquityResearchPlugin
        plugin = EquityResearchPlugin()
        res = plugin.execute("update_profile", {
            "capital": "50k",
            "risk_profile": "conservative",
        })
        assert res.success is True
        assert res.data["profile"]["investment_amount"] == 50000.0
        assert res.data["profile"]["risk_tolerance"] == "CONSERVATIVE"


class TestDialogManagerRobustness:
    @pytest.fixture
    def mock_core(self):
        core = MagicMock()
        core.active_context = ActiveTargetContext()
        core.plugin_manager = None
        return core

    def test_three_turn_partial_then_single_slot_filling(self, mock_core):
        """User gives horizon + capital in Turn 2, and risk in Turn 3."""
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="FIND_OR_SUGGEST_EQUITY",
            missing_slots=["horizon", "capital", "risk_profile"],
            active_question="Duration, budget aur risk preference batayein.",
            language="hi",
        )

        # Turn 2: gives 1 month and 50000
        handled, resp1 = dm.process_locked_turn("1 month aur mera budget 50000", mock_core)
        assert handled is True
        assert dm.has_active_lock() is True
        assert dm.active_lock.filled_slots["horizon"] == "1_MONTH"
        assert dm.active_lock.filled_slots["capital"] == 50000.0
        assert "risk_profile" in dm.active_lock.all_missing_slots

        # Turn 3: gives "moderate"
        handled, resp2 = dm.process_locked_turn("moderate", mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert "₹50,000" in resp2
        assert "moderate" in resp2

    def test_invalid_slot_value_does_not_corrupt_state(self, mock_core):
        """Entering invalid budget prompts user and does NOT corrupt validly filled slots."""
        dm = DialogManager()
        dm.set_pending_goal(
            pending_goal="FIND_OR_SUGGEST_EQUITY",
            missing_slots=["horizon", "capital", "risk_profile"],
            active_question="Duration, budget aur risk preference batayein.",
            language="hi",
        )

        # Turn 2: gives 1 month
        dm.process_locked_turn("1 month ke liye", mock_core)
        assert dm.active_lock.filled_slots["horizon"] == "1_MONTH"

        # Turn 3: user provides risk preference "moderate" (leaving capital missing)
        handled, prompt = dm.process_locked_turn("moderate", mock_core)
        assert handled is True
        assert dm.has_active_lock() is True
        # horizon and risk_profile are both preserved!
        assert dm.active_lock.filled_slots["horizon"] == "1_MONTH"
        assert dm.active_lock.filled_slots["risk_profile"] == "MODERATE"
        assert "capital" not in dm.active_lock.filled_slots
        assert "budget / capital" in prompt

        # Turn 4: user says invalid non-numeric text for capital
        handled, prompt2 = dm.process_locked_turn("kuch bhi chalega", mock_core)
        assert handled is True
        assert dm.has_active_lock() is True
        # valid slots are still preserved!
        assert dm.active_lock.filled_slots["horizon"] == "1_MONTH"
        assert dm.active_lock.filled_slots["risk_profile"] == "MODERATE"
        assert "capital" not in dm.active_lock.filled_slots
        assert "Budget amount mujhe clear nahi hua" in prompt2

        # Turn 5: user finally provides valid budget
        handled, final_resp = dm.process_locked_turn("50000", mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert "₹50,000" in final_resp

