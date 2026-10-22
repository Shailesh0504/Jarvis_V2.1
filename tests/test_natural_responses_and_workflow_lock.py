# tests/test_natural_responses_and_workflow_lock.py
"""
Unit and Integration Tests for Natural Response Generation & Active Workflow Lock.
Validates:
1. Natural Response Synthesis: non-robotic, rotated variations, English vs Hinglish mirroring.
2. Windows Application Registry: Store vs. Storage isolation, core Windows 11 apps.
3. Structured Entity Resolution: password length extraction, browser containers.
4. Active Multi-Turn Workflow Lock: slot filling ("12." -> password generation) and cancellation.
"""

import pytest
from unittest.mock import MagicMock

from core.app import JarvisCore
from core.natural_responses import NaturalResponseSynthesizer
from core.semantic.parsers.security import parse_password_generation, generate_secure_password
from core.windows_app_resolver import WindowsAppResolver
from core.dialog_manager import DialogManager


class TestNaturalResponseSynthesizer:
    """Validates natural response generation without robotic templates."""

    def test_open_app_variations_and_non_robotic(self):
        r1 = NaturalResponseSynthesizer.open_app("Chrome", language="hi")
        r2 = NaturalResponseSynthesizer.open_app("Chrome", language="hi")
        r3 = NaturalResponseSynthesizer.open_app("Chrome", language="hi")

        for r in [r1, r2, r3]:
            # No robotic templates
            assert "successfully" not in r.lower()
            assert "operation completed" not in r.lower()
            assert "target application" not in r.lower()
            assert "chrome" in r.lower()

        # Should rotate through variations
        results = {r1, r2, r3}
        assert len(results) >= 2, "Expected rotation across repeated calls"

    def test_language_mirroring_open_app(self):
        hi_resp = NaturalResponseSynthesizer.open_app("Excel", language="hi")
        en_resp = NaturalResponseSynthesizer.open_app("Excel", language="en")

        assert any(w in hi_resp.lower() for w in ["khol diya", "open ho gaya", "open kar diya"])
        assert any(w in en_resp.lower() for w in ["opened excel", "excel is open"])

    def test_open_website_with_container(self):
        resp = NaturalResponseSynthesizer.open_website("YouTube", container="Chrome", language="hi")
        assert "youtube" in resp.lower()
        assert "chrome" in resp.lower()
        assert any(w in resp.lower() for w in ["mein khol raha hoon", "mein open kar diya"])

    def test_toggle_device_bluetooth(self):
        off_resp = NaturalResponseSynthesizer.toggle_device("Bluetooth", state=False, language="hi")
        on_resp = NaturalResponseSynthesizer.toggle_device("Bluetooth", state=True, language="hi")

        assert "Bluetooth" in off_resp
        assert any(w in off_resp.lower() for w in ["off kar diya", "band kar diya"])
        assert any(w in on_resp.lower() for w in ["on kar diya", "chalu kar diya"])

        en_off = NaturalResponseSynthesizer.toggle_device("Bluetooth", state=False, language="en")
        assert "turned off" in en_off.lower() or "disabled" in en_off.lower()

    def test_multi_entity_browsers(self):
        resp = NaturalResponseSynthesizer.multi_entity_result(
            action="open",
            succeeded=["Chrome", "Brave"],
            failed=[],
            language="hi"
        )
        assert resp == "Ji, dono browsers open kar diye." or "dono browsers" in resp.lower()


class TestWindowsAppStoreResolution:
    """Verifies Windows 11 20 core apps and strict store vs storage isolation."""

    def test_store_alias_resolves_to_microsoft_store(self):
        resolver = WindowsAppResolver.get_instance()
        match = resolver.resolve_app("store")
        assert match is not None
        assert match.canonical_id == "store"
        assert match.display_name == "Microsoft Store"

    def test_microsoft_store_phrase_resolves_correctly(self):
        resolver = WindowsAppResolver.get_instance()
        match = resolver.resolve_app("microsoft store")
        assert match is not None
        assert match.canonical_id == "store"

    def test_storage_does_not_resolve_to_store_or_prompt_storage(self):
        resolver = WindowsAppResolver.get_instance()
        match = resolver.resolve_app("storage")
        # 'storage' must NOT resolve to Microsoft Store
        if match:
            assert match.canonical_id != "store"


class TestSecurityAndEntityParsing:
    """Verifies structured entity parsing for security and passwords."""

    def test_parse_password_with_explicit_length(self):
        act = parse_password_generation("8 digit password generate karo", "8 digit password generate karo")
        assert act is not None
        assert act.intent == "GENERATE_PASSWORD"
        assert act.parameters["length"] == 8
        assert act.needs_clarification is False

        act_en = parse_password_generation("generate a 16 character password", "generate a 16 character password")
        assert act_en is not None
        assert act_en.parameters["length"] == 16
        assert act_en.needs_clarification is False

    def test_parse_password_bare_requires_clarification(self):
        act = parse_password_generation("ek password generate karo", "ek password generate karo")
        assert act is not None
        assert act.intent == "GENERATE_PASSWORD"
        assert act.needs_clarification is True
        assert act.missing_slot == "length"
        assert "Kitne characters ka?" in act.clarification_prompt

    def test_generate_secure_password(self):
        pwd = generate_secure_password(14)
        assert len(pwd) == 14
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)
        assert any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pwd)


class TestDialogManagerWorkflowLock:
    """Verifies active multi-turn workflow lock lifecycle."""

    def test_workflow_lock_slot_filling_numeric(self):
        dm = DialogManager()
        dm.set_lock(
            workflow_type="PASSWORD_GENERATE",
            required_slots=["length"],
            prompt_question="Kitne characters ka?",
            language="hi"
        )
        assert dm.has_active_lock() is True

        # Follow up input: "12."
        mock_core = MagicMock()
        handled, resp = dm.process_locked_turn("12.", mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert "12" in resp
        assert "clipboard" in resp.lower()

    def test_workflow_lock_cancellation(self):
        dm = DialogManager()
        dm.set_lock(
            workflow_type="PASSWORD_GENERATE",
            required_slots=["length"],
            prompt_question="Kitne characters ka?",
            language="hi"
        )
        assert dm.has_active_lock() is True

        # User says cancel
        mock_core = MagicMock()
        handled, resp = dm.process_locked_turn("cancel", mock_core)
        assert handled is True
        assert dm.has_active_lock() is False
        assert any(w in resp.lower() for w in ["cancel", "radd", "chhod"])


class TestEndToEndCoreWorkflowLock:
    """Integration test verifying JarvisCore end-to-end multi-turn interaction."""

    @pytest.fixture
    def core(self):
        return JarvisCore()

    def test_e2e_password_generation_workflow(self, core):
        # Turn 1: User asks for a password without length
        resp1 = core.process_input("Ek password generate karo.")
        assert "Kitne characters ka?" in resp1
        assert core.dialog_manager.has_active_lock() is True

        # Turn 2: User specifies length "12."
        resp2 = core.process_input("12.")
        assert core.dialog_manager.has_active_lock() is False
        assert "12" in resp2
        assert any(w in resp2.lower() for w in ["clipboard", "copy"])
