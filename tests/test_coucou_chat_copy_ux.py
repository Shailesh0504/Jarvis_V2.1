# tests/test_coucou_chat_copy_ux.py
"""Tests for Coucou Native Text Selection, Multi-Message Drag, Ctrl+A, Ctrl+C, and Zero Copy UI."""

import pytest
from PySide6.QtCore import Qt, QKeyCombination, QUrl
from PySide6.QtGui import QTextCursor, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit

from gui.island.views import CoucouChatCard, CoucouMessageBubble, parse_markdown_code_blocks
from gui.island.chat_view import IslandChatView
from gui.views.chat_view import ChatView, LiveChatBrowser


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_markdown_code_block_parser():
    """Verify that markdown text is cleanly divided into text and code blocks."""
    raw_text = (
        "Here is a Python function:\n"
        "```python\n"
        "def add(a, b):\n"
        "    return a + b\n"
        "```\n"
        "Enjoy coding!"
    )
    segments = parse_markdown_code_blocks(raw_text)
    assert len(segments) == 3
    assert segments[0]["type"] == "text"
    assert segments[1]["type"] == "code"
    assert segments[1]["lang"] == "python"
    assert "def add(a, b):" in segments[1]["content"]


def test_coucou_message_bubble_zero_copy_buttons(qapp):
    """Verify CoucouMessageBubble has NO copy buttons or icons, and text is selectable."""
    user_bubble = CoucouMessageBubble(role="user", content="Open chrome browser")
    # Acceptance Requirement 15: No copy buttons or copy icons
    copy_btns = [b for b in user_bubble.findChildren(QPushButton) if "copy" in b.text().lower() or "📋" in b.text()]
    assert len(copy_btns) == 0

    assistant_bubble = CoucouMessageBubble(
        role="assistant",
        content="Here is code:\n```python\nprint('hello')\n```"
    )
    asst_copy_btns = [b for b in assistant_bubble.findChildren(QPushButton) if "copy" in b.text().lower() or "📋" in b.text()]
    assert len(asst_copy_btns) == 0


def test_mouse_partial_text_selection_and_native_ctrl_c(qapp):
    """Test #1, #2, #5: Verify user can select a partial word/sentence and copy natively."""
    card = CoucouChatCard()
    card.add_message("assistant", "Hello Shailesh! Kaise hain aap?")
    qapp.processEvents()

    doc = card.chat_display.document()
    found_cursor = doc.find("Kaise hain")
    assert not found_cursor.isNull()
    assert found_cursor.selectedText() == "Kaise hain"

    # Set selection on the document view
    card.chat_display.setTextCursor(found_cursor)
    assert card.chat_display.textCursor().hasSelection()
    assert card.chat_display.textCursor().selectedText() == "Kaise hain"

    # Native copy
    card.chat_display.copy()
    clipboard = QApplication.clipboard()
    assert clipboard.text() == "Kaise hain"

    # Test #8: Selection should not disappear after copy
    assert card.chat_display.textCursor().hasSelection()
    assert card.chat_display.textCursor().selectedText() == "Kaise hain"
    card.close()


def test_multi_message_continuous_text_selection(qapp):
    """Test #3, #7: Verify mouse selection can span across multiple chat messages continuously."""
    card = CoucouChatCard()
    card.add_message("user", "hi")
    card.add_message("assistant", "Hello Shailesh! Kaise hain aap?")
    card.add_message("user", "Mausam kaisa hai?")
    qapp.processEvents()

    doc = card.chat_display.document()
    c_start = doc.find("hi")
    c_end = doc.find("Kaise hain")
    assert not c_start.isNull()
    assert not c_end.isNull()

    # Span selection across user message + assistant response
    span_cursor = QTextCursor(doc)
    span_cursor.setPosition(c_start.selectionStart())
    span_cursor.setPosition(c_end.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)

    card.chat_display.setTextCursor(span_cursor)
    sel_text = card.chat_display.textCursor().selectedText()
    assert "hi" in sel_text
    assert "Hello Shailesh!" in sel_text
    assert "Kaise hain" in sel_text

    # Native copy across messages
    card.chat_display.copy()
    clipboard = QApplication.clipboard()
    copied = clipboard.text()
    assert "hi" in copied
    assert "Hello Shailesh!" in copied
    assert "Kaise hain" in copied
    card.close()


def test_ctrl_a_chat_selection_vs_input_field(qapp):
    """Test #4, #6: Verify Ctrl+A selects chat messages when in chat, but selects input when in input field."""
    card = CoucouChatCard()
    card.add_message("user", "hi")
    card.add_message("assistant", "Hello Shailesh! Kaise hain aap?")
    card.input_field.setText("Ask something new")
    card.show()
    qapp.processEvents()

    # Case A: Input field has focus -> Ctrl+A selects only input field text
    card.input_field.setFocus()
    assert card.input_field.hasFocus()
    key_event_ctrl_a = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    card.keyPressEvent(key_event_ctrl_a)
    assert card.input_field.selectedText() == "Ask something new"

    # Case B: Chat display has focus -> Ctrl+A selects chat messages
    card.chat_display.setFocus()
    assert card.chat_display.hasFocus()
    card.keyPressEvent(key_event_ctrl_a)
    chat_sel = card.chat_display.textCursor().selectedText()
    assert "hi" in chat_sel
    assert "Hello Shailesh!" in chat_sel
    # Input field text must NOT be in chat selection
    assert "Ask something new" not in chat_sel
    card.close()


def test_auto_scroll_safety_protects_active_selection(qapp):
    """Test #9, #12: Verify auto-scroll is safely suppressed when user has active text selection."""
    card = CoucouChatCard()
    card.resize(400, 200)
    card.show()
    qapp.processEvents()

    for i in range(10):
        card.add_message("user" if i % 2 == 0 else "assistant", f"Message line {i}")
    qapp.processEvents()

    # Select some text
    doc = card.chat_display.document()
    found = doc.find("Message line 2")
    assert not found.isNull()
    card.chat_display.setTextCursor(found)
    assert card.chat_display.textCursor().hasSelection()

    # Attempt scroll_to_bottom while selection is active
    card.scroll_to_bottom(force=True)
    qapp.processEvents()

    # Active selection must NOT be destroyed or moved
    assert card.chat_display.textCursor().hasSelection()
    assert card.chat_display.textCursor().selectedText() == "Message line 2"
    card.close()


def test_no_copy_buttons_or_anchors_in_html(qapp):
    """Test #15: Verify no copy buttons, links, or icons exist in HTML documents."""
    card = CoucouChatCard()
    card.add_message("user", "test query")
    card.add_message("assistant", "test response with ```python\ncode\n```")
    html_out = card.chat_display.toHtml()

    assert "copy-msg" not in html_out
    assert "copy-code" not in html_out
    assert "📋" not in html_out
    assert "Copy code" not in html_out
    assert "Copied!" not in html_out

    island_chat = IslandChatView()
    island_chat.add_message("User", "test query")
    island_chat.add_message("Jarvis", "test response with ```python\ncode\n```")
    island_html = island_chat.chat_display.toHtml()

    assert "copy-msg" not in island_html
    assert "copy-code" not in island_html
    assert "📋" not in island_html
    assert "Copy code" not in island_html
    assert "Copied!" not in island_html

    chat_view = ChatView()
    chat_view.add_message("You", "test query")
    chat_view.add_message("Jarvis", "test response with ```python\ncode\n```")
    chat_html = chat_view.chat_display.toHtml()

    assert "copy-msg" not in chat_html
    assert "copy-code" not in chat_html
    assert "📋" not in chat_html
    assert "Copy code" not in chat_html
    assert "Copied!" not in chat_html


def test_hindi_hinglish_unicode_selection_and_copy(qapp):
    """Test #10: Verify Hindi, Hinglish, and English unicode text is naturally selectable and copyable."""
    card = CoucouChatCard()
    hindi_msg = "नमस्ते Shailesh! आज दिल्ली का मौसम कैसा है? 28°C और धूप खिली है।"
    card.add_message("assistant", hindi_msg)
    qapp.processEvents()

    doc = card.chat_display.document()
    target_phrase = "आज दिल्ली का मौसम कैसा है?"
    found = doc.find(target_phrase)
    assert not found.isNull()
    assert found.selectedText() == target_phrase

    card.chat_display.setTextCursor(found)
    card.chat_display.copy()

    clipboard = QApplication.clipboard()
    assert clipboard.text() == target_phrase
    card.close()


def test_coucou_chat_card_auto_scroll_to_bottom(qapp):
    """Verify CoucouChatCard pins scroll to bottom when there is no active text selection."""
    card = CoucouChatCard()
    card.resize(400, 200)
    card.show()
    qapp.processEvents()

    for i in range(15):
        card.add_message("user" if i % 2 == 0 else "assistant", f"Auto scroll test message number {i}.")

    for _ in range(10):
        qapp.processEvents()

    vsb = card.chat_display.verticalScrollBar()
    assert vsb.maximum() > 0
    assert card.chat_display._auto_scroll_to_bottom is True
    assert vsb.value() == vsb.maximum()

    # User scrolls up manually
    vsb.setValue(0)
    card.chat_display._on_scroll_value_changed(0)
    assert card.chat_display._auto_scroll_to_bottom is False

    # New message re-engages auto scroll
    card.add_message("assistant", "Fresh incoming message.")
    for _ in range(10):
        qapp.processEvents()

    assert card.chat_display._auto_scroll_to_bottom is True
    assert vsb.value() == vsb.maximum()
    card.close()


def test_avatar_layout_and_zero_jarvis_label_in_selection(qapp):
    """Acceptance Tests #2, #3, #10, #11: Avatar has dedicated cell, no overlap, and 'JARVIS' is NOT in selectable text."""
    card = CoucouChatCard()
    card.add_message("assistant", "Hello Shailesh! Kaise hain aap?")
    qapp.processEvents()

    # Verify no 'JARVIS' text exists in the selectable plain text
    plain_text = card.chat_display.toPlainText().strip()
    assert "JARVIS" not in plain_text
    assert "Hello Shailesh! Kaise hain aap?" in plain_text

    # Verify document has registered avatar image resource
    doc = card.chat_display.document()
    avatar_img = doc.resource(doc.ResourceType.ImageResource, QUrl("jarvis://avatar.png"))
    assert avatar_img is not None

    # Verify full select and copy contains exact message text without 'JARVIS'
    card.chat_display.selectAll()
    card.chat_display.copy()
    clipboard_text = QApplication.clipboard().text()
    assert "JARVIS" not in clipboard_text
    assert clipboard_text == "Hello Shailesh! Kaise hain aap?"
    card.close()


def test_selection_preserved_when_new_message_arrives(qapp):
    """Acceptance Test #8: User text selection is preserved without destruction when a new message arrives."""
    card = CoucouChatCard()
    card.add_message("assistant", "Initial message text to select.")
    qapp.processEvents()

    # Select phrase
    doc = card.chat_display.document()
    found = doc.find("message text")
    assert not found.isNull()
    card.chat_display.setTextCursor(found)
    assert card.chat_display.textCursor().hasSelection()
    assert card.chat_display.textCursor().selectedText() == "message text"

    # New message arrives
    card.add_message("assistant", "A completely new message arrived in background.")
    qapp.processEvents()

    # Selection must still be active and exact
    assert card.chat_display.textCursor().hasSelection()
    assert card.chat_display.textCursor().selectedText() == "message text"
    card.close()


def test_island_character_bot_visible_in_chat_view(qapp):
    """
    Acceptance Tests #1, #2, #8: Mochi/JARVIS character remains visible and animated
    in chat view with dedicated layout space, never hidden or replaced with placeholder.
    """
    from gui.island.island import CoucouIslandWidget
    island = CoucouIslandWidget()
    island.show()
    island.set_mode("expanded")
    for _ in range(40):
        island._on_anim_tick()
        qapp.processEvents()
    island.set_view("overview")
    qapp.processEvents()
    assert island.character.isVisible() is True
    assert island.character.isHidden() is False

    # In chat view, Mochi character MUST remain visible and alive
    island.set_view("chat")
    for _ in range(10):
        island._on_anim_tick()
        qapp.processEvents()
    assert island._current_view == "chat"
    assert island.character.isVisible() is True
    assert island.character.isHidden() is False

    # Dedicated layout space: bot_spacer width is 64px, character width is ~56px
    assert island.view_chat.bot_spacer.width() >= 64
    assert abs(island.character.width() - 56) <= 2
    assert abs(island.character.height() - 56) <= 2

    # Test #8: Mochi continues responding to state animations in chat view
    island.set_system_state("listening")
    qapp.processEvents()
    assert island.character.current_state == "listening"

    island.set_system_state("thinking")
    qapp.processEvents()
    assert island.character.current_state == "thinking"

    island.set_system_state("speaking")
    qapp.processEvents()
    assert island.character.current_state == "speaking"

    island.set_system_state("working")
    qapp.processEvents()
    assert island.character.current_state == "working"

    island.set_system_state("idle")
    qapp.processEvents()
    assert island.character.current_state == "idle"

    # Switching back to overview preserves character
    island.set_view("overview")
    qapp.processEvents()
    assert island._current_view == "overview"
    assert island.character.isVisible() is True
    assert island.character.isHidden() is False
    island.close()

