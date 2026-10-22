# gui/island/chat_view.py
"""Compact Conversational Chat Surface for JARVIS Island with Coucou Simplicity and ChatGPT-style Copy UX.

Features:
- Dynamic conversation area with compact bubbles (user right-aligned, JARVIS left-aligned)
- Markdown fenced code blocks formatted with ChatGPT-style top bars and 'Copy code' buttons
- Message-level ChatGPT-style 'Copy' action with audio feedback and instant status
- Clean input bar: 'Ask JARVIS…' with typing, mic toggle, send button, and file attachment
- Auto-scroll and clear conversation support
- Expands gracefully without dominating screen space
"""

import html
import re
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import (
    QColor, QFont, QPainter, QLinearGradient, QPixmap, QTextDocument,
    QDesktopServices, QTextCursor, QKeySequence
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTextBrowser, QVBoxLayout, QWidget
)


def parse_markdown_code_blocks(text: str) -> List[dict]:
    """
    Parses conversational text into sequential markdown text and fenced code blocks.
    Returns list of dicts: {"type": "text"|"code", "lang": str, "content": str}
    """
    pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\r?\n?(.*?)```", re.DOTALL)
    segments = []
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            pre_text = text[last_idx:start]
            if pre_text:
                segments.append({"type": "text", "lang": "", "content": pre_text})
        lang = match.group(1).strip() or "code"
        code_content = match.group(2)
        segments.append({"type": "code", "lang": lang, "content": code_content})
        last_idx = end

    if last_idx < len(text):
        post_text = text[last_idx:]
        if post_text:
            segments.append({"type": "text", "lang": "", "content": post_text})

    if not segments:
        segments.append({"type": "text", "lang": "", "content": text})

    return segments


class IslandChatView(QWidget):
    """Compact contextual chat view for JARVIS Island."""

    message_submitted = Signal(str)
    voice_toggle_requested = Signal()
    file_attach_requested = Signal()
    clear_requested = Signal()

    def __init__(self, core=None, parent=None):
        super().__init__(parent)
        self.core = core
        self._raw_messages: List[str] = []
        self._raw_code_blocks: List[str] = []
        self._auto_scroll_to_bottom = True
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Chat Log Viewer
        self.chat_display = QTextBrowser()
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.anchorClicked.connect(self._on_anchor_clicked)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #0e0f11;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 10px;
                color: #f5f6f8;
                font-size: 12px;
                line-height: 1.4;
            }
            QScrollBar:vertical {
                background: #090a0d;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1d1f23;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2a2d33;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        vsb = self.chat_display.verticalScrollBar()
        vsb.rangeChanged.connect(self._on_scroll_range_changed)
        vsb.valueChanged.connect(self._on_scroll_value_changed)

        # Register high-DPI 20x20 round avatar pixmap (cyan gradient with 'J') as in-memory document resource
        avatar_pix = QPixmap(20, 20)
        avatar_pix.fill(Qt.transparent)
        painter = QPainter(avatar_pix)
        painter.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 20, 20)
        grad.setColorAt(0, QColor("#22d3ee"))
        grad.setColorAt(1, QColor("#0369a1"))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 20, 20)
        painter.setPen(QColor("#06121a"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(0, 0, 20, 20, Qt.AlignCenter, "J")
        painter.end()
        self.chat_display.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl("jarvis://avatar.png"), avatar_pix)

        layout.addWidget(self.chat_display, stretch=1)

        # Bottom Input Bar
        bar = QHBoxLayout()
        bar.setSpacing(6)

        # File Attachment Button
        self.attach_btn = QPushButton("📎")
        self.attach_btn.setToolTip("Attach file for JARVIS")
        self.attach_btn.setFixedSize(32, 32)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #141518;
                color: #9398a1;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d1f23;
                color: #f5f6f8;
                border-color: #22d3ee;
            }
        """)
        self.attach_btn.clicked.connect(self.file_attach_requested.emit)
        bar.addWidget(self.attach_btn)

        # Mic Toggle Button
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setToolTip("Toggle Voice Input")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #141518;
                color: #22d3ee;
                border: 1px solid rgba(34, 211, 238, 0.3);
                border-radius: 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(34, 211, 238, 0.15);
            }
        """)
        self.mic_btn.clicked.connect(self.voice_toggle_requested.emit)
        bar.addWidget(self.mic_btn)

        # Text Input Field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask JARVIS…")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #141518;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #22d3ee;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send)
        bar.addWidget(self.input_field, stretch=1)

        # Send Button
        self.send_btn = QPushButton("↑")
        self.send_btn.setToolTip("Send")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #f5f6f8;
                color: #0b0c0e;
                border: none;
                border-radius: 16px;
                font-size: 15px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #22d3ee;
                color: #000000;
            }
        """)
        self.send_btn.clicked.connect(self._on_send)
        bar.addWidget(self.send_btn)

        layout.addLayout(bar)

    def _on_anchor_clicked(self, url: QUrl):
        """Dispatches ChatGPT-style copy link clicks for messages and code snippets."""
        scheme = url.scheme()
        url_str = url.toString() if hasattr(url, "toString") else str(url)
        if scheme in ("copy-msg", "copy_msg") or url_str.startswith(("copy-msg:", "copy_msg:")):
            try:
                val_str = url.path() if url.path() else url_str.split(":", 1)[1]
                idx = int(val_str)
                if 0 <= idx < len(self._raw_messages):
                    self._copy_to_clipboard(self._raw_messages[idx])
            except Exception:
                pass
        elif scheme in ("copy-code", "copy_code") or url_str.startswith(("copy-code:", "copy_code:")):
            try:
                val_str = url.path() if url.path() else url_str.split(":", 1)[1]
                idx = int(val_str)
                if 0 <= idx < len(self._raw_code_blocks):
                    self._copy_to_clipboard(self._raw_code_blocks[idx])
            except Exception:
                pass
        elif scheme in ("http", "https") or url_str.startswith(("http://", "https://")):
            QDesktopServices.openUrl(url)

    def _copy_to_clipboard(self, text: str):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)
        try:
            from gui.sound_effects import Sound
            Sound.play("pop")
        except Exception:
            pass

    def keyPressEvent(self, event):
        """Dispatches Ctrl+A to input field if input has focus; otherwise selects chat conversation."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if self.input_field.hasFocus():
                self.input_field.selectAll()
            else:
                self.chat_display.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_scroll_range_changed(self, min_val: int, max_val: int):
        if self._auto_scroll_to_bottom and not self.chat_display.textCursor().hasSelection():
            self.chat_display.verticalScrollBar().setValue(max_val)

    def _on_scroll_value_changed(self, value: int):
        if self.chat_display.textCursor().hasSelection():
            self._auto_scroll_to_bottom = False
            return
        vsb = self.chat_display.verticalScrollBar()
        if vsb.maximum() - value <= 50:
            self._auto_scroll_to_bottom = True
        else:
            self._auto_scroll_to_bottom = False

    def scroll_to_bottom(self, force: bool = True):
        # Auto-scroll safety: preserve active user text selection without interruption
        if self.chat_display.textCursor().hasSelection():
            return
        if force:
            self._auto_scroll_to_bottom = True
        vsb = self.chat_display.verticalScrollBar()
        vsb.setValue(vsb.maximum())
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
        QTimer.singleShot(10, self._deferred_scroll_to_bottom)
        QTimer.singleShot(60, self._deferred_scroll_to_bottom)
        QTimer.singleShot(180, self._deferred_scroll_to_bottom)

    def _deferred_scroll_to_bottom(self):
        if self._auto_scroll_to_bottom and not self.chat_display.textCursor().hasSelection():
            vsb = self.chat_display.verticalScrollBar()
            vsb.setValue(vsb.maximum())
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.chat_display.setTextCursor(cursor)
            self.chat_display.ensureCursorVisible()

    def showEvent(self, event):
        super().showEvent(event)
        self.scroll_to_bottom(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_scroll_to_bottom:
            self.scroll_to_bottom(force=False)

    def _on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.add_message("User", text)
        self.message_submitted.emit(text)
        self.scroll_to_bottom(force=True)

    def _handle_send(self):
        self._on_send()

    def _on_submit(self):
        self._on_send()

    def add_message(self, sender: str, text: str) -> None:
        """Appends formatted message bubble into conversation log with Coucou style & zero copy buttons."""
        is_user = sender.lower() in ("user", "you")

        self._raw_messages.append(text)

        if is_user:
            escaped_body = (
                html.escape(text)
                .replace("\n", "<br/>")
            )
            html_line = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 8px;">
              <tr>
                <td align="right">
                  <table cellpadding="7" cellspacing="0" border="0" style="background-color: #1e2025; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px;">
                    <tr>
                      <td style="color: #f5f6f8; font-size: 11.5px; font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.45;">
                        {escaped_body}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """
        else:
            segments = parse_markdown_code_blocks(text)
            body_parts = []
            for seg in segments:
                if seg["type"] == "text":
                    t = seg["content"]
                    if t.strip():
                        t_esc = html.escape(t).replace("\n", "<br/>")
                        body_parts.append(f'<div style="color: #f5f6f8; font-size: 11.5px; line-height: 1.45; font-family: \'Segoe UI\', Arial, sans-serif; margin-bottom: 3px;">{t_esc}</div>')
                elif seg["type"] == "code":
                    code_raw = seg["content"]
                    self._raw_code_blocks.append(code_raw)
                    c_esc = html.escape(code_raw)
                    lang = seg["lang"].upper() if seg["lang"] else "CODE"
                    code_html = f"""
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 4px 0; background-color: #0d1117; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;">
                      <tr>
                        <td style="background-color: #161b22; padding: 3px 8px; font-size: 10px; font-weight: bold; color: #8b949e; border-bottom: 1px solid rgba(255, 255, 255, 0.06);">
                          {lang}
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 6px 8px;">
                          <pre style="margin: 0; font-family: Consolas, monospace; font-size: 11px; color: #e6edf3; white-space: pre-wrap; word-wrap: break-word;">{c_esc}</pre>
                        </td>
                      </tr>
                    </table>
                    """
                    body_parts.append(code_html)

            body_html = "".join(body_parts)
            if not body_html.strip():
                t_esc = html.escape(text).replace("\n", "<br/>")
                body_html = f'<div style="color: #f5f6f8; font-size: 11.5px; line-height: 1.45; font-family: \'Segoe UI\', Arial, sans-serif;">{t_esc}</div>'

            html_line = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 8px;">
              <tr>
                <td width="28" valign="top" style="padding-top: 1px;">
                  <img src="jarvis://avatar.png" width="20" height="20"/>
                </td>
                <td align="left" valign="top">
                  <table cellpadding="8" cellspacing="0" border="0" style="background-color: #0e0f11; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 14px;">
                    <tr>
                      <td style="color: #f5f6f8; font-size: 11.5px; font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.45;">
                        {body_html}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            """

        has_sel = self.chat_display.textCursor().hasSelection()
        saved_cursor = QTextCursor(self.chat_display.textCursor()) if has_sel else None

        cursor = QTextCursor(self.chat_display.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html_line)

        if has_sel and saved_cursor:
            self.chat_display.setTextCursor(saved_cursor)
        else:
            self.scroll_to_bottom(force=True)

    def clear(self):
        self._raw_messages.clear()
        self._raw_code_blocks.clear()
        self.chat_display.clear()
        self.clear_requested.emit()
