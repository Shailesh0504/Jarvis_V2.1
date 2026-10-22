# gui/island/icons.py
"""Vector SVG paths and QIcon renderers adapted from Coucou Windows client.

Renders scalable, crisp icons matching Coucou's 24x24 optical grid:
- house (Overview)
- bubble (Chat)
- plus (Drop / New Task)
- gear / gearFill (Settings)
- speakerOn / speakerOff (Voice)
- arrowUp (Send)
- arrowUpRight (Jump / Open)
- xmark (Close / Collapse)
- check (Success / Done)
- bang (Warning / Alert)
- doc (File Context)
- stack (Workflows / Apps)
- timer (Reminders)
- mic (Microphone)
"""

from PySide6.QtCore import Qt, QSize, QByteArray
from PySide6.QtGui import QIcon, QPainter, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer


SVG_PATHS = {
    "house": "M12 3.2 2.8 10.6V21h6.6v-5.4h5.2V21h6.6V10.6L12 3.2z",
    "bubble": "M12 3.6c-5 0-9 3.3-9 7.4 0 2.3 1.3 4.4 3.3 5.7-.2 1.2-.8 2.4-1.7 3.4 1.9-.2 3.6-.9 4.9-1.9 .8.2 1.6.3 2.5.3 5 0 9-3.3 9-7.5s-4-7.4-9-7.4z",
    "plus": "M11 4h2v7h7v2h-7v7h-2v-7H4v-2h7V4z",
    "gear": "M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8zm0 1.8a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2zM10.9 2h2.2l.35 2.1c.6.17 1.16.4 1.67.71l1.9-1 1.55 1.55-1 1.9c.3.5.54 1.07.7 1.67l2.13.35v2.2l-2.12.35c-.17.6-.4 1.16-.71 1.67l1 1.9-1.55 1.55-1.9-1c-.5.3-1.07.54-1.67.7L13.1 22h-2.2l-.35-2.12c-.6-.17-1.16-.4-1.67-.71l-1.9 1L5.43 18.6l1-1.9c-.3-.5-.54-1.07-.7-1.67L3.6 14.7v-2.2l2.12-.35c.17-.6.4-1.16.71-1.67l-1-1.9 1.55-1.55 1.9 1c.5-.3 1.07-.54 1.67-.7L10.9 2z",
    "gearFill": "M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8zm0 1.8a1.6 1.6 0 1 1 0 3.2 1.6 1.6 0 0 1 0-3.2zM10.9 2h2.2l.35 2.1c.6.17 1.16.4 1.67.71l1.9-1 1.55 1.55-1 1.9c.3.5.54 1.07.7 1.67l2.13.35v2.2l-2.12.35c-.17.6-.4 1.16-.71 1.67l1 1.9-1.55 1.55-1.9-1c-.5.3-1.07.54-1.67.7L13.1 22h-2.2l-.35-2.12c-.6-.17-1.16-.4-1.67-.71l-1.9 1L5.43 18.6l1-1.9c-.3-.5-.54-1.07-.7-1.67L3.6 14.7v-2.2l2.12-.35c.17-.6.4-1.16.71-1.67l-1-1.9 1.55-1.55 1.9 1c.5-.3 1.07-.54 1.67-.7L10.9 2z",
    "speakerOn": "M11 4.5 6.5 8.2H3.4v7.6h3.1L11 19.5v-15zm3.2 3a5.3 5.3 0 0 1 0 9 .9.9 0 0 0 .9 1.55 7.1 7.1 0 0 0 0-12.1.9.9 0 0 0-.9 1.55zm2.6-3.1a8.9 8.9 0 0 1 0 15.2.9.9 0 0 0 .92 1.55 10.7 10.7 0 0 0 0-18.3.9.9 0 0 0-.92 1.55z",
    "speakerOff": "M11 4.5 6.5 8.2H3.4v7.6h3.1L11 19.5v-15zm3.6 4.1 1.27-1.27 2.33 2.33 2.33-2.33 1.27 1.27L19.47 11l2.33 2.33-1.27 1.27-2.33-2.33-2.33 2.33-1.27-1.27L16.93 11 14.6 8.6z",
    "arrowUp": "M12 4.5 5.5 11l1.5 1.5 4-4V19.5h2V8.5l4 4L18.5 11 12 4.5z",
    "arrowUpRight": "M6 6h12v12h-2V9.41L7.41 18 6 16.59 14.59 8H6V6z",
    "xmark": "M6.4 5 12 10.6 17.6 5 19 6.4 13.4 12 19 17.6 17.6 19 12 13.4 6.4 19 5 17.6 10.6 12 5 6.4 6.4 5z",
    "timer": "M12 4.2a7.8 7.8 0 1 0 0 15.6 7.8 7.8 0 0 0 0-15.6zm0 1.9a5.9 5.9 0 1 1 0 11.8 5.9 5.9 0 0 1 0-11.8zm-.95 2.3v4.2l3.3 2 .95-1.55-2.4-1.45V8.4h-1.85zM9.2 2h5.6v1.7H9.2V2z",
    "doc": "M6.5 2.6h7l4 4v14.8h-11V2.6zm6.6 1.6v3.3h3.3l-3.3-3.3zM8.6 11h6.8v1.5H8.6V11zm0 3.4h6.8v1.5H8.6v-1.5z",
    "stack": "M5 8h14v11.5H5V8zm1.8-3h10.4v1.6H6.8V5zm1.6-2.6h7.2V4H8.4V2.4z",
    "check": "M5 12.5 9.5 17 19 7.5",
    "bang": "M12 4a1.2 1.2 0 0 1 1.2 1.2v7.6a1.2 1.2 0 0 1-2.4 0V5.2A1.2 1.2 0 0 1 12 4zm0 12a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z",
    "mic": "M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zm5 9a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z",
    "micOff": "M19 11h-1.7c0 .58-.1 1.13-.27 1.64l1.27 1.27c.61-.88 1-1.92 1-2.91zm-4.37-4.37L15 6.24V5a3 3 0 0 0-3-3 3 3 0 0 0-3 3v.37l6.63 6.63zM4.27 3 3 4.27l6.01 6.01V11a3 3 0 0 0 3 3c.39 0 .76-.08 1.1-.21l1.62 1.62A5 5 0 0 1 7 11H5a7 7 0 0 0 6 6.92V21h2v-3.08c1.37-.18 2.62-.77 3.63-1.64l3.1 3.1 1.27-1.27L4.27 3z"
}


def create_coucou_icon(name: str, color: QColor = QColor("#f5f6f8"), size: int = 16) -> QIcon:
    """Creates a pixel-perfect scalable QIcon from Coucou SVG path data using QSvgRenderer."""
    path_data = SVG_PATHS.get(name)
    if not path_data:
        return QIcon()

    hex_color = color.name() if isinstance(color, QColor) else str(color)
    is_stroke_only = name in ("check", "arrowUpRight")
    
    if is_stroke_only:
        svg_xml = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
            <path d="{path_data}" fill="none" stroke="{hex_color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>"""
    else:
        svg_xml = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
            <path d="{path_data}" fill="{hex_color}" />
        </svg>"""

    renderer = QSvgRenderer(QByteArray(svg_xml.encode("utf-8")))
    if not renderer.isValid():
        return QIcon()

    scale_factor = 2  # High DPI rendering
    pixmap = QPixmap(size * scale_factor, size * scale_factor)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)
