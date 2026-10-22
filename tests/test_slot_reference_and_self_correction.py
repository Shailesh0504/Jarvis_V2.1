# tests/test_slot_reference_and_self_correction.py
"""
Unit and integration test suite for Step 2 & Step 3:
- Intra-utterance self-repair in SpeechRepairEngine
- Candidate options disambiguation (ordinals & recency: nayi wali, pehli wali, doosri wali)
- Multi-slot workflow correction continuity with next-question prompts
- Deictic foreground reference resolution and execution ("Usko foreground mein lao")
- Compose lock suspension with WorkflowState.SUSPENDED
"""

import pytest
from unittest.mock import MagicMock, patch

from core.speech_repair import SpeechRepairEngine
from core.dialog_manager import DialogManager, WorkflowLock, WorkflowState
from core.reference_resolver import ReferenceResolver, ReferenceTargetType
from core.context import ActiveTargetContext
from core.target_engine import UniversalTargetDiscoveryEngine, TargetRequest


class TestSpeechRepairSelfCorrection:
    """Verifies intra-utterance self-repair, false starts, and negation-contrast."""

    @pytest.fixture
    def engine(self):
        return SpeechRepairEngine.get_instance()

    def test_mid_utterance_recipient_correction(self, engine):
        res = engine.repair_transcript("Rahul ko... nahi Rohit ko message bhejo")
        assert res.repaired is True
        assert res.final_text == "Rohit ko message bhejo"
        assert res.reason == "mid_utterance_restart"

    def test_negation_contrast_app_switch(self, engine):
        res = engine.repair_transcript("Chrome mat kholo, Brave kholo")
        assert res.repaired is True
        assert res.final_text == "Brave kholo"
        assert res.reason == "negation_contrast"

    def test_time_slot_self_correction(self, engine):
        res = engine.repair_transcript("5 baje meeting rakho... sorry 6 baje")
        assert res.repaired is True
        assert res.final_text == "6 baje meeting rakho"
        assert res.reason == "time_self_correction"

    def test_city_entity_self_correction(self, engine):
        res = engine.repair_transcript("Pune ka weather batao... sorry Mumbai ka")
        assert res.repaired is True
        assert res.final_text == "Mumbai ka weather batao"
        assert res.reason == "slot_self_correction"

    def test_numeric_volume_self_correction(self, engine):
        res = engine.repair_transcript("Volume 50 karo... actually 30")
        assert res.repaired is True
        assert res.final_text == "Volume 30 karo"
        assert res.reason == "number_self_correction"

    def test_mid_utterance_abort_cancellation(self, engine):
        res = engine.repair_transcript("Folder delete karo... are nahi cancel")
        assert res.repaired is True
        assert res.final_text == "cancel"
        assert res.reason == "mid_utterance_cancellation"


class TestCandidateOptionsDisambiguation:
    """Verifies ordinal and recency candidate disambiguation in DialogManager."""

    @pytest.fixture
    def dialog_mgr(self):
        dm = DialogManager()
        dm.release_lock()
        dm.clear_suspended_workflows()
        return dm

    def test_resolve_candidate_selection_recency_nayi_wali(self, dialog_mgr):
        candidates = [
            {"name": "Sales_2025.xlsx", "path": "C:/docs/Sales_2025.xlsx", "mtime": 100},
            {"name": "Sales_2026.xlsx", "path": "C:/docs/Sales_2026.xlsx", "mtime": 200},
        ]
        chosen = dialog_mgr._resolve_candidate_selection("nayi wali", candidates)
        assert chosen is not None
        assert chosen["name"] == "Sales_2026.xlsx"

    def test_resolve_candidate_selection_ordinal_pehli_wali(self, dialog_mgr):
        candidates = [
            {"name": "Sales_2025.xlsx", "path": "C:/docs/Sales_2025.xlsx", "mtime": 100},
            {"name": "Sales_2026.xlsx", "path": "C:/docs/Sales_2026.xlsx", "mtime": 200},
        ]
        chosen = dialog_mgr._resolve_candidate_selection("pehli wali", candidates)
        assert chosen is not None
        assert chosen["name"] == "Sales_2025.xlsx"

    def test_resolve_candidate_selection_ordinal_doosri_wali(self, dialog_mgr):
        candidates = [
            {"name": "Sales_2025.xlsx", "path": "C:/docs/Sales_2025.xlsx", "mtime": 100},
            {"name": "Sales_2026.xlsx", "path": "C:/docs/Sales_2026.xlsx", "mtime": 200},
        ]
        chosen = dialog_mgr._resolve_candidate_selection("doosri wali", candidates)
        assert chosen is not None
        assert chosen["name"] == "Sales_2026.xlsx"

    def test_resolve_candidate_selection_purani_wali(self, dialog_mgr):
        candidates = [
            {"name": "Sales_2025.xlsx", "path": "C:/docs/Sales_2025.xlsx", "mtime": 100},
            {"name": "Sales_2026.xlsx", "path": "C:/docs/Sales_2026.xlsx", "mtime": 200},
        ]
        chosen = dialog_mgr._resolve_candidate_selection("purani wali", candidates)
        assert chosen is not None
        assert chosen["name"] == "Sales_2025.xlsx"

    def test_excel_open_workflow_resolves_nayi_wali_to_newer_file(self, dialog_mgr):
        """Ensures 'nayi wali' chooses the newer candidate instead of opening a blank workbook."""
        candidates = [
            {"name": "Sales_2025.xlsx", "path": "C:/docs/Sales_2025.xlsx", "mtime": 100},
            {"name": "Sales_2026.xlsx", "path": "C:/docs/Sales_2026.xlsx", "mtime": 200},
        ]
        dialog_mgr.set_lock(
            workflow_type="EXCEL_OPEN",
            required_slots=["file_target"],
            target_plugin="excel",
            target_action="open",
            prompt_question="Kaunsi file open karni hai?"
        )
        dialog_mgr.active_lock.candidate_options = candidates

        mock_core = MagicMock()
        mock_core.plugin_manager = MagicMock()
        mock_core.active_context = MagicMock()

        handled, resp = dialog_mgr.process_locked_turn("nayi wali", mock_core)
        assert handled is True
        assert "Sales_2026.xlsx" in resp
        mock_core.plugin_manager.execute_action.assert_called_once_with(
            "windows", "launch_app", {"app_name": "excel", "path": "C:/docs/Sales_2026.xlsx"}
        )


class TestWorkflowCorrectionContinuity:
    """Verifies workflow slot corrections in multi-turn compose flows."""

    @pytest.fixture
    def dialog_mgr(self):
        dm = DialogManager()
        dm.release_lock()
        dm.clear_suspended_workflows()
        return dm

    def test_mid_workflow_recipient_correction_prompts_next_slot(self, dialog_mgr):
        dialog_mgr.set_lock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body", "send_confirm"],
            target_plugin="email",
            target_action="send",
            initial_slots={"recipient": "Rohit"},
            prompt_question="Subject kya hai?"
        )
        mock_core = MagicMock()
        handled, resp = dialog_mgr.process_locked_turn("Nahi Rahul ko", mock_core)
        assert handled is True
        assert "recipient Rahul kar diya" in resp
        # Verifies next question is appended rather than terminating speech
        assert "Subject" in resp
        assert dialog_mgr.active_lock.filled_slots["recipient"] == "Rahul"

    def test_fresh_command_during_compose_suspends_with_proper_state(self, dialog_mgr):
        dialog_mgr.set_lock(
            workflow_type="EMAIL_COMPOSE",
            required_slots=["recipient", "subject", "body", "send_confirm"],
            target_plugin="email",
            target_action="send",
            initial_slots={"recipient": "Rahul"},
            prompt_question="Subject kya hai?"
        )
        mock_core = MagicMock()
        handled, resp = dialog_mgr.process_locked_turn("Chrome kholo", mock_core)
        assert handled is False  # Passed through to routing
        assert dialog_mgr.active_lock is None
        assert dialog_mgr.suspended_lock is not None
        assert dialog_mgr.suspended_lock.state == WorkflowState.SUSPENDED
        assert dialog_mgr.suspended_lock.workflow_type == "EMAIL_COMPOSE"


class TestDeicticForegrounding:
    """Verifies 'Usko foreground mein lao' reference resolution and execution."""

    def test_reference_resolver_resolves_foreground_target(self):
        ctx = ActiveTargetContext()
        ctx.application = "spotify"
        resolved = ReferenceResolver.resolve("Usko foreground mein lao", active_context=ctx)
        assert resolved.resolved is True
        assert resolved.action == "foreground"
        assert resolved.target_name == "spotify"
        assert "Spotify foreground mein le aaya." in resolved.explanation

    def test_target_engine_executes_foreground_action(self):
        wm_mock = MagicMock()
        wm_mock.list_all_windows.return_value = []
        engine = UniversalTargetDiscoveryEngine(window_manager=wm_mock)

        with patch("core.universal_window_resolver.get_universal_window_resolver") as mock_resolver:
            mock_resolver.return_value.get_context_app.return_value = "spotify"
            outcome = engine.execute(TargetRequest(target="current", action="focus"))

        assert outcome.success is True
        assert "Spotify foreground mein le aaya." in outcome.message
        wm_mock.execute_operation.assert_called_with("focus", "spotify")
