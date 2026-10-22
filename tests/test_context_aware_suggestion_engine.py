# tests/test_context_aware_suggestion_engine.py
"""
Tests for Context-Aware Answer + Intelligent Suggestion Engine in Jarvis V2.1.
Covers:
- Goal recognition & next-step suggestions (Travel, Weather, IT, DNS, Excel, Music, System cleanup, Backup)
- Negative suppression (Simple completed commands, greetings, static factual GK, math, questions from Jarvis)
- Capability-aware filtering (CapabilityRegistry gating, unsupported operations)
- Multi-factor SuggestionScore evaluation (threshold >= 0.75, repetition penalties)
- Turn N+1 DialogManager follow-up handling (affirmation execution, rejection backoff, topic switching)
"""

import pytest
from unittest.mock import MagicMock

from core.capabilities import CapabilityRegistry
from core.dialog_manager import DialogManager
from core.intelligence.models import (
    ContextualSuggestion,
    SuggestionCategory,
    SuggestionScore,
)
from core.intelligence.suggestion_manager import SuggestionManager, get_suggestion_manager


class TestContextAwareSuggestionEngine:
    """Test suite for Context-Aware Answer + Intelligent Suggestion Engine."""

    @pytest.fixture
    def suggestion_mgr(self):
        """Creates a fresh SuggestionManager instance for isolated testing."""
        return SuggestionManager(
            min_global_cooldown_sec=1.0,
            min_pattern_cooldown_sec=1.0,
            rejection_backoff_sec=300.0,
            confirmation_timeout_sec=30.0,
        )

    @pytest.fixture
    def dialog_mgr(self):
        """Creates a fresh DialogManager instance."""
        return DialogManager()

    # =========================================================================
    # 1. POSITIVE SUGGESTION TESTS
    # =========================================================================

    def test_travel_planning_suggestion(self, suggestion_mgr):
        user_input = "Mujhe Mumbai jana hai, kaise jaaun?"
        answer = "Mumbai jaane ke liye train, flight aur road travel options available hain."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "TRAVEL_PLANNING"
        assert sug.category == SuggestionCategory.NEXT_STEP
        assert sug.action == "compare_travel_routes"
        assert sug.decision == "SUGGEST"
        assert "compare" in sug.text.lower() or "routes" in sug.text.lower()
        assert sug.score.total >= 0.75

    def test_weather_forecast_suggestion(self, suggestion_mgr):
        user_input = "Aaj Mumbai mein weather kaisa hai?"
        answer = "Mumbai mein abhi taapman 30°C hai aur aasmaan saaf hai."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "WEATHER_CHECK"
        assert sug.category == SuggestionCategory.RELEVANT_INFORMATION
        assert sug.action == "get_hourly_forecast"
        assert "hourly forecast" in sug.text.lower() or "forecast" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_it_troubleshooting_suggestion(self, suggestion_mgr):
        user_input = "RDP connect nahi ho raha, kya karu?"
        answer = "RDP connection fail hone ke aam kaaran network unreachable hona, port 3389 block hona, ya Remote Desktop Services stopped hona ho sakte hain."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "IT_TROUBLESHOOTING"
        assert sug.category == SuggestionCategory.NEXT_STEP
        assert sug.action == "start_troubleshooting_checklist"
        assert "checklist" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_dns_setup_suggestion(self, suggestion_mgr):
        user_input = "Windows mein DNS kya hai?"
        answer = "DNS (Domain Name System) internet ka phonebook hai, jo human-readable domain names ko IP addresses mein translate karta hai."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "DNS_EXPLANATION_OR_SETUP"
        assert sug.category == SuggestionCategory.USEFUL_ACTION
        assert sug.action == "show_dns_setup_guide"
        assert "dns" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_excel_duplicate_removal_suggestion(self, suggestion_mgr):
        user_input = "Excel mein duplicate entries kaise hataun?"
        answer = "Excel mein duplicate entries hatane ke liye aap Data tab mein jaakar Remove Duplicates feature use kar sakte hain."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "EXCEL_DUPLICATE_REMOVAL"
        assert sug.category == SuggestionCategory.USEFUL_ACTION
        assert sug.action == "show_excel_formula_example"
        assert "countif" in sug.text.lower() or "formula" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_music_desire_suggestion(self, suggestion_mgr):
        user_input = "Gaana sunne ka mann hai"
        answer = "Bilkul, music sunna ek accha idea hai."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "MUSIC_DESIRE"
        assert sug.category == SuggestionCategory.ALTERNATIVE
        assert sug.action == "play_trending_songs"
        assert "play" in sug.text.lower() or "songs" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_system_cleanup_suggestion(self, suggestion_mgr):
        user_input = "Computer ko thoda clean kaise kar sakta hoon?"
        answer = "Computer clean karne ke liye temporary files delete karein, browser cache clear karein, aur unused apps uninstall karein."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "SYSTEM_CLEANUP"
        assert sug.category == SuggestionCategory.USEFUL_ACTION
        assert sug.action == "open_disk_cleanup"
        assert "clean" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    def test_backup_planning_suggestion(self, suggestion_mgr):
        user_input = "Files ka backup kaise banayein?"
        answer = "Files ka safe backup banane ke liye external drive ya cloud storage par regular backup schedule configure karna chahiye."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)

        assert sug is not None
        assert sug.goal == "BACKUP_PLANNING"
        assert sug.category == SuggestionCategory.NEXT_STEP
        assert sug.action == "show_backup_options"
        assert "backup" in sug.text.lower()
        assert sug.decision == "SUGGEST"

    # =========================================================================
    # 2. NEGATIVE SUPPRESSION TESTS
    # =========================================================================

    def test_static_factual_qa_suppressed(self, suggestion_mgr):
        """Factual lookups must answer and stop immediately without suggestions."""
        queries = [
            ("India ki capital kya hai?", "India ki capital New Delhi hai."),
            ("2 + 2 kitna hota hai", "2 + 2 ka answer 4 hai."),
            ("What is the currency of Japan?", "The currency of Japan is the Japanese Yen (JPY)."),
            ("Solar system ka sabse bada planet kaunsa hai?", "Solar system ka sabse bada planet Jupiter hai."),
            ("Full form of RAM", "RAM ka full form Random Access Memory hai."),
        ]
        for q, a in queries:
            sug = suggestion_mgr.evaluate_conversational_suggestion(q, a)
            assert sug is None, f"Expected suppression for factual query '{q}', but got suggestion"

    def test_greetings_and_small_talk_suppressed(self, suggestion_mgr):
        """Greetings and casual small talk must not receive suggestions."""
        greetings = [
            ("Good morning", "Good morning! Aapka din shubh ho."),
            ("Hello", "Hello! Main aapki kya madad kar sakta hoon?"),
            ("Kaise ho?", "Main badhiya hoon, aap bataiye?"),
            ("Thank you", "You are welcome!"),
        ]
        for q, a in greetings:
            sug = suggestion_mgr.evaluate_conversational_suggestion(q, a)
            assert sug is None, f"Expected suppression for greeting '{q}', but got suggestion"

    def test_simple_completed_commands_suppressed(self, suggestion_mgr):
        """Direct completed actions must execute and stop immediately without suggestions."""
        commands = [
            ("Chrome kholo", "Chrome open kar diya hai."),
            ("Volume 50 kar do", "System volume 50% par set kar diya hai."),
            ("Recycle bin empty karo", "Recycle bin empty kar diya hai."),
            ("Lock system", "System lock kar diya hai."),
            ("Take screenshot", "Screenshot save kar liya hai."),
            ("Notepad band karo", "Notepad close kar diya hai."),
        ]
        for q, a in commands:
            sug = suggestion_mgr.evaluate_conversational_suggestion(q, a)
            assert sug is None, f"Expected suppression for simple command '{q}', but got suggestion"

    def test_jarvis_active_question_suppressed(self, suggestion_mgr):
        """If Jarvis already asks a question (slot-filling / selection), suppress suggestion."""
        user_input = "Excel file open karo"
        answer = "Kaunsi Excel file open karni hai, Boss?"
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)
        assert sug is None

    def test_unsupported_operation_suppressed(self, suggestion_mgr):
        """Unsupported operations (like registry optimization) must be suppressed."""
        user_input = "Windows ka pura registry clean aur optimize kaise karu?"
        answer = "Ye exact operation abhi meri available capabilities mein nahi hai."
        sug = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)
        assert sug is None

    # =========================================================================
    # 3. SCORING & DEBUG LOG TESTS
    # =========================================================================

    def test_suggestion_score_calculation(self):
        score = SuggestionScore(
            goal_alignment=1.0,
            context_alignment=0.90,
            capability_match=1.0,
            confidence=0.95,
            usefulness=0.90,
            repetition_penalty=0.0,
        )
        assert score.total >= 0.75
        d = score.to_dict()
        assert "total" in d
        assert d["total"] >= 0.75

    def test_debug_string_representation(self):
        score = SuggestionScore(goal_alignment=1.0, capability_match=1.0)
        sug = ContextualSuggestion(
            goal="TRAVEL_PLANNING",
            text="Kya main dono routes compare karke dikhaun?",
            capability_available=True,
            score=score,
            decision="SUGGEST",
        )
        debug_str = sug.to_debug_string()
        assert "GOAL:\nTRAVEL_PLANNING" in debug_str
        assert "CAPABILITY:\nAVAILABLE" in debug_str
        assert "DECISION:\nSUGGEST" in debug_str

    def test_repetition_cooldown_penalty(self, suggestion_mgr):
        """Suggesting the same goal within cooldown period applies repetition penalty."""
        user_input = "Mujhe Mumbai jana hai, kaise jaaun?"
        answer = "Train, flight aur road travel options available hain."

        # First call: permitted
        sug1 = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)
        assert sug1 is not None

        # Immediate second call for same goal: repetition penalty reduces score
        sug2 = suggestion_mgr.evaluate_conversational_suggestion(user_input, answer)
        assert sug2 is None  # Suppressed due to cooldown

    # =========================================================================
    # 4. DIALOG MANAGER MULTI-TURN FOLLOW-UP EXECUTION TESTS
    # =========================================================================

    def test_dialog_manager_affirmative_followup(self, dialog_mgr):
        """Affirming a suggestion executes the suggested action."""
        mock_core = MagicMock()
        mock_core.suggestion_manager = MagicMock()

        sug = ContextualSuggestion(
            suggestion_id="test1234",
            goal="TRAVEL_PLANNING",
            action="compare_travel_routes",
            target="Mumbai",
            text="Kya main dono routes compare karke dikhaun ya ticket booking site kholun?",
        )
        dialog_mgr.set_pending_contextual_suggestion(sug)
        assert dialog_mgr.has_pending_contextual_suggestion()
        assert dialog_mgr.awaits_user_followup()

        handled, resp = dialog_mgr.interpret_turn_n_plus_1("haan compare karke dikhao", mock_core)
        assert handled is True
        assert "mumbai" in resp.lower()
        assert "routes" in resp.lower() or "open" in resp.lower()
        assert not dialog_mgr.has_pending_contextual_suggestion()

    def test_dialog_manager_rejection_followup(self, dialog_mgr):
        """Rejecting a suggestion records backoff and acknowledges politely."""
        mock_core = MagicMock()
        mock_core.suggestion_manager = MagicMock()

        sug = ContextualSuggestion(
            suggestion_id="test5678",
            goal="WEATHER_CHECK",
            action="get_hourly_forecast",
            target="Mumbai",
            text="Kya aap agle 6 ghante ka hourly forecast dekhna chahenge?",
        )
        dialog_mgr.set_pending_contextual_suggestion(sug)

        handled, resp = dialog_mgr.interpret_turn_n_plus_1("nahi rehne do", mock_core)
        assert handled is True
        assert "koi baat nahi" in resp.lower()
        assert not dialog_mgr.has_pending_contextual_suggestion()

    def test_dialog_manager_topic_switch_overrides_suggestion(self, dialog_mgr):
        """If user speaks a brand new command instead, suggestion is cleared and command passes to pipeline."""
        mock_core = MagicMock()
        mock_core.suggestion_manager = MagicMock()

        sug = ContextualSuggestion(
            suggestion_id="test9999",
            goal="IT_TROUBLESHOOTING",
            action="start_troubleshooting_checklist",
            text="Kya main step-by-step troubleshooting checklist batana shuru karun?",
        )
        dialog_mgr.set_pending_contextual_suggestion(sug)

        # User says unrelated command
        handled, resp = dialog_mgr.interpret_turn_n_plus_1("chrome kholo", mock_core)
        # Should not be handled as suggestion follow-up; cleared for generic pipeline
        assert handled is False
        assert not dialog_mgr.has_pending_contextual_suggestion()


class TestJarvisCoreSuggestionIntegration:
    """End-to-end integration test of context-aware suggestions in JarvisCore."""

    @pytest.fixture
    def jarvis(self, tmp_path):
        import os
        import shutil
        from main import create_jarvis

        orig_plugins = os.path.abspath("plugins")
        temp_plugins = tmp_path / "plugins"
        shutil.copytree(orig_plugins, temp_plugins)

        db_path = os.path.join(tmp_path, "sug_test.db").replace("\\", "/")
        cfg_content = f"""
system:
  name: "JARVIS_SUG_TEST"
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

    def test_e2e_weather_suggestion_and_affirmation(self, jarvis):
        """Tests that weather query appends hourly forecast suggestion, and 'haan' affirms it."""
        resp1 = jarvis.process_input("Aaj Mumbai mein weather kaisa hai?")
        assert "weather" in resp1.lower() or "mumbai" in resp1.lower() or "taapman" in resp1.lower() or "forecast" in resp1.lower()
        # Suggestion should be appended
        assert "hourly forecast" in resp1.lower() or "forecast" in resp1.lower()

        # Follow-up turn affirms
        resp2 = jarvis.process_input("haan")
        assert "mumbai" in resp2.lower()
        assert "ghante" in resp2.lower() or "saaf" in resp2.lower() or "forecast" in resp2.lower()

    def test_e2e_factual_gk_no_suggestion(self, jarvis):
        """Factual GK queries must not receive suggestions."""
        resp = jarvis.process_input("India ki capital kya hai?")
        assert "delhi" in resp.lower()
        assert "hourly forecast" not in resp.lower()
        assert "routes compare" not in resp.lower()
        assert "checklist" not in resp.lower()

    def test_e2e_simple_command_no_suggestion(self, jarvis):
        """Simple completed commands must not receive suggestions."""
        resp = jarvis.process_input("volume 50 kar do")
        assert "volume" in resp.lower() or "50" in resp.lower()
        assert "hourly forecast" not in resp.lower()
        assert "routes compare" not in resp.lower()
        assert "checklist" not in resp.lower()

