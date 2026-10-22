# tests/test_settings_lifecycle.py
"""Phase 1 Regression Test: Settings lifecycle must never terminate JARVIS."""

import os
import sys
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent

# Ensure offscreen Qt environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"


from main import create_jarvis


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def jarvis_gui_core(tmp_path):
    db_file = os.path.join(tmp_path, "lifecycle_test.db").replace("\\", "/")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(f"""
system:
  name: "JARVIS_LIFECYCLE_TEST"
memory:
  db_path: "{db_file}"
brain:
  llm_provider: "mock"
reminder:
  db_path: "{str(tmp_path / 'lifecycle_reminders.db').replace(chr(92), '/')}"
plugins:
  plugin_dir: "plugins"
  auto_load: true
""")
    return create_jarvis(str(cfg_file))


def test_settings_open_close_does_not_terminate_application(qapp, jarvis_gui_core):
    """
    Verifies Phase 1 Contract:
    1. Start JARVIS
    2. Open Settings
    3. Close Settings (via closeSettings, hide, and closeEvent)
    4. Verify JARVIS window is still alive
    5. Verify Dynamic Island remains available
    6. Verify backend remains connected
    7. Verify QApplication.quitOnLastWindowClosed is False
    """
    from gui.app import JarvisMainWindow, JarvisStudioWindow

    window = JarvisMainWindow(jarvis_gui_core)
    window.show()
    qapp.processEvents()

    # Monitor aboutToQuit to guarantee Qt never attempts shutdown on Settings close
    quit_triggered = []
    qapp.aboutToQuit.connect(lambda: quit_triggered.append(True))

    # 1. Verify JARVIS is alive and Dynamic Island is ready
    assert window.isVisible()
    assert hasattr(window, "island")
    assert window.island is not None
    assert qapp.quitOnLastWindowClosed() is False

    # 2. Open Settings
    window.openSettings()
    qapp.processEvents()
    assert window.studio_window.isVisible()
    assert window.studio_window.stack.currentIndex() == 9  # Settings tab

    # 3. Simulate User Clicking 'X' (Native Close Event) on Studio/Settings Window
    close_event = QCloseEvent()
    window.studio_window.closeEvent(close_event)
    qapp.processEvents()

    # 4. Verify Close Event was ignored and window was hidden, NOT destroyed
    assert close_event.isAccepted() is False
    assert not window.studio_window.isVisible()
    assert len(quit_triggered) == 0, "FATAL: aboutToQuit was emitted when Settings closed!"

    # 5. Verify JARVIS Window, Dynamic Island, and Core remain alive and available
    assert window.isVisible()
    assert window.island.isVisible()
    assert window.core is jarvis_gui_core
    assert hasattr(window, "character")
    assert window.character is not None

    # 6. Test native studio_window.close() call
    window.openSettings()
    qapp.processEvents()
    assert window.studio_window.isVisible()

    window.studio_window.close()
    qapp.processEvents()
    assert not window.studio_window.isVisible()
    assert window.isVisible()
    assert len(quit_triggered) == 0, "FATAL: aboutToQuit was emitted when studio_window.close() called!"

    # 7. Test explicit closeSettings()
    window.openSettings()
    qapp.processEvents()
    assert window.studio_window.isVisible()

    window.closeSettings()
    qapp.processEvents()
    assert not window.studio_window.isVisible()
    assert window.isVisible()
    assert len(quit_triggered) == 0

    # 8. Verify separate lifecycle boundaries
    assert hasattr(window, "openSettings")
    assert hasattr(window, "closeSettings")
    assert hasattr(window, "exitApplication")
    assert window.closeSettings != window.exitApplication

    # Cleanup
    window.close()
