# tests/test_websites_gui_view.py
"""
Unit and Integration tests for Saved Websites GUI Management in Jarvis V2.1.
Validates:
- Loading and viewing saved website shortcuts (GLPI, Human 3D, etc.).
- Real-time search filtering across aliases, names, and URLs.
- In-place editing of URLs and verification of immediate resolution ("open glpi" -> new URL).
- Toggling active state (Enable / Disable) and verification that disabled shortcuts are ignored.
- Deletion of website shortcuts.
- In-browser test opening (webbrowser.open).
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(["-platform", "offscreen"])

from core.website_knowledge import WebsiteKnowledgeStore
from gui.views.websites_view import AddEditWebsiteDialog, WebsitesView
from plugins.browser.website_resolver import AmbiguousWebsiteError, UnknownWebsiteError, WebsiteResolver


@pytest.fixture(scope="session")
def qapp():
    return _app


@pytest.fixture
def store_and_view(tmp_path):
    db_file = str(tmp_path / "test_websites.db")
    store = WebsiteKnowledgeStore(db_path=db_file)
    # Pre-populate with initial entries
    store.learn(
        alias="glpi",
        url="https://glpi-jioinstitute1.msappproxy.net/front/center.php",
        canonical_name="Glpi"
    )
    store.learn(
        alias="human 3d",
        url="https://www.zygotebody.com/",
        canonical_name="Human 3D View"
    )
    WebsiteResolver.configure_knowledge_store(store)

    # Mock JarvisCore with this store
    mock_core = MagicMock()
    mock_core.website_knowledge = store

    view = WebsitesView(jarvis_core=mock_core)
    yield store, view

    WebsiteResolver.configure_knowledge_store(None)


def test_websites_view_loads_and_displays_saved_sites(store_and_view):
    """Verifies that WebsitesView displays all learned websites in table with correct columns."""
    store, view = store_and_view
    view.refresh_websites()

    assert view.table.rowCount() == 2
    # Check that GLPI and Human 3D are present
    aliases_in_table = [view.table.item(r, 1).text().lower() for r in range(view.table.rowCount())]
    assert any("glpi" in a for a in aliases_in_table)
    assert any("human" in a for a in aliases_in_table)

    # Verify initial resolution
    res = WebsiteResolver.resolve("open glpi")
    assert res.final_url == "https://glpi-jioinstitute1.msappproxy.net/front/center.php"
    assert res.source == "user_learned"


def test_websites_view_search_filtering(store_and_view):
    """Verifies that the search bar filters rows dynamically."""
    store, view = store_and_view

    # Filter for 'glpi'
    view.search_input.setText("glpi")
    assert view.table.rowCount() == 1
    assert view.table.item(0, 1).text().lower() == "glpi"

    # Filter for non-existent text
    view.search_input.setText("non_existent_portal")
    assert view.table.rowCount() == 0

    # Clear filter
    view.search_input.setText("")
    assert view.table.rowCount() == 2


def test_edit_website_url_immediately_updates_resolution(store_and_view):
    """
    Core User Requirement:
    User changes GLPI URL in GUI from:
    https://glpi-jioinstitute1.msappproxy.net/front/center.php
    to:
    https://new-glpi-url.example/front/center.php
    Then 'open glpi' automatically resolves to the new URL.
    """
    store, view = store_and_view

    # Find GLPI entry ID
    glpi_entry = None
    for entry in store.list_entries():
        if "glpi" in entry.get("normalized_aliases", []):
            glpi_entry = entry
            break
    assert glpi_entry is not None

    new_url = "https://new-glpi-url.example/front/center.php"

    # Update via store / GUI edit action
    updated = store.update_entry(glpi_entry["id"], url=new_url)
    assert updated["url"] == new_url

    # Refresh GUI view
    view.refresh_websites()

    # Verify table reflects new URL
    urls_in_table = [view.table.item(r, 3).text() for r in range(view.table.rowCount())]
    assert new_url in urls_in_table

    # CRITICAL: Verify 'open glpi' now resolves immediately to the new URL!
    res = WebsiteResolver.resolve("open glpi")
    assert res.final_url == new_url
    assert res.canonical_name == "Glpi"

    # Hindi/Hinglish speech variations also resolve to new URL
    res_hindi = WebsiteResolver.resolve("glpi kholo")
    assert res_hindi.final_url == new_url


def test_toggle_enable_disable_website(store_and_view):
    """Verifies that disabling a website prevents resolution, and re-enabling restores it."""
    store, view = store_and_view

    glpi_entry = next(e for e in store.list_entries() if "glpi" in e.get("normalized_aliases", []))

    # 1. Disable GLPI
    new_state = store.toggle_enabled(glpi_entry["id"])
    assert new_state is False

    view.refresh_websites()

    # Resolution should now fail / treat GLPI as not configured
    with pytest.raises(UnknownWebsiteError):
        WebsiteResolver.resolve("open glpi")

    # 2. Re-enable GLPI
    new_state = store.toggle_enabled(glpi_entry["id"])
    assert new_state is True

    view.refresh_websites()

    # Resolution works again
    res = WebsiteResolver.resolve("open glpi")
    assert res.source == "user_learned"


def test_delete_website_removes_from_gui_and_resolution(store_and_view):
    """Verifies that deleting an entry removes it from the table and store."""
    store, view = store_and_view

    glpi_entry = next(e for e in store.list_entries() if "glpi" in e.get("normalized_aliases", []))

    # Delete
    deleted = store.delete_by_id(glpi_entry["id"])
    assert deleted is True

    view.refresh_websites()
    assert view.table.rowCount() == 1

    # Should no longer resolve
    with pytest.raises(UnknownWebsiteError):
        WebsiteResolver.resolve("open glpi")


def test_test_open_invokes_webbrowser(store_and_view):
    """Verifies that clicking 'Test' calls webbrowser.open with target URL."""
    store, view = store_and_view

    with patch("webbrowser.open") as mock_browser_open:
        view._test_open("https://glpi-jioinstitute1.msappproxy.net/front/center.php")
        mock_browser_open.assert_called_once_with("https://glpi-jioinstitute1.msappproxy.net/front/center.php")


def test_add_edit_dialog_validation(qapp):
    """Verifies URL and alias validation inside AddEditWebsiteDialog."""
    dlg = AddEditWebsiteDialog()
    # Empty inputs
    dlg._validate_and_accept()
    assert "alias" in dlg.error_label.text().lower()

    # Invalid URL
    dlg.alias_input.setText("portal")
    dlg.url_input.setText("not_a_valid_url")
    dlg._validate_and_accept()
    assert "invalid" in dlg.error_label.text().lower() or "domain" in dlg.error_label.text().lower() or "http" in dlg.error_label.text().lower()

    # Valid input
    dlg.url_input.setText("https://mycompany.com/portal")
    dlg._validate_and_accept()
    assert dlg.get_data()["url"] == "https://mycompany.com/portal"
