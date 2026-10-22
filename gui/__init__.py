# gui/__init__.py
"""GUI package for Jarvis V2 Desktop Application."""

import os
import sys
from .app import JarvisMainWindow

__all__ = ["JarvisMainWindow", "launch_gui"]


def launch_gui(jarvis_core, bypass_auth: bool = False):
    """Launches the PySide6 Desktop GUI application with optional Face Authentication."""
    # Ensure Windows taskbar groups and shows the custom application icon instead of python.exe
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("jarvis.ai.desktop.assistant.v2")
        except Exception:
            pass

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QIcon
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Set application-wide icon for taskbar, dialogs, and main windows
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "jarvis_logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    default_font = QFont("Segoe UI", 10)
    default_font.setPointSize(10)
    app.setFont(default_font)

    from .styles import MODERN_DARK_STYLE
    from PySide6.QtGui import QPalette, QColor
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#141518"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#f5f6f8"))
    app.setPalette(pal)
    app.setStyleSheet(MODERN_DARK_STYLE)

    # Biometric Face Authentication Gate
    from security.face_authenticator import FaceAuthenticator
    from .dialogs.face_auth_dialog import FaceAuthDialog
    authenticator = FaceAuthenticator(config=getattr(jarvis_core, "config", {}))

    if authenticator.enabled and not bypass_auth:
        auth_dialog = FaceAuthDialog(authenticator=authenticator)
        auth_dialog.exec()
        if not auth_dialog.is_authenticated:
            print("\n[!] Biometric authentication cancelled or failed. Exiting Jarvis.")
            return 0

    window = JarvisMainWindow(jarvis_core)
    window.setFont(default_font)
    window.show()
    return app.exec()
