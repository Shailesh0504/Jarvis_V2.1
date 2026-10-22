# tests/test_context_aware_suggestion_chips.py
"""
Comprehensive test suite for Intelligent Context-Aware Suggestion Chips in Jarvis V2.1.
Validates:
1. Dynamic replacement of legacy static quick-command buttons.
2. Context-aware suggestions for active applications (Chrome, Excel, Explorer, VLC).
3. Conversation-aware suggestions (IT/RDP troubleshooting, Travel planning, Music desires).
4. Pending slot filling & confirmation lifecycle.
5. Post-action refresh & redundancy suppression (suppress already open apps/sites/volumes).
6. Zero-suggestion rule for pure factual Q&A / calculations / greetings.
7. Execution pipeline uniformity: chip click routes through standard semantic input pipeline.
8. Double-click duplicate execution protection and executing state feedback.
9. User correction awareness.
10. Unsupported capability suppression.
11. Unseen conversational test cases.
"""

from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication

from core.intelligence.models import SuggestionChip
from core.intelligence.suggestion_manager import SuggestionManager, get_suggestion_manager
from core.context import ActiveTargetContext
from core.dialog_manager import DialogManager, WorkflowLock
from gui.views.chat_view import ChatView


@pytest.fixture(scope="module")
def qapp():
    """Provides a persistent QApplication instance for headless Qt UI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def suggestion_manager():
    return SuggestionManager()


# =============================================================================
# 1. TEST MATRIX CASES: SUGGESTION MANAGER INTELLIGENCE
# =============================================================================

def test_1_static_chips_replaced_by_dynamic_suggestions(suggestion_manager):
    """Scenario 1: Default state generates dynamic context-driven chips, not static hardcoded 5."""
    chips = suggestion_manager.generate_contextual_chips()
    labels = [c.label for c in chips]
    # Ensure legacy static list is NOT returned verbatim
    legacy_static = ["Chrome kholo", "Volume 50 karo", "Screenshot lo", "Excel clean karo", "status"]
    assert labels != legacy_static


def test_2_chrome_active_context(suggestion_manager):
    """Scenario 2: When Chrome is active, suggest Chrome/browser actions and no Excel actions."""
    act_ctx = ActiveTargetContext(application="chrome")
    chips = suggestion_manager.generate_contextual_chips(active_context=act_ctx)
    labels = [c.label for c in chips]

    assert any("YouTube" in l or "Gmail" in l or "tab" in l.lower() for l in labels)
    # Must NOT show Excel actions
    assert not any("Formula" in l or "C2" in l or "Sheet" in l for l in labels)


def test_3_excel_active_context(suggestion_manager):
    """Scenario 3: When Excel is active, suggest Excel actions and no Chrome website actions."""
    act_ctx = ActiveTargetContext(application="excel")
    chips = suggestion_manager.generate_contextual_chips(active_context=act_ctx)
    labels = [c.label for c in chips]

    assert any("C2" in l or "Formula" in l or "Save" in l or "Excel" in l for l in labels)
    # Must NOT show Chrome actions
    assert not any("YouTube" in l or "Gmail" in l for l in labels)


def test_4_pending_question_slot_filling(suggestion_manager):
    """Scenario 4: When Jarvis asks a pending clarification question, chips fill the missing slot."""
    # A. Browser clarification
    chips_browser = suggestion_manager.generate_contextual_chips(
        last_assistant_response="Kaunsa browser open karun, Boss?"
    )
    labels_browser = [c.label for c in chips_browser]
    assert "Chrome" in labels_browser
    assert "Brave" in labels_browser

    # B. Song clarification
    chips_music = suggestion_manager.generate_contextual_chips(
        last_assistant_response="Kaunsa gaana play karna hai?"
    )
    labels_music = [c.label for c in chips_music]
    assert any("Hanuman Chalisa" in l or "Bhajan" in l or "Latest" in l for l in labels_music)

    # C. WorkflowLock candidate options
    dm = DialogManager()
    dm.active_lock = WorkflowLock(
        workflow_type="EXCEL_OPEN",
        required_slots=["file_target"],
        candidate_options=[{"name": "sales_q3.xlsx"}, {"name": "inventory.csv"}]
    )
    chips_lock = suggestion_manager.generate_contextual_chips(dialog_manager=dm)
    labels_lock = [c.label for c in chips_lock]
    assert "sales_q3.xlsx" in labels_lock
    assert "inventory.csv" in labels_lock


def test_5_confirmation_pending_chips(suggestion_manager):
    """Scenario 10: Confirmation-required action presents confirmation chips."""
    dm = DialogManager()
    dm.confirmation_manager.request_confirmation(
        action="system.shutdown",
        language="hi",
        parameters={},
        prompt="Kya aap system shutdown karna chahte hain?"
    )
    chips = suggestion_manager.generate_contextual_chips(dialog_manager=dm)
    labels = [c.label for c in chips]
    commands = [c.command for c in chips]

    assert "Haan, kar do" in labels
    assert "Nahi, cancel karo" in labels
    assert "haan" in commands
    assert "nahi" in commands


def test_6_redundant_suggestions_suppressed(suggestion_manager):
    """Scenario 6: Suppress redundant actions if already complete or active."""
    # A. Chrome already active -> do NOT suggest "Chrome kholo"
    act_ctx = ActiveTargetContext(application="chrome")
    chips = suggestion_manager.generate_contextual_chips(active_context=act_ctx)
    commands = [c.command.lower() for c in chips]
    labels = [c.label.lower() for c in chips]
    assert not any("open chrome" in cmd or "chrome kholo" in lbl for cmd, lbl in zip(commands, labels))

    # B. YouTube already open -> do NOT suggest "YouTube kholo"
    act_ctx_yt = ActiveTargetContext(application="chrome", website="youtube")
    chips_yt = suggestion_manager.generate_contextual_chips(active_context=act_ctx_yt)
    labels_yt = [c.label.lower() for c in chips_yt]
    assert not any("youtube kholo" in l for l in labels_yt)

    # C. Volume is already 50 in system state -> do NOT suggest volume 50
    chips_vol = suggestion_manager.generate_contextual_chips(
        active_context=act_ctx,
        system_state={"volume": 50}
    )
    commands_vol = [c.command.lower() for c in chips_vol]
    assert not any("volume 50" in cmd for cmd in commands_vol)


def test_7_conversation_aware_troubleshooting(suggestion_manager):
    """Scenario 7 & 8: IT Troubleshooting conversation produces relevant diagnostic chips."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="RDP connect nahi ho raha hai error aa raha hai",
        last_assistant_response="Network, DNS aur RDP service check kar sakte hain."
    )
    labels = [c.label for c in chips]
    assert "Network check" in labels
    assert "DNS check" in labels
    assert "RDP service check" in labels


def test_8_zero_suggestion_rule_for_static_factual_qa(suggestion_manager):
    """Scenario 8 & Section 10: Simple factual questions result in NO suggestions (empty list)."""
    # Capital of India
    chips_gk = suggestion_manager.generate_contextual_chips(
        last_user_input="India ki capital kya hai?",
        last_assistant_response="Bharat ki rajdhani New Delhi hai."
    )
    assert chips_gk == []

    # Simple math calculation
    chips_calc = suggestion_manager.generate_contextual_chips(
        last_user_input="5 * 12 kitna hota hai?",
        last_assistant_response="60 hota hai."
    )
    assert chips_calc == []

    # Casual greeting
    chips_greet = suggestion_manager.generate_contextual_chips(
        last_user_input="Hello Jarvis kaise ho?",
        last_assistant_response="Main badhiya hoon, Boss!"
    )
    assert chips_greet == []


def test_9_travel_planning_conversation(suggestion_manager):
    """Scenario: Travel planning produces travel-related chips."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Mujhe Mumbai jana hai",
        last_assistant_response="Mumbai ke liye flight, train aur road routes available hain."
    )
    labels = [c.label for c in chips]
    assert "Route options" in labels
    assert "Train options" in labels
    assert "Flight options" in labels


def test_10_music_desire_conversation(suggestion_manager):
    """Scenario: Music desire produces music-related chips."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Gaana sunne ka mann hai",
        last_assistant_response="Kaunsa gaana sunna pasand karenge?"
    )
    labels = [c.label for c in chips]
    assert any("Arijit Singh" in l or "Hanuman Chalisa" in l or "Latest" in l for l in labels)


def test_11_user_correction_handling(suggestion_manager):
    """Scenario 13: User correction adapts suggestions to new entity/goal."""
    # User originally asked for YouTube, then corrected to Gmail
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Nahi, Gmail kholo",
        last_assistant_response="Opening Gmail."
    )
    # Suggestions should be Chrome/browser actions without redundant Gmail
    labels = [c.label for c in chips]
    assert not any("Gmail kholo" == l for l in labels)


def test_12_unsupported_capability_suppression(suggestion_manager):
    """Scenario 12: Unsupported or dangerous operations are never suggested."""
    with patch("core.capabilities.CapabilityRegistry.is_unsupported_operation", return_value=(True, "Refusal")):
        act_ctx = ActiveTargetContext(application="chrome")
        chips = suggestion_manager.generate_contextual_chips(active_context=act_ctx)
        assert chips == []


# =============================================================================
# 2. TEST MATRIX CASES: GUI VIEW & EXECUTION PIPELINE
# =============================================================================

def test_13_gui_same_execution_pipeline(qapp):
    """Scenario 9: Chip click routes through exact same message_submitted pipeline."""
    mock_core = MagicMock()
    chat_view = ChatView(mock_core)

    submitted_messages = []
    chat_view.message_submitted.connect(lambda msg: submitted_messages.append(msg))

    chip = SuggestionChip(
        label="YouTube kholo",
        command="open youtube",
        target="youtube"
    )
    chat_view.set_suggestion_chips([chip])

    # Click the generated chip button
    assert len(chat_view._active_chip_buttons) == 1
    chip_btn = chat_view._active_chip_buttons[0]
    chip_btn.click()

    # Verify standard message submission
    assert len(submitted_messages) == 1
    assert submitted_messages[0] == "open youtube"


def test_14_gui_double_click_duplicate_guard(qapp):
    """Scenario 11 & Section 18: Rapid successive clicks on a chip execute only once."""
    mock_core = MagicMock()
    chat_view = ChatView(mock_core)

    submitted_messages = []
    chat_view.message_submitted.connect(lambda msg: submitted_messages.append(msg))

    chip = SuggestionChip(label="New tab", command="open new tab", target="chrome")
    chat_view.set_suggestion_chips([chip])

    chip_btn = chat_view._active_chip_buttons[0]

    # First click
    chip_btn.click()
    assert chip_btn.text() == "⏳ Executing..."
    assert not chip_btn.isEnabled()

    # Second click while executing
    chip_btn.click()

    # Must execute exactly once
    assert len(submitted_messages) == 1
    assert submitted_messages[0] == "open new tab"


def test_15_gui_empty_chips_collapses_container(qapp):
    """Section 10: When no suggestions exist, chips container collapses gracefully."""
    mock_core = MagicMock()
    chat_view = ChatView(mock_core)

    # Populate with chips
    chat_view.set_suggestion_chips([SuggestionChip(label="Test", command="test")])
    assert not chat_view.chips_container.isHidden()

    # Clear with empty list
    chat_view.set_suggestion_chips([])
    assert chat_view.chips_container.isHidden()


# =============================================================================
# 3. UNSEEN CONVERSATION TESTS (SECTION 25)
# =============================================================================

def test_16_unseen_browser_desire(suggestion_manager):
    """Unseen conversation: 'Yaar browser mein kuch dekhna hai' -> browser-related actions."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Yaar browser mein kuch dekhna hai",
        last_assistant_response="Browser open kar sakte hain, kya dekhna pasand karenge?"
    )
    labels = [c.label for c in chips]
    assert any("YouTube" in l or "tab" in l.lower() for l in labels)


def test_17_unseen_excel_report_work(suggestion_manager):
    """Unseen conversation: 'Abhi Excel khol rakha hai, report banana hai' -> Excel actions."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Abhi Excel khol rakha hai, report banana hai",
        last_assistant_response="Haan Boss, data enter ya formula calculate kar sakte hain."
    )
    labels = [c.label for c in chips]
    assert any("Formula" in l or "C2" in l or "Save" in l for l in labels)


def test_18_unseen_system_cleanup_request(suggestion_manager):
    """Unseen conversation: 'Mujhe system ka basic cleanup karna hai' -> supported cleanup actions."""
    chips = suggestion_manager.generate_contextual_chips(
        last_user_input="Mujhe system ka basic cleanup karna hai",
        last_assistant_response="Main recycle bin empty kar sakta hoon aur temp files check kar sakta hoon."
    )
    labels = [c.label for c in chips]
    assert "Recycle bin empty karo" in labels
    assert "Temp files check karo" in labels
    assert "RAM usage check karo" in labels
