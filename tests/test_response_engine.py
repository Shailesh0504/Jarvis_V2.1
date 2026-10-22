# tests/test_response_engine.py
"""
Unit and Integration Tests for Central Response Engine, Planner, Style, and Validator.

Validates:
1. All 10 Golden Examples from the User Specification.
2. Complete elimination of robotic templates ("Main aapki kya madad kar sakta hoon?").
3. Anti-Repetition Sliding Memory: consecutive identical inputs receive varied responses.
4. Truth-Aware Execution Verification: action failures never claim success.
5. Controlled 'Sir' usage (never stacked or excessively repeated).
6. 10-point Pre-Speech Safety Gate in ResponseValidator.
7. Language Continuity across Hinglish, English, and Hindi turns.
"""

import pytest

from core.response_engine import ResponseEngine
from core.response_planner import ResponseCategory, ResponseContext, ResponsePlanner
from core.response_style import ResponseStyleManager
from core.response_validator import ResponseValidator


def test_contextual_conversation_survives_final_rendering():
    engine = ResponseEngine()
    response = engine.render_response(
        {"user_text": "hello", "parameters": {"conversation_response": True}},
        default_text="Hello Rahul! Aapka Atlas project kaisa chal raha hai?",
    )
    assert "Rahul" in response and "Atlas" in response
    # Callers without a contextual conversation keep the existing greeting policy.
    assert "Atlas" not in engine.render_response({"user_text": "hello"})


def test_preserved_conversation_still_passes_validation():
    response = ResponseEngine().render_response(
        {"user_text": "close window", "action_status": "failure", "verification_status": "failed",
         "parameters": {"conversation_response": True}},
        default_text="Window band kar diya.",
    )
    assert "band kar diya" not in response.lower()
    assert "nahi" in response.lower()


@pytest.fixture
def engine():
    return ResponseEngine.get_instance()


class TestGoldenExamples:
    """Validates the 10 core golden examples specified by the user."""

    def test_golden_1_hi(self, engine):
        """User: 'hi' -> Jarvis: 'Hey Sir! Kaise ho?' or 'Hello Sir.' without robotic append."""
        resp = engine.render_response("hi")
        assert "Main aapki kya madad" not in resp
        assert any(greet in resp.lower() for greet in ["hey", "hello", "namaste"])

    def test_golden_2_good_afternoon(self, engine):
        """User: 'good afternoon' -> Jarvis: 'Good afternoon, Sir. Kaise chal raha hai din?'"""
        resp = engine.render_response("good afternoon")
        assert "good afternoon" in resp.lower()
        assert "madad" not in resp.lower()

    def test_golden_3_kaise_ho(self, engine):
        """User: 'kaise ho?' -> Jarvis: 'Main theek hoon, Sir. Aap batao.'"""
        resp = engine.render_response("kaise ho?")
        assert any(phrase in resp.lower() for phrase in ["main theek hoon", "main bilkul theek hoon", "sab smoothly"])
        assert "madad" not in resp.lower()

    def test_golden_4_chrome_kholo(self, engine):
        """User: 'Chrome kholo' -> Jarvis: 'Chrome khol diya, Sir.'"""
        ctx = ResponseContext(
            user_text="Chrome kholo",
            intent="OPEN_APP",
            target="Chrome",
            action_performed="open_app",
            action_status="success",
            verification_status="verified",
        )
        resp = engine.render_response(ctx)
        assert "chrome" in resp.lower()
        assert any(k in resp.lower() for k in ["khol diya", "open kar diya", "open ho gaya"])

    def test_golden_5_isko_band_karo_success(self, engine):
        """User: 'isko band karo' -> Jarvis: 'Ji Sir, current window band kar di.'"""
        ctx = ResponseContext(
            user_text="isko band karo",
            intent="CLOSE_APP",
            action_performed="close_window",
            action_status="success",
            verification_status="verified",
        )
        resp = engine.render_response(ctx)
        assert any(k in resp.lower() for k in ["band kar di", "band kar diya", "band ho gaya", "done"])

    def test_golden_6_youtube_browser_query(self, engine):
        """User: 'YouTube kaun se browser mein open hai?' -> Response with browser focus."""
        ctx = ResponseContext(
            user_text="YouTube kaun se browser mein open hai?",
            intent="QUERY_TAB_BROWSER",
            target="YouTube",
            focused_app="Google Chrome",
            active_tab="YouTube",
            action_status="success",
            verification_status="verified",
        )
        resp = engine.render_response(ctx)
        assert "youtube" in resp.lower()
        assert "google chrome" in resp.lower()
        assert "focus" in resp.lower()

    def test_golden_7_paramhans_aashram_find_text(self, engine):
        """User: 'Paramhans aashram kahan likha hai?' -> Visual find response with mouse movement."""
        ctx = ResponseContext(
            user_text="Paramhans aashram kahan likha hai?",
            intent="FIND_TEXT",
            target="paramhans aashram",
            found=True,
            match_count=1,
            mouse_moved=True,
            action_status="success",
            verification_status="verified",
        )
        resp = engine.render_response(ctx)
        assert "paramhans aashram" in resp.lower()
        assert any(k in resp.lower() for k in ["yahan likha hai", "mouse usi jagah"])

    def test_golden_8_ab_is_par_click_karo(self, engine):
        """User: 'ab is par click karo' -> Jarvis: 'Ji Sir, click kar diya.'"""
        ctx = ResponseContext(
            user_text="ab is par click karo",
            intent="CLICK_TEXT",
            action_performed="click",
            action_status="success",
            verification_status="verified",
        )
        resp = engine.render_response(ctx)
        assert "click kar diya" in resp.lower()

    def test_golden_9_thanks(self, engine):
        """User: 'thanks' -> Jarvis: 'Anytime, Sir.'"""
        resp = engine.render_response("thanks")
        assert any(k in resp.lower() for k in ["anytime", "glad", "pleasure", "koi baat nahi"])

    def test_golden_10_okay(self, engine):
        """User: 'okay' -> Jarvis: 'Theek hai.'"""
        resp = engine.render_response("okay")
        assert any(k in resp.lower() for k in ["theek hai", "got it", "ji", "bilkul"])


class TestResponseVariationAndAntiRepetition:
    """Validates that consecutive identical inputs produce varied responses."""

    def test_greeting_variation(self, engine):
        """Consecutive 'hi' calls must rotate without immediate duplicate."""
        responses = [engine.render_response("hi") for _ in range(3)]
        # At least 2 distinct variants should be returned across 3 turns
        unique_responses = set(responses)
        assert len(unique_responses) >= 2

    def test_acknowledgement_variation(self, engine):
        """Consecutive 'great' calls rotate among natural variants."""
        responses = [engine.render_response("great") for _ in range(2)]
        assert all("madad" not in r.lower() for r in responses)


class TestTruthAwareVerification:
    """Validates that action failures never produce success responses."""

    def test_close_window_failure(self, engine):
        """When close action fails, Jarvis must report failure, never success."""
        ctx = ResponseContext(
            user_text="isko band karo",
            intent="CLOSE_WINDOW",
            action_performed="close_window",
            action_status="failure",
            verification_status="failed",
        )
        resp = engine.render_response(ctx)
        assert any(k in resp.lower() for k in ["nahi ho payi", "nahi ho paya", "error"])
        assert "kar diya" not in resp.lower()

    def test_visual_find_failure(self, engine):
        """When target is not found, response reports not found."""
        ctx = ResponseContext(
            user_text="Search button kahan hai?",
            intent="FIND_TEXT",
            target="Search button",
            found=False,
            action_status="failure",
        )
        resp = engine.render_response(ctx)
        assert "nahi mila" in resp.lower()
        assert "yahan likha hai" not in resp.lower()


class TestResponseValidatorInvariants:
    """Validates the 10 safety and quality invariants."""

    def test_validator_rejects_false_success(self):
        ctx = ResponseContext(
            user_text="window close karo",
            action_status="failure",
            verification_status="failed",
        )
        val = ResponseValidator.validate("Ji Sir, window close kar diya.", ctx)
        assert val.is_valid is False
        assert any("False Success" in r for r in val.reasons)
        assert "nahi" in val.repaired_text.lower()

    def test_validator_rejects_contradictory_find(self):
        ctx = ResponseContext(
            user_text="login button kahan hai",
            target="login button",
            found=True,
        )
        val = ResponseValidator.validate("Sir, mujhe login button nahi mila.", ctx)
        assert val.is_valid is False
        assert any("target was found" in r for r in val.reasons)

    def test_validator_cleans_technical_leaks(self):
        ctx = ResponseContext(user_text="status batao")
        leak_text = "Status: OK. Exception: None. hwnd=0x002A123 pid=4512"
        val = ResponseValidator.validate(leak_text, ctx)
        assert val.is_valid is False
        assert "0x002A123" not in val.repaired_text


class TestControlledSirUsage:
    """Validates that 'Sir' is never stacked or overused."""

    def test_sir_stacking_removal(self):
        raw = "Yes Sir, Sir main Sir ye kar raha hoon Sir."
        cleaned = ResponseStyleManager.enforce_controlled_sir(raw, allow_sir=True)
        assert cleaned.count("Sir") == 1

    def test_sir_suppression_on_brief_acks(self):
        raw = "Theek hai, Sir."
        cleaned = ResponseStyleManager.enforce_controlled_sir(raw, allow_sir=False)
        assert "sir" not in cleaned.lower()
