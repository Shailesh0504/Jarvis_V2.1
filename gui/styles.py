# gui/styles.py
"""Coucou Aesthetic Glassmorphic & Dynamic Island QSS Stylesheet for Jarvis V2.

Faithfully implements the color palette, typography scale, pill tabs,
capsule buttons, and obsidian island aesthetic from Louis-CFM/coucou:
  --ink: #f5f6f8 (primary text)
  --dim: #9398a1 (secondary text)
  --dim-3: #6b7079 (muted text)
  --card: #141518 (card container)
  --card-flat: #0e0f11 (flat backdrop)
  --tab-on: #1d1f23 (active tab pill)
  --hairline: rgba(255, 255, 255, 0.065)
  --cyan: #22d3ee | --green: #22c55e | --amber: #f5a524 | --red: #f4505e
"""

MODERN_DARK_STYLE = """
/* ==========================================================================
   Global Window & Base Styles (Coucou Obsidian Dark Palette)
   ========================================================================== */
QMainWindow, QWidget {
    background-color: #090a0d;
    color: #f5f6f8;
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}

QLabel {
    background-color: transparent;
    color: #f5f6f8;
}

/* ==========================================================================
   Tooltips (Coucou Dark Glass Aesthetic)
   ========================================================================== */
QToolTip {
    background-color: #141518;
    color: #f5f6f8;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 6px;
    padding: 4px 8px;
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 11px;
    font-weight: 500;
}

/* ==========================================================================
   Coucou Dynamic Island Header Bar
   ========================================================================== */
#header_bar {
    background-color: #000000;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    padding: 8px 18px;
}

#logo_label {
    color: #f5f6f8;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

#status_badge {
    background-color: rgba(34, 197, 94, 0.12);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.4);
    border-radius: 999px;
    padding: 4px 14px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

#status_badge[state="ready"] {
    background-color: rgba(34, 197, 94, 0.12);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.4);
}

#status_badge[state="listening"] {
    background-color: rgba(34, 211, 238, 0.16);
    color: #22d3ee;
    border: 1px solid rgba(34, 211, 238, 0.6);
}

#status_badge[state="thinking"] {
    background-color: rgba(139, 92, 246, 0.16);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.5);
}

#status_badge[state="executing"] {
    background-color: rgba(59, 130, 246, 0.16);
    color: #60a5fa;
    border: 1px solid rgba(59, 130, 246, 0.5);
}

#status_badge[state="speaking"] {
    background-color: rgba(192, 132, 252, 0.16);
    color: #c084fc;
    border: 1px solid rgba(192, 132, 252, 0.5);
}

#status_badge[state="paused"] {
    background-color: rgba(107, 112, 121, 0.2);
    color: #9398a1;
    border: 1px solid rgba(107, 112, 121, 0.4);
}

#status_badge[state="error"] {
    background-color: rgba(244, 80, 94, 0.18);
    color: #f4505e;
    border: 1px solid rgba(244, 80, 94, 0.6);
}

/* Header Telemetry Pills */
QFrame.header-pill {
    background-color: #141518;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 999px;
    padding: 3px 10px;
}

/* ==========================================================================
   Sidebar Navigation (Coucou Pill Tabs)
   ========================================================================== */
#sidebar {
    background-color: #0b0c0e;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    min-width: 205px;
    max-width: 205px;
}

QPushButton.nav-btn {
    background-color: transparent;
    color: #9398a1;
    border: none;
    border-radius: 999px;
    padding: 9px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    margin: 2px 10px;
}

QPushButton.nav-btn:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: #f5f6f8;
}

QPushButton.nav-btn:checked, QPushButton.nav-btn.active {
    background-color: #1d1f23;
    color: #f5f6f8;
    border-left: 3px solid #22d3ee;
    font-weight: 600;
}

/* ==========================================================================
   Cards & Glass Panels (Coucou #141518 Card Scheme)
   ========================================================================== */
QFrame.card, QFrame[class="card"] {
    background-color: #141518;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
}

QFrame.card:hover, QFrame[class="card"]:hover {
    border-color: rgba(255, 255, 255, 0.12);
}

QLabel.card-title, QLabel[class="card-title"] {
    background-color: transparent;
    color: #9398a1;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

QLabel.card-value, QLabel[class="card-value"] {
    background-color: transparent;
    color: #f5f6f8;
    font-size: 20px;
    font-weight: 700;
    min-height: 28px;
}

QLabel.card-sub, QLabel[class="card-sub"] {
    background-color: transparent;
    color: #6b7079;
    font-size: 11px;
}

/* ==========================================================================
   Chat View & Bubbles (Coucou Messaging Styling)
   ========================================================================== */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background: #090a0d;
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: #1d1f23;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #2a2d33;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    height: 0px;
}

QFrame.chat-line-user, QFrame.chat-line-assistant, QFrame.bubble-user, QFrame.bubble-assistant {
    background-color: transparent;
    border: none;
    border-radius: 10px;
    padding: 4px 8px;
    margin: 2px 0px;
}

QFrame.chat-line-user:hover, QFrame.chat-line-assistant:hover {
    background-color: rgba(255, 255, 255, 0.035);
}

/* ==========================================================================
   Input & Controls (Coucou Sleek Pill Elements)
   ========================================================================== */
QLineEdit, QTextEdit {
    background-color: #141518;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    color: #f5f6f8;
    padding: 10px 14px;
    font-size: 13px;
}

QLineEdit:focus, QTextEdit:focus {
    border-color: #22d3ee;
    background-color: #16181d;
}

QPushButton.primary-btn {
    background-color: #f5f6f8;
    color: #0b0c0e;
    border: none;
    border-radius: 999px;
    padding: 9px 20px;
    font-weight: 700;
    font-size: 13px;
}

QPushButton.primary-btn:hover {
    background-color: #ffffff;
}

QPushButton.primary-btn:pressed {
    background-color: #e2e4e9;
}

QPushButton.chip-btn {
    background-color: #141518;
    color: #9398a1;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    padding: 5px 14px;
    font-size: 11px;
}

QPushButton.chip-btn:hover {
    background-color: #1d1f23;
    color: #f5f6f8;
    border-color: rgba(255, 255, 255, 0.16);
}

/* Chat Toolbar & Action Buttons */
QPushButton.toolbar-btn {
    background-color: #141518;
    color: #9398a1;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton.toolbar-btn:hover {
    background-color: #1d1f23;
    color: #f5f6f8;
    border-color: rgba(255, 255, 255, 0.16);
}

QPushButton.toolbar-btn-danger {
    background-color: rgba(244, 80, 94, 0.1);
    color: #f4505e;
    border: 1px solid rgba(244, 80, 94, 0.3);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton.toolbar-btn-danger:hover {
    background-color: rgba(244, 80, 94, 0.22);
    color: #ff8d97;
    border-color: #f4505e;
}

QPushButton.toolbar-btn-mute-on {
    background-color: rgba(34, 197, 94, 0.12);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.35);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton.toolbar-btn-mute-on:hover {
    background-color: rgba(34, 197, 94, 0.22);
    color: #34d399;
}

QPushButton.toolbar-btn-muted {
    background-color: rgba(245, 165, 36, 0.12);
    color: #f5a524;
    border: 1px solid rgba(245, 165, 36, 0.35);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton.toolbar-btn-muted:hover {
    background-color: rgba(245, 165, 36, 0.22);
    color: #fbbf24;
}

QPushButton.bubble-copy-btn, QPushButton.bubble-action-btn {
    background-color: rgba(255, 255, 255, 0.05);
    color: #9398a1;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton.bubble-copy-btn:hover, QPushButton.bubble-action-btn:hover {
    background-color: #1d1f23;
    color: #f5f6f8;
    border-color: rgba(255, 255, 255, 0.18);
}

QMenu {
    background-color: #141518;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 6px;
    color: #f5f6f8;
}

QMenu::item {
    padding: 8px 18px;
    border-radius: 8px;
    font-size: 12px;
}

QMenu::item:selected {
    background-color: #1d1f23;
    color: #22d3ee;
}

QPushButton.listen-btn-active {
    background-color: rgba(34, 211, 238, 0.18);
    color: #22d3ee;
    border: 1px solid #22d3ee;
    border-radius: 999px;
    padding: 10px 20px;
    font-weight: 700;
}

/* ==========================================================================
   Tables & Lists
   ========================================================================== */
QTableWidget {
    background-color: #141518;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    gridline-color: rgba(255, 255, 255, 0.04);
    color: #f5f6f8;
}

QHeaderView::section {
    background-color: #0e0f11;
    color: #9398a1;
    padding: 8px;
    border: 1px solid rgba(255, 255, 255, 0.05);
    font-weight: 600;
    font-size: 12px;
}

/* ==========================================================================
   Coucou Dynamic Island & Top Notch Container Styles
   ========================================================================== */
#coucou_island_card {
    background-color: #0b0c0e;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 22px;
}

#coucou_notch_bar {
    background-color: #000000;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 20px;
    padding: 2px 10px;
}

#coucou_header {
    background-color: #0c0d10;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-top-left-radius: 22px;
    border-top-right-radius: 22px;
    padding: 6px 14px;
}

QPushButton.coucou-tab {
    background-color: transparent;
    color: #9398a1;
    border: 1px solid transparent;
    border-radius: 999px;
    padding: 5px 14px;
    font-size: 11.5px;
    font-weight: 600;
}

QPushButton.coucou-tab:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: #f5f6f8;
}

QPushButton.coucou-tab:checked {
    background-color: #1d1f23;
    color: #f5f6f8;
    border: 1px solid rgba(255, 255, 255, 0.12);
}

QPushButton.coucou-icon-btn {
    background-color: #141518;
    color: #9398a1;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton.coucou-icon-btn:hover {
    background-color: #1d1f23;
    color: #f5f6f8;
    border-color: rgba(255, 255, 255, 0.14);
}
"""
