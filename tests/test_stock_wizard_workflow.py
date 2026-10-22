# tests/test_stock_wizard_workflow.py
"""
End-to-end integration tests for Jarvis Stock Query Wizard and Conversation Workflow.
Verifies voice commands, wizard browser opening, workflow state locking,
slot parameter updates, follow-up conversation queries, and cancellation.
"""

from unittest.mock import patch
import pytest
from core.app import JarvisCore
from core.dialog_manager import DialogManager
from stock.stock_service import StockService


@pytest.fixture
def jarvis_core():
    """Builds a test JarvisCore instance and resets singletons."""
    from core.equity_research.manager import EquityResearchManager
    from stock.stock_service import StockService
    EquityResearchManager.get_instance()._profile.investment_amount = None
    EquityResearchManager.get_instance()._profile.risk_tolerance = None
    EquityResearchManager.get_instance()._profile.sector_preferences = []
    service = StockService.get_instance()
    service.current_state = "IDLE"
    service.active_params = {}
    service.last_shortlist = []
    service.last_response = None
    core = JarvisCore(config_path="config.yaml")
    if hasattr(core, "execution_verifier") and core.execution_verifier:
        from unittest.mock import MagicMock
        core.execution_verifier.verify_browser_opened = MagicMock(return_value=MagicMock(verified=True))
    return core


class TestStockWizardVoiceAndWorkflow:
    """Tests voice command triggers, browser opening, and active dialogue locking."""

    @patch("webbrowser.open")
    def test_voice_commands_trigger_wizard_open(self, mock_web_open, jarvis_core):
        """Validates all required voice triggers from Section 21."""
        test_phrases = [
            "mujhe koi stock suggest karo",
            "koi achha stock batao",
            "kaunsa stock buy kar sakta hoon?",
            "short term ke liye stock batao",
            "long term investment ke liye stock suggest karo",
            "mere liye stocks shortlist karo",
            "IT sector ke stocks batao",
            "large cap stock suggest karo",
            "moderate risk ke stocks dikhao",
        ]

        expected_spoken_ack = "Bilkul. Main stock selection ke liye kuch details chahunga. Maine selection window open kar di hai."

        for phrase in test_phrases:
            resp = jarvis_core.process_input(phrase, source="cli")
            assert resp == expected_spoken_ack, f"Failed voice response for query: {phrase}"
            assert mock_web_open.called, f"Browser was not opened for query: {phrase}"
            mock_web_open.reset_mock()

            # Verify DialogManager has active STOCK_SELECTION_WORKFLOW lock
            assert jarvis_core.dialog_manager.has_active_lock(), f"Lock not active for {phrase}"
            assert jarvis_core.dialog_manager.active_lock.workflow_type == "STOCK_SELECTION_WORKFLOW"

            # Clear lock for next iteration
            jarvis_core.dialog_manager.release_lock()

    @patch("webbrowser.open")
    def test_short_slot_utterances_update_active_workflow(self, mock_web_open, jarvis_core):
        """Verifies that short utterances during active workflow update parameters."""
        # Step 1: Open workflow
        resp1 = jarvis_core.process_input("mujhe koi stock suggest karo", source="cli")
        assert "selection window open" in resp1.lower()
        assert jarvis_core.dialog_manager.has_active_lock()

        # Step 2: "large cap"
        resp_mcap = jarvis_core.process_input("large cap", source="cli")
        assert "large cap set" in resp_mcap.lower()
        assert jarvis_core.dialog_manager.active_lock.filled_slots.get("market_cap") == ["large_cap"]

        # Step 3: "moderate"
        resp_risk = jarvis_core.process_input("moderate", source="cli")
        assert "moderate set" in resp_risk.lower()
        assert jarvis_core.dialog_manager.active_lock.filled_slots.get("risk") == "moderate"

        # Step 4: "3 months"
        resp_horiz = jarvis_core.process_input("3 months", source="cli")
        assert "3 mahine set" in resp_horiz.lower()
        assert jarvis_core.dialog_manager.active_lock.filled_slots.get("horizon") == "3_12_months"

        # Step 5: "₹1 lakh"
        resp_cap = jarvis_core.process_input("₹1 lakh", source="cli")
        assert "budget" in resp_cap.lower() and "100,000" in resp_cap
        assert jarvis_core.dialog_manager.active_lock.filled_slots.get("capital") == 100000.0

        # Step 6: "IT"
        resp_sec = jarvis_core.process_input("IT", source="cli")
        assert "it set" in resp_sec.lower()
        assert jarvis_core.dialog_manager.active_lock.filled_slots.get("sectors") == ["IT"]

        # Step 7: "analyze stocks"
        resp_analyze = jarvis_core.process_input("analyze stocks", source="cli")
        assert "selection complete hai" in resp_analyze.lower()

        # Cleanup
        jarvis_core.dialog_manager.release_lock()

    @patch("webbrowser.open")
    def test_followup_conversation_queries(self, mock_web_open, jarvis_core):
        """Tests Section 14 follow-up conversation queries."""
        # 1. Run initial analysis
        service = StockService.get_instance()
        service.initialize_workflow()
        service.analyze({
            "horizon": "3_12_months",
            "risk": "moderate",
            "capital": 200000.0,
            "objective": ["growth"],
            "market_cap": ["large_cap", "mid_cap"],
            "sectors": ["Any"],
        })

        # Set active lock
        jarvis_core.dialog_manager.set_lock(
            workflow_type="STOCK_SELECTION_WORKFLOW",
            required_slots=["horizon", "risk"],
        )

        # A. Technical setup follow-up
        resp_tech = jarvis_core.process_input("technical setup batao", source="cli")
        assert "technical setup" in resp_tech.lower() or "trend" in resp_tech.lower()

        # B. Risk inquiry follow-up
        resp_risk = jarvis_core.process_input("iske risks kya hain?", source="cli")
        assert "key risks" in resp_risk.lower() or "risk" in resp_risk.lower()

        # C. Sector filter follow-up
        resp_sec = jarvis_core.process_input("isme se IT wale dikhao", source="cli")
        assert "it sector" in resp_sec.lower() or "candidates" in resp_sec.lower()

        # D. Risk reduction follow-up
        resp_red = jarvis_core.process_input("risk kam karo", source="cli")
        assert "conservative set" in resp_red.lower()

        # E. Market cap follow-up
        resp_mcap = jarvis_core.process_input("sirf large cap", source="cli")
        assert "large cap" in resp_mcap.lower()

        # Cleanup
        jarvis_core.dialog_manager.release_lock()

    @patch("webbrowser.open")
    def test_workflow_cancellation(self, mock_web_open, jarvis_core):
        """Verifies cancellation releases the lock cleanly."""
        jarvis_core.process_input("mujhe koi stock suggest karo", source="cli")
        assert jarvis_core.dialog_manager.has_active_lock()

        resp_cancel = jarvis_core.process_input("cancel karo", source="cli")
        assert "cancel kar diya" in resp_cancel.lower()
        assert not jarvis_core.dialog_manager.has_active_lock()
