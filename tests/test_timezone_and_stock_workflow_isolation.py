# tests/test_timezone_and_stock_workflow_isolation.py
"""
Unit and integration tests for TimezoneManager, Stock Workflow Isolation,
Action Verification, Window Recovery, and Conversational Resilience.
"""

import pytest
import datetime
from unittest.mock import MagicMock, patch
from core.timezone_manager import TimezoneManager, get_timezone_manager


class TestTimezoneManager:
    """Test suite for TimezoneManager singleton and resolution hierarchy."""

    def test_singleton_instance(self):
        tm1 = TimezoneManager.get_instance()
        tm2 = get_timezone_manager()
        assert tm1 is tm2

    def test_get_ist_timezone_offset(self):
        tm = TimezoneManager.get_instance()
        ist = tm.get_ist_timezone()
        assert ist is not None
        now_ist = datetime.datetime.now(ist)
        # Offset for IST should be +05:30 (19800 seconds)
        offset = now_ist.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 5.5 * 3600

    def test_fallback_when_zoneinfo_fails(self):
        tm = TimezoneManager.get_instance()
        with patch("zoneinfo.ZoneInfo", side_effect=Exception("No time zone found with key Asia/Kolkata")):
            # Clear cache to force resolution attempt
            with tm._lock:
                tm._cached_tz.pop("Asia/Kolkata", None)
            tz = tm.get_timezone("Asia/Kolkata")
            assert tz is not None
            now = datetime.datetime.now(tz)
            assert now.utcoffset().total_seconds() == 5.5 * 3600

    def test_to_timezone_conversion(self):
        tm = TimezoneManager.get_instance()
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        ist_now = tm.to_timezone(utc_now, "Asia/Kolkata")
        assert ist_now.tzinfo is not None
        assert ist_now.utcoffset().total_seconds() == 5.5 * 3600

    def test_startup_validation_does_not_crash(self):
        tm = TimezoneManager.get_instance()
        with patch("zoneinfo.ZoneInfo", side_effect=Exception("Simulated missing tzdata")):
            status = tm.validate_on_startup()
            assert status is True


class TestStockWorkflowRoutingAndIsolation:
    """Test stock selection workflow routing, verification, greetings, and failure isolation."""

    @pytest.fixture
    def jarvis_core(self):
        from core.app import JarvisCore
        core = JarvisCore("config.yaml")
        core.dialog_manager.release_lock()
        return core

    def test_routing_equivalence_suggest_and_select(self):
        """'stock suggest karo' and 'mujhe best stock select kar ke do' both route to equity research wizard."""
        from core.semantic.goal_resolver import UniversalGoalResolver
        res1 = UniversalGoalResolver.resolve("stock suggest karo")
        assert res1 is not None
        assert res1.intent == "EQUITY_RESEARCH"
        assert res1.parameters.get("open_wizard") is True

        res2 = UniversalGoalResolver.resolve("mujhe best stock select kar ke do")
        assert res2 is not None
        assert res2.intent == "EQUITY_RESEARCH"
        assert res2.parameters.get("open_wizard") is True

    def test_greetings_work_while_stock_workflow_locked(self, jarvis_core):
        """'hi' and 'hello' must return friendly greetings even when STOCK_SELECTION_WORKFLOW is locked."""
        jarvis_core.dialog_manager.set_lock(
            workflow_type="STOCK_SELECTION_WORKFLOW",
            required_slots=["horizon", "risk"],
            target_plugin="equity_research",
            target_action="research_shortlist",
            prompt_question="Prompt",
            language="hi"
        )
        assert jarvis_core.dialog_manager.has_active_lock()

        # 'hi' must be handled as a greeting without crashing or raising timezone errors
        resp_hi = jarvis_core.process_input("hi")
        assert any(greet in resp_hi.lower() for greet in ["hello", "namaste", "madad", "batao", "kaise", "haan"])
        assert "No time zone found" not in resp_hi
        assert "An error occurred" not in resp_hi

        # 'hello' must also be handled as a greeting
        resp_hello = jarvis_core.process_input("hello")
        assert any(greet in resp_hello.lower() for greet in ["hello", "namaste", "madad", "batao", "kaise", "haan"])
        assert "No time zone found" not in resp_hello

    def test_window_recovery_when_user_reports_not_open(self, jarvis_core):
        """'selection window open nahi hua' triggers recovery response rather than crash or misunderstanding."""
        jarvis_core.dialog_manager.set_lock(
            workflow_type="STOCK_SELECTION_WORKFLOW",
            required_slots=["horizon", "risk"],
            target_plugin="equity_research",
            target_action="research_shortlist",
            prompt_question="Prompt",
            language="hi"
        )

        with patch("webbrowser.open", return_value=True):
            resp = jarvis_core.process_input("selection window open nahi hua")
            assert "window" in resp.lower() or "dobara" in resp.lower() or "browser" in resp.lower() or "dashboard" in resp.lower()
            assert "No time zone found" not in resp

    def test_action_verification_claimed_success_when_verified(self, jarvis_core):
        """When stock window verification succeeds, Jarvis confirms window was opened."""
        jarvis_core.dialog_manager.release_lock()
        jarvis_core.execution_verifier.verify_browser_opened = MagicMock(return_value=MagicMock(verified=True))
        resp = jarvis_core.process_input("stock suggest karo")
        assert "Maine selection window open kar di hai" in resp

    def test_action_verification_honest_feedback_when_verification_fails(self, jarvis_core):
        """When stock window verification fails, Jarvis does not falsely claim the window was opened."""
        jarvis_core.dialog_manager.release_lock()
        jarvis_core.execution_verifier.verify_browser_opened = MagicMock(return_value=MagicMock(verified=False))
        resp = jarvis_core.process_input("stock suggest karo")
        assert "open nahi ho saki" in resp or "nahi khul" in resp
        assert "Maine selection window open kar di hai" not in resp

    def test_module_failure_isolation(self, jarvis_core):
        """Even if stock service throws an unexpected exception, process_input handles it cleanly."""
        jarvis_core.dialog_manager.set_lock(
            workflow_type="STOCK_SELECTION_WORKFLOW",
            required_slots=["horizon", "risk"],
            target_plugin="equity_research",
            target_action="research_shortlist",
            prompt_question="Prompt",
            language="hi"
        )

        with patch("stock.stock_service.StockService.get_instance", side_effect=RuntimeError("Simulated stock subsystem explosion")):
            # A slot turn inside stock workflow
            resp = jarvis_core.process_input("large cap")
            # Must fail gracefully and release lock
            assert "takneeki samasya" in resp or "reset" in resp
            assert not jarvis_core.dialog_manager.has_active_lock()

            # Subsequent basic commands must work immediately without lingering lock
            resp_after = jarvis_core.process_input("hi")
            assert "takneeki samasya" not in resp_after
            assert any(greet in resp_after.lower() for greet in ["hello", "namaste", "madad", "batao", "kaise", "haan"])
